"""
Yeh service har item ke liye sabse sasti available dukan dhoondti hai.

Simple rule abhi: sabse kam price wali shop jiske paas stock hai.
Aage chal ke isme distance-based weighting bhi add kar sakte ho
(jaise: price + thoda sa distance penalty, taaki bahut door ki
sasti dukan na chuni jaaye).
"""
import math
from typing import Optional
from sqlalchemy.orm import Session

from .. import models


def _distance_km(lat1, lon1, lat2, lon2) -> float:
    """Haversine formula - do coordinates ke beech ki seedhi doori."""
    if None in (lat1, lon1, lat2, lon2):
        return 0.0
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def find_cheapest_shop_for_item(
    db: Session,
    item_id: int,
    customer_lat: Optional[float] = None,
    customer_lng: Optional[float] = None,
    max_distance_km: float = 15.0,
) -> Optional[models.ShopItem]:
    """
    Item ke liye sabse sasti dukan return karta hai jaha stock available hai.
    Agar customer location di hai, to bahut door ki dukan exclude ho jaati hai.
    """
    candidates = (
        db.query(models.ShopItem)
        .join(models.Shop)
        .filter(
            models.ShopItem.item_id == item_id,
            models.ShopItem.in_stock == True,  # noqa: E712
            models.Shop.is_open == True,  # noqa: E712
        )
        .all()
    )

    if not candidates:
        return None

    if customer_lat is not None and customer_lng is not None:
        candidates = [
            c
            for c in candidates
            if _distance_km(customer_lat, customer_lng, c.shop.latitude, c.shop.longitude)
            <= max_distance_km
        ] or candidates  # agar sab dur hain to fir bhi kuch dikhao

    # sabse sasti pehle
    candidates.sort(key=lambda c: c.price)
    return candidates[0]


def find_alternate_shops_for_item(
    db: Session,
    item_id: int,
    exclude_shop_id: int,
    customer_lat: Optional[float] = None,
    customer_lng: Optional[float] = None,
) -> list[models.ShopItem]:
    """
    Jab dukandar item 'not available' mark karta hai, tab yeh function
    baaki dukano ki list deta hai jaha wo item mil sakta hai (price order mein).
    """
    candidates = (
        db.query(models.ShopItem)
        .join(models.Shop)
        .filter(
            models.ShopItem.item_id == item_id,
            models.ShopItem.in_stock == True,  # noqa: E712
            models.Shop.is_open == True,  # noqa: E712
            models.ShopItem.shop_id != exclude_shop_id,
        )
        .all()
    )
    candidates.sort(key=lambda c: c.price)
    return candidates
