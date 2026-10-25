"""NOWPayments (USDT BEP20) : payment banana, IPN verify, status se credit. Keys sirf env me (config)."""
import hashlib
import hmac
import json
import logging
import time
from decimal import Decimal

import aiohttp

import config
import db
import extras
import payments
import util

log = logging.getLogger("nowpay")
API = "https://api.nowpayments.io/v1"
_sess = None
_checked = {}      # order_id -> last status-check time (polling throttle)
_warned = set()    # partially_paid ka admin alert ek baar


class PayError(Exception):
    pass


def _session():
    global _sess
    if _sess is None or _sess.closed:
        _sess = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
    return _sess


async def _call(method, path, **kw):
    try:
        async with _session().request(method, API + path, headers={"x-api-key": config.NOWPAY_KEY}, **kw) as r:
            txt = await r.text()
            try:
                data = json.loads(txt)
            except Exception:
                data = {"message": txt[:200]}
            return r.status, data
    except Exception as e:
        log.warning("nowpayments %s failed: %s", path, e)
        raise PayError("net")


async def min_amount():
    try:
        st, d = await _call("GET", f"/min-amount?currency_from={config.USDT_CCY}&currency_to={config.USDT_CCY}")
        if st == 200 and d.get("min_amount"):
            return Decimal(str(d["min_amount"]))
    except Exception:
        pass
    return None


async def create_payment(order_id, amount, desc):
    """amount (Decimal USDT, fee ke saath). Return dict: payment_id, pay_address, pay_amount, ttl."""
    body = {"price_amount": float(amount), "price_currency": config.USDT_PRICE_CCY, "pay_currency": config.USDT_CCY,
            "order_id": order_id, "order_description": desc[:100]}
    if config.BASE_URL and config.NOWPAY_IPN_SECRET:
        body["ipn_callback_url"] = f"{config.BASE_URL.rstrip('/')}/nowpay/ipn"
    st, d = await _call("POST", "/payment", json=body)
    if st not in (200, 201) or not d.get("pay_address"):
        log.warning("nowpayments create failed %s %s", st, d)
        raise PayError(str(d.get("message") or d.get("code") or st))
    return {"payment_id": d["payment_id"], "pay_address": d["pay_address"],
            "pay_amount": Decimal(str(d.get("pay_amount") or amount)), "ttl": config.USDT_TTL}


async def get_payment(pid):
    st, d = await _call("GET", f"/payment/{pid}")
    return d if st == 200 else None


def verify_sig(raw, sig):
    """x-nowpayments-sig = HMAC-SHA512(IPN secret, JSON with keys sorted). Secret na ho to kabhi accept nahi."""
    if not config.NOWPAY_IPN_SECRET or not sig:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    msg = json.dumps(data, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    good = hmac.new(config.NOWPAY_IPN_SECRET.encode(), msg.encode(), hashlib.sha512).hexdigest()
    return data if hmac.compare_digest(good, str(sig).lower()) else None


async def _admins(bot, text):
    for a in config.ADMIN_IDS:
        await util.notify(bot, a, text)


async def process(bot, pay):
    """Ek payment status (IPN ya API se) lagao. Return order status ya None."""
    oid = str(pay.get("order_id") or "")
    o = await db.order_row(oid)
    if not o or o["method"] != "usdt":
        return None
    status = pay.get("payment_status")
    if status == "finished":
        got = Decimal(str(pay.get("actually_paid") or 0))
        need = Decimal(str(o["pay_amount"] or 0))
        if o["status"] == "failed":
            await db.usdt_reopen(oid)
        if got < need * Decimal("0.99"):
            await db.order_set_status(oid, "mismatch")
            await _admins(bot, f"⚠️ USDT payment kam aayi\nOrder <code>{oid}</code> user <code>{o['user_id']}</code>\n"
                               f"Chahiye {need} USDT, mila {got}. Manual dekho (/addad se credit kar sakte ho).")
            return "mismatch"
        done = await db.complete_order(oid, None)
        if done:
            extras.feed(f"💵 USDT payment ✅ {o['usdt']} USDT — user <code>{o['user_id']}</code> ({done['kind']})")
            await util.notify(bot, o["user_id"], payments.paid_msg(done))
        return "paid"
    if status == "partially_paid":
        if oid not in _warned:
            _warned.add(oid)
            await _admins(bot, f"⚠️ USDT <b>partially paid</b>\nOrder <code>{oid}</code> user <code>{o['user_id']}</code>\n"
                               f"Chahiye {pay.get('pay_amount')}, mila {pay.get('actually_paid')} USDT. User ko baaki bhejna hoga ya manual credit.")
            await util.notify(bot, o["user_id"], "⚠️ Tumne USDT kam bheje. Order poora nahi hua. Baaki amount usi address par bhejo ya Support se contact karo.")
        return "pending"
    if status in ("failed", "expired", "refunded"):
        await db.order_set_status(oid, "failed")
        return "failed"
    return o["status"]


async def sync_order(bot, o):
    """Polling fallback (webhook na aaye to bhi): har 12 sec se zyada nahi. Return fresh status."""
    now = time.monotonic()
    if o["status"] != "pending" or not o["gateway_ref"] or now - _checked.get(o["order_id"], -1e9) < 12:
        return o["status"]
    _checked[o["order_id"]] = now
    if len(_checked) > 3000:
        _checked.clear()
    try:
        pay = await get_payment(o["gateway_ref"])
    except PayError:
        return o["status"]
    if not pay:
        return o["status"]
    pay["order_id"] = o["order_id"]
    return await process(bot, pay) or o["status"]
