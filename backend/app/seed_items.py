"""
Ek baar chalane wala script — categories aur images assign karta hai.
Chalane ka tarika: backend folder mein jaake terminal mein likho:
python -m app.seed_items
"""
from .database import SessionLocal
from .models import Item

CATEGORY_IMAGES = {
    "grocery": "https://cdn-icons-png.flaticon.com/512/3082/3082031.png",
    "vegetables": "https://cdn-icons-png.flaticon.com/512/2153/2153788.png",
    "fruits": "https://cdn-icons-png.flaticon.com/512/415/415733.png",
    "dairy": "https://cdn-icons-png.flaticon.com/512/2674/2674486.png",
    "masala": "https://cdn-icons-png.flaticon.com/512/2276/2276931.png",
    "snacks": "https://cdn-icons-png.flaticon.com/512/2553/2553691.png",
    "beverages": "https://cdn-icons-png.flaticon.com/512/2405/2405479.png",
    "personal_care": "https://cdn-icons-png.flaticon.com/512/2553/2553651.png",
    "household": "https://cdn-icons-png.flaticon.com/512/995/995053.png",
    "medicine": "https://cdn-icons-png.flaticon.com/512/2913/2913461.png",
    "stationery": "https://cdn-icons-png.flaticon.com/512/2143/2143151.png",
    "baby_care": "https://cdn-icons-png.flaticon.com/512/3524/3524659.png",
}

# naam ke keyword ke hisaab se category tay hoti hai
KEYWORD_CATEGORY = {
    "dal": "grocery", "chawal": "grocery", "atta": "grocery", "chini": "grocery",
    "namak": "grocery", "tel": "grocery", "sarson": "grocery",
    "aloo": "vegetables", "pyaz": "vegetables", "tamatar": "vegetables",
    "sabzi": "vegetables", "bhindi": "vegetables", "gobi": "vegetables",
    "seb": "fruits", "kela": "fruits", "aam": "fruits", "santra": "fruits",
    "doodh": "dairy", "dahi": "dairy", "paneer": "dairy", "ghee": "dairy",
    "haldi": "masala", "mirch": "masala", "jeera": "masala", "garam": "masala",
    "biskut": "snacks", "namkeen": "snacks", "chips": "snacks",
    "chai": "beverages", "coffee": "beverages", "cold": "beverages",
    "sabun": "personal_care", "shampoo": "personal_care", "tooth": "personal_care",
    "detergent": "household", "jhadu": "household", "phenyl": "household",
    "dawai": "medicine", "medicine": "medicine", "bandage": "medicine",
    "copy": "stationery", "pen": "stationery", "pencil": "stationery",
    "diaper": "baby_care", "baby": "baby_care",
}

NEW_ITEMS = [
    # (name, unit, category)
    ("Aloo", "kg", "vegetables"), ("Pyaz", "kg", "vegetables"), ("Tamatar", "kg", "vegetables"),
    ("Bhindi", "kg", "vegetables"), ("Gobi", "piece", "vegetables"),
    ("Seb", "kg", "fruits"), ("Kela", "dozen", "fruits"), ("Santra", "kg", "fruits"),
    ("Doodh", "litre", "dairy"), ("Dahi", "kg", "dairy"), ("Paneer", "kg", "dairy"), ("Ghee", "kg", "dairy"),
    ("Haldi Powder", "packet", "masala"), ("Mirch Powder", "packet", "masala"), ("Jeera", "packet", "masala"),

    # -------- BISCUITS (snacks) --------
    ("Parle-G", "packet", "snacks"),
    ("Parle Krackjack", "packet", "snacks"),
    ("Parle Monaco", "packet", "snacks"),
    ("Parle Hide & Seek", "packet", "snacks"),
    ("Parle 20-20", "packet", "snacks"),
    ("Parle Milk Shakti", "packet", "snacks"),
    ("Britannia Good Day", "packet", "snacks"),
    ("Britannia Marie Gold", "packet", "snacks"),
    ("Britannia Bourbon", "packet", "snacks"),
    ("Britannia Milk Bikis", "packet", "snacks"),
    ("Britannia Nutrichoice", "packet", "snacks"),
    ("Britannia Tiger", "packet", "snacks"),
    ("Britannia 50-50", "packet", "snacks"),
    ("Britannia Little Hearts", "packet", "snacks"),
    ("Sunfeast Dark Fantasy", "packet", "snacks"),
    ("Sunfeast Marie Light", "packet", "snacks"),
    ("Sunfeast Bounce", "packet", "snacks"),
    ("Sunfeast Snacky", "packet", "snacks"),
    ("Oreo", "packet", "snacks"),
    ("Oreo Cream", "packet", "snacks"),
    ("Cadbury Bournvita Biscuits", "packet", "snacks"),
    ("Cadbury Oreo Chocolate", "packet", "snacks"),
    ("McVitie's Digestive", "packet", "snacks"),
    ("McVitie's Marie", "packet", "snacks"),
    ("Priyagold Nice Time", "packet", "snacks"),
    ("Priyagold Butter Bite", "packet", "snacks"),
    ("Anmol Nice", "packet", "snacks"),
    ("Anmol Jim Jam", "packet", "snacks"),
    ("Horlicks Biscuits", "packet", "snacks"),
    ("Unibic Cashew Cookies", "packet", "snacks"),
    ("Unibic Choco Chip Cookies", "packet", "snacks"),
    ("Patanjali Doodh Biscuit", "packet", "snacks"),
    ("Cream Cracker", "packet", "snacks"),
    ("Coconut Biscuit", "packet", "snacks"),
    ("Elaichi Biscuit", "packet", "snacks"),
    ("Rusk (Toast)", "packet", "snacks"),

    ("Namkeen", "packet", "snacks"), ("Chips", "packet", "snacks"),
    ("Coffee", "packet", "beverages"), ("Cold Drink", "bottle", "beverages"),
    ("Nahane Ka Sabun", "piece", "personal_care"), ("Shampoo", "bottle", "personal_care"),
    ("Toothpaste", "piece", "personal_care"),
    ("Detergent Powder", "kg", "household"), ("Jhadu", "piece", "household"), ("Phenyl", "bottle", "household"),
    ("Paracetamol", "strip", "medicine"), ("Bandage", "packet", "medicine"),
    ("Copy", "piece", "stationery"), ("Pen", "piece", "stationery"),
    ("Baby Diaper", "packet", "baby_care"),
]


def run():
    db = SessionLocal()
    try:
        # existing items ko category + image do
        items = db.query(Item).all()
        for item in items:
            name_lower = item.name.lower()
            for keyword, cat in KEYWORD_CATEGORY.items():
                if keyword in name_lower:
                    item.category = cat
                    break
            else:
                item.category = item.category or "grocery"
            item.image_url = CATEGORY_IMAGES.get(item.category, CATEGORY_IMAGES["grocery"])

        # naye items add karo (jo already nahi hain)
        existing_names = {i.name.lower() for i in items}
        for name, unit, cat in NEW_ITEMS:
            if name.lower() not in existing_names:
                db.add(Item(
                    name=name, unit=unit, category=cat,
                    image_url=CATEGORY_IMAGES.get(cat, CATEGORY_IMAGES["grocery"])
                ))

        db.commit()
        print("Done! Categories aur images assign ho gaye.")
    finally:
        db.close()


if __name__ == "__main__":
    run()