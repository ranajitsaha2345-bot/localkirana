# FILE NAAM: telegram_webhook.py
# KAHA RAKHNA HAI: backend/app/routers/  folder ke andar
#
# ZAROORI: Ye route PUBLIC hona chahiye (auth check mat lagana) — Telegram
# khud isko call karta hai, koi logged-in shopkeeper nahi.
#
# NOTE: "from ..services.realtime import manager" line — aapke screenshot mein
# app/services/realtime.py file dikh rahi hai, wahi websocket wala code hoga.
# Usme jo bhi connection-manager object/class hai (jiska naam "manager" na ho
# to sahi naam yahan daalna), aur uske paas shop_id ko message bhejne wala
# function hona chahiye. Mujhe realtime.py ka content bhej doge to main is
# file ko exact match kar dunga (abhi maine "manager.send_to_shop(...)" ek
# andaza laga kar likha hai).

from fastapi import APIRouter, Request
from sqlalchemy.orm import Session

from .. import models
from ..database import SessionLocal
from ..services.realtime import manager  # <-- realtime.py dekh kar naam confirm karna

router = APIRouter(tags=["telegram-webhook"])


@router.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    update = await request.json()
    message = update.get("message")
    if not message:
        return {"ok": True}

    reply_to = message.get("reply_to_message")
    text = message.get("text", "")

    if not reply_to:
        # Normal type karke (bina reply ke) bheja gaya message — ignore karo,
        # taaki galat shop ko jawab na chala jaye.
        return {"ok": True}

    replied_msg_id = reply_to["message_id"]

    db: Session = SessionLocal()
    try:
        original = (
            db.query(models.SupportMessage)
            .filter(models.SupportMessage.telegram_message_id == replied_msg_id)
            .first()
        )
        if not original:
            return {"ok": True}

        shop_id = original.shop_id

        row = models.SupportMessage(
            shop_id=shop_id,
            sender_role="support",
            message=text,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        row.telegram_message_id = message["message_id"]
        db.commit()

        shop = db.query(models.Shop).get(shop_id)
        if shop:
            await manager.send_to_user(
                shop.owner_id,
                "support_message",
                {
                    "id": row.id,
                    "sender_role": "support",
                    "message": row.message,
                    "created_at": row.created_at.isoformat(),
                },
            )
    finally:
        db.close()

    return {"ok": True}