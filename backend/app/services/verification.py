"""
Pickup verification - do tareeke:
1. QR code scan (customer ke phone par QR dikhta hai, dukandar scan karta hai)
2. 4-digit code (jab customer ke paas phone/internet na ho)
"""
import random
import uuid


def generate_verification_code() -> str:
    """4 digit ka code, jaise '4821'."""
    return f"{random.randint(0, 9999):04d}"


def generate_qr_token() -> str:
    return str(uuid.uuid4())
