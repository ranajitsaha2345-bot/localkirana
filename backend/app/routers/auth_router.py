from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from datetime import datetime, timedelta
from ..services.email import generate_otp, send_otp_email

router = APIRouter(prefix="/auth", tags=["auth"])
import os
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

class GoogleLogin(BaseModel):
    credential: str
    role: str = "customer"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    role: str = "customer"


@router.post("/google", response_model=schemas.Token)
def google_login(payload: GoogleLogin, db: Session = Depends(get_db)):
    try:
        idinfo = google_id_token.verify_oauth2_token(
            payload.credential, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError:
        raise HTTPException(400, "Google verification fail ho gaya, dobara try karo")

    google_id = idinfo["sub"]
    email = idinfo.get("email")
    name = idinfo.get("name", "User")

    user = db.query(models.User).filter(models.User.google_id == google_id).first()
    if not user and email:
        user = db.query(models.User).filter(models.User.email == email).first()

    if not user:
        requested_role = models.UserRole.shopkeeper if payload.role == "shopkeeper" else models.UserRole.customer
        user = models.User(
            name=name,
            phone=None,
            email=email,
            google_id=google_id,
            password_hash=auth.hash_password(google_id),
            role=requested_role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if not user.google_id:
            user.google_id = google_id
            db.commit()

    token = auth.create_access_token({"sub": str(user.id)})
    return schemas.Token(
        access_token=token, role=user.role, user_id=user.id, name=user.name,
        cash_unlocked=user.cash_unlocked, online_payment_count=user.online_payment_count,
    )


@router.post("/signup", response_model=schemas.Token)
def signup(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.phone == payload.phone).first()
    if existing:
        raise HTTPException(400, "Yeh phone number pehle se registered hai")

    user = models.User(
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
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

@router.post("/request-otp")
def request_otp(payload: schemas.RequestOTPLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.phone == payload.phone).first()
    if not user:
        # Naya user hai - auto-create karo (password nahi chahiye)
        requested_role = models.UserRole.shopkeeper if payload.role == "shopkeeper" else models.UserRole.customer
        user = models.User(
            name=payload.name or "User",
            phone=payload.phone,
            email=payload.email,
            password_hash=auth.hash_password(payload.phone),  # dummy, kabhi use nahi hoga
            role=requested_role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if payload.email and user.email != payload.email:
            user.email = payload.email
            db.commit()

    if not user.email:
        raise HTTPException(400, "Gmail address zaroori hai")

    otp = generate_otp()
    user.reset_code = otp
    user.reset_code_expiry = datetime.utcnow() + timedelta(minutes=10)
    db.commit()

    send_otp_email(user.email, otp, user.name)
    return {"message": "OTP aapke Gmail par bhej diya gaya hai"}


@router.post("/verify-login-otp", response_model=schemas.Token)
def verify_login_otp(payload: schemas.VerifyLoginOTP, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.phone == payload.phone).first()
    if not user or not user.reset_code:
        raise HTTPException(400, "Pehle OTP mangwao")
    if user.reset_code != payload.otp:
        raise HTTPException(400, "OTP galat hai")
    if datetime.utcnow() > user.reset_code_expiry:
        raise HTTPException(400, "OTP expire ho gaya, dobara try karo")

    user.reset_code = None
    user.reset_code_expiry = None
    db.commit()

    token = auth.create_access_token({"sub": str(user.id)})
    return schemas.Token(
        access_token=token, role=user.role, user_id=user.id, name=user.name,
        cash_unlocked=user.cash_unlocked, online_payment_count=user.online_payment_count,
    )

@router.post("/forgot-password")
def forgot_password(payload: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.phone == payload.phone).first()
    if not user:
        raise HTTPException(404, "Yeh phone number registered nahi hai")
    if not user.email:
        raise HTTPException(400, "Is account me Gmail add nahi hai, OTP nahi bhej sakte")

    otp = generate_otp()
    user.reset_code = otp
    user.reset_code_expiry = datetime.utcnow() + timedelta(minutes=10)
    db.commit()

    send_otp_email(user.email, otp, user.name)
    return {"message": "OTP aapke Gmail par bhej diya gaya hai"}


@router.post("/verify-otp")
def verify_otp(payload: schemas.VerifyOTPRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.phone == payload.phone).first()
    if not user or not user.reset_code:
        raise HTTPException(400, "OTP request nahi mila, pehle Forgot Password karo")
    if user.reset_code != payload.otp:
        raise HTTPException(400, "OTP galat hai")
    if datetime.utcnow() > user.reset_code_expiry:
        raise HTTPException(400, "OTP expire ho gaya, dobara try karo")

    return {"message": "OTP sahi hai"}


@router.post("/reset-password")
def reset_password(payload: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.phone == payload.phone).first()
    if not user or not user.reset_code:
        raise HTTPException(400, "OTP request nahi mila, pehle Forgot Password karo")
    if user.reset_code != payload.otp:
        raise HTTPException(400, "OTP galat hai")
    if datetime.utcnow() > user.reset_code_expiry:
        raise HTTPException(400, "OTP expire ho gaya, dobara try karo")

    user.password_hash = auth.hash_password(payload.new_password)
    user.reset_code = None
    user.reset_code_expiry = None
    db.commit()

    return {"message": "Password successfully change ho gaya"}
