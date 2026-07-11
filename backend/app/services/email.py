import os
import random
import resend

resend.api_key = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL")  # jaise: "LocalKirana <otp@yourdomain.com>"


def generate_otp() -> str:
    return str(random.randint(100000, 999999))


def send_otp_email(to_email: str, otp: str, name: str = ""):
    subject = "LocalKirana - Password Reset OTP"
    body = f"""Namaste {name},

Aapka LocalKirana password reset OTP hai: {otp}

Yeh OTP agle 10 minute tak valid hai. Kisi ke saath share mat karna.

Agar aapne yeh request nahi ki, to is email ko ignore kar sakte hain.

- LocalKirana Team
"""
    resend.Emails.send({
        "from": FROM_EMAIL,
        "to": to_email,
        "subject": subject,
        "text": body,
    })