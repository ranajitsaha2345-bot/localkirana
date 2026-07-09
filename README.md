# LocalKirana — Hyperlocal Kirana Order + Pickup App

Ye poora system 3 hisso mein hai:
```
localkirana/
├── backend/        FastAPI server - saara business logic yaha hai
└── frontend/       customer.html + shopkeeper.html - do web apps
```

---

## 1. Backend chalao (Cursor ke terminal mein)

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# .env file kholo aur RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET daalo (neeche steps hain)

uvicorn app.main:app --reload --port 8000
```
Ab `http://localhost:8000/docs` khol ke poora API interactive dekh sakte ho (Swagger UI, FastAPI automatic banata hai).

---

## 2. Razorpay setup (real online payment ke liye)

1. https://dashboard.razorpay.com par signup karo.
2. Shuru mein **Test Mode** use karo (bina bank verification ke turant kaam karta hai, fake card numbers se test payment ho jaata hai).
3. Settings → API Keys → "Generate Test Key" → Key Id + Key Secret milega.
4. `.env` file mein daalo:
   ```
   RAZORPAY_KEY_ID=rzp_test_xxxxxxxx
   RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxx
   ```
5. Jab app live karna ho: business documents (PAN, bank account, GST agar hai) submit karke **Live Mode** activate karo. Live keys `rzp_live_...` se shuru hongi — bas `.env` mein replace kar dena, code mein kuch nahi badalna padega.
6. Test card ke liye Razorpay ki test-card list use karo: https://razorpay.com/docs/payments/payments/test-card-upi-details/

---

## 3. Google Maps setup

1. https://console.cloud.google.com par project banao.
2. **Maps Embed API** enable karo (billing account lagega, lekin Google $200/month free credit deta hai jo chhoti app ke liye kaafi hai).
3. Credentials → API Key banao.
4. `frontend/customer.html` mein `YOUR_GOOGLE_MAPS_API_KEY` ko apni real key se replace karo (Ctrl+F se dhoond lo).
5. Security ke liye: Google Console mein us key ko apni domain tak restrict kar dena (HTTP referrer restriction).

---

## 4. Frontend chalao

Sabse simple tareeka - koi build step nahi chahiye, seedhe browser mein file kholo:

```bash
cd frontend
python3 -m http.server 5500
```
Phir browser mein kholo:
- Customer app: `http://localhost:5500/customer.html`
- Shopkeeper app: `http://localhost:5500/shopkeeper.html`

`customer.html` aur `shopkeeper.html` dono ke top mein `const API = "http://localhost:8000";` line hai — jab backend ko real server par deploy karoge, yaha uska URL daal dena.

---

## 5. Poora flow test karne ka tareeka

1. **Shopkeeper app** khol ke ek dukan signup karo (location automatic browser se lega, allow kar dena).
2. Inventory tab mein items ke price set karo (jaise Dal ₹120, Chini ₹45).
3. Do-teen alag phone number se 2-3 dukane bana lo taaki price-comparison test ho sake.
4. **Customer app** khol ke doosra account banao, items select karo, "Sabse Sasti Dukan Dhoondo" dabao.
5. "Done" dabao → dukandar ke app mein turant order aa jaayega (WebSocket se real-time).
6. Dukandar item ✓ ya ✕ karega.
7. Customer payment karega (Razorpay test mode mein fake card se).
8. Dukandar "Ready" dabayega.
9. Customer ko QR + 4-digit code dikhega. Dukandar "Pickup Verify" tab se scan ya code se confirm karega.
10. Dono taraf confirmation aa jaayega.

---

## 6. Mobile app (PWA) — abhi turant kaise "app jaisa" banaye

`manifest.json` already add kiya hai. Android/iPhone Chrome mein site kholo → browser menu mein **"Add to Home Screen"** milega → app ka icon home screen par aa jaayega, full-screen chalega, bilkul native app jaisa lagega. Iske liye Play Store approval ki zaroorat nahi.

**Agla step jab business scale kare:** isi backend API ko reuse karke **React Native** mein native Android/iOS app banwana — us waqt bata dena, main uska code bhi bana dunga. Abhi PWA fastest aur sabse sasta rasta hai real users tak pahunchne ka.

---

## 7. Production deployment (jab real users ke liye live karna ho)

| Hissa | Suggestion |
|---|---|
| Backend | Railway.app ya Render.com (free tier available, `git push` se deploy) |
| Database | Neon.tech ya Supabase (free PostgreSQL) — `.env` mein `DATABASE_URL` badal dena |
| Frontend | Netlify ya Vercel (free, `frontend/` folder seedhe drag-drop kar sakte ho) |
| Domain | Namecheap/GoDaddy se `.in` domain (~₹500/year) |

Yeh sab free-tier se shuru ho sakta hai, paisa tabhi lagega jab users badhenge.

---

## 8. Abhi jo baaki hai (agle steps)

- [ ] Shopkeeper ke "not available" hone par customer khud se alternate dukan select kar sake, uska ek chhota UI (backend endpoint already ready hai: item availability update response mein `alternatives` list aati hai)
- [ ] Order history page (dono taraf)
- [ ] SMS notification jab customer ke paas app na khula ho (Twilio/MSG91 se)
- [ ] Admin panel dukano ko verify/approve karne ke liye
- [ ] Rating/review system

Bata dena in mein se kaunsa pehle chahiye, main bana dunga.
