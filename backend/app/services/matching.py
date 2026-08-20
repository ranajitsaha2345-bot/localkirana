"""
Yeh service har item ke liye sabse achi dukan dhoondti hai.

Rule: koi shop kabhi exclude nahi hoti, chahe kitni bhi door ho.
Lekin ranking mein distance ka weight bahut zyada hai — matlab
paas ki shop (chahe thodi mehengi ho) upar aayegi, aur bahut door
ki sasti shop bhi list mein rahegi lekin bahut niche.
"""
import math
from typing import Optional
from sqlalchemy.orm import Session

from .. import models

# Distance ka weight - jitna zyada, utna distance ka asar strong hoga
# 0.15 ka matlab: har 1km door jaane par price mein ~15% ka "penalty" lagta hai score mein
DISTANCE_WEIGHT = 0.15


def _distance_km(lat1, lon1, lat2, lon2) -> Optional[float]:
    """Haversine formula - do coordinates ke beech ki seedhi doori. Location na ho to None."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _score(price: float, dist: Optional[float]) -> float:
    """Kam score = behtar rank. Distance na pata ho to sirf price se score banta hai."""
    if dist is None:
        return price
    return price * (1 + dist * DISTANCE_WEIGHT)


def find_cheapest_shop_for_item(
    db: Session,
    item_id: int,
    customer_lat: Optional[float] = None,
    customer_lng: Optional[float] = None,
) -> Optional[models.ShopItem]:
    """
    Item ke liye sabse achi dukan return karta hai (paas + sasta dono ka combined score).
    Koi shop exclude nahi hoti - bas jo score mein sabse upar aaye wahi chuni jaati hai.
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

    def key(c):
        dist = _distance_km(customer_lat, customer_lng, c.shop.latitude, c.shop.longitude)
        return _score(c.price, dist)

    candidates.sort(key=key)
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
    baaki dukano ki list deta hai (paas + sasta ke hisaab se ranked).
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

    def key(c):
        dist = _distance_km(customer_lat, customer_lng, c.shop.latitude, c.shop.longitude)
        return _score(c.price, dist)

    candidates.sort(key=key)
    return candidates


def rank_shops_for_item(
    db: Session,
    item_id: int,
    customer_lat: Optional[float] = None,
    customer_lng: Optional[float] = None,
) -> list[tuple[models.ShopItem, Optional[float]]]:
    """
    Item bechne wali saari dukano ko 'paas + sasta' ke combined score se sort karta hai.
    Score jitna kam, utna upar. Koi shop list se bahar nahi hoti.
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
        return []

    scored = []
    for c in candidates:
        dist = _distance_km(customer_lat, customer_lng, c.shop.latitude, c.shop.longitude)
        scored.append((c, dist, _score(c.price, dist)))

    scored.sort(key=lambda x: x[2])
    return [(c, dist) for c, dist, _ in scored]
NEARBY_RADIUS_KM = 50.0


def has_nearby_stock(db: Session, item_id: int, customer_lat: Optional[float], customer_lng: Optional[float]) -> bool:
    """Kya customer ke 15km radius mein koi shop hai jo ye item bechti hai aur stock mein hai.
    Location na di ho to gate skip - True return hoga (item normal dikhega)."""
    if customer_lat is None or customer_lng is None:
        return True
    rows = (
        db.query(models.ShopItem)
        .join(models.Shop)
        .filter(
            models.ShopItem.item_id == item_id,
            models.ShopItem.in_stock == True,  # noqa: E712
            models.Shop.is_open == True,  # noqa: E712
        )
        .all()
    )
    for r in rows:
        dist = _distance_km(customer_lat, customer_lng, r.shop.latitude, r.shop.longitude)
        if dist is not None and dist <= NEARBY_RADIUS_KM:
            return True
    return False