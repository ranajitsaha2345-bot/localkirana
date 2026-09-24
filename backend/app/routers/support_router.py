# FILE NAAM: support.py
# KAHA RAKHNA HAI: backend/app/routers/  folder ke andar
#
# NOTE: "from ..auth import get_current_user" line mein maan kar chala hoon
# ki aapki login-check wali file "auth.py" app folder mein hai (screenshot mein
# dikh rahi hai) aur usme "get_current_user" naam ka function hai. Agar function
# ka naam kuch aur hai, wahi yahan daal dena — mujhe auth.py ka content bhej doge
# to main exact kar dunga.

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..auth import get_current_user
from ..services.telegram_service import send_to_telegram

router = APIRouter(prefix="/shop/support", tags=["support"])


@router.get("/messages", response_model=List[schemas.SupportMessageOut])
def get_support_messages(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    shop = current_user.shop
    if not shop:
        raise HTTPException(404, "Shop not found")

    rows = (
        db.query(models.SupportMessage)
        .filter(models.SupportMessage.shop_id == shop.id)
        .order_by(models.SupportMessage.created_at.asc())
        .all()
    )
    return rows


@router.post("/message", response_model=schemas.SupportMessageOut)
async def send_support_message(
    payload: schemas.SupportMessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    shop = current_user.shop
    if not shop:
        raise HTTPException(404, "Shop not found")

    # 1. Pehle DB mein save karo
    row = models.SupportMessage(
        shop_id=shop.id,
        sender_role="shopkeeper",
        message=payload.message,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # 2. Telegram par forward karo — shop ka naam/id prefix karke
    text = f"🏪 {shop.name} (shop_id={shop.id}):\n{payload.message}"
    telegram_msg_id = await send_to_telegram(text)

    # 3. Is row ka telegram_message_id save karo (reply-matching ke liye)
    row.telegram_message_id = telegram_msg_id
    db.commit()
    db.refresh(row)

    return row