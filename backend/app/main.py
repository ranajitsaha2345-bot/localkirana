from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt, JWTError

from .database import Base, engine, SessionLocal
from . import models
from .auth import SECRET_KEY, ALGORITHM
from .services.realtime import manager
from .routers import auth_router, customer_router, shop_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="LocalKirana API", version="1.0.0")

# Production mein allow_origins ko apni actual domain tak limit karna
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(customer_router.router)
app.include_router(shop_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}


def _default_catalog():
    """Seed data - roz-marra ke items, taaki demo turant chala sako."""
    defaults = [
        ("Dal (Toor)", "kg", "grocery"),
        ("Chini", "kg", "grocery"),
        ("Sarson Tel", "litre", "grocery"),
        ("Biskut (Parle-G)", "packet", "grocery"),
        ("Atta", "kg", "grocery"),
        ("Chawal", "kg", "grocery"),
        ("Namak", "kg", "grocery"),
        ("Chai Patti", "packet", "grocery"),
    ]
    db = SessionLocal()
    try:
        for name, unit, category in defaults:
            if not db.query(models.Item).filter(models.Item.name == name).first():
                db.add(models.Item(name=name, unit=unit, category=category))
        db.commit()
    finally:
        db.close()


_default_catalog()


# ---------------------------------------------------------------------------
# WebSocket - real-time notifications (naya order, ready, verified, etc.)
# Client isse connect karta hai: wss://.../ws?token=<jwt access token>
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        await websocket.close(code=4001)
        return

    await manager.connect(user_id, websocket)
    try:
        while True:
            # client se kuch aane ki zaroorat nahi, bas connection zinda rakhna hai
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
# Frontend files serve karne ke liye
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/customer.html")
def serve_customer():
    return FileResponse(os.path.join(FRONTEND_DIR, "customer.html"))

@app.get("/shopkeeper.html")
def serve_shopkeeper():
    return FileResponse(os.path.join(FRONTEND_DIR, "shopkeeper.html"))

@app.get("/")
def serve_root():
    return FileResponse(os.path.join(FRONTEND_DIR, "customer.html"))

@app.get("/manifest.json")
def serve_manifest():
    return FileResponse(os.path.join(FRONTEND_DIR, "manifest.json"))