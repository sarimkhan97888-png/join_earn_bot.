import os


def _int(name, default):
    """Env khali / galat ho to default (Render me khali value daal dene par crash na ho)."""
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return int(default)


BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
BASE_URL = os.environ["BASE_URL"].rstrip("/")  # e.g. https://yourbot.onrender.com
PORT = _int("PORT", 8080)
APP_NAME = os.getenv("APP_NAME", "Profitix")      # loading banner / welcome me dikhta hai
DB_POOL_MAX = _int("DB_POOL_MAX", 15)
DB_POOL_MIN = _int("DB_POOL_MIN", 4)
BACKUP_BOT_TOKEN = os.getenv("BACKUP_BOT_TOKEN", "")  # optional: daily data backup is bot se admin ko jata hai
PAYOUT_CHANNEL_ID = os.getenv("PAYOUT_CHANNEL_ID", "@PROFITIXPAYOUT").strip()      # public payout proof channel (-100... ya @username); khali = band
PAYOUT_CHANNEL_LINK = os.getenv("PAYOUT_CHANNEL_LINK", "https://t.me/PROFITIXPAYOUT").strip()  # https://t.me/... app me floating button
ADMIN_FEED = _int("ADMIN_FEED", 1)  # 1 = main bot par har event ki khabar admins ko
LEDGER_KEEP = 10            # har user ki transaction history me itni hi entries rakhte hain
SUPPORT_KEEP_HOURS = 24     # support text/photo/voice itne ghante baad delete
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
# Support agents: sirf Support inbox + support notifications + Premium Level 3 perks (withdraw/deposit/admin panel nahi)
SUPPORT_IDS = [int(x) for x in os.getenv("SUPPORT_IDS", "").split(",") if x.strip().lstrip("-").isdigit() and int(x) not in ADMIN_IDS]
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/telegram")

# Deposit: FamPay UPI + Gmail IMAP se mail padhke auto-confirm (fam.py)
FAM_UPI_ID = os.getenv("FAM_UPI_ID", "").strip()
PAYEE_NAME = os.getenv("PAYEE_NAME", os.getenv("APP_NAME", "Profitix"))
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER", "").strip()
IMAP_PASS = os.getenv("IMAP_PASS", "").replace(" ", "")  # Gmail App Password (sirf Render env me)
IMAP_FOLDERS = [x.strip() for x in os.getenv("IMAP_FOLDERS", "[Gmail]/All Mail|[Gmail]/Spam").split("|") if x.strip()]  # spam bhi padhte hain
ALLOWED_SENDER_DOMAINS = [d.strip().lower() for d in os.getenv("ALLOWED_SENDER_DOMAINS", "famapp.in,fampay.in").split(",") if d.strip()]
REQUIRE_DKIM = os.getenv("REQUIRE_DKIM", "1") == "1"
FAM_POLL_SECONDS = _int("FAM_POLL_SECONDS", 8)
FAM_TTL = _int("FAM_TTL", 180)   # order itne second valid (3 min)
FAM_GRACE = 60              # expiry ke baad bhi itni der mail chalegi (mail delay)
MAX_PENDING_FAM = 2         # ek user ke khule orders
MAX_FAM_ORDERS_PER_HOUR = 8
MAX_CLAIMS_PER_HOUR = 5

# Economy
COIN_PER_INR = 100          # 100 coin = Rs 1
JOIN_REWARD = 50            # joiner ko per channel join
AD_COST = 60                # advertiser ka MINIMUM per-member price (isse zyada kuch bhi rakh sakta hai)
TASK_FEE = 10               # har join par platform fee: joiner ko price - TASK_FEE milta hai
REFER_REWARD = 100          # refer complete (dost ka pehla withdraw paid) par referrer ko
MIN_TASK_MEMBERS = 10
MAX_TASK_MEMBERS = 100000
MIN_DEPOSIT_COINS = 2000    # = Rs 20
MAX_DEPOSIT_COINS = 200000  # = Rs 2000
MIN_WITHDRAW_COINS = 1500   # = Rs 15 (tax ke baad Rs 13.50)
WITHDRAW_TAX_PERCENT = 10   # withdraw par tax (coins me kat-ta hai)
HOLD_HOURS = 24
WD_LOCK_HOURS = 24           # channel-join se kamaye coins itne ghante baad withdraw hote hain
RECHECK_DAYS = 7
REJOIN_PERCENT = 50         # channel leave ke baad rejoin par (sirf ek baar) itna % reward wapas, 24h hold me
MAX_DEVICE_CHANGES = 3     # device badalne par re-verify kitni baar allowed
# Premium levels. None = unlimited. fee None = normal WITHDRAW_TAX_PERCENT. wd_hours = pending withdraw itne ghante me admin ne
# na kiya to expire+refund (kam = tez). tasks = roz kitne task (channel+group+bot work milake) bana sakte hain. ref = refer reward.
PLANS = {
    1: dict(members=50, price=19, days=7, tasks=2, wd=2, fee=None, wd_hours=24, ref=100, top=False),
    2: dict(members=100, price=39, days=15, tasks=5, wd=5, fee=None, wd_hours=12, ref=100, top=False),
    3: dict(members=None, price=69, days=30, tasks=None, wd=None, fee=0, wd_hours=5, ref=200, top=True),
}
TOP_LEVEL = 3               # is level ke users ke task list me sabse upar dikhte hain

# Bot Work (referral / bot task)
BW_MIN_REWARD = 220         # poster kam se kam itna coin per user de sakta hai
BW_MIN_USERS = 1
BW_MAX_USERS = 10000
BW_REVIEW_HOURS = 48        # poster is time tak review na kare to case admin ke paas chala jata hai
BW_REPORT_HOURS = 48        # reject ke baad itne ghante tak worker report kar sakta hai

STRICT_FP = os.getenv("STRICT_FP", "1") == "1"  # 1 = same fingerprint + same IP wala dusra account verify nahi hoga
MIN_TASKS_FOR_WITHDRAW = _int("MIN_TASKS_FOR_WITHDRAW", 2)  # withdraw se pehle itne task complete hone chahiye (channel join / bot work)
MIN_TASKS_FOR_REFER = _int("MIN_TASKS_FOR_REFER", 2)  # dost itne task kare tab referrer ko reward
ORDER_EXPIRY_MIN = _int("ORDER_EXPIRY_MIN", 4)  # itne minute baad unpaid deposit/premium order history me Failed dikhta hai
WITHDRAW_EXPIRE_HOURS = _int("WITHDRAW_EXPIRE_HOURS", 48)  # pending withdraw itne ghante me approve na ho to expire + refund
BW_MAX_ATTEMPTS = _int("BW_MAX_ATTEMPTS", 2)  # bot work me ek worker ke kitne try (reject ke baad retry), uske baad lock

# Google Play redeem code withdraw: ₹10 ke multiple (unlimited), tax upar se
GPLAY_STEP_INR = _int("GPLAY_STEP_INR", 10)

# Free user roz itne channel task bana sakta hai (Bot Work Premium Level 1+ se)
FREE_TASKS_DAILY = _int("FREE_TASKS_DAILY", 2)
FREE_TASK_MEMBERS = _int("FREE_TASK_MEMBERS", 10)   # free user ek task me max itne members

# Force join: app kholne se pehle ye channel join hona zaroori (bot is channel ka ADMIN ho). "off" likho to band.
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "@ProfitEarningOfficial").strip()
if FORCE_CHANNEL.lower() in ("off", "none", "0", "false"):
    FORCE_CHANNEL = ""
FORCE_LINK = os.getenv("FORCE_LINK", "https://t.me/ProfitEarningOfficial").strip()

# Daily streak: roz kam se kam 1 task => Day N par N*STREAK_STEP coins, STREAK_DAYS ke baad reset
STREAK_STEP = _int("STREAK_STEP", 10)
STREAK_DAYS = _int("STREAK_DAYS", 7)

# ---- USDT (BEP20): seedha tumhare wallet me. Bot blockchain scan karke amount match se auto credit karta hai ----
from decimal import Decimal as _D
USDT_WALLET = os.getenv("USDT_WALLET", "").strip()                 # tumhara Trust Wallet BEP20 (0x...) address
USDT_ON = len(USDT_WALLET) == 42 and USDT_WALLET.startswith("0x")
USDT_INR_RATE = _D(os.getenv("USDT_INR_RATE", "90") or "90")      # 1 USDT = kitne rupaye
USDT_FEE_PCT = _D(os.getenv("USDT_FEE_PCT", "0.5") or "0.5")      # deposit/premium par extra %
USDT_MIN = _D(os.getenv("USDT_MIN", "0.10") or "0.10")
USDT_MAX = _D(os.getenv("USDT_MAX", "10000") or "10000")
USDT_CONTRACT = os.getenv("USDT_CONTRACT", "0x55d398326f99059fF775485246999027B3197955").strip()  # BSC-USD (USDT BEP20)
USDT_RPCS = [x.strip() for x in os.getenv("USDT_RPCS", "https://bsc-dataseed.binance.org,https://bsc-dataseed1.defibit.io,"
                                          "https://bsc-dataseed1.ninicoin.io,https://bsc-rpc.publicnode.com").split(",") if x.strip()]
USDT_CONFIRMS = _int("USDT_CONFIRMS", 3)                           # itne blocks baad payment final maano
USDT_TTL = _int("USDT_TTL", 180)                                   # order ka payment time (sec) = 3 min

# Refer milestone bonus: itne completed refers par itne extra coins (ad balance me, sirf task ke liye)
REF_BONUSES = {10: 300, 20: 500, 30: 800, 40: 1100, 50: 1500}

# Amazon voucher withdraw: ₹10 ke multiple (unlimited), tax upar se
AMAZON_STEP_INR = _int("AMAZON_STEP_INR", 10)


# /send ka default promo message (bina text ke /send likhne par yahi jata hai)
PROMO_TEXT = """╔═══════ ⟡ 💎 ⟡ ═══════╗
🚀 𓆩♡𓆪 ɴᴇᴡ ᴛᴀsᴋ & ᴇᴀʀɴ ʙᴏᴛ 𓆩♡𓆪 🚀
╚═══════ ⟡ 💎 ⟡ ═══════╝

🤖 𓆩♡𓆪 ʙᴏᴛ: @Sarimproifitix_bot
                       @Sarimproifitix_bot

💸 ᴄʀᴇᴀᴛᴇ ᴛᴀsᴋs & ᴇᴀʀɴ
🎯 ᴄᴏᴍᴘʟᴇᴛᴇ ᴛᴀsᴋs • ɢᴇᴛ ʀᴇᴡᴀʀᴅs

👥 ɢᴇᴛ ғʀᴇᴇ ᴛᴇʟᴇɢʀᴀᴍ ᴍᴇᴍʙᴇʀs
🎁 ɪɴᴠɪᴛᴇ ғʀɪᴇɴᴅs & ᴇᴀʀɴ ʀᴇғᴇʀʀᴀʟ ʀᴇᴡᴀʀᴅs

💰 ɪɴsᴛᴀɴᴛ ᴡɪᴛʜᴅʀᴀᴡᴀʟs
💳 ᴜᴘɪ | ᴜsᴅᴛ | ʀᴇᴅᴇᴇᴍ ᴄᴏᴅᴇ
🎁 ᴀᴍᴀᴢᴏɴ ᴠᴏᴜᴄʜᴇʀs

💵 ᴍɪɴɪᴍᴜᴍ ᴡɪᴛʜᴅʀᴀᴡᴀʟ: ₹𝟏5

━━━━━━━━━━━━━━━━━━
🔥 ᴄʀᴇᴀᴛᴇ • ᴄᴏᴍᴘʟᴇᴛᴇ • ᴇᴀʀɴ 🔥
━━━━━━━━━━━━━━━━━━"""


# ---- AI Support (Profile -> AI Support). Key sirf Render env me. Khali = option app me dikhta hi nahi ----
AI_API_KEY = (os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or "").strip()   # purana tareeka: ek ya kai key comma (,) se
import re as _re
_numbered = sorted((k for k in os.environ if _re.fullmatch(r"AI_API_KEY_\d+", k)), key=lambda k: int(k.rsplit("_", 1)[1]))   # AI_API_KEY_1, AI_API_KEY_2 ...
AI_KEYS = []
for _v in [AI_API_KEY] + [os.environ[k] for k in _numbered]:
    for _k in _v.replace("\n", ",").split(","):
        if _k.strip() and _k.strip() not in AI_KEYS:
            AI_KEYS.append(_k.strip())
AI_API_KEY = AI_KEYS[0] if AI_KEYS else ""
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic").strip().lower()   # "anthropic" ya "openai" (OpenAI-compatible: OpenAI/Groq/Gemini...)
AI_MODEL = os.getenv("AI_MODEL", "").strip() or ("claude-haiku-5-5" if AI_PROVIDER == "anthropic" else "gpt-4o-mini")
AI_BASE_URL = os.getenv("AI_BASE_URL", "").strip().rstrip("/") or ("https://api.anthropic.com" if AI_PROVIDER == "anthropic" else "https://api.openai.com/v1")
AI_KEEP_MINUTES = _int("AI_KEEP_MINUTES", 60)       # AI chat itne minute baad delete
AI_HOURLY_LIMIT = _int("AI_HOURLY_LIMIT", 20)       # ek user ke itne sawal per AI_KEEP_MINUTES window
AI_MAX_CHARS = 500                                  # ek sawal max itne akshar

def _prizes(name, default):
    import os
    try:
        v = [int(x) for x in os.getenv(name, default).split(",") if x.strip()]
    except ValueError:
        v = [int(x) for x in default.split(",")]
    return (v + [0, 0, 0])[:3]


LB_PRIZES = {"refer": _prizes("LB_REFER_PRIZES", "1000,600,300"), "coin": _prizes("LB_COIN_PRIZES", "600,400,200")}


# ---- Ads (Monetag) ----
ADS_REWARD = int(os.getenv("ADS_REWARD", "5"))   # coins per ad
ADS_DAILY = int(os.getenv("ADS_DAILY", "10"))    # ek user roz max ads

# ---- Monetag (rewarded interstitial, video) ----
MT_ZONE = os.getenv("MONETAG_ZONE", "12150359")
MT_SECRET = os.getenv("MONETAG_SECRET", "")           # postback URL ka secret (?secret=...). Khali = Monetag band
MT_ON = bool(MT_SECRET)
MT_REWARD = int(os.getenv("MONETAG_REWARD", str(ADS_REWARD)))


def ads_any():
    return MT_ON
