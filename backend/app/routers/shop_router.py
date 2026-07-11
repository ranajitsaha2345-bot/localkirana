from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..services import matching, realtime, verification

router = APIRouter(prefix="/shop", tags=["shop"])
require_shopkeeper = auth.require_role(models.UserRole.shopkeeper)


def _get_owned_shop(db: Session, user: models.User) -> models.Shop:
    shop = db.query(models.Shop).filter(models.Shop.owner_id == user.id).first()
    if not shop:
        raise HTTPException(404, "Tumhari dukan register nahi hai")
    return shop

    
@router.get("/my-qr")
def get_my_shop_qr(db: Session = Depends(get_db),
                    user: models.User = Depends(require_shopkeeper)):
    """Dukandar ka apna shop QR data - isse ek baar print/display karo dukan mein."""
    shop = _get_owned_shop(db, user)
    return {"shop_id": shop.id, "shop_name": shop.name, "qr_data": f"shop:{shop.id}"}


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


# ---------------------------------------------------------------------------
# Inventory - dukandar apni dukan mein items aur price set karta hai
# ---------------------------------------------------------------------------
@router.post("/items", response_model=schemas.ItemOut)
def create_master_item(name: str, unit: str = "unit", category: str = "general",
                        db: Session = Depends(get_db),
                        user: models.User = Depends(require_shopkeeper)):
    """Agar catalog mein item pehle se nahi hai (jaise 'dal', 'chini'), to yeh banata hai."""
    existing = db.query(models.Item).filter(models.Item.name == name).first()
    if existing:
        return existing
    item = models.Item(name=name, unit=unit, category=category)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/inventory")
def upsert_inventory(payload: schemas.ShopItemUpsert, db: Session = Depends(get_db),
                      user: models.User = Depends(require_shopkeeper)):
    """Dukandar apni dukan ke item ka price/stock set ya update karta hai."""
    shop = _get_owned_shop(db, user)
    item = db.query(models.Item).get(payload.item_id)
    if not item:
        raise HTTPException(404, "Item catalog mein nahi mila")

    shop_item = (
        db.query(models.ShopItem)
        .filter(models.ShopItem.shop_id == shop.id, models.ShopItem.item_id == payload.item_id)
        .first()
    )
    if shop_item:
        shop_item.price = payload.price
        shop_item.in_stock = payload.in_stock
    else:
        shop_item = models.ShopItem(
            shop_id=shop.id, item_id=payload.item_id,
            price=payload.price, in_stock=payload.in_stock,
        )
        db.add(shop_item)
    db.commit()
    return {"status": "ok", "item": item.name, "price": payload.price, "in_stock": payload.in_stock}


# ---------------------------------------------------------------------------
# Order queue - dukandar ke phone par jo naye orders aate hain
# ---------------------------------------------------------------------------
@router.get("/orders", response_model=list[schemas.ShopOrderOut])
def list_shop_orders(status_filter: str | None = None, db: Session = Depends(get_db),
                      user: models.User = Depends(require_shopkeeper)):
    """Dukandar apne saare orders yaha dekhta hai (pending, ready, completed, etc.)."""
    shop = _get_owned_shop(db, user)
    q = db.query(models.ShopOrder).filter(models.ShopOrder.shop_id == shop.id)
    if status_filter:
        q = q.filter(models.ShopOrder.status == status_filter)
    orders = q.order_by(models.ShopOrder.created_at.desc()).all()
    return [_to_shop_order_out(db, so) for so in orders]


@router.get("/orders/{shop_order_id}", response_model=schemas.ShopOrderOut)
def get_shop_order(shop_order_id: int, db: Session = Depends(get_db),
                    user: models.User = Depends(require_shopkeeper)):
    shop = _get_owned_shop(db, user)
    so = db.query(models.ShopOrder).get(shop_order_id)
    if not so or so.shop_id != shop.id:
        raise HTTPException(404, "Order nahi mila")
    return _to_shop_order_out(db, so)


# ---------------------------------------------------------------------------
# RULE 1: Accept (right) / Cross - item-level availability check
# ---------------------------------------------------------------------------
@router.patch("/order-items/{shop_order_item_id}/availability")
async def mark_item_availability(
    shop_order_item_id: int,
    payload: schemas.ItemAvailabilityUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_shopkeeper),
):
    """
    Dukandar har item ko right (available) ya cross (not_available) karta hai.
    - Agar 'available' -> bas mark ho jaata hai.
    - Agar 'not_available' -> customer ko turant baaki dukano ki list bhej dete hain
      jaha wo item mil sakta hai.
    Jab saare items check ho jaate hain, order ka overall status automatically update
    hota hai aur customer ko notify kiya jaata hai.
    """
    soi = db.query(models.ShopOrderItem).get(shop_order_item_id)
    if not soi:
        raise HTTPException(404, "Item nahi mila")

    shop = _get_owned_shop(db, user)
    shop_order = soi.shop_order
    if shop_order.shop_id != shop.id:
        raise HTTPException(403, "Yeh order tumhari dukan ka nahi hai")

    if shop_order.status not in (
        models.ShopOrderStatus.pending_shop_review,
        models.ShopOrderStatus.partially_unavailable,
    ):
        raise HTTPException(400, "Is order ke items ab edit nahi ho sakte")

    soi.availability = payload.availability
    db.flush()

    alternatives_payload = None
    if payload.availability == models.ItemAvailability.not_available:
        alt_shop_items = matching.find_alternate_shops_for_item(
            db, soi.item_id, exclude_shop_id=shop.id
        )
        alternatives_payload = [
            {"shop_id": a.shop_id, "shop_name": a.shop.name, "price": a.price}
            for a in alt_shop_items
        ]
        # customer ko turant batao ki yeh item is dukan mein nahi hai
        await realtime.manager.send_to_user(
            shop_order.order.customer_id,
            "item_not_available",
            {
                "shop_order_id": shop_order.id,
                "item_id": soi.item_id,
                "item_name": soi.item.name,
                "shop_name": shop.name,
                "alternatives": alternatives_payload,
            },
        )

    # check karo ki saare items review ho gaye ya nahi
    all_items = shop_order.items
    still_pending = any(i.availability == models.ItemAvailability.pending for i in all_items)

    if not still_pending:
        any_unavailable = any(
            i.availability == models.ItemAvailability.not_available for i in all_items
        )
        if any_unavailable:
            shop_order.status = models.ShopOrderStatus.partially_unavailable
        else:
            shop_order.status = models.ShopOrderStatus.awaiting_payment
            # recompute amount sirf available items ka (agar kuch removed ho)
            shop_order.amount = sum(
                i.unit_price * i.quantity for i in all_items
                if i.availability == models.ItemAvailability.available
            )
            await realtime.manager.send_to_user(
                shop_order.order.customer_id,
                "ready_for_payment",
                {"shop_order_id": shop_order.id, "amount": shop_order.amount},
            )

    db.commit()
    db.refresh(soi)
    return {
        "item_id": soi.item_id,
        "availability": soi.availability,
        "shop_order_status": shop_order.status,
        "alternatives": alternatives_payload,
    }


# ---------------------------------------------------------------------------
# RULE 2 support: shopkeeper dekh sake customer cash ke liye eligible hai ya nahi
# (Asli 10-order rule /customer/... routes mein enforce hota hai, yeh sirf info hai)
# ---------------------------------------------------------------------------
@router.get("/orders/{shop_order_id}/customer-eligibility")
def customer_eligibility(shop_order_id: int, db: Session = Depends(get_db),
                          user: models.User = Depends(require_shopkeeper)):
    shop = _get_owned_shop(db, user)
    so = db.query(models.ShopOrder).get(shop_order_id)
    if not so or so.shop_id != shop.id:
        raise HTTPException(404, "Order nahi mila")
    import os
    required = int(os.getenv("ONLINE_PAYMENTS_REQUIRED_FOR_CASH", "10"))
    customer = so.order.customer
    remaining = max(0, required - customer.online_payment_count)
    return {
        "customer_name": customer.name,
        "online_payment_count": customer.online_payment_count,
        "cash_unlocked": customer.cash_unlocked,
        "online_payments_remaining_for_cash": remaining,
    }


# ---------------------------------------------------------------------------
# Ready button
# ---------------------------------------------------------------------------
@router.post("/orders/{shop_order_id}/ready", response_model=schemas.ShopOrderOut)
async def mark_ready(shop_order_id: int, db: Session = Depends(get_db),
                      user: models.User = Depends(require_shopkeeper)):
    """
    Dukandar saman bag mein daal ke 'Ready' dabata hai.
    Isse QR token + 4-digit code generate hota hai, aur customer ko
    map location ke saath notification jaati hai.
    """
    shop = _get_owned_shop(db, user)
    so = db.query(models.ShopOrder).get(shop_order_id)
    if not so or so.shop_id != shop.id:
        raise HTTPException(404, "Order nahi mila")

    if so.status != models.ShopOrderStatus.confirmed:
        raise HTTPException(
            400, "Order abhi 'ready' nahi ho sakta - payment confirm nahi hua hai"
        )

    so.qr_token = verification.generate_qr_token()
    so.verification_code = verification.generate_verification_code()
    so.status = models.ShopOrderStatus.ready
    so.ready_at = datetime.utcnow()
    db.commit()
    db.refresh(so)

    await realtime.manager.send_to_user(
        so.order.customer_id,
        "order_ready",
        {
            "shop_order_id": so.id,
            "message": f"Aapka order taiyar hai, {shop.name} aa jaiye",
            "shop_name": shop.name,
            "shop_address": shop.address,
            "shop_latitude": shop.latitude,
            "shop_longitude": shop.longitude,
            "qr_token": so.qr_token,
            "verification_code": so.verification_code,
        },
    )
    return _to_shop_order_out(db, so)


# ---------------------------------------------------------------------------
# RULE 3: Final checkout verification - QR scan YA 4-digit code
# ---------------------------------------------------------------------------
@router.post("/orders/{shop_order_id}/verify-qr", response_model=schemas.ShopOrderOut)
async def verify_pickup_qr(shop_order_id: int, payload: schemas.VerifyQRRequest,
                            db: Session = Depends(get_db),
                            user: models.User = Depends(require_shopkeeper)):
    """Dukandar customer ke phone ka QR scan karta hai - isse call hota hai."""
    shop = _get_owned_shop(db, user)
    so = db.query(models.ShopOrder).get(shop_order_id)
    if not so or so.shop_id != shop.id:
        raise HTTPException(404, "Order nahi mila")

    if so.status != models.ShopOrderStatus.ready:
        raise HTTPException(400, "Order abhi pickup ke liye ready nahi hai")

    if payload.qr_token != so.qr_token:
        raise HTTPException(400, "QR code match nahi hua")

    return await _complete_pickup(db, so)



@router.post("/orders/verify-code-only", response_model=schemas.ShopOrderOut)
async def verify_pickup_code_only(payload: schemas.VerifyCodeRequest, db: Session = Depends(get_db), user: models.User = Depends(require_shopkeeper)):
    """
    Sirf code se pickup verify karo - Order ID daalne ki zaroorat nahi.
    Shop ke saare 'ready' orders mein se code match karke dhoondta hai.
    """
    shop = _get_owned_shop(db, user)
    so = db.query(models.ShopOrder).filter(
        models.ShopOrder.shop_id == shop.id,
        models.ShopOrder.status == models.ShopOrderStatus.ready,
        models.ShopOrder.verification_code == payload.code
    ).first()

    if not so:
        raise HTTPException(400, "Is code se koi order nahi mila")

    return await _complete_pickup(db, so)


async def _complete_pickup(db: Session, so: models.ShopOrder) -> schemas.ShopOrderOut:
    so.status = models.ShopOrderStatus.completed
    so.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(so)

    customer_id = so.order.customer_id
    shop = db.query(models.Shop).get(so.shop_id)

    # dono taraf confirmation - customer aur dukandar
    await realtime.manager.send_to_user(
        customer_id, "order_received",
        {"shop_order_id": so.id, "message": f"Order confirm ho gaya - {shop.name} se mil gaya"},
    )
    await realtime.manager.send_to_user(
        shop.owner_id, "order_completed",
        {"shop_order_id": so.id, "customer_name": so.order.customer.name},
    )
    return _to_shop_order_out(db, so)
