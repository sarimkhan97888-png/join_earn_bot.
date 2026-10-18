"""Deposit / premium orders ko gateway ke status API se verify karke settle karna."""
import logging
import time

import config
import db
import gateway
import util

log = logging.getLogger("payments")
_last = {}


async def settle(bot, o, min_gap=0):
    """Order pending ho to gateway se status pooch ke, paid ho to credit karo. Return final status."""
    if o["status"] != "pending" or not o["gateway_ref"]:
        return o["status"]
    now = time.monotonic()
    if min_gap and now - _last.get(o["order_id"], 0) < min_gap:
        return "pending"
    _last[o["order_id"]] = now
    if len(_last) > 5000:
        for k in [k for k, v in _last.items() if now - v > 600]:
            _last.pop(k, None)
    try:
        state, amt, _ = await gateway.check_payment(o["gateway_ref"])
    except Exception:
        log.exception("check_payment failed for %s", o["order_id"])
        return "pending"
    if state == "failed":
        await db.order_set_status(o["order_id"], "failed")
        return "failed"
    if state != "paid":
        return "pending"
    done = await db.complete_order(o["order_id"], amt)
    if done:
        _last.pop(o["order_id"], None)
        if done["kind"] == "deposit":
            msg = f"✅ <b>Deposit successful!</b>\n+{done['coins']} coins ad balance me add ho gaye."
        else:
            msg = f"✅ <b>Premium activated!</b> {config.PREMIUM_DAYS} din ke liye."
        await util.notify(bot, done["user_id"], msg)
        return "paid"
    row = await db.order_row(o["order_id"])
    return row["status"] if row else "pending"
