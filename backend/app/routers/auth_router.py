from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=schemas.Token)
def signup(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.phone == payload.phone).first()
    if existing:
        raise HTTPException(400, "Yeh phone number pehle se registered hai")

    user = models.User(
        name=payload.name,
        phone=payload.phone,
        password_hash=auth.hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if payload.role == models.UserRole.shopkeeper:
        if not (payload.shop_name and payload.shop_address is not None
                and payload.shop_latitude is not None and payload.shop_longitude is not None):
            raise HTTPException(400, "Shopkeeper ke liye shop_name, address, latitude, longitude zaroori hai")
        shop = models.Shop(
            owner_id=user.id,
            name=payload.shop_name,
            address=payload.shop_address,
            latitude=payload.shop_latitude,
            longitude=payload.shop_longitude,
        )
        db.add(shop)
        db.commit()

    token = auth.create_access_token({"sub": str(user.id)})
    return schemas.Token(
        access_token=token, role=user.role, user_id=user.id, name=user.name,
        cash_unlocked=user.cash_unlocked, online_payment_count=user.online_payment_count,
    )


@router.post("/login", response_model=schemas.Token)
def login(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.phone == payload.phone).first()
    if not user or not auth.verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Phone number ya password galat hai")

    token = auth.create_access_token({"sub": str(user.id)})
    return schemas.Token(
        access_token=token, role=user.role, user_id=user.id, name=user.name,
        cash_unlocked=user.cash_unlocked, online_payment_count=user.online_payment_count,
    )
