import os

BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
BASE_URL = os.environ["BASE_URL"].rstrip("/")  # e.g. https://yourbot.onrender.com
PORT = int(os.getenv("PORT", "8080"))
APP_NAME = os.getenv("APP_NAME", "Profitix")      # loading banner / welcome me dikhta hai
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "15"))
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "4"))
BACKUP_BOT_TOKEN = os.getenv("BACKUP_BOT_TOKEN", "")  # optional: daily data backup is bot se admin ko jata hai
LEDGER_KEEP = 10            # har user ki transaction history me itni hi entries rakhte hain
SUPPORT_KEEP_HOURS = 24     # support text/photo/voice itne ghante baad delete
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/telegram")

# Payment gateway (apni API ke hisaab se gateway.py adapt karna)
GATEWAY_URL = os.getenv("GATEWAY_URL", "https://elitepay.co.in/api/public/v1").rstrip("/")
GATEWAY_KEY = os.getenv("GATEWAY_KEY", "")
GATEWAY_SECRET = os.getenv("GATEWAY_SECRET", "")
AUTO_PAYOUT = os.getenv("AUTO_PAYOUT", "0") == "1"  # 1 = withdraw gateway se automatic UPI payout
AUTO_PAYOUT_MAX_INR = float(os.getenv("AUTO_PAYOUT_MAX_INR", "500"))  # isse bada withdraw admin approval me jata hai
AUTO_PAYOUT_DAILY = int(os.getenv("AUTO_PAYOUT_DAILY", "2"))          # ek user ke 24h me max auto payouts

# Economy
COIN_PER_INR = 100          # 100 coin = Rs 1
JOIN_REWARD = 50            # joiner ko per channel join
AD_COST = 110               # advertiser ko per member (10 coin = platform fee)
REFER_REWARD = 100          # refer complete (dost ka pehla withdraw paid) par referrer ko
MIN_TASK_MEMBERS = 10
MAX_TASK_MEMBERS = 100000
MIN_DEPOSIT_COINS = 2000    # = Rs 20
MIN_WITHDRAW_COINS = 1500   # = Rs 15 (tax ke baad Rs 13.50; Elite payout min Rs 10)
WITHDRAW_TAX_PERCENT = 10   # withdraw par tax (coins me kat-ta hai)
HOLD_HOURS = 24
REJOIN_PERCENT = 50         # channel leave ke baad rejoin par (sirf ek baar) itna % reward wapas, 24h hold me
MAX_DEVICE_CHANGES = 3     # device badalne par re-verify kitni baar allowed
PREMIUM_PRICE = 49          # Rs
PREMIUM_DAYS = 30

# Bot Work (referral / bot task)
BW_MIN_REWARD = 220         # poster kam se kam itna coin per user de sakta hai
BW_MIN_USERS = 1
BW_MAX_USERS = 10000
BW_REVIEW_HOURS = 48        # poster is time tak review na kare to case admin ke paas chala jata hai
BW_REPORT_HOURS = 48        # reject ke baad itne ghante tak worker report kar sakta hai

STRICT_FP = os.getenv("STRICT_FP", "1") == "1"  # 1 = same fingerprint + same IP wala dusra account verify nahi hoga
MIN_TASKS_FOR_WITHDRAW = int(os.getenv("MIN_TASKS_FOR_WITHDRAW", "2"))  # withdraw se pehle itne task complete hone chahiye (channel join / bot work)
MIN_TASKS_FOR_REFER = int(os.getenv("MIN_TASKS_FOR_REFER", "2"))  # dost itne task kare tab referrer ko reward
ORDER_EXPIRY_MIN = int(os.getenv("ORDER_EXPIRY_MIN", "30"))  # itne minute baad unpaid deposit/premium order history me Failed dikhta hai
