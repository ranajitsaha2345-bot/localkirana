"""
Simple in-memory WebSocket manager.
Har user (customer ya shopkeeper) apne user_id se connect hota hai.
Jab bhi kuch event hota hai (naya order, item unavailable, ready, verified)
hum us user ko turant message bhej dete hain.

Note: Yeh single-server ke liye theek hai. Jab app scale karega aur
multiple servers honge, tab isse Redis pub/sub jaisi cheez se replace karna.
"""
import json
from typing import Dict
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: Dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active and websocket in self.active[user_id]:
            self.active[user_id].remove(websocket)
            if not self.active[user_id]:
                del self.active[user_id]

    async def send_to_user(self, user_id: int, event: str, data: dict):
        connections = self.active.get(user_id, [])
        payload = json.dumps({"event": event, "data": data})
        for ws in list(connections):
            try:
                await ws.send_text(payload)
            except Exception:
                self.disconnect(user_id, ws)


manager = ConnectionManager()
