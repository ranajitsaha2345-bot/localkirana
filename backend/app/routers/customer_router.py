from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from .. import models, schemas, auth
from ..database import get_db
from ..services import matching, payment, realtime

router = APIRouter(prefix="/customer", tags=["customer"])
require_customer = auth.require_role(models.UserRole.customer)
class ScanShopRequest(BaseModel):
    qr_data: str

@router.get("/items", response_model=list[schemas.ItemOut])
def list_items(category: str | None = None, search: str | None = None, db: Session = Depends(get_db)):
    """Poora catalog - dal, chini, oil, biskut, etc. Category aur search se filter hota hai."""
    query = db.query(models.Item)
    if category and category != "all":
        query = query.filter(models.Item.category == category)
    if search:
        query = query.filter(models.Item.name.ilike(f"%{search}%"))
    items = query.all()

    price_rows = (
        db.query(
            models.ShopItem.item_id,
            func.min(models.ShopItem.price).label("min_price"),
            func.count(models.ShopItem.id).label("shop_count"),
        )
        .filter(models.ShopItem.in_stock == True)  # noqa: E712
        .group_by(models.ShopItem.item_id)
        .all()
    )
    price_map = {row.item_id: (row.min_price, row.shop_count) for row in price_rows}

    result = []
    for it in items:
        min_price, shop_count = price_map.get(it.id, (None, 0))
        result.append(
            schemas.ItemOut(
                id=it.id, name=it.name, unit=it.unit, category=it.category,
                image_url=it.image_url, starting_price=min_price, shop_count=shop_count,
            )
        )
    return result


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    """Saare unique categories - tabs banane ke liye."""
    rows = db.query(models.Item.category).distinct().all()
    return sorted(set(r[0] for r in rows if r[0]))


@router.post("/cart/match", response_model=schemas.CartMatchResponse)
def match_cart(
    payload: schemas.CartMatchRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_customer),
):
    """
    Yehi wo jaadu hai: har item ke liye sabse sasti available dukan dhoondta hai
    aur customer ko "Done" dabane se pehle preview dikhata hai.
    """
    result_lines = []
    grand_total = 0.0

    for line in payload.lines:
        item = db.query(models.Item).get(line.item_id)
        if not item:
            raise HTTPException(404, f"Item id {line.item_id} nahi mila")

        best = matching.find_cheapest_shop_for_item(
            db, line.item_id, payload.latitude, payload.longitude
        )
        if best:
            line_total = best.price * line.quantity
            grand_total += line_total
            result_lines.append(
                schemas.MatchedLine(
                    item_id=item.id, item_name=item.name, quantity=line.quantity,
                    shop_id=best.shop_id, shop_name=best.shop.name,
                    unit_price=best.price, line_total=line_total, available=True,
                )
            )
        else:
            result_lines.append(
                schemas.MatchedLine(
                    item_id=item.id, item_name=item.name, quantity=line.quantity,
                    shop_id=None, shop_name=None, unit_price=None,
                    line_total=None, available=False,
                )
            )

    return schemas.CartMatchResponse(lines=result_lines, grand_total=grand_total)


@router.post("/orders", response_model=list[schemas.ShopOrderOut])
async def place_order(
    payload: schemas.PlaceOrderRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_customer),
):
    """
    'Done' button yahin hit karta hai.
    Har item apni sabse sasti dukan ke saath group ho jaata hai,
    aur har dukan ke liye alag ShopOrder ban jaata hai.
    """
    order = models.Order(customer_id=user.id)
    db.add(order)
    db.flush()

    # item_id -> matched shop_item, taaki same shop ke items ek saath group ho
    shop_groups: dict[int, list] = {}
    unmatched = []

    for line in payload.lines:
        best = matching.find_cheapest_shop_for_item(
            db, line.item_id, payload.latitude, payload.longitude
        )
        if not best:
            unmatched.append(line.item_id)
            continue
        shop_groups.setdefault(best.shop_id, []).append((line, best))

    if not shop_groups:
        raise HTTPException(400, "Koi bhi item kisi dukan mein available nahi hai abhi")

    created_shop_orders = []
    for shop_id, lines in shop_groups.items():
        shop_order = models.ShopOrder(order_id=order.id, shop_id=shop_id)
        db.add(shop_order)
        db.flush()

        total = 0.0
        for line, shop_item in lines:
            soi = models.ShopOrderItem(
                shop_order_id=shop_order.id,
                item_id=line.item_id,
                quantity=line.quantity,
                unit_price=shop_item.price,
            )
            total += shop_item.price * line.quantity
            db.add(soi)
        shop_order.amount = total
        created_shop_orders.append(shop_order)

    db.commit()

    result = []
    for so in created_shop_orders:
        db.refresh(so)
        shop = db.query(models.Shop).get(so.shop_id)
        # dukandar ko turant real-time notification
        await realtime.manager.send_to_user(
            shop.owner_id, "new_order", {"shop_order_id": so.id}
        )
        result.append(_to_shop_order_out(db, so))

    return result


@router.get("/orders/{order_id}/shop-orders", response_model=list[schemas.ShopOrderOut])
def get_order_status(
    order_id: int, db: Session = Depends(get_db),
    user: models.User = Depends(require_customer),
):
    """Customer apne order ka live status dekhne ke liye isse poll karega."""
    shop_orders = (
        db.query(models.ShopOrder)
        .join(models.Order)
        .filter(models.Order.id == order_id, models.Order.customer_id == user.id)
        .all()
    )
    if not shop_orders:
        raise HTTPException(404, "Order nahi mila")
    return [_to_shop_order_out(db, so) for so in shop_orders]


@router.post("/shop-orders/{shop_order_id}/pay/create", response_model=schemas.RazorpayOrderOut)
def create_payment(
    shop_order_id: int, db: Session = Depends(get_db),
    user: models.User = Depends(require_customer),
):
    so = db.query(models.ShopOrder).get(shop_order_id)
    if not so or so.order.customer_id != user.id:
        raise HTTPException(404, "Order nahi mila")
    if so.status != models.ShopOrderStatus.awaiting_payment:
        raise HTTPException(400, "Yeh order payment ke liye taiyar nahi hai - dukandar abhi items check kar raha hai")
    
    if so.amount < 1:
        raise HTTPException(400, "Order amount kam se kam ₹1 hona chahiye online payment ke liye")
    rp_order = payment.create_razorpay_order(so.amount, receipt=f"shop_order_{so.id}")
    so.razorpay_order_id = rp_order["id"]
    so.payment_mode = models.PaymentMode.online
    db.commit()

    return schemas.RazorpayOrderOut(
        razorpay_order_id=rp_order["id"],
        amount_paise=rp_order["amount"],
        key_id=payment.RAZORPAY_KEY_ID,
    )


@router.post("/shop-orders/{shop_order_id}/pay/verify")
def verify_payment(
    shop_order_id: int, payload: schemas.RazorpayVerifyRequest,
    db: Session = Depends(get_db), user: models.User = Depends(require_customer),
):
    so = db.query(models.ShopOrder).get(shop_order_id)
    if not so or so.order.customer_id != user.id:
        raise HTTPException(404, "Order nahi mila")

    ok = payment.verify_payment_signature(
        payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature
    )
    if not ok:
        raise HTTPException(400, "Payment verify nahi hua - signature match nahi hua")

    so.payment_status = models.PaymentStatus.paid
    so.razorpay_payment_id = payload.razorpay_payment_id
    so.status = models.ShopOrderStatus.confirmed

    # cash-eligibility counter badhao
    user.online_payment_count += 1
    from .. import services  # local import to avoid cycle
    import os
    required = int(os.getenv("ONLINE_PAYMENTS_REQUIRED_FOR_CASH", "10"))
    if user.online_payment_count >= required:
        user.cash_unlocked = True

    db.commit()
    return {"status": "paid", "online_payment_count": user.online_payment_count,
            "cash_unlocked": user.cash_unlocked}


@router.post("/shop-orders/{shop_order_id}/pay/cash")
def choose_cash(
    shop_order_id: int, db: Session = Depends(get_db),
    user: models.User = Depends(require_customer),
):
    if not user.cash_unlocked:
        raise HTTPException(
            403,
            "Cash on pickup abhi unlock nahi hai. Pehle "
            f"{10 - user.online_payment_count} online payments aur karo.",
        )
    so = db.query(models.ShopOrder).get(shop_order_id)
    if not so or so.order.customer_id != user.id:
        raise HTTPException(404, "Order nahi mila")
    if so.status != models.ShopOrderStatus.awaiting_payment:
        raise HTTPException(400, "Yeh order payment ke liye taiyar nahi hai - dukandar abhi items check kar raha hai")

    so.payment_mode = models.PaymentMode.cash
    so.payment_status = models.PaymentStatus.cash_on_pickup
    so.status = models.ShopOrderStatus.confirmed
    db.commit()
    return {"status": "confirmed", "payment_mode": "cash"}


def _to_shop_order_out(db: Session, so: models.ShopOrder) -> schemas.ShopOrderOut:
    shop = db.query(models.Shop).get(so.shop_id)
    customer = db.query(models.User).get(so.order.customer_id)
    items = [
        schemas.ShopOrderItemOut(
            id=i.id, item_id=i.item_id, item_name=i.item.name,
            quantity=i.quantity, unit_price=i.unit_price, availability=i.availability,
        )
        for i in so.items
    ]
    return schemas.ShopOrderOut(
        id=so.id, order_id=so.order_id, shop_id=so.shop_id, shop_name=shop.name,
        customer_id=customer.id, customer_name=customer.name, customer_phone=customer.phone,
        status=so.status, payment_mode=so.payment_mode, payment_status=so.payment_status,
        amount=so.amount, verification_code=so.verification_code, qr_token=so.qr_token,
        items=items, created_at=so.created_at, ready_at=so.ready_at,
    )


@router.post("/scan-shop")
async def scan_shop_qr(
    payload: ScanShopRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_customer),
):
    """
    Customer dukan mein pahunch kar shop ka static QR scan karta hai.
    Isse dukandar ko turant customer ke active order ki poori details
    ek notification mein mil jaati hai.
    """
    qr_data = payload.qr_data or ""
    if not qr_data.startswith("shop:"):
        raise HTTPException(400, "Yeh Wait dukan ka QR nahi hai")

    try:
        shop_id = int(qr_data.split("shop:")[1])
    except (IndexError, ValueError):
        raise HTTPException(400, "QR data samajh nahi aaya")

    shop = db.query(models.Shop).get(shop_id)
    if not shop:
        raise HTTPException(404, "Yeh dukan Wait mein registered nahi hai")

    active_statuses = [
        models.ShopOrderStatus.pending_shop_review,
        models.ShopOrderStatus.partially_unavailable,
        models.ShopOrderStatus.awaiting_payment,
        models.ShopOrderStatus.confirmed,
        models.ShopOrderStatus.ready,
    ]
    so = (
        db.query(models.ShopOrder)
        .join(models.Order)
        .filter(
            models.ShopOrder.shop_id == shop_id,
            models.Order.customer_id == user.id,
            models.ShopOrder.status.in_(active_statuses),
        )
        .order_by(models.ShopOrder.created_at.desc())
        .first()
    )

    if not so:
        raise HTTPException(404, f"Aapka koi active order {shop.name} mein nahi mila")

    items_summary = [
        {"item_name": i.item.name, "quantity": i.quantity}
        for i in so.items
        if i.availability != models.ItemAvailability.not_available
    ]

    await realtime.manager.send_to_user(
        shop.owner_id,
        "customer_arrived",
        {
            "shop_order_id": so.id,
            "customer_name": user.name,
            "customer_phone": user.phone,
            "items": items_summary,
            "amount": so.amount,
            "payment_mode": so.payment_mode,
            "payment_status": so.payment_status,
            "status": so.status,
        },
    )

    return {
        "status": "ok",
        "message": f"{shop.name} ko aapke aane ki suchna bhej di gayi",
        "shop_order_id": so.id,
        "shop_order_status": so.status,
    }
@router.get("/items/{item_id}/shops")
def shops_for_item(
    item_id: int,
    latitude: float | None = None,
    longitude: float | None = None,
    db: Session = Depends(get_db),
):
    """Ek particular item kis-kis dukan mein milta hai — paas + sasta pehle."""
    item = db.query(models.Item).get(item_id)
    if not item:
        raise HTTPException(404, "Item nahi mila")

    ranked = matching.rank_shops_for_item(db, item_id, latitude, longitude)
    if not ranked:
        return {"item_id": item.id, "item_name": item.name, "shops": []}

    shops_out = []
    for shop_item, distance_km in ranked:
        rating_info = _get_shop_rating(db, shop_item.shop_id)
        shops_out.append({
            "shop_id": shop_item.shop_id,
            "shop_name": shop_item.shop.name,
            "shop_address": shop_item.shop.address,
            "price": shop_item.price,
            "unit": item.unit,
            "distance_km": round(distance_km, 2) if distance_km is not None else None,
            "average_rating": rating_info[0],
            "total_reviews": rating_info[1],
        })

    return {"item_id": item.id, "item_name": item.name, "shops": shops_out}


@router.get("/shops/{shop_id}/items")
def shop_catalog(shop_id: int, db: Session = Depends(get_db)):
    """Ek dukan ka poora catalog — dukan naam par click karne par khulta hai."""
    shop = db.query(models.Shop).get(shop_id)
    if not shop:
        raise HTTPException(404, "Dukan nahi mili")

    rows = (
        db.query(models.ShopItem)
        .join(models.Item)
        .filter(models.ShopItem.shop_id == shop_id, models.ShopItem.in_stock == True)  # noqa: E712
        .all()
    )
    items = [
        {
            "item_id": r.item.id,
            "name": r.item.name,
            "unit": r.item.unit,
            "category": r.item.category,
            "image_url": r.item.image_url,
            "price": r.price,
        }
        for r in rows
    ]
    rating_info = _get_shop_rating(db, shop.id)
    return {
        "shop_id": shop.id, "shop_name": shop.name, "shop_address": shop.address,
        "items": items, "average_rating": rating_info[0], "total_reviews": rating_info[1],
    }

@router.post("/shop-orders/{shop_order_id}/review", response_model=schemas.ReviewOut)
def submit_review(
    shop_order_id: int,
    payload: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_customer),
):
    """Order complete hone ke baad customer dukan ko review de sakta hai — ek order, ek review."""
    so = db.query(models.ShopOrder).get(shop_order_id)
    if not so or so.order.customer_id != user.id:
        raise HTTPException(404, "Order nahi mila")
    if so.status != models.ShopOrderStatus.completed:
        raise HTTPException(400, "Sirf pickup complete hue order par review de sakte ho")

    existing = db.query(models.Review).filter(models.Review.shop_order_id == shop_order_id).first()
    if existing:
        raise HTTPException(400, "Is order ka review pehle hi diya ja chuka hai")

    review = models.Review(
        shop_order_id=shop_order_id, shop_id=so.shop_id, customer_id=user.id,
        rating=payload.rating, comment=payload.comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return schemas.ReviewOut(
        id=review.id, customer_name=user.name, rating=review.rating,
        comment=review.comment, created_at=review.created_at,
    )


@router.get("/shops/{shop_id}/reviews", response_model=list[schemas.ReviewOut])
def get_shop_reviews(shop_id: int, db: Session = Depends(get_db)):
    """Baaki customers ke liye — dukan ke saare reviews, naye pehle."""
    reviews = (
        db.query(models.Review)
        .filter(models.Review.shop_id == shop_id)
        .order_by(models.Review.created_at.desc())
        .all()
    )
    return [
        schemas.ReviewOut(
            id=r.id, customer_name=r.customer.name, rating=r.rating,
            comment=r.comment, created_at=r.created_at,
        )
        for r in reviews
    ]
def _get_shop_rating(db: Session, shop_id: int) -> tuple[float | None, int]:
    reviews = db.query(models.Review).filter(models.Review.shop_id == shop_id).all()
    if not reviews:
        return None, 0
    avg = sum(r.rating for r in reviews) / len(reviews)
    return round(avg, 1), len(reviews)
@router.get("/shop-orders/{shop_order_id}/messages", response_model=list[schemas.ChatMessageOut])
def get_messages_customer(
    shop_order_id: int, db: Session = Depends(get_db),
    user: models.User = Depends(require_customer),
):
    so = db.query(models.ShopOrder).get(shop_order_id)
    if not so or so.order.customer_id != user.id:
        raise HTTPException(404, "Order nahi mila")
    msgs = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.shop_order_id == shop_order_id)
        .order_by(models.ChatMessage.created_at)
        .all()
    )
    return [
        schemas.ChatMessageOut(
            id=m.id, sender_id=m.sender_id, sender_role=m.sender_role,
            sender_name=m.sender.name, message=m.message, created_at=m.created_at,
        )
        for m in msgs
    ]


@router.post("/shop-orders/{shop_order_id}/messages", response_model=schemas.ChatMessageOut)
async def send_message_customer(
    shop_order_id: int, payload: schemas.ChatMessageCreate,
    db: Session = Depends(get_db), user: models.User = Depends(require_customer),
):
    so = db.query(models.ShopOrder).get(shop_order_id)
    if not so or so.order.customer_id != user.id:
        raise HTTPException(404, "Order nahi mila")

    text = payload.message.strip()
    if not text:
        raise HTTPException(400, "Khali message nahi bhej sakte")

    msg = models.ChatMessage(
        shop_order_id=shop_order_id, sender_id=user.id,
        sender_role=models.UserRole.customer, message=text,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    shop = db.query(models.Shop).get(so.shop_id)
    await realtime.manager.send_to_user(
        shop.owner_id, "new_message",
        {"shop_order_id": shop_order_id, "sender_name": user.name, "message": text},
    )
    return schemas.ChatMessageOut(
        id=msg.id, sender_id=msg.sender_id, sender_role=msg.sender_role,
        sender_name=user.name, message=msg.message, created_at=msg.created_at,
    )