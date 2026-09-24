from dotenv import load_dotenv
load_dotenv()
# FILE NAAM: telegram_service.py
# KAHA RAKHNA HAI: backend/app/services/  folder ke andar
# (jaha email.py, payment.py, matching.py waghera already hain, wahi)

import os
from typing import Optional

import httpx

# Render/Vercel ke Environment Variables mein ye 2 set karna hai:
#   TELEGRAM_BOT_TOKEN        -> BotFather se mila token
#   TELEGRAM_SUPPORT_CHAT_ID  -> 8511681584
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_SUPPORT_CHAT_ID = os.getenv("TELEGRAM_SUPPORT_CHAT_ID")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def send_to_telegram(text: str, reply_to_message_id: Optional[int] = None) -> int:
    """
    Support chat ID par message bhejta hai.
    Return value: Telegram ka apna message_id (isko DB mein telegram_message_id
    column mein store karo — isi se aage reply-matching hogi).
    """
    payload = {
        "chat_id": TELEGRAM_SUPPORT_CHAT_ID,
        "text": text,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["result"]["message_id"]


async def set_webhook(webhook_url: str) -> dict:
    """Ek hi baar chalana hai (deploy ke baad) taaki Telegram aapke
    /webhook/telegram endpoint par updates bhejna shuru kare."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{TELEGRAM_API}/setWebhook", json={"url": webhook_url})
        resp.raise_for_status()
        return resp.json()