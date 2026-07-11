from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from .models import UserRole, ShopOrderStatus, ItemAvailability, PaymentMode, PaymentStatus


# ---------- Auth ----------
class UserCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    password: str
    role: UserRole
    # agar shopkeeper hai to yeh bhi bhejna
    shop_name: Optional[str] = None
    shop_address: Optional[str] = None
    shop_latitude: Optional[float] = None
    shop_longitude: Optional[float] = None
    
    # ---------- Forgot Password ----------

class ForgotPasswordRequest(BaseModel):
    phone: str


class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str


class ResetPasswordRequest(BaseModel):
    phone: str
    otp: str
    new_password: str



class UserLogin(BaseModel):
    phone: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    user_id: int
    name: str
    cash_unlocked: bool = False
    online_payment_count: int = 0


# ---------- Catalog ----------
class ItemOut(BaseModel):
    id: int
    name: str
    unit: str
    category: str

    class Config:
        from_attributes = True


class ShopItemUpsert(BaseModel):
    item_id: int
    price: float
    in_stock: bool = True


# ---------- Cart matching ----------
class CartLine(BaseModel):
    item_id: int
    quantity: float = Field(gt=0)


class CartMatchRequest(BaseModel):
    lines: List[CartLine]
    # optional: customer location, taaki paas ki dukan prefer ho
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class MatchedLine(BaseModel):
    item_id: int
    item_name: str
    quantity: float
    shop_id: Optional[int]
    shop_name: Optional[str]
    unit_price: Optional[float]
    line_total: Optional[float]
    available: bool


class CartMatchResponse(BaseModel):
    lines: List[MatchedLine]
    grand_total: float


# ---------- Orders ----------
class PlaceOrderRequest(BaseModel):
    lines: List[CartLine]
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class ShopOrderItemOut(BaseModel):
    id: int
    item_id: int
    item_name: str
    quantity: float
    unit_price: float
    availability: ItemAvailability

    class Config:
        from_attributes = True


class ShopOrderOut(BaseModel):
    id: int
    order_id: int
    shop_id: int
    shop_name: str
    customer_id: int
    customer_name: str
    status: ShopOrderStatus
    payment_mode: Optional[PaymentMode]
    payment_status: PaymentStatus
    amount: float
    verification_code: Optional[str]
    qr_token: str
    items: List[ShopOrderItemOut]
    created_at: datetime
    ready_at: Optional[datetime]

    class Config:
        from_attributes = True


class ItemAvailabilityUpdate(BaseModel):
    availability: ItemAvailability


class ConfirmShopOrderRequest(BaseModel):
    payment_mode: PaymentMode


class VerifyCodeRequest(BaseModel):
    code: str


class VerifyQRRequest(BaseModel):
    qr_token: str


class RazorpayOrderOut(BaseModel):
    razorpay_order_id: str
    amount_paise: int
    currency: str = "INR"
    key_id: str


class RazorpayVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
