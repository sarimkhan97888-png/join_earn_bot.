"""Task-added notifications (paced broadcast) + daily data backup (alag bot token se)."""
import asyncio
import csv
import html
import json
import io
import logging
import time
import zipfile
from datetime import datetime, timedelta, timezone

from telegram import Bot
from telegram.error import Forbidden, RetryAfter, TelegramError

import config
import i18n
import db
import util

log = logging.getLogger("extras")
_bk = {"bot": None}
TABLES = ["users", "tasks", "completions", "ledger", "orders", "botworks", "bw_subs", "withdrawals",
          "referrals", "gift_codes", "gift_redeems"]


# ---------- notifications ----------
async def job_bcast(ctx):
    """Har 30s: naye task ka broadcast banao, phir ~20 msg/sec ki raftaar se users ko bhejo."""
    await db.bc_enqueue()
    b = await db.bc_next()
    if not b:
        return
    t0 = time.monotonic()
    last, sent = b["last_uid"], 0
    while time.monotonic() - t0 < 25:
        users = await db.bc_users(last, 100)
        if not users:
            await db.bc_progress(b["id"], last, sent, True)
            return
        for r in users:
            try:
                await ctx.bot.send_message(r["id"], i18n.tr(b["text"], r["lang"] or "en"), parse_mode="HTML", disable_notification=False)
                sent += 1
            except Forbidden:
                await db.set_notify(r["id"], False)  # bot block kiya: dobara try nahi
            except RetryAfter as e:
                ra = e.retry_after
                await db.bc_progress(b["id"], last, sent)
                await asyncio.sleep(min(ra.total_seconds() if hasattr(ra, "total_seconds") else float(ra), 20) + 1)
                return
            except TelegramError:
                pass
            last = r["id"]
            await asyncio.sleep(0.05)
    await db.bc_progress(b["id"], last, sent)


# ---------- backup ----------
async def _bot():
    if not config.BACKUP_BOT_TOKEN:
        return None
    if _bk["bot"] is None:
        _bk["bot"] = Bot(config.BACKUP_BOT_TOKEN)
        await _bk["bot"].initialize()
    return _bk["bot"]


async def build_backup():
    """[(filename, bytes)] : har table ki CSV, ek zip me (zip 45MB se bada ho to alag-alag gz files)."""
    files = []
    for t in TABLES:
        rows = await db.pool.fetch(f"SELECT * FROM {t}")
        buf = io.StringIO()
        w = csv.writer(buf)
        if rows:
            w.writerow(list(rows[0].keys()))
            for r in rows:
                w.writerow(["" if v is None else v for v in r.values()])
        files.append((f"{t}.csv", buf.getvalue().encode()))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, d in files:
            zf.writestr(n, d)
    if z.tell() <= 45 * 1024 * 1024:
        return [(f"backup_{stamp}.zip", z.getvalue())]
    out = []
    import gzip
    for n, d in files:
        out.append((f"{n[:-4]}_{stamp}.csv.gz", gzip.compress(d)))
    return out


async def send_backup():
    """True = bheja. Token na ho to chupchap False."""
    bot = await _bot()
    if not bot or not config.ADMIN_IDS:
        return False
    parts = await build_backup()
    ok = False
    for aid in config.ADMIN_IDS:
        for name, data in parts:
            if len(data) > 49 * 1024 * 1024:
                continue
            try:
                await bot.send_document(aid, io.BytesIO(data), filename=name,
                                        caption=f"🗄 Profitix backup {datetime.now(timezone.utc):%d %b %Y %H:%M} UTC")
                ok = True
            except TelegramError as e:
                log.warning("backup send fail admin=%s: %s", aid, e)  # admin ne backup bot /start nahi kiya hoga
                break
    return ok


async def job_backup(ctx):
    try:
        await send_backup()
    except Exception:
        log.exception("backup failed")


# ---------- withdraw alerts: backup bot (buttons) ----------
async def bk_send(text, kb):
    """Withdraw alert + buttons admins ko BACKUP bot se. Backup bot nahi/ admin ne /start nahi kiya to main bot se.
    Return json text {"b": {admin: msg_id}, "m": {...}} (baad me delete karne ke liye)."""
    out = {"b": {}, "m": {}}
    bk = None
    try:
        bk = await _bot()
    except Exception:
        log.exception("backup bot init failed")
    for aid in config.ADMIN_IDS:
        sent = False
        if bk:
            try:
                m = await bk.send_message(aid, text, parse_mode="HTML", reply_markup=kb)
                out["b"][str(aid)] = m.message_id
                sent = True
            except TelegramError as e:
                log.warning("backup bot alert fail admin=%s: %s (backup bot /start kiya?)", aid, e)
        if not sent and util.main_bot:
            try:
                m = await util.main_bot.send_message(aid, text, parse_mode="HTML", reply_markup=kb)
                out["m"][str(aid)] = m.message_id
            except TelegramError:
                pass
    return json.dumps(out)


async def bk_delete(wid):
    """Is withdraw ke saare admin alert messages delete (approve/reject/expire/paid/failed par)."""
    try:
        raw = await db.wd_pop_msgs(wid)
        if not raw:
            return
        d = json.loads(raw)
        for key, bot in (("b", _bk["bot"]), ("m", util.main_bot)):
            for aid, mid in (d.get(key) or {}).items():
                if not bot:
                    continue
                try:
                    await bot.delete_message(int(aid), int(mid))
                except TelegramError:
                    pass
    except Exception:
        log.exception("bk_delete failed #%s", wid)


# ---------- public payout proof channel ----------
def _mask_upi(upi):
    name, _, bank = (upi or "").partition("@")
    return (name[:2] + "***" + ("@" + bank if bank else "")) if name else "***"


async def post_payout(w):
    """Withdraw sach me paid hone par public proof channel me post (UPI masked). Kabhi raise nahi karta."""
    if not config.PAYOUT_CHANNEL_ID or not util.main_bot:
        return
    try:
        cid = int(config.PAYOUT_CHANNEL_ID) if config.PAYOUT_CHANNEL_ID.lstrip("-").isdigit() else config.PAYOUT_CHANNEL_ID
        when = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        if w.get("method") == "usdt":
            a = w["upi"]
            await util.main_bot.send_message(
                cid, f"✅ <b>Payout successful</b>\n💸 Amount: <b>{w['usdt']} USDT</b> (BEP20)\n"
                     f"👛 Wallet: <code>{html.escape(a[:6] + '…' + a[-4:])}</code>\n🔗 <a href=\"https://bscscan.com/tx/{w['tx']}\">TxID: {w['tx'][:10]}…{w['tx'][-6:]}</a>\n"
                     f"🆔 Withdraw #{w['id']}\n🕒 {when:%d %b %Y, %H:%M} IST", parse_mode="HTML", disable_web_page_preview=True)
            return
        await util.main_bot.send_message(
            cid, f"✅ <b>Payout successful</b>\n💸 Amount: <b>₹{float(w['amount_inr']):.2f}</b>\n"
                 f"🏦 UPI: <code>{html.escape(_mask_upi(w['upi']))}</code>\n🆔 Withdraw #{w['id']}\n"
                 f"🕒 {when:%d %b %Y, %H:%M} IST", parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        log.warning("payout channel post failed #%s: %s", w.get("id"), e)


# ---------- admin live feed (main bot) ----------
_feed_q = None
_feed_task = None


async def _feed_worker():
    while True:
        lines = [await _feed_q.get()]
        while not _feed_q.empty() and len(lines) < 12:
            lines.append(_feed_q.get_nowait())
        bot = util.main_bot
        if not bot:
            continue
        txt = "\n".join(lines)
        for aid in config.ADMIN_IDS:
            await util.notify(bot, aid, txt, disable_notification=True)
        await asyncio.sleep(0.4)


def feed(text):
    """Admins ko main bot par ek line ki khabar (queue: flood limit se bachne ke liye batch + silent). Kabhi raise nahi karta."""
    global _feed_q, _feed_task
    if not config.ADMIN_FEED or not config.ADMIN_IDS:
        return
    try:
        if _feed_q is None:
            _feed_q = asyncio.Queue(maxsize=500)
        if _feed_task is None or _feed_task.done():
            _feed_task = asyncio.get_running_loop().create_task(_feed_worker())
        _feed_q.put_nowait(f"{datetime.now(timezone(timedelta(hours=5, minutes=30))):%H:%M} {text}")
    except Exception:
        pass  # queue full / loop nahi: feed ke liye kuch rokna nahi


def uname(u):
    """User ko feed me dikhane ka chhota text: name/@username + id."""
    n = (u.get("first_name") if hasattr(u, "get") else None) or ""
    un = u.get("username") if hasattr(u, "get") else None
    nm = html.escape(f"@{un}" if un else n[:24] or "-")
    return f"{nm} (<code>{u['id']}</code>)"


def _new_user(row):
    feed(f"🆕 <b>New user</b> {uname(row)}")


db.new_user_hook = _new_user
