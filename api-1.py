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
from urllib.parse import parse_qsl

import qrcode
from aiohttp import web
from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M, WebAppInfo
from telegram.error import TelegramError

import botwork
import config
import db
import gateway
import payments
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
        if time.time() - int(data.get("auth_date", "0")) > 86400:
            return None
        return json.loads(data["user"])
    except Exception:
        return None


def ok(**kw):
    return web.json_response({"ok": True, **kw})


def err(msg):
    return web.json_response({"ok": False, "msg": msg})


def iso(dt):
    return dt.isoformat() if dt else None


def to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
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
            "gmail": u["gmail"], "upi": u["upi"], "device_ok": u["device_ok"],
            "device_state": u.get("device_state", "ok"), "admin": u["id"] in config.ADMIN_IDS}


def cfg(request):
    return {"coin_per_inr": config.COIN_PER_INR, "join_reward": config.JOIN_REWARD, "ad_cost": config.AD_COST,
            "min_task_members": config.MIN_TASK_MEMBERS, "max_task_members": config.MAX_TASK_MEMBERS,
            "min_deposit": config.MIN_DEPOSIT_COINS, "min_withdraw": config.MIN_WITHDRAW_COINS,
            "hold_hours": config.HOLD_HOURS, "premium_price": config.PREMIUM_PRICE,
            "premium_days": config.PREMIUM_DAYS, "bw_min_reward": config.BW_MIN_REWARD,
            "bw_min_users": config.BW_MIN_USERS, "bw_max_users": config.BW_MAX_USERS,
            "support_url": config.SUPPORT_URL, "bot_username": request.app["bot"].username,
            "withdraw_tax": config.WITHDRAW_TAX_PERCENT, "app_name": config.APP_NAME,
            "refer_reward": config.REFER_REWARD,
            "auto_payout": bool(config.AUTO_PAYOUT)}


# ---------------- auth + rate limit + device check ----------------
_rl = {}
_rl_gc = [0.0]
# Device verify ke bina sirf ye endpoints chalte hain (baaki sab server par block)
OPEN_PATHS = {"/api/me", "/api/verify", "/api/support", "/api/support/send", "/api/support/photo", "/api/wallet",
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
        if u["banned"]:
            return web.json_response({"ok": False, "msg": "🚫 Account banned."}, status=403)
        u = await with_device(u, request.headers.get("X-Device", ""), request.headers.get("X-Fp", ""))
        if not u["device_ok"] and u["id"] not in config.ADMIN_IDS and request.path not in OPEN_PATHS:
            return web.json_response({"ok": False, "code": "need_verify",
                                      "msg": "🔐 Pehle device verify karo."})
        request["u"] = u
        request["tg"] = user
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception:
        log.exception("api error %s", request.path)
        return err("⚠️ Server error. Thodi der baad try karo.")


# ---------------- me / home ----------------
@routes.get("/api/me")
async def api_me(request):
    u = request["u"]
    left, led = await asyncio.gather(db.left_chats(u["id"]), db.recent_ledger(u["id"]))
    blocked = [{"chat_id": r["chat_id"], "title": r["title"], "link": r["link"]} for r in left]
    hist = [{"kind": r["kind"], "amount": r["amount"], "at": iso(r["created_at"])} for r in led]
    return ok(me=pub(u), blocked=blocked, history=hist, cfg=cfg(request))


# ---------------- channel tasks (worker) ----------------
@routes.get("/api/tasks")
async def api_tasks(request):
    uid = request["u"]["id"]
    ch = [{"id": t["id"], "title": t["title"], "link": t["link"], "reward": config.JOIN_REWARD}
          for t in await db.open_tasks(uid)]
    bw = [{"id": b["id"], "title": b["title"], "link": b["link"], "reward": b["reward"]}
          for b in await db.bw_open(uid)]
    mine = [{"id": r["id"], "status": r["status"], "title": r["title"], "reward": r["reward"]}
            for r in await db.bw_mine(uid)]
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
        return ok(msg=f"Join verified! +{config.JOIN_REWARD} coins ({config.HOLD_HOURS}h hold me)")
    return err({"dup": "Ye task tum pehle kar chuke ho.", "own": "Apne channel se coin nahi mil sakta.",
                "closed": "Task full ho gaya."}[res])


@routes.post("/api/rejoin")
async def api_rejoin(request):
    uid = request["u"]["id"]
    bot = request.app["bot"]
    for r in await db.left_chats(uid):
        if await util.member_status(bot, r["chat_id"], uid):
            await db.unblock(r["chat_id"], uid)
    if await db.left_chats(uid):
        return err("❌ Abhi bhi kuch channels join nahi kiye.")
    return ok(msg="Unblocked! Ab tasks kar sakte ho.")


# ---------------- wallet ----------------
@routes.get("/api/wallet")
async def api_wallet(request):
    uid = request["u"]["id"]
    orders = [{"id": r["order_id"], "kind": r["kind"], "coins": r["coins"], "amount": r["amount_inr"],
               "status": r["status"], "at": iso(r["created_at"])} for r in await db.order_history(uid)]
    wds = [{"id": r["id"], "coins": r["coins"], "amount": float(r["amount_inr"]), "fee": r["fee_coins"], "upi": r["upi"],
            "status": r["status"], "at": iso(r["created_at"])} for r in await db.wd_history(uid)]
    return ok(orders=orders, withdrawals=wds)


async def make_order(request, kind, coins, amount):
    uid = request["u"]["id"]
    if not cooldown(uid, "order", 5):
        return too_fast()
    if await db.pending_orders(uid) >= 5:
        return err("Bahut saare pending orders hain. Thodi der baad try karo.")
    order_id = f"{kind[0].upper()}{uid}{int(time.time() * 1000)}"
    try:
        res = await gateway.create_order(order_id, amount, f"{kind} {uid}")
    except Exception:
        log.exception("gateway create_order failed")
        return err("❌ Payment gateway abhi available nahi. Baad me try karo.")
    if not res.get("ref"):
        log.error("gateway response me payment id nahi mili; keys=%s",
                  list(res.get("raw", {}).keys()) if isinstance(res.get("raw"), dict) else None)
        return err("Payment gateway se payment ID nahi mili. Support se contact karo.")
    await db.new_order(order_id, uid, kind, coins, amount, res["ref"])
    qr = res.get("qr_url")
    if not qr and res.get("upi_url"):
        bio = io.BytesIO()
        qrcode.make(res["upi_url"]).save(bio, "PNG")
        qr = "data:image/png;base64," + base64.b64encode(bio.getvalue()).decode()
    return ok(order_id=order_id, amount=amount, coins=coins, qr=qr, pay_url=res.get("pay_url") or res.get("upi_url"))


@routes.post("/api/deposit")
async def api_deposit(request):
    coins = to_int((await body(request)).get("coins"))
    if coins < config.MIN_DEPOSIT_COINS or coins % config.COIN_PER_INR or coins > 10_000_000:
        return err(f"Min {config.MIN_DEPOSIT_COINS} coins aur 100 ke multiple me daalo.")
    return await make_order(request, "deposit", coins, coins // config.COIN_PER_INR)


@routes.post("/api/premium/buy")
async def api_premium_buy(request):
    return await make_order(request, "premium", 0, config.PREMIUM_PRICE)


@routes.get("/api/order")
async def api_order(request):
    row = await db.order_row(request.query.get("id", ""))
    if not row or row["user_id"] != request["u"]["id"]:
        return ok(status="none")
    return ok(status=await payments.settle(request.app["bot"], row, min_gap=4))


@routes.post("/api/withdraw")
async def api_withdraw(request):
    u = request["u"]
    uid = u["id"]
    coins = to_int((await body(request)).get("coins"))
    if not u["device_ok"]:
        return err("🔐 Withdraw ke liye pehle device verify karo.")
    if not cooldown(uid, "wd", 8):
        return too_fast()
    if await db.is_blocked(uid):
        return err("🚫 Tum blocked ho. Pehle left channel rejoin karo.")
    if not u["upi"]:
        return err("Pehle Profile me apna UPI ID set karo.")
    if coins < config.MIN_WITHDRAW_COINS or coins % config.COIN_PER_INR or coins > u["balance"]:
        return err(f"Min {config.MIN_WITHDRAW_COINS} coins, 100 ke multiple me, aur max {u['balance']}.")
    r = await db.request_withdraw(uid, coins)
    if not r:
        return err("❌ Withdraw nahi ho paya. Balance aur verification check karo.")
    wid, upi, fee, net = r
    auto = payouts.eligible(u, net, await db.wd_recent_count(uid))
    t = asyncio.create_task(_after_withdraw(request.app["bot"], u, wid, coins, fee, net, upi, auto))
    _bg.add(t)
    t.add_done_callback(_bg.discard)
    if auto:
        return ok(msg=f"Withdraw #{wid} process ho raha hai: ₹{net:.2f} → {upi}. 2-5 minute me aa jayega.")
    return ok(msg=f"Withdraw request #{wid} bhej di gayi. {coins} coins − {fee} tax = ₹{net:.2f} → {upi}. "
                  f"Admin approve karega to paisa aa jayega.")


async def _after_withdraw(bot, u, wid, coins, fee, net, upi, auto):
    try:
        if auto:
            await payouts.send(bot, wid)  # fail/unsure par payouts.send khud admin ko alert karta hai
            return
        why = ""
        if u["suspect"]:
            why += "\n⚠️ <b>Suspect:</b> iska device fingerprint kisi aur account se match karta hai. Pehle check karo."
        if config.AUTO_PAYOUT and not u["suspect"]:
            why += "\nℹ️ Auto limit se bahar / abhi auto pause hai, isliye manual approval."
        for a in config.ADMIN_IDS:
            await util.notify(bot, a,
                              f"💸 Withdraw #{wid}\nUser: <code>{u['id']}</code>\n{coins} coins − {fee} tax = "
                              f"<b>₹{net:.2f}</b> payable\nUPI: <code>{upi}</code>{why}", reply_markup=payouts.admin_kb(wid))
    except Exception:
        log.exception("after_withdraw failed for #%s", wid)


# ---------------- support (user <-> admin, sab Mini App ke andar) ----------------
def is_admin(request):
    return request["u"]["id"] in config.ADMIN_IDS


def sniff_mime(b):
    return "image/png" if b[:4] == b"\x89PNG" else "image/webp" if b[:4] == b"RIFF" else "image/jpeg"


async def read_text_photo(request):
    """JSON {text,...} ya multipart (text, photo, uid). Return (fields dict, photo bytes|None) ya (None, error)."""
    fields, photo = {}, None
    if (request.content_type or "").startswith("multipart/"):
        try:
            reader = await request.multipart()
            async for part in reader:
                if part.name == "photo":
                    buf = bytearray()
                    while True:
                        chunk = await part.read_chunk(65536)
                        if not chunk:
                            break
                        buf += chunk
                        if len(buf) > 1_500_000:
                            return None, "Photo 1.5MB se chhoti bhejo."
                    photo = bytes(buf)
                else:
                    fields[part.name] = (await part.text())[:1100]
        except Exception:
            return None, "Upload fail hua. Dobara try karo."
    else:
        fields = await body(request)
    if photo is not None and (not photo or not _img_ok(photo)):
        return None, "Sirf photo (JPG/PNG/WEBP) bhej sakte ho."
    return fields, photo


def msg_json(rows):
    return [{"id": r["id"], "from": r["sender"], "text": r["text"], "photo": r["has_photo"], "at": iso(r["created_at"])}
            for r in rows]


@routes.get("/api/support")
async def api_support(request):
    return ok(msgs=msg_json(await db.sup_list(request["u"]["id"])))


@routes.get("/api/support/photo")
async def api_support_photo(request):
    row = await db.sup_file(to_int(request.query.get("id")))
    if not row or (row["user_id"] != request["u"]["id"] and not is_admin(request)):
        return web.Response(status=404, text="gone")
    data = bytes(row["data"])
    return web.Response(body=data, content_type=sniff_mime(data), headers={"Cache-Control": "private, max-age=86400"})


@routes.post("/api/support/send")
async def api_support_send(request):
    uid = request["u"]["id"]
    if not cooldown(uid, "sup", 1.5):
        return too_fast()
    fields, photo = await read_text_photo(request)
    if fields is None:
        return err(photo)
    text = str(fields.get("text", "")).strip()[:1000]
    if not text and photo is None:
        return err("Message khali hai.")
    if await db.sup_recent_count(uid) >= 20:
        return err("Bahut zyada messages ho gaye. Thodi der baad likho.")
    if photo is not None and await db.sup_recent_photos(uid) >= 5:
        return err("Ek ghante me 5 photo hi bhej sakte ho.")
    await db.sup_add(uid, "user", text, photo)
    # Admin ko sirf ek link-wala notification (message text DM me nahi). Reply Mini App ke andar hota hai.
    if not await db.sup_notif_recent(uid):
        tg = request["tg"]
        name = f"@{tg['username']}" if tg.get("username") else (tg.get("first_name") or str(uid))
        kb = M([[B("💬 Open chat", web_app=WebAppInfo(url=f"{config.BASE_URL}/app?support={uid}"))]])
        for a in config.ADMIN_IDS:
            try:
                m = await request.app["bot"].send_message(
                    a, f"🎧 <b>Naya support message</b>\nFrom: {html.escape(name)} (<code>{uid}</code>)\n"
                       f"Neeche button se chat kholo aur wahin reply do.", parse_mode="HTML", reply_markup=kb)
                await db.sup_notif_add(a, m.message_id, uid)
            except TelegramError:
                log.warning("support notify failed for admin %s", a)
    return ok()


@routes.get("/api/admin/support")
async def api_admin_threads(request):
    if not is_admin(request):
        return err("Not allowed")
    rows = await db.sup_threads()
    return ok(threads=[{"uid": r["user_id"], "name": ("@" + r["username"]) if r["username"] else (r["first_name"] or str(r["user_id"])),
                        "last": r["last_text"], "from": r["last_sender"], "at": iso(r["last_at"])} for r in rows])


@routes.get("/api/admin/support/chat")
async def api_admin_chat(request):
    if not is_admin(request):
        return err("Not allowed")
    uid = to_int(request.query.get("uid"))
    u = await db.get_user(uid)
    if not u:
        return err("User nahi mila.")
    name = ("@" + u["username"]) if u["username"] else (u["first_name"] or str(uid))
    return ok(msgs=msg_json(await db.sup_list(uid)), name=name, uid=uid)


@routes.post("/api/admin/support/reply")
async def api_admin_reply(request):
    if not is_admin(request):
        return err("Not allowed")
    fields, photo = await read_text_photo(request)
    if fields is None:
        return err(photo)
    uid = to_int(fields.get("uid"))
    text = str(fields.get("text", "")).strip()[:1000]
    if not text and photo is None:
        return err("Message khali hai.")
    if not await db.get_user(uid):
        return err("User nahi mila.")
    await db.sup_add(uid, "admin", text, photo)
    bot = request.app["bot"]
    body_txt = html.escape(text) if text else "📷 Photo bheji gayi hai."
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
    return ok(link=f"https://t.me/{request.app['bot'].username}?start=r{uid}", total=st["total"], done=st["done"],
              earned=st["done"] * config.REFER_REWARD, reward=config.REFER_REWARD, items=items)


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
    if u["device_db"] or u["device_state"] == "other" or await db.set_device(u["id"], sha(dev), fp) != "ok":
        # device/ID mismatch ya device kisi aur account ka: block (self-service verify nahi)
        await db.flag_suspect(u["id"])
        await util.notify(bot, u["id"], "🚫 <b>Device verification fail</b>\nYe device kisi aur account se linked hai "
                          "ya tumhara account pehle kisi aur device se verify tha. Account block hai, Customer service se contact karo.")
        return err("🚫 Device verification fail. Account block hai, Customer service se contact karo.")
    await util.notify(bot, u["id"], "✅ <b>Device verify ho gaya!</b>\nTelegram ID + device save ho gaye. Ab app kholo 👇",
                      reply_markup=M([[B("🚀 Open App", web_app=WebAppInfo(url=f"{config.BASE_URL}/app"))]]))
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


@routes.post("/api/task/preview")
async def api_task_preview(request):
    if not util.is_prem(request["u"]):
        return err("Pehle Premium lo.")
    r = await resolve_chat(request, (await body(request)).get("chat"), False)
    if isinstance(r, str):
        return err(r)
    return ok(title=r["title"])


@routes.post("/api/task/create")
async def api_task_create(request):
    u = request["u"]
    d = await body(request)
    if not util.is_prem(u):
        return err("Pehle Premium lo.")
    n = to_int(d.get("count"))
    if not (config.MIN_TASK_MEMBERS <= n <= config.MAX_TASK_MEMBERS):
        return err(f"Members {config.MIN_TASK_MEMBERS} se {config.MAX_TASK_MEMBERS} ke beech rakho.")
    cost = n * config.AD_COST
    admin = u["id"] in config.ADMIN_IDS  # admin ke liye task free (coins nahi katte)
    if not admin and u["ad_balance"] < cost:
        return err(f"Coins kam hain. Chahiye {cost}, ad balance {u['ad_balance']}. Wallet se deposit karo.")
    r = await resolve_chat(request, d.get("chat"), True)
    if isinstance(r, str):
        return err(r)
    tid = await db.create_task(u["id"], r["chat_id"], r["title"], r["link"], n, free=admin)
    if not tid:
        return err("Ad balance kam hai. Pehle deposit karo.")
    return ok(msg=f"Task #{tid} live ho gaya! {r['title']} ke liye {n} members.")


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
        return err("Pehle Premium lo.")
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
    bid = await db.bw_create(u["id"], title, link, reward, n, free=u["id"] in config.ADMIN_IDS)
    if not bid:
        return err(f"Ad balance kam hai. Chahiye {reward * n} coins. Wallet se deposit karo.")
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
    fields, photo = {}, None
    try:
        reader = await request.multipart()
        async for part in reader:
            if part.name == "photo":
                buf = bytearray()
                while True:
                    chunk = await part.read_chunk(65536)
                    if not chunk:
                        break
                    buf += chunk
                    if len(buf) > 5_000_000:
                        return err("Screenshot 5MB se chhota bhejo.")
                photo = bytes(buf)
            else:
                fields[part.name] = (await part.text())[:400]
    except Exception:
        return err("Upload fail hua. Dobara try karo.")
    if not photo or not _img_ok(photo):
        return err("Screenshot (photo) upload karo.")
    ref = fields.get("ref", "").strip()
    if not URL_RE.match(ref):
        return err("Us bot ka sahi refer link daalo (https://...).")
    res, sid, b = await db.bw_submit(to_int(fields.get("bid")), uid, "pending",
                                     hashlib.sha256(photo).hexdigest(), ref)
    if res != "ok":
        return err({"dup": "Tum ye task pehle submit kar chuke ho, ya ye screenshot pehle use ho chuka hai.",
                    "own": "Apna hi task nahi kar sakte.", "full": "Is task ke saare slots full ho gaye.",
                    "closed": "Ye task ab available nahi."}[res])
    me = request["tg"] if "tg" in request else {}
    name = f"@{me['username']}" if me.get("username") else (me.get("first_name") or str(uid))
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    cap = (f"🤖 <b>Bot Work submission</b> #{sid}\nTask: {esc(b['title'])}\n"
           f"Worker: {esc(name)} (<code>{uid}</code>)\nRefer link: {esc(ref)}\nReward: {b['reward']} coins\n\n"
           "Screenshot dekho. Sahi ho to <b>Done</b>, nahi to Reject.")
    kb = M([[B("✅ Done", callback_data=f"bws_ok:{sid}"), B("❌ Reject", callback_data=f"bws_no:{sid}")]])
    try:
        m = await bot.send_photo(b["owner_id"], photo, caption=cap, parse_mode="HTML", reply_markup=kb)
        await db.bw_set_photo(sid, m.photo[-1].file_id)
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
    await botwork.send_report(request.app["bot"], sid)
    return ok(msg="Report bhej di gayi. Admin check karke decision lega.")
