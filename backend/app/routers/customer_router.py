from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from .. import models, schemas, auth
from ..database import get_db
from ..services import matching, payment, realtime

router = APIRouter(prefix="/customer", tags=["customer"])
require_customer = auth.require_role(models.UserRole.customer)
class ScanShopRequest(BaseModel):
    qr_data: str

@router.get("/items", response_model=list[schemas.ItemOut])
def list_items(db: Session = Depends(get_db)):
    """Poora catalog - dal, chini, oil, biskut, etc."""
    return db.query(models.Item).all()


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
        customer_id=customer.id, customer_name=customer.name,
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
        raise HTTPException(400, "Yeh LocalKirana dukan ka QR nahi hai")

    try:
        shop_id = int(qr_data.split("shop:")[1])
    except (IndexError, ValueError):
        raise HTTPException(400, "QR data samajh nahi aaya")

    shop = db.query(models.Shop).get(shop_id)
    if not shop:
        raise HTTPException(404, "Yeh dukan LocalKirana mein registered nahi hai")

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
