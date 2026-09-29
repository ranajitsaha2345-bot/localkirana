import os, re, httpx
from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from auth import get_current_user  # <-- yahi ek line apne project ke hisaab se badalni pad sakti hai

router = APIRouter()

BOT_TOKEN = os.getenv("CUSTOMER_BOT_TOKEN")
CHAT_ID = os.getenv("CUSTOMER_SUPPORT_CHAT_ID")
WEBHOOK_SECRET = os.getenv("CUSTOMER_WEBHOOK_SECRET")

_messages = {}  # user_id -> list of messages

class Msg(BaseModel):
    message: str

@router.post("/customer-support/send")
async def send(body: Msg, user=Depends(get_current_user)):
    _messages.setdefault(user.id, []).append({"from": "customer", "text": body.message})
    text = f"#C{user.id} {user.name}\n{body.message}"
    async with httpx.AsyncClient() as c:
        await c.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                     json={"chat_id": CHAT_ID, "text": text})
    return {"ok": True}

@router.get("/customer-support/messages")
async def messages(user=Depends(get_current_user)):
    return _messages.get(user.id, [])

@router.post("/telegram/customer-webhook/{secret}")
async def webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403)
    data = await request.json()
    msg = data.get("message") or {}
    if str(msg.get("chat", {}).get("id")) != str(CHAT_ID):
        return {"ok": True}
    reply = msg.get("reply_to_message")
    if not reply or not msg.get("text"):
        return {"ok": True}
    m = re.match(r"#C(\d+)", reply.get("text", ""))
    if m:
        _messages.setdefault(int(m.group(1)), []).append({"from": "support", "text": msg["text"]})
    return {"ok": True}