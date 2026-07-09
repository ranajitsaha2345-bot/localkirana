"""
Razorpay integration.

Setup steps (yeh tumhe khud karna hoga):
1. https://dashboard.razorpay.com par account banao (business KYC lagega
   live payments ke liye; test mode turant mil jaata hai).
2. Settings -> API Keys se Key Id aur Key Secret copy karo.
3. .env file mein RAZORPAY_KEY_ID aur RAZORPAY_KEY_SECRET daalo.
4. Test mode mein tum bina real paise ke poora flow test kar sakte ho.
"""
import os
import hmac
import hashlib
import razorpay

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

_client = None
if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    _client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


def is_configured() -> bool:
    return _client is not None


def create_razorpay_order(amount_rupees: float, receipt: str) -> dict:
    """Razorpay order banata hai. Amount paise mein bhejna padta hai (rupee x 100)."""
    if not _client:
        raise RuntimeError(
            "Razorpay configure nahi hai. .env mein RAZORPAY_KEY_ID/SECRET daalo."
        )
    amount_paise = int(round(amount_rupees * 100))
    order = _client.order.create(
        {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "payment_capture": 1,
        }
    )
    return order


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """
    Razorpay checkout se payment hone ke baad frontend se signature aati hai.
    Isse verify karna zaroori hai warna koi fake 'payment success' bhej sakta hai.
    """
    if not RAZORPAY_KEY_SECRET:
        return False
    body = f"{order_id}|{payment_id}"
    expected_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)
