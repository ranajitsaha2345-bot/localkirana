import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import relationship

from .database import Base


class UserRole(str, enum.Enum):
    customer = "customer"
    shopkeeper = "shopkeeper"


class ShopOrderStatus(str, enum.Enum):
    pending_shop_review = "pending_shop_review"   # dukandar ne abhi dekha nahi
    partially_unavailable = "partially_unavailable"  # kuch item nahi mile
    awaiting_payment = "awaiting_payment"          # sab item available, ab customer payment karega
    confirmed = "confirmed"                        # payment ho gaya (online ya cash-on-pickup)
    ready = "ready"                                 # dukandar ne ready dabaya
    completed = "completed"                         # customer ne pickup kar liya
    cancelled = "cancelled"


class ItemAvailability(str, enum.Enum):
    pending = "pending"
    available = "available"
    not_available = "not_available"


class PaymentMode(str, enum.Enum):
    online = "online"
    cash = "cash"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    cash_on_pickup = "cash_on_pickup"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)

    # cash-eligibility rule: pehle N online payments ke baad hi cash allowed
    online_payment_count = Column(Integer, default=0)
    cash_unlocked = Column(Boolean, default=False)

    # forgot-password OTP
    reset_code = Column(String, nullable=True)
    reset_code_expiry = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    shop = relationship("Shop", back_populates="owner", uselist=False)


class Shop(Base):
    __tablename__ = "shops"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    is_open = Column(Boolean, default=True)

    owner = relationship("User", back_populates="shop")
    inventory = relationship("ShopItem", back_populates="shop")


class Item(Base):
    """Master catalog - dal, chini, oil, biskut, etc."""
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    unit = Column(String, default="unit")  # kg, litre, piece
    category = Column(String, default="general")


class ShopItem(Base):
    """Ek shop mein ek item ka price aur stock."""
    __tablename__ = "shop_items"

    id = Column(Integer, primary_key=True, index=True)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    price = Column(Float, nullable=False)
    in_stock = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    shop = relationship("Shop", back_populates="inventory")
    item = relationship("Item")


class Order(Base):
    """Customer ka poora cart - isse multiple shops ke ShopOrder banenge."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("User")
    shop_orders = relationship("ShopOrder", back_populates="order")


class ShopOrder(Base):
    """Ek order ka woh hissa jo ek particular dukan ko jaata hai."""
    __tablename__ = "shop_orders"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=False)

    status = Column(Enum(ShopOrderStatus), default=ShopOrderStatus.pending_shop_review)
    payment_mode = Column(Enum(PaymentMode), nullable=True)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.pending)
    amount = Column(Float, default=0.0)

    razorpay_order_id = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)

    qr_token = Column(String, default=lambda: str(uuid.uuid4()))
    verification_code = Column(String, nullable=True)  # 4-digit fallback

    created_at = Column(DateTime, default=datetime.utcnow)
    ready_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    order = relationship("Order", back_populates="shop_orders")
    shop = relationship("Shop")
    items = relationship("ShopOrderItem", back_populates="shop_order")


class ShopOrderItem(Base):
    __tablename__ = "shop_order_items"

    id = Column(Integer, primary_key=True, index=True)
    shop_order_id = Column(Integer, ForeignKey("shop_orders.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=False)
    availability = Column(Enum(ItemAvailability), default=ItemAvailability.pending)

    shop_order = relationship("ShopOrder", back_populates="items")
    item = relationship("Item")
