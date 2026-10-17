import os

BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
BASE_URL = os.environ["BASE_URL"].rstrip("/")  # e.g. https://yourbot.onrender.com
PORT = int(os.getenv("PORT", "8080"))
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/telegram")

# Payment gateway (apni API ke hisaab se gateway.py adapt karna)
GATEWAY_URL = os.getenv("GATEWAY_URL", "")
GATEWAY_KEY = os.getenv("GATEWAY_KEY", "")
GATEWAY_SECRET = os.getenv("GATEWAY_SECRET", "")
AUTO_PAYOUT = os.getenv("AUTO_PAYOUT", "0") == "1"  # 1 = admin approve par gateway se auto UPI payout

# Economy
COIN_PER_INR = 100          # 100 coin = Rs 1
JOIN_REWARD = 100           # joiner ko per channel join
AD_COST = 110               # advertiser ko per member (10 coin = platform fee)
MIN_TASK_MEMBERS = 10
MAX_TASK_MEMBERS = 100000
MIN_DEPOSIT_COINS = 10000   # = Rs 100
MIN_WITHDRAW_COINS = 1000   # = Rs 10
WITHDRAW_TAX_PERCENT = 10   # withdraw par tax (coins me kat-ta hai)
HOLD_HOURS = 24
PREMIUM_PRICE = 49          # Rs
PREMIUM_DAYS = 30

# Bot Work (referral / bot task)
BW_MIN_REWARD = 220         # poster kam se kam itna coin per user de sakta hai
BW_MIN_USERS = 1
BW_MAX_USERS = 10000
BW_REVIEW_HOURS = 48        # poster is time tak review na kare to case admin ke paas chala jata hai
BW_REPORT_HOURS = 48        # reject ke baad itne ghante tak worker report kar sakta hai
