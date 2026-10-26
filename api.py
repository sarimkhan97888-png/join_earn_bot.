"""JSON API for the Telegram Mini App."""
import asyncio
import base64
import hashlib
import hmac
import html
import io
import json
import logging
import re
import time
import types
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal
from urllib.parse import parse_qsl, quote

import qrcode
from aiohttp import web
from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M, LabeledPrice, WebAppInfo
from telegram.error import TelegramError

import adminops
import botwork
import config
import db
import extras
import i18n
import fam
import payouts
import util

log = logging.getLogger("api")
routes = web.RouteTableDef()

URL_RE = re.compile(r"^https?://\S{4,300}$")
UPI_RE = re.compile(r"^[a-zA-Z0-9.\-_]{2,}@[a-zA-Z]{2,}$")
HEX64 = re.compile(r"^[a-f0-9]{64}$")
_bg = set()  # background tasks ke references (garbage collect na ho)


# ---------------- helpers ----------------
def check_init_data(init_data: str):
    """Telegram WebApp initData validate karo; user dict return karta hai."""
    data = dict(parse_qsl(init_data or "", keep_blank_values=True))
    h = data.pop("hash", None)
    if not h:
        return None
    s = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(secret, s.encode(), hashlib.sha256).hexdigest(), h):
        return None
    try:
        age = time.time() - int(data.get("auth_date", "0"))
        if age > 6 * 3600 or age < -300:  # 6h se purana (replay) ya future date reject
            return None
        return json.loads(data["user"])
    except Exception:
        return None


def ok(**kw):
    if "msg" in kw:
        kw["msg"] = i18n.tr(kw["msg"])
    return web.json_response({"ok": True, **kw})


def err(msg):
    return web.json_response({"ok": False, "msg": i18n.tr(msg)})


def iso(dt):
    return dt.isoformat() if dt else None


def to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError, OverflowError):
        return default


async def body(request):
    try:
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def pub(u):
    return {"id": u["id"], "balance": u["balance"], "hold": u["hold"], "total_earned": u["total_earned"],
            "ad_balance": u["ad_balance"], "premium": util.is_prem(u), "premium_until": iso(u["premium_until"]),
            "level": util.level(u), "real_level": util.real_level(u),
            "gmail": u["gmail"], "upi": u["upi"], "device_ok": u["device_ok"],
            "device_state": u.get("device_state", "ok"), "admin": u["id"] in config.ADMIN_IDS, "support": u["id"] in config.SUPPORT_IDS, "debt": u.get("debt", 0), "notify": bool(u.get("notify", True)),
            "lang": u.get("lang") or "en", "lang_set": bool(u.get("lang"))}


def plans_json():
    return [{"level": k, "price": p["price"], "days": p["days"], "tasks": p["tasks"], "wd": p["wd"],
             "fee": config.WITHDRAW_TAX_PERCENT if p["fee"] is None else p["fee"], "wd_hours": p["wd_hours"],
             "ref": p["ref"], "top": p["top"], "members": p.get("members")} for k, p in sorted(config.PLANS.items())]


def cfg(request):
    return {"coin_per_inr": config.COIN_PER_INR, "join_reward": config.JOIN_REWARD, "ad_cost": config.AD_COST, "task_fee": config.TASK_FEE, "max_members": (None if request["u"]["id"] in config.ADMIN_IDS else util.plan(request["u"])["members"]),
            "min_task_members": config.MIN_TASK_MEMBERS, "max_task_members": config.MAX_TASK_MEMBERS,
            "min_deposit": config.MIN_DEPOSIT_COINS, "min_withdraw": config.MIN_WITHDRAW_COINS, "gplay_step": config.GPLAY_STEP_INR * config.COIN_PER_INR, "amazon_step": config.AMAZON_STEP_INR * config.COIN_PER_INR,
            "hold_hours": config.HOLD_HOURS, "plans": plans_json(),
            "bw_min_reward": config.BW_MIN_REWARD,
            "bw_min_users": config.BW_MIN_USERS, "bw_max_users": config.BW_MAX_USERS,
            "support_url": config.SUPPORT_URL, "bot_username": request.app["bot"].username,
            "withdraw_tax": util.plan(request["u"])["fee"], "wd_hours": util.plan(request["u"])["wd_hours"],
            "wd_daily": None if request["u"]["id"] in config.ADMIN_IDS else util.plan(request["u"])["wd"],
            "tasks_daily": None if request["u"]["id"] in config.ADMIN_IDS else util.plan(request["u"])["tasks"],
            "free_wd_hours": config.WITHDRAW_EXPIRE_HOURS, "free_wd": 1, "free_tasks": config.FREE_TASKS_DAILY, "free_members": config.FREE_TASK_MEMBERS, "payout_link": config.PAYOUT_CHANNEL_LINK, "app_name": config.APP_NAME,
            "refer_reward": util.plan(request["u"])["ref"], "min_tasks": config.MIN_TASKS_FOR_WITHDRAW, "min_ref_tasks": config.MIN_TASKS_FOR_REFER, "order_expiry_min": config.ORDER_EXPIRY_MIN,
            "upi_id": config.FAM_UPI_ID, "max_deposit": config.MAX_DEPOSIT_COINS, "fam_ttl": config.FAM_TTL,
            "usdt_on": config.USDT_ON, "usdt_rate": float(config.USDT_INR_RATE), "usdt_fee": float(config.USDT_FEE_PCT),
            "usdt_min": float(config.USDT_MIN), "usdt_max": float(config.USDT_MAX)}


# ---------------- auth + rate limit + device check ----------------
_rl = {}
_rl_gc = [0.0]
# Device verify ke bina sirf ye endpoints chalte hain (baaki sab server par block)
OPEN_PATHS = {"/api/me", "/api/lang", "/api/verify", "/api/support", "/api/support/send", "/api/support/photo", "/api/wallet",
              "/api/order", "/api/tasks"}
_cd = {}
_giftfail = {}


def cooldown(uid, key, secs):
    """Spam roko: ek user ek action ko `secs` se pehle dobara nahi kar sakta."""
    t = time.monotonic()
    k = (uid, key)
    if t - _cd.get(k, 0) < secs:
        return False
    _cd[k] = t
    if len(_cd) > 30000:  # purane entries memory se hatao
        for kk in [kk for kk, v in _cd.items() if t - v > 120]:
            _cd.pop(kk, None)
    return True


def gift_locked(uid):
    t = time.time()
    L = [x for x in _giftfail.get(uid, []) if t - x < 3600]
    _giftfail[uid] = L
    if len(_giftfail) > 20000:
        for k in [k for k, v in _giftfail.items() if not v or t - v[-1] > 3600]:
            _giftfail.pop(k, None)
    return len(L) >= 5


def too_fast():
    return err("Thoda ruko, bahut tez kar rahe ho.")


def rate_ok(uid):
    t = time.monotonic()
    L = _rl.setdefault(uid, [])
    while L and t - L[0] > 10:
        L.pop(0)
    L.append(t)
    if t - _rl_gc[0] > 120:  # purane users memory se hatao (1 lakh users par leak na ho)
        _rl_gc[0] = t
        for k in [k for k, v in _rl.items() if not v or t - v[-1] > 10]:
            _rl.pop(k, None)
    return len(L) <= 30


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


async def with_device(u, dev, fp):
    """Har request par device dobara check: stored device se match nahi hua to device_ok=False (bypass nahi)."""
    u = dict(u)
    u["device_db"] = bool(u["device_ok"])
    u["device_state"] = "none"
    if u.get("dev_bypass"):  # admin ne is user ko device check se chhoot di hai
        u["device_ok"] = True
        u["device_state"] = "ok"
        return u
    if not u["device_ok"]:
        # Unverified user: agar ye device kisi AUR Telegram account se bandha hai to block ("other")
        if u["id"] not in config.ADMIN_IDS and HEX64.match(dev):
            owner = await db.device_owner(sha(dev))
            if owner and owner != u["id"]:
                u["device_state"] = "other"
                await db.flag_suspect(u["id"])
        return u
    good = False
    if u["id"] in config.ADMIN_IDS:
        good = True
    elif HEX64.match(dev) and sha(dev) == u["device_hash"]:
        good = True
    elif u["dev_ver"] == 1 and HEX64.match(dev) and HEX64.match(fp) and fp == u["fp"]:
        # purani (sirf fingerprint wali) verification: chupchap naye device token par migrate
        good = await db.rebind_device(u["id"], sha(dev), fp, counted=False)
    u["device_ok"] = good
    u["device_state"] = "ok" if good else "changed"
    if not good:  # same TG id, alag device: block + suspect flag
        await db.flag_suspect(u["id"])
    return u


_fj = {}          # uid -> (member?, time)
_fj_warn = [-1e9]
FORCE_OPEN = {"/api/me", "/api/verify", "/api/lang", "/api/force/check", "/api/streak/seen"}


async def force_ok(bot, uid, fresh=False):
    """True = force-join channel ka member (ya check band/ho nahi paya: tab user ko rokte nahi). Member 2 min cache, non-member 4 sec."""
    if not config.FORCE_CHANNEL or uid in config.ADMIN_IDS:
        return True
    t = time.monotonic()
    v = _fj.get(uid)
    if not fresh and v and t - v[1] < (120 if v[0] else 4):
        return v[0]
    st = await util.member_status(bot, config.FORCE_CHANNEL, uid)
    if st is None:  # bot channel me admin nahi / Telegram error: user ko mat roko, admin ko batao
        if t - _fj_warn[0] > 3600:
            _fj_warn[0] = t
            extras.feed("🚨 Force-join check nahi ho pa raha: bot ko " + html.escape(config.FORCE_CHANNEL) + " me <b>Admin</b> banao. Tab tak sabko andar jaane de raha hu.")
        return True
    if len(_fj) > 100000:
        _fj.clear()
    _fj[uid] = (st, t)
    return st


@web.middleware
async def auth_mw(request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)
    user = check_init_data(request.headers.get("X-Init-Data", ""))
    if not user:
        return web.json_response({"ok": False, "msg": "Session invalid. Bot se app dobara kholo."}, status=401)
    if not rate_ok(user["id"]):
        return web.json_response({"ok": False, "msg": "Bahut tez! Thoda ruko."}, status=429)
    try:
        u = await db.ensure_user(types.SimpleNamespace(
            id=user["id"], username=user.get("username"), first_name=user.get("first_name")))
        i18n.remember(u["id"], u.get("lang"))
        i18n.cur.set(u.get("lang") or "en")
        if u["banned"]:
            return web.json_response({"ok": False, "msg": i18n.tr("🚫 Account banned.")}, status=403)
        u = await with_device(u, request.headers.get("X-Device", ""), request.headers.get("X-Fp", ""))
        if not u["device_ok"] and u["id"] not in config.ADMIN_IDS and request.path not in OPEN_PATHS:
            return web.json_response({"ok": False, "code": "need_verify",
                                      "msg": i18n.tr("🔐 Pehle device verify karo.")})
        need_join = not await force_ok(request.app["bot"], u["id"])
        if need_join and request.path not in FORCE_OPEN:
            return web.json_response({"ok": False, "code": "need_join", "link": config.FORCE_LINK,
                                      "msg": i18n.tr("📢 Pehle hamara channel join karo.")})
        u["need_join"] = need_join
        request["u"] = u
        request["tg"] = user
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception:
        log.exception("api error %s", request.path)
        return err("⚠️ Server error. Thodi der baad try karo.")


def client_ip(request):
    xf = request.headers.get("X-Forwarded-For", "")
    return (xf.split(",")[0].strip() if xf else (request.remote or ""))[:64]


@routes.get("/api/news")
async def api_news(request):
    rows = await db.news_list()
    await db.news_mark_seen(request["u"]["id"])
    return ok(items=[{"id": r["id"], "text": r["text"], "photo": r["has_photo"], "at": iso(r["created_at"])} for r in rows])


_news_img = {}


@routes.get("/news/photo/{nid}")
async def news_photo(request):
    """Broadcast ki photo (Telegram se laake cache). Public: announcement sabke liye hai."""
    nid = to_int(request.match_info["nid"])
    data = _news_img.get(nid)
    if data is None:
        fid = await db.news_photo(nid)
        if not fid:
            raise web.HTTPNotFound()
        try:
            f = await request.app["bot"].get_file(fid)
            data = bytes(await f.download_as_bytearray())
        except TelegramError:
            raise web.HTTPNotFound()
        if len(_news_img) > 30:
            _news_img.clear()
        _news_img[nid] = data
    return web.Response(body=data, content_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@routes.post("/api/streak/seen")
async def api_streak_seen(request):
    await db.streak_seen(request["u"]["id"])
    return ok()


@routes.post("/api/force/check")
async def api_force_check(request):
    u = request["u"]
    if not cooldown(u["id"], "force", 2):
        return too_fast()
    if await force_ok(request.app["bot"], u["id"], fresh=True):
        return ok(joined=True, msg="✅ Verify ho gaya! Welcome.")
    return err("❌ Abhi channel join nahi dikha. Join karke thodi der baad Verify dabao.")


# ---------------- me / home ----------------
@routes.get("/api/me")
async def api_me(request):
    u = request["u"]
    left, led, tdone, wdone, queued = await asyncio.gather(
        db.left_chats(u["id"]), db.recent_ledger(u["id"]), db.created_today(u["id"]), db.wd_today(u["id"]), db.prem_queued(u["id"]))
    blocked = [{"chat_id": r["chat_id"], "title": r["title"], "link": r["link"]} for r in left]
    hist = [{"kind": r["kind"], "amount": r["amount"], "at": iso(r["created_at"])} for r in led]
    me = pub(u)
    me["streak"] = await db.streak_info(u["id"])
    me["news_unread"] = int(await db.news_unread(u["id"]) or 0)
    me.update(need_join=bool(u.get("need_join")), join_link=config.FORCE_LINK)
    me.update(tasks_today=tdone, wd_today=wdone, queued=[{"level": r["level"], "days": r["days"]} for r in queued])
    return ok(me=me, blocked=blocked, history=hist, cfg=cfg(request))


# ---------------- channel tasks (worker) ----------------
@routes.get("/api/tasks")
async def api_tasks(request):
    uid = request["u"]["id"]
    ot, bo, bm = await asyncio.gather(db.open_tasks(uid), db.bw_open(uid), db.bw_mine(uid))
    ch = [{"id": t["id"], "title": t["title"], "link": t["link"], "reward": t["reward"]} for t in ot]
    bw = [{"id": b["id"], "title": b["title"], "link": b["link"], "reward": b["reward"],
           "instructions": b["instructions"], "needs_dev": b["needs_dev"],
           "retry": b["my_attempts"] > 0, "my_reason": b["my_reason"]} for b in bo]
    mine = [{"id": r["id"], "status": r["status"], "title": r["title"], "reward": r["reward"],
             "reason": r["reject_reason"], "locked": r["status"] == "rejected" and r["attempt"] >= config.BW_MAX_ATTEMPTS}
            for r in bm]
    return ok(channels=ch, botworks=bw, mine=mine)


@routes.post("/api/task/check")
async def api_check(request):
    u = request["u"]
    uid = u["id"]
    bot = request.app["bot"]
    tid = to_int((await body(request)).get("id"))
    if not u["device_ok"]:
        return err("🔐 Pehle Profile me device verify karo.")
    if not cooldown(uid, "check", 1.5):
        return too_fast()
    if await db.is_blocked(uid):
        return err("🚫 Tum blocked ho. Pehle left channel rejoin karo.")
    t = await db.get_task(tid)
    if not t or t["status"] != "active":
        return err("Ye task ab available nahi.")
    st = await util.member_status(bot, t["chat_id"], uid)
    if st is None:
        return err("⚠️ Verify nahi ho paya. Thodi der baad try karo.")
    if not st:
        return err("❌ Pehle channel join karo, phir Check dabao.")
    if not await db.joined_after(t["chat_id"], uid, t["created_at"]):
        return err("❌ Join record nahi mila. Channel leave karke dobara join karo, phir Check dabao.")
    res = await db.claim(tid, uid)
    if res == "ok":
        extras.feed(f"✅ Task #{tid} join verified — {extras.uname(request['u'])}")
        st = db.pop_streak(uid)
        return ok(msg=f"Join verified! +{t['reward']} coins ({config.HOLD_HOURS}h hold me)",
                  streak=({"day": st[0], "reward": st[1]} if st else None))
    return err({"dup": "Ye task tum pehle kar chuke ho.", "own": "Apne channel se coin nahi mil sakta.",
                "closed": "Task full ho gaya."}[res])


@routes.post("/api/rejoin")
async def api_rejoin(request):
    uid = request["u"]["id"]
    bot = request.app["bot"]
    got = 0
    for r in await db.left_chats(uid):
        if await util.member_status(bot, r["chat_id"], uid):
            got += await db.unblock(r["chat_id"], uid) or 0
    if await db.left_chats(uid):
        return err("❌ Abhi bhi kuch channels join nahi kiye.")
    if got:
        return ok(msg=f"Unblocked! Ab tasks kar sakte ho. {got} coins ({config.REJOIN_PERCENT}%) {config.HOLD_HOURS}h hold me mile.")
    return ok(msg="Unblocked! Ab tasks kar sakte ho.")


# ---------------- wallet ----------------
@routes.get("/api/wallet")
async def api_wallet(request):
    uid = request["u"]["id"]
    oh, wh = await asyncio.gather(db.order_history(uid), db.wd_history(uid))
    orders = [{"id": r["order_id"], "kind": r["kind"], "coins": r["coins"], "amount": r["amount_inr"],
               "status": r["status"], "at": iso(r["created_at"])} for r in oh]
    wds = [{"id": r["id"], "coins": r["coins"], "amount": float(r["amount_inr"]), "fee": r["fee_coins"], "upi": r["upi"],
            "status": r["status"], "gp": db.is_code(r["upi"]), "amz": r["upi"] == db.AMAZON, "code": r["code"] if db.is_code(r["upi"]) else None,
            "usdt": float(r["usdt"]) if r["method"] == "usdt" else None, "tx": r["tx"],
            "at": iso(r["created_at"])} for r in wh]
    return ok(orders=orders, withdrawals=wds)


def make_qr(text):
    bio = io.BytesIO()
    qrcode.make(text).save(bio, "PNG")
    return "data:image/png;base64," + base64.b64encode(bio.getvalue()).decode()


async def make_order(request, kind, coins, amount, level=None, mode=None):
    """Fam order: base amount + 1..99 paise (unique). User ye exact amount Fam UPI par bhejta hai."""
    u = request["u"]
    uid = u["id"]
    if not config.FAM_UPI_ID:
        return err("❌ Payment abhi available nahi. Baad me try karo.")
    if not cooldown(uid, "order", 5):
        return too_fast()
    pend, hour = await db.fam_order_counts(uid)
    if pend >= config.MAX_PENDING_FAM:
        return err("Pehle wale payment order ko pura karo ya 12 minute ruko, phir naya banao.")
    if hour >= config.MAX_FAM_ORDERS_PER_HOUR:
        return err("Bahut saare orders. Thodi der baad try karo.")
    order_id = f"{kind[0].upper()}{uid}{int(time.time() * 1000)}"
    pay = await db.fam_new_order(order_id, uid, kind, coins, amount * 100, level, mode)
    if not pay:
        return err("Abhi bahut log payment kar rahe hain. 1 minute baad try karo.")
    extras.feed(f"🧾 {('Premium L%s' % level) if kind == 'premium' else 'Deposit'} order bana ₹{pay / 100:.2f} — {extras.uname(u)}")
    amt = f"{pay // 100}.{pay % 100:02d}"
    link = f"upi://pay?pa={quote(config.FAM_UPI_ID)}&pn={quote(config.PAYEE_NAME)}&am={amt}&cu=INR&tn={quote(order_id[-8:])}"
    return ok(order_id=order_id, amount=amount, pay_amount=amt, coins=coins, upi_id=config.FAM_UPI_ID,
              pay_url=link, qr=make_qr(link), expires_in=config.FAM_TTL)


def _usdt_ceil(inr):
    return (Decimal(inr) / config.USDT_INR_RATE).quantize(Decimal("0.01"), ROUND_CEILING)


def _usdt_total(u):
    """User jo USDT chunta hai usme fee % add (4 decimal tak upar round)."""
    return (u * (1 + config.USDT_FEE_PCT / 100)).quantize(Decimal("0.0001"), ROUND_CEILING)


@routes.post("/api/usdt/order")
async def api_usdt_order(request):
    """USDT BEP20 payment: deposit (ad balance coins) ya premium. Address + exact amount deta hai."""
    u = request["u"]
    uid = u["id"]
    if not config.USDT_ON:
        return err("❌ USDT payment abhi available nahi. Baad me try karo.")
    d = await body(request)
    kind = "premium" if d.get("kind") == "premium" else "deposit"
    level = mode = None
    if kind == "premium":
        level, mode, e = prem_args(u, d)
        if e:
            return err(e)
        inr = config.PLANS[level]["price"]
        usdt = _usdt_ceil(inr)
        coins = 0
    else:
        try:
            usdt = Decimal(str(d.get("usdt") or "0")).quantize(Decimal("0.01"), ROUND_DOWN)
        except Exception:
            usdt = Decimal(0)
        if not (config.USDT_MIN <= usdt <= config.USDT_MAX):
            return err(f"Amount {config.USDT_MIN} se {config.USDT_MAX} USDT ke beech daalo.")
        coins = int(usdt * config.USDT_INR_RATE * config.COIN_PER_INR)
        inr = coins // config.COIN_PER_INR
    if not cooldown(uid, "order", 5):
        return too_fast()
    pend, hour = await db.usdt_order_counts(uid)
    if pend >= 3:
        return err("Pehle wale USDT orders pure karo ya thodi der ruko, phir naya banao.")
    if hour >= 10:
        return err("Bahut saare orders. Thodi der baad try karo.")
    base = _usdt_total(usdt).quantize(Decimal("0.01"), ROUND_CEILING)   # fee ke saath, 2 decimal; upar random 0.0001-0.0099 judta hai
    order_id = f"U{uid}{int(time.time() * 1000)}"
    pay = await db.usdt_order_new(order_id, uid, kind, coins, inr, level, mode, usdt, base, config.USDT_WALLET)
    if not pay:
        return err("Abhi bahut log payment kar rahe hain. 1 minute baad try karo.")
    extras.feed(f"💵 USDT {('Premium L%s' % level) if kind == 'premium' else 'Deposit'} order {pay} USDT — {extras.uname(u)}")
    return ok(order_id=order_id, usdt=float(usdt), coins=coins, pay_amount=format(pay, "f"), address=config.USDT_WALLET,
              qr=make_qr(f"ethereum:{config.USDT_CONTRACT}@56/transfer?address={config.USDT_WALLET}&uint256={int(pay * 10 ** 18)}"),
              expires_in=config.USDT_TTL, network="BEP20")


@routes.post("/api/deposit/claim")
async def api_deposit_claim(request):
    """'Paise bheje par credit nahi hua': Fam app wala transaction id + amount."""
    u = request["u"]
    d = await body(request)
    txn = re.sub(r"[^A-Za-z0-9]", "", str(d.get("txn") or "")).upper()
    try:
        paise = int(Decimal(str(d.get("amount") or "0").replace(",", "")) * 100)
    except Exception:
        paise = 0
    if not (8 <= len(txn) <= 40):
        return err("Transaction ID sahi daalo (Fam app me payment detail me hota hai).")
    if not (config.MIN_DEPOSIT_COINS <= paise <= config.MAX_DEPOSIT_COINS):
        return err(f"Amount ₹{config.MIN_DEPOSIT_COINS // 100} se ₹{config.MAX_DEPOSIT_COINS // 100} ke beech daalo.")
    if not cooldown(u["id"], "claim", 10):
        return too_fast()
    st, extra = await db.fam_claim(u["id"], txn, paise)
    if st == "credited":
        return ok(msg=f"✅ Payment mil gayi! +{paise} coins ad balance me add ho gaye.", credited=True)
    if st == "pending":
        extras.feed(f"🧾 Deposit claim #{extra} ₹{paise / 100:.2f} — {extras.uname(u)}")
        try:
            await fam.claim_alert(extra, u["id"], txn, paise)
        except Exception:
            log.exception("claim alert failed")
        return ok(msg="Claim bhej diya. Admin check karke credit kar dega. Mail aate hi apne aap bhi ho jayega.")
    if st == "dup":
        return err("Is transaction ka claim pehle se pending hai.")
    if st == "limit":
        return err("Bahut claims. Thodi der baad try karo.")
    return err("Ye transaction pehle hi use ho chuka hai ya amount match nahi karta.")


@routes.post("/api/deposit")
async def api_deposit(request):
    coins = to_int((await body(request)).get("coins"))
    if coins < config.MIN_DEPOSIT_COINS or coins % config.COIN_PER_INR or coins > config.MAX_DEPOSIT_COINS:
        return err(f"Min {config.MIN_DEPOSIT_COINS} aur max {config.MAX_DEPOSIT_COINS} coins, 100 ke multiple me daalo.")
    return await make_order(request, "deposit", coins, coins // config.COIN_PER_INR)


def prem_args(u, d):
    """(level, mode, error). Active premium ke dauran alag level: mode 'now' (turant) ya 'later' (purana khatam hone ke baad)."""
    lvl = to_int(d.get("level"))
    if lvl not in config.PLANS:
        return None, None, "Sahi premium level chuno."
    cur = util.real_level(u)
    mode = d.get("mode")
    if cur and lvl != cur:
        if lvl < cur:
            mode = "later"  # chhota level turant lagana bekar hai: purana khatam hone ke baad
        elif mode not in ("now", "later"):
            return None, None, "Turant active karna hai ya purana premium khatam hone ke baad? Chuno."
    else:
        mode = "now"
    return lvl, mode, None


@routes.post("/api/premium/buy")
async def api_premium_buy(request):
    lvl, mode, e = prem_args(request["u"], await body(request))
    if e:
        return err(e)
    return await make_order(request, "premium", 0, config.PLANS[lvl]["price"], lvl, mode)


@routes.post("/api/premium/stars")
async def api_premium_stars(request):
    """Telegram Stars se premium: jitne rupaye utne Stars. Invoice link banake deta hai; payment bot handler pakadta hai."""
    u = request["u"]
    lvl, mode, e = prem_args(u, await body(request))
    if e:
        return err(e)
    if not cooldown(u["id"], "order", 5):
        return too_fast()
    p = config.PLANS[lvl]
    await db.order_supersede_stars(u["id"])
    order_id = f"T{u['id']}{int(time.time() * 1000)}"
    try:
        link = await request.app["bot"].create_invoice_link(
            title=f"{config.APP_NAME} Premium Level {lvl}", description=i18n.tr(f"{p['days']} din ka Premium Level {lvl}", i18n.cur.get()),
            payload=order_id, provider_token="", currency="XTR", prices=[LabeledPrice(f"Level {lvl} · {p['days']} din", p["price"])])
    except TelegramError:
        log.exception("create_invoice_link failed")
        return err("❌ Stars payment abhi available nahi. Baad me try karo.")
    await db.new_order(order_id, u["id"], "premium", 0, p["price"], None, lvl, mode, "stars")
    extras.feed(f"🧾 Premium L{lvl} Stars invoice ({p['price']} ⭐) — {extras.uname(u)}")
    return ok(link=link, order_id=order_id)


@routes.post("/api/lang")
async def api_lang(request):
    lang = str((await body(request)).get("lang"))
    if lang not in i18n.LANGS:
        return err("Galat bhasha.")
    await db.set_lang(request["u"]["id"], lang)
    i18n.remember(request["u"]["id"], lang)
    i18n.cur.set(lang)
    return ok(lang=lang, msg="✅ Bhasha badal gayi.")


@routes.get("/api/order")
async def api_order(request):
    row = await db.order_row(request.query.get("id", ""))
    if not row or row["user_id"] != request["u"]["id"]:
        return ok(status="none")
    return ok(status=row["status"])


@routes.post("/api/withdraw")
async def api_withdraw(request):
    u = request["u"]
    uid = u["id"]
    bd = await body(request)
    coins = to_int(bd.get("coins"))
    gplay = bd.get("method") == "gplay"
    amazon = bd.get("method") == "amazon"
    usdt_wd = bd.get("method") == "usdt"
    addr = str(bd.get("addr") or "").strip()
    if not u["device_ok"]:
        return err("🔐 Withdraw ke liye pehle device verify karo.")
    if not cooldown(uid, "wd", 8):
        return too_fast()
    if await db.is_blocked(uid):
        return err("🚫 Tum blocked ho. Pehle left channel rejoin karo.")
    if usdt_wd:
        if not config.USDT_ON:
            return err("❌ USDT withdraw abhi available nahi.")
        if not re.fullmatch(r"0x[a-fA-F0-9]{40}", addr):
            return err("BEP20 (BSC) wallet address sahi daalo: 0x se shuru, 42 characters.")
    elif not u["upi"]:
        return err("Pehle Profile me apna UPI ID set karo.")
    if u.get("debt", 0) > 0:
        return err(f"⚠️ Tumne pehle channel leave kiya tha, {u['debt']} coins ka hisaab baaki hai. "
                   f"Agle channel rewards se ye kat-ta rahega; poora kat-ne ke baad withdraw khulega.")
    pl = util.plan(u)
    is_admin_u = uid in config.ADMIN_IDS
    if not is_admin_u and pl["wd"] is not None and await db.wd_today(uid) >= pl["wd"]:
        if pl["level"] < max(config.PLANS):
            return err(f"⚠️ Aaj ke {pl['wd']} withdraw ho chuke. Level upgrade karo ya kal (12 baje ke baad) dobara karo.")
        return err(f"⚠️ Aaj ke {pl['wd']} withdraw ho chuke. Kal (12 baje ke baad) dobara karo.")
    if uid not in config.ADMIN_IDS and config.MIN_TASKS_FOR_WITHDRAW > 0:
        done = await db.tasks_done(uid)
        if done < config.MIN_TASKS_FOR_WITHDRAW:
            return err(f"⚠️ Withdraw ke liye kam se kam {config.MIN_TASKS_FOR_WITHDRAW} task complete karo "
                       f"(channel join ya bot work). Abhi complete: {done}.")
    step = config.GPLAY_STEP_INR * config.COIN_PER_INR
    if amazon:
        astep = config.AMAZON_STEP_INR * config.COIN_PER_INR
        if coins < astep or coins % astep:
            return err(f"Amazon voucher ₹{config.AMAZON_STEP_INR} ke multiple me hota hai ({astep} coins ke multiple me daalo, jaise {astep}, {astep * 2}, {astep * 5}).")
    elif gplay:
        if coins < step or coins % step:
            return err(f"Google Play code ₹{config.GPLAY_STEP_INR} ke multiple me hota hai ({step} coins ke multiple me daalo, jaise {step}, {step * 2}, {step * 5}).")
    elif coins < config.MIN_WITHDRAW_COINS or coins % config.COIN_PER_INR:
        return err(f"Min {config.MIN_WITHDRAW_COINS} coins aur 100 ke multiple me daalo.")
    pct = pl["fee"]
    need = coins + db.wd_fee(coins, pct)
    if need > u["balance"]:
        mx = u["balance"] * 100 // (100 + pct) // 100 * 100
        return err(f"{coins} coins + {db.wd_fee(coins, pct)} tax = {need} coins chahiye, balance {u['balance']}. "
                   f"Max withdraw: {mx} coins.")
    usdt_amt = (Decimal(coins) / config.COIN_PER_INR / config.USDT_INR_RATE).quantize(Decimal("0.0001"), ROUND_DOWN) if usdt_wd else None
    r = await db.request_withdraw(uid, coins, pct, pl["level"] if not is_admin_u else 0, pl["wd_hours"],
                                  None if is_admin_u else pl["wd"], gplay=gplay, amazon=amazon, addr=addr if usdt_wd else None, usdt=usdt_amt)
    if r == "limit":
        return err(f"⚠️ Aaj ke {pl['wd']} withdraw ho chuke. Kal dobara karo.")
    if not r:
        return err("❌ Withdraw nahi ho paya. Balance aur verification check karo.")
    wid, upi, fee, net = r
    t = asyncio.create_task(_after_withdraw(request.app["bot"], u, wid, coins, fee, net, upi, pl["level"] if not is_admin_u else 0, usdt_amt))
    _bg.add(t)
    t.add_done_callback(_bg.discard)
    if usdt_wd:
        return ok(msg=f"USDT withdraw request #{wid} bhej di gayi. {usdt_amt} USDT (BEP20) → {addr[:8]}…{addr[-6:]} (balance se {coins} + {fee} tax = {coins + fee} coins kate). "
                      f"Admin bhejega to Transaction ID (TxID) bot me aayegi aur Wallet me bhi dikhegi. {pl['wd_hours']} ghante me process na hua to coins apne aap wapas aa jayenge.")
    if amazon:
        return ok(msg=f"Amazon voucher request #{wid} bhej di gayi. ₹{net:.2f} ka voucher (balance se {coins} + {fee} tax = {coins + fee} coins kate). "
                      f"Admin voucher code bhejega to wo bot me aayega aur Wallet → Gift Codes me bhi dikhega. {pl['wd_hours']} ghante me process na hua to coins apne aap wapas aa jayenge.")
    if gplay:
        return ok(msg=f"Google Play code request #{wid} bhej di gayi. ₹{net:.2f} ka code (balance se {coins} + {fee} tax = {coins + fee} coins kate). "
                      f"Admin code bhejega to wo bot me aayega aur Wallet → Gift Codes me bhi dikhega. {pl['wd_hours']} ghante me process na hua to coins apne aap wapas aa jayenge.")
    return ok(msg=f"Withdraw request #{wid} bhej di gayi. ₹{net:.2f} → {upi} (balance se {coins} + {fee} tax = {coins + fee} coins kate). "
                  f"Admin approve karega to paisa aa jayega. {pl['wd_hours']} ghante me process na hua to coins apne aap wapas aa jayenge.")


async def _after_withdraw(bot, u, wid, coins, fee, net, upi, lvl=0, usdt=None):
    try:
        extras.feed(f"💸 <b>Withdraw request</b> [{util.tag(lvl)}] #{wid}: " + (f"{usdt} USDT" if usdt else f"₹{net:.2f}") + f" → <code>{html.escape(upi)}</code>, {coins + fee} coins kate "
                    f"— {extras.uname(u)}")
        why = ""
        if u["suspect"]:
            why += "\n⚠️ <b>Suspect:</b> iska device fingerprint kisi aur account se match karta hai. Pehle check karo."
        await payouts.alert(bot, f"💸 <b>{util.tag(lvl)}</b> · Withdraw #{wid}\nUser: <code>{u['id']}</code>\n₹{net:.2f} payable "
                                 f"(user se {coins + fee} coins kate = {coins} + {fee} tax)\n"
                                 + (f"💵 <b>USDT (BEP20) bhejna hai: {usdt} USDT</b>\nAddress: <code>{html.escape(upi)}</code>\nBhejne ke baad: <code>/txid {wid} TXHASH</code> ya Admin Panel > Withdraws" if usdt
                                    else f"🛒 <b>Amazon voucher code bhejna hai</b>\n<code>/gpcode {wid} CODE</code> ya Admin Panel > Withdraws" if upi == db.AMAZON
                                    else f"🎁 <b>Google Play redeem code bhejna hai</b>\n<code>/gpcode {wid} CODE</code> ya Admin Panel > Withdraws" if upi == db.GPLAY
                                    else f"UPI: <code>{html.escape(upi)}</code>") + why,
                            payouts.admin_kb(wid, db.is_code(upi) or bool(usdt)), wid=wid)
    except Exception:
        log.exception("after_withdraw failed for #%s", wid)


# ---------------- admin panel (sirf ADMIN_IDS) ----------------
def adm_only(request):
    return request["u"]["id"] in config.ADMIN_IDS


def _u_row(r):
    return {"id": r["id"], "name": r["first_name"] or "", "username": r["username"] or "", "balance": r["balance"],
            "ad": r["ad_balance"], "banned": r["banned"], "level": int(r["premium_level"] or 0) if (r["premium_until"] and r["premium_until"].timestamp() > time.time()) else 0,
            "verified": r["device_ok"], "at": iso(r["created_at"])}


def _wd_row(w):
    return {"id": w["id"], "user": w["user_id"], "coins": w["coins"], "fee": w["fee_coins"], "inr": float(w["amount_inr"]),
            "upi": w["upi"], "gp": db.is_code(w["upi"]), "amz": w["upi"] == db.AMAZON, "usdt": float(w["usdt"]) if w["method"] == "usdt" else None, "status": w["status"], "level": int(w.get("level") or 0), "at": iso(w["created_at"])}


@routes.get("/api/admin/stats")
async def api_adm_stats(request):
    if not adm_only(request):
        return err("Not allowed")
    return ok(stats=await db.adm_stats())


@routes.get("/api/admin/users")
async def api_adm_users(request):
    if not adm_only(request):
        return err("Not allowed")
    return ok(users=[_u_row(r) for r in await db.adm_users(request.query.get("q", ""))])


@routes.get("/api/admin/user")
async def api_adm_user(request):
    if not adm_only(request):
        return err("Not allowed")
    d = await db.adm_user(to_int(request.query.get("id")))
    if not d:
        return err("User nahi mila.")
    out = _u_row(d)
    out.update(upi=d["upi"] or "", gmail=d["gmail"] or "", hold=d["hold"], earned=d["total_earned"], debt=d["debt"],
               suspect=d["suspect"], bypass=d["dev_bypass"], tasks_done=d["tasks_done"], refs=d["refs"],
               until=iso(d["premium_until"]),
               wds=[{"id": w["id"], "coins": w["coins"], "inr": float(w["amount_inr"]), "status": w["status"], "at": iso(w["created_at"])} for w in d["wds"]],
               ledger=[{"kind": l["kind"], "amount": l["amount"], "at": iso(l["created_at"])} for l in d["ledger"]])
    return ok(user=out)


@routes.post("/api/admin/user/act")
async def api_adm_user_act(request):
    if not adm_only(request):
        return err("Not allowed")
    d = await body(request)
    good, msg = await adminops.user_act(request.app["bot"], to_int(d.get("id")), str(d.get("act")), to_int(d.get("amount")))
    return ok(msg=msg) if good else err(msg)


@routes.get("/api/admin/withdraws")
async def api_adm_wd(request):
    if not adm_only(request):
        return err("Not allowed")
    pend, rec = await db.adm_wd_list()
    return ok(pending=[_wd_row(w) for w in pend], recent=[_wd_row(w) for w in rec])


@routes.post("/api/admin/withdraw/act")
async def api_adm_wd_act(request):
    if not adm_only(request):
        return err("Not allowed")
    d = await body(request)
    act = str(d.get("act"))
    if act not in ("ok", "no", "paid", "refund"):
        return err("Galat action")
    good, msg = await adminops.wd_act(request.app["bot"], to_int(d.get("id")), act, str(d.get("code") or ""))
    return ok(msg=msg) if good else err(msg)


@routes.get("/api/admin/deposits")
async def api_adm_dep(request):
    if not adm_only(request):
        return err("Not allowed")
    claims, unm = await db.fam_review()
    return ok(claims=[{"id": c["id"], "user": c["user_id"], "txn": c["txn_id"], "inr": c["amount_paise"] / 100, "at": iso(c["created_at"])} for c in claims],
              unmatched=[{"txn": p["txn_id"], "inr": p["pay_paise"] / 100, "sender": p["sender"], "at": iso(p["created_at"])} for p in unm])


@routes.post("/api/admin/deposit/act")
async def api_adm_dep_act(request):
    if not adm_only(request):
        return err("Not allowed")
    d = await body(request)
    k, bot = str(d.get("kind")), request.app["bot"]
    if k in ("claim_ok", "claim_no"):
        good, msg = await adminops.claim_act(bot, to_int(d.get("id")), k == "claim_ok")
    elif k == "ignore":
        good, msg = await adminops.ignore_pay(str(d.get("txn") or "").upper())
    elif k == "assign":
        good, msg = await adminops.assign(bot, str(d.get("txn") or "").upper(), to_int(d.get("uid")))
    else:
        return err("Galat action")
    return ok(msg=msg) if good else err(msg)


@routes.get("/api/admin/tasks")
async def api_adm_tasks(request):
    if not adm_only(request):
        return err("Not allowed")
    ch, bw = await db.adm_tasks()
    return ok(channels=[{"id": t["id"], "owner": t["owner_id"], "name": t["username"] or "", "title": t["title"], "target": t["target"], "done": t["joined"]} for t in ch],
              botworks=[{"id": t["id"], "owner": t["owner_id"], "name": t["username"] or "", "title": t["title"], "target": t["target"], "reward": t["reward"]} for t in bw])


@routes.post("/api/admin/task/cancel")
async def api_adm_task_cancel(request):
    if not adm_only(request):
        return err("Not allowed")
    d = await body(request)
    kind = "bw" if d.get("kind") == "bw" else "ch"
    refund = await db.adm_cancel(kind, to_int(d.get("id")))
    if refund is None:
        return err("Ye task cancel nahi ho sakta.")
    extras.feed(f"🛑 Admin ne {'bot work' if kind == 'bw' else 'task'} #{d.get('id')} cancel kiya (refund {refund} coins)")
    return ok(msg=f"Cancel hua. Owner ko {refund} coins refund.")


# ---------------- support (user <-> admin, sab Mini App ke andar) ----------------
def is_admin(request):
    return request["u"]["id"] in config.ADMIN_IDS


def is_support(request):
    """Support inbox: admin ya support agent."""
    return request["u"]["id"] in config.ADMIN_IDS or request["u"]["id"] in config.SUPPORT_IDS


def sniff_mime(b):
    if b[:4] == b"\x1a\x45\xdf\xa3":
        return "audio/webm"
    if b[:4] == b"OggS":
        return "audio/ogg"
    if b[4:8] == b"ftyp":
        return "audio/mp4"
    return "image/png" if b[:4] == b"\x89PNG" else "image/webp" if b[:4] == b"RIFF" else "image/jpeg"


def _voice_ok(b):
    """Voice note: webm (Chrome/Android), ogg, mp4/m4a (iOS) ka asli header check."""
    return b[:4] == b"\x1a\x45\xdf\xa3" or b[:4] == b"OggS" or b[4:8] == b"ftyp"


async def read_text_photo(request):
    """JSON {text,...} ya multipart (text, photo, voice, uid). Return (fields, photo|None, voice|None) ya (None, error, None)."""
    fields, photo, voice = {}, None, None
    if (request.content_type or "").startswith("multipart/"):
        try:
            reader = await request.multipart()
            async for part in reader:
                if part.name in ("photo", "voice"):
                    lim = 1_500_000 if part.name == "photo" else 900_000
                    buf = bytearray()
                    while True:
                        chunk = await part.read_chunk(65536)
                        if not chunk:
                            break
                        buf += chunk
                        if len(buf) > lim:
                            return None, ("Photo 1.5MB se chhoti bhejo." if part.name == "photo" else "Voice bahut lambi hai (max 60 sec)."), None
                    if part.name == "photo":
                        photo = bytes(buf)
                    else:
                        voice = bytes(buf)
                else:
                    fields[part.name] = ((await part.read_chunk(4096)) or b"").decode("utf-8", "ignore")[:1100]  # sirf pehla 4KB, bada part memory na khaye
        except Exception:
            return None, "Upload fail hua. Dobara try karo.", None
    else:
        fields = await body(request)
    if photo is not None and (not photo or not _img_ok(photo)):
        return None, "Sirf photo (JPG/PNG/WEBP) bhej sakte ho.", None
    if voice is not None and (len(voice) < 200 or not _voice_ok(voice)):
        return None, "Voice sahi record nahi hui. Dobara try karo.", None
    if photo is not None and voice is not None:
        return None, "Ek message me photo ya voice, dono nahi.", None
    return fields, photo, voice


def msg_json(rows):
    return [{"id": r["id"], "from": r["sender"], "text": r["text"], "photo": r["has_photo"], "voice": r["has_voice"], "at": iso(r["created_at"])}
            for r in rows]


@routes.get("/api/support")
async def api_support(request):
    return ok(msgs=msg_json(await db.sup_list(request["u"]["id"])))


@routes.get("/api/support/photo")
async def api_support_photo(request):
    row = await db.sup_file(to_int(request.query.get("id")))
    if not row or (row["user_id"] != request["u"]["id"] and not is_support(request)):
        return web.Response(status=404, text="gone")
    data = bytes(row["data"])
    return web.Response(body=data, content_type=sniff_mime(data), headers={"Cache-Control": "private, max-age=86400"})


@routes.post("/api/support/send")
async def api_support_send(request):
    uid = request["u"]["id"]
    if not cooldown(uid, "sup", 1.5):
        return too_fast()
    fields, photo, voice = await read_text_photo(request)
    if fields is None:
        return err(photo)
    text = str(fields.get("text", "")).strip()[:1000]
    if not text and photo is None and voice is None:
        return err("Message khali hai.")
    if voice is not None and not util.is_prem(request["u"]):
        return err("🎤 Voice message sirf Premium users bhej sakte hain. Text ya photo bhejo.")
    if await db.sup_recent_count(uid) >= 20:
        return err("Bahut zyada messages ho gaye. Thodi der baad likho.")
    if photo is not None or voice is not None:
        if await db.sup_recent_photos(uid) >= 5:
            return err("Ek ghante me 5 photo/voice hi bhej sakte ho.")
        if await db.sup_recent_photos(uid, 24) >= 15:
            return err("Aaj ke liye photo/voice ki limit ho gayi. Kal bhejo ya text likho.")
    await db.sup_add(uid, "user", text, photo, voice)
    # Admin ko sirf ek link-wala notification (message text DM me nahi). Reply Mini App ke andar hota hai.
    if not await db.sup_notif_recent(uid):
        tg = request["tg"]
        name = f"@{tg['username']}" if tg.get("username") else (tg.get("first_name") or str(uid))
        kb = M([[B("💬 Open chat", web_app=WebAppInfo(url=f"{config.BASE_URL}/app?support={uid}"))]])
        for a in dict.fromkeys(list(config.ADMIN_IDS) + list(config.SUPPORT_IDS)):
            try:
                m = await request.app["bot"].send_message(
                    a, f"🎧 <b>Naya support message</b> [{util.tag(util.real_level(request['u']))}]\nFrom: {html.escape(name)} (<code>{uid}</code>)\n"
                       f"Neeche button se chat kholo aur wahin reply do.", parse_mode="HTML", reply_markup=kb)
                await db.sup_notif_add(a, m.message_id, uid)
            except TelegramError:
                log.warning("support notify failed for admin %s", a)
    return ok()


@routes.get("/api/admin/support")
async def api_admin_threads(request):
    if not is_support(request):
        return err("Not allowed")
    rows = await db.sup_threads()
    return ok(threads=[{"uid": r["user_id"], "name": ("@" + r["username"]) if r["username"] else (r["first_name"] or str(r["user_id"])),
                        "last": r["last_text"], "from": r["last_sender"], "at": iso(r["last_at"]), "lvl": r["lvl"]} for r in rows])


@routes.get("/api/admin/support/chat")
async def api_admin_chat(request):
    if not is_support(request):
        return err("Not allowed")
    uid = to_int(request.query.get("uid"))
    u = await db.get_user(uid)
    if not u:
        return err("User nahi mila.")
    name = ("@" + u["username"]) if u["username"] else (u["first_name"] or str(uid))
    return ok(msgs=msg_json(await db.sup_list(uid)), name=name, uid=uid)


@routes.post("/api/admin/support/reply")
async def api_admin_reply(request):
    if not is_support(request):
        return err("Not allowed")
    fields, photo, voice = await read_text_photo(request)
    if fields is None:
        return err(photo)
    uid = to_int(fields.get("uid"))
    text = str(fields.get("text", "")).strip()[:1000]
    if not text and photo is None and voice is None:
        return err("Message khali hai.")
    if not await db.get_user(uid):
        return err("User nahi mila.")
    await db.sup_add(uid, "admin", text, photo, voice)
    bot = request.app["bot"]
    body_txt = html.escape(text) if text else ("🎤 Voice message bheja gaya hai." if voice is not None else "📷 Photo bheji gayi hai.")
    await util.notify(bot, uid, f"🎧 <b>Support reply</b>\n\n{body_txt}\n\nPoori chat: App → Profile → Customer service")
    for r in await db.sup_notif_pop(uid):  # reply ho gaya: admin ke saare notification delete
        try:
            await bot.delete_message(r["admin_id"], r["msg_id"])
        except TelegramError:
            pass
    return ok()


# ---------------- refer ----------------
@routes.get("/api/refer")
async def api_refer(request):
    uid = request["u"]["id"]
    st, lst = await asyncio.gather(db.ref_stats(uid), db.ref_list(uid))
    items = [{"name": (r["first_name"] or "User")[:20], "status": r["status"], "at": iso(r["created_at"])} for r in lst]
    ms = [{"n": n, "bonus": bn, "got": st["done"] >= n} for n, bn in sorted(config.REF_BONUSES.items())]
    return ok(link=f"https://t.me/{request.app['bot'].username}?start=r{uid}", total=st["total"], done=st["done"],
              earned=st["done"] * util.plan(request["u"])["ref"] + sum(m["bonus"] for m in ms if m["got"]),
              reward=util.plan(request["u"])["ref"], items=items, milestones=ms)


# ---------------- profile ----------------
@routes.post("/api/gift")
async def api_gift(request):
    u = request["u"]
    code = str((await body(request)).get("code", "")).strip().upper()
    if not u["device_ok"]:
        return err("🔐 Gift code ke liye pehle device verify karo.")
    if gift_locked(u["id"]):
        return err("Bahut galat attempts. 1 ghante baad try karo.")
    if not cooldown(u["id"], "gift", 3):
        return too_fast()
    if not re.fullmatch(r"[A-Z0-9]{4,20}", code):
        return err("Sahi gift code daalo.")
    res, coins = await db.gift_redeem(u["id"], code)
    if res == "invalid":
        _giftfail.setdefault(u["id"], []).append(time.time())
    if res == "ok":
        extras.feed(f"🎁 Gift code redeem: {coins} coins — {extras.uname(request['u'])}")
        return ok(msg=f"Gift code redeem hua! +{coins} coins balance me add ho gaye.")
    return err({"invalid": "Ye gift code galat hai.", "used_up": "Is gift code ki limit khatam ho gayi.",
                "dup": "Tum ye code pehle use kar chuke ho."}[res])


@routes.post("/api/upi")
async def api_upi(request):
    upi = str((await body(request)).get("upi", "")).strip().lower()
    if not cooldown(request["u"]["id"], "upi", 3):
        return too_fast()
    if not UPI_RE.match(upi):
        return err("UPI ID sahi nahi hai (e.g. name@upi).")
    if not await db.set_upi(request["u"]["id"], upi):
        return err("Ye UPI kisi aur account se linked hai.")
    return ok(msg="UPI save ho gaya.")


@routes.post("/api/verify")
async def api_verify(request):
    u = request["u"]
    d = await body(request)
    fp = str(d.get("fp", ""))
    dev = str(d.get("dev", ""))
    if u["device_ok"]:
        return ok(msg="Already verified")
    if not cooldown(u["id"], "verify", 3):
        return too_fast()
    if not HEX64.match(dev) or not HEX64.match(fp):
        return err("Device check fail hua. App band karke dobara kholo.")
    bot = request.app["bot"]
    if u["device_db"] or u["device_state"] == "other" or await db.set_device(u["id"], sha(dev), fp, client_ip(request)) != "ok":
        # device/ID mismatch ya device kisi aur account ka: block (self-service verify nahi)
        await db.flag_suspect(u["id"])
        await util.notify(bot, u["id"], "🚫 <b>Device verification fail</b>\nYe device kisi aur account se linked hai "
                          "ya tumhara account pehle kisi aur device se verify tha. Account block hai, Customer service se contact karo.")
        return err("🚫 Device verification fail. Account block hai, Customer service se contact karo.")
    await util.notify(bot, u["id"], "✅ <b>Device verify ho gaya!</b>\n\n" + util.WELCOME + "\n\n👇 Ab app kholo",
                      reply_markup=M([[B(i18n.tr("🚀 Open App"), web_app=WebAppInfo(url=f"{config.BASE_URL}/app"))]]))
    return ok(msg="Device verified! Bot par wapas jao aur Open App dabao.")


# ---------------- premium: channel task posting ----------------
def parse_ident(s):
    s = str(s or "").strip()
    m = re.search(r"t\.me/([A-Za-z][A-Za-z0-9_]{3,})", s)
    if m:
        return "@" + m.group(1)
    if s.startswith("@") and len(s) > 4:
        return s
    if re.fullmatch(r"-?\d{5,}", s):
        return int(s)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,}", s):
        return "@" + s
    return None


async def resolve_chat(request, raw, make_link):
    bot = request.app["bot"]
    uid = request["u"]["id"]
    ident = parse_ident(raw)
    if ident is None:
        return "❌ Channel ka @username ya t.me link daalo."
    try:
        chat = await bot.get_chat(ident)
    except TelegramError:
        return "❌ Chat nahi mili. Bot ko pehle us channel/group me Admin banao aur sahi @username do."
    if chat.type not in ("channel", "group", "supergroup"):
        return "❌ Sirf channel ya group allowed hai."
    try:
        me = await bot.get_chat_member(chat.id, bot.id)
    except TelegramError:
        me = None
    if not me or me.status != "administrator":
        return f"❌ Bot is chat me Admin nahi hai. @{bot.username} ko Admin banao (Invite Users permission ke saath)."
    try:
        um = await bot.get_chat_member(chat.id, uid)
    except TelegramError:
        um = None
    if not um or um.status not in ("creator", "administrator"):
        return "❌ Tum is chat ke admin/owner nahi ho."
    if chat.username:
        link = f"https://t.me/{chat.username}"
    elif make_link:
        try:
            link = (await bot.create_chat_invite_link(chat.id)).invite_link
        except TelegramError:
            return "❌ Invite link nahi ban paya. Bot ko 'Invite Users' permission do."
    else:
        link = ""
    return {"chat_id": chat.id, "title": chat.title or str(chat.id), "link": link}


async def task_limit_err(u):
    """Roz ki task limit (channel + group + bot work milake) premium level ke hisaab se. Admin unlimited."""
    if u["id"] in config.ADMIN_IDS:
        return None
    pl = util.plan(u)
    if pl["tasks"] is not None and await db.created_today(u["id"]) >= pl["tasks"]:
        if pl["level"] < max(config.PLANS):
            return f"Aaj ki task limit ({pl['tasks']}) poori ho gayi. Level upgrade karo ya kal dobara banao."
        return f"Aaj ki task limit ({pl['tasks']}) poori ho gayi. Kal dobara banao."
    return None


@routes.post("/api/task/preview")
async def api_task_preview(request):
    r = await resolve_chat(request, (await body(request)).get("chat"), False)
    if isinstance(r, str):
        return err(r)
    return ok(title=r["title"])


@routes.post("/api/task/create")
async def api_task_create(request):
    u = request["u"]
    d = await body(request)
    e = await task_limit_err(u)
    if e:
        return err(e)
    n = to_int(d.get("count"))
    admin = u["id"] in config.ADMIN_IDS  # admin ke liye task free (coins nahi katte)
    cap = config.MAX_TASK_MEMBERS if admin else (util.plan(u)["members"] or config.MAX_TASK_MEMBERS)
    if not (config.MIN_TASK_MEMBERS <= n <= config.MAX_TASK_MEMBERS):
        return err(f"Members {config.MIN_TASK_MEMBERS} se {config.MAX_TASK_MEMBERS} ke beech rakho.")
    if n > cap:
        return err(f"Tumhare level me ek task me max {cap} members. Zyada ke liye Premium upgrade karo.")
    price = to_int(d.get("price")) or config.AD_COST
    if price < config.AD_COST or price > 100000:
        return err(f"Per member price kam se kam {config.AD_COST} coins rakho.")
    cost = n * price
    if not admin and u["ad_balance"] + u["balance"] < cost:
        return err(f"Coins kam hain. Chahiye {cost}, tumhare paas {u['ad_balance'] + u['balance']} (ad balance + earnings). Wallet se deposit karo ya aur kamao.")
    r = await resolve_chat(request, d.get("chat"), True)
    if isinstance(r, str):
        return err(r)
    tid = await db.create_task(u["id"], r["chat_id"], r["title"], r["link"], n, free=admin, price=price)
    if not tid:
        return err("Ad balance kam hai. Pehle deposit karo.")
    extras.feed(f"📢 <b>Naya channel task</b> #{tid}: {html.escape(r['title'] or '')} — {n} members, by {extras.uname(u)}")
    asyncio.create_task(util.notify(request.app["bot"], u["id"], f"✅ Tumhara task #{tid} live ho gaya: {html.escape(r['title'] or '')} ({n} members)."))
    return ok(msg=f"Task #{tid} live ho gaya! {r['title']} ke liye {n} members. Har joiner ko {price - config.TASK_FEE} coins milenge.")


@routes.post("/api/notify")
async def api_notify(request):
    on = bool((await body(request)).get("on"))
    await db.set_notify(request["u"]["id"], on)
    return ok(notify=on, msg="🔔 Notification ON" if on else "🔕 Notification OFF")


@routes.get("/api/task/my")
async def api_task_my(request):
    rows = await db.my_tasks(request["u"]["id"])
    return ok(tasks=[{"id": t["id"], "title": t["title"], "joined": t["joined"], "target": t["target"],
                      "status": t["status"]} for t in rows])


@routes.post("/api/task/cancel")
async def api_task_cancel(request):
    refund = await db.cancel_task(to_int((await body(request)).get("id")), request["u"]["id"])
    if refund is None:
        return err("Ye task cancel nahi ho sakta.")
    return ok(msg=f"Task cancel hua. {refund} coins refund hue.")


# ---------------- bot work ----------------
@routes.post("/api/bw/create")
async def api_bw_create(request):
    u = request["u"]
    d = await body(request)
    if not util.is_prem(u):
        return err("Bot Work banana Premium Level 1 se khulta hai. Premium lo.")
    e = await task_limit_err(u)
    if e:
        return err(e)
    title = str(d.get("title", "")).strip()
    link = str(d.get("link", "")).strip()
    reward = to_int(d.get("reward"))
    n = to_int(d.get("count"))
    if not (3 <= len(title) <= 40):
        return err("Title 3 se 40 characters ka rakho.")
    if not URL_RE.match(link):
        return err("Sahi refer link daalo (https://...).")
    if not (config.BW_MIN_REWARD <= reward <= 100000):
        return err(f"Reward min {config.BW_MIN_REWARD} coins hona chahiye.")
    if not (config.BW_MIN_USERS <= n <= config.BW_MAX_USERS):
        return err(f"Users {config.BW_MIN_USERS} se {config.BW_MAX_USERS} ke beech rakho.")
    instr = str(d.get("instructions", "")).strip()[:400]
    needs_dev = bool(d.get("needs_dev"))
    bid = await db.bw_create(u["id"], title, link, reward, n, free=u["id"] in config.ADMIN_IDS,
                             instructions=instr, needs_dev=needs_dev)
    if not bid:
        return err(f"Coins kam hain. Chahiye {reward * n} coins (ad balance + earnings). Wallet se deposit karo ya aur kamao.")
    extras.feed(f"🤖 <b>Naya bot work</b> #{bid}: {html.escape(title)} — {n} users x {reward} coins, by {extras.uname(u)}")
    asyncio.create_task(util.notify(request.app["bot"], u["id"], f"✅ Tumhara Bot Work #{bid} live ho gaya: {html.escape(title)}."))
    return ok(msg=f"Bot work #{bid} live ho gaya!")


@routes.get("/api/bw/my")
async def api_bw_my(request):
    rows = await db.bw_my(request["u"]["id"])
    return ok(items=[{"id": r["id"], "title": r["title"], "reward": r["reward"], "target": r["target"],
                      "used": r["used"], "done": r["done"], "pending": r["pending"], "status": r["status"]}
                     for r in rows])


@routes.post("/api/bw/cancel")
async def api_bw_cancel(request):
    refund = await db.bw_cancel(to_int((await body(request)).get("id")), request["u"]["id"])
    if refund is None:
        return err("Ye bot work cancel nahi ho sakta.")
    return ok(msg=f"Bot work cancel hua. {refund} coins refund hue.")


def _img_ok(b):
    return b[:3] == b"\xff\xd8\xff" or b[:8] == b"\x89PNG\r\n\x1a\n" or (b[:4] == b"RIFF" and b[8:12] == b"WEBP")


@routes.post("/api/bw/submit")
async def api_bw_submit(request):
    u = request["u"]
    uid = u["id"]
    bot = request.app["bot"]
    if not u["device_ok"]:
        return err("🔐 Pehle Profile me device verify karo.")
    if not cooldown(uid, "bw", 10):
        return too_fast()
    if await db.is_blocked(uid):
        return err("🚫 Tum blocked ho. Pehle left channel rejoin karo.")
    fields, photos = {}, {}
    try:
        reader = await request.multipart()
        async for part in reader:
            if part.name in ("photo", "photo2"):
                buf = bytearray()
                while True:
                    chunk = await part.read_chunk(65536)
                    if not chunk:
                        break
                    buf += chunk
                    if len(buf) > 5_000_000:
                        return err("Screenshot 5MB se chhota bhejo.")
                photos[part.name] = bytes(buf)
            else:
                fields[part.name] = ((await part.read_chunk(4096)) or b"").decode("utf-8", "ignore")[:400]
    except Exception:
        return err("Upload fail hua. Dobara try karo.")
    photo, photo2 = photos.get("photo"), photos.get("photo2")
    if not photo or not _img_ok(photo):
        return err("Screenshot (photo) upload karo.")
    bw0 = await db.bw_get(to_int(fields.get("bid")))
    if bw0 and bw0["needs_dev"] and (not photo2 or not _img_ok(photo2)):
        return err("Is bot me device verification hai: 2 photo chahiye. Dusri photo me device verification ka result (success ya failed) dikhao.")
    if not (bw0 and bw0["needs_dev"]):
        photo2 = None
    if photo2 and hashlib.sha256(photo2).hexdigest() == hashlib.sha256(photo).hexdigest():
        return err("Dono photo alag-alag hone chahiye.")
    ref = fields.get("ref", "").strip()
    if not URL_RE.match(ref):
        return err("Us bot ka sahi refer link daalo (https://...).")
    res, sid, b = await db.bw_submit(to_int(fields.get("bid")), uid, "pending",
                                     hashlib.sha256(photo).hexdigest(), ref,
                                     hashlib.sha256(photo2).hexdigest() if photo2 else None)
    if res != "ok":
        return err({"dup": "Tum ye task pehle submit kar chuke ho, ya ye screenshot pehle use ho chuka hai.",
                    "own": "Apna hi task nahi kar sakte.",
                    "locked": "Is task me tumhare 2 try ho chuke hain, ab ye task tumhare liye lock hai.", "full": "Is task ke saare slots full ho gaye.",
                    "closed": "Ye task ab available nahi."}[res])
    extras.feed(f"📸 Bot work submission #{sid} (task #{to_int(fields.get('bid'))}) — {extras.uname(request['u'])}")
    me = request["tg"] if "tg" in request else {}
    name = f"@{me['username']}" if me.get("username") else (me.get("first_name") or str(uid))
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    cap = (f"🤖 <b>Bot Work submission</b> #{sid}\nTask: {esc(b['title'])}\n"
           f"Worker: {esc(name)} (<code>{uid}</code>)\nRefer link: {esc(ref)}\nReward: {b['reward']} coins\n\n"
           "Screenshot dekho. Sahi ho to <b>Done</b>, nahi to Reject." + ("\n🔐 Is bot me device verification hai: upar wali alag photo me uska result dekho." if photo2 else ""))
    kb = M([[B("✅ Done", callback_data=f"bws_ok:{sid}"), B("❌ Reject", callback_data=f"bws_no:{sid}")]])
    ol = await i18n.lang_of(b["owner_id"])  # poster ki bhasha me caption
    cap = i18n.tr(cap, ol)
    try:
        f2 = None
        if photo2:  # pehle device-verification wali photo, phir buttons wali main photo
            m2 = await bot.send_photo(b["owner_id"], photo2, parse_mode="HTML",
                                      caption=i18n.tr(f"🔐 <b>Device verification screenshot</b> (submission #{sid}). Result success hai ya failed, dekho.", ol))
            f2 = m2.photo[-1].file_id
        m = await bot.send_photo(b["owner_id"], photo, caption=cap, parse_mode="HTML", reply_markup=kb)
        await db.bw_set_photo(sid, m.photo[-1].file_id, f2)
    except TelegramError:
        await db.bw_drop(sid)
        return err("Owner tak bhej nahi paya (unhone bot start nahi kiya hoga). Baad me try karo.")
    return ok(msg="Submit ho gaya! Status: Pending. Owner check karke Done karega to coins mil jayenge.")


@routes.post("/api/bw/report")
async def api_bw_report(request):
    sid = to_int((await body(request)).get("sid"))
    r = await db.bw_report(sid, request["u"]["id"], "Worker ne reject ke baad report kiya")
    if not r:
        return err("Ye report nahi ho sakta (already reported ya time khatam).")
    extras.feed(f"🚩 Bot work report #{sid} — {extras.uname(request['u'])}")
    await botwork.send_report(request.app["bot"], sid)
    return ok(msg="Report bhej di gayi. Admin check karke decision lega.")
