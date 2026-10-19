"""Task-added notifications (paced broadcast) + daily data backup (alag bot token se)."""
import asyncio
import csv
import io
import logging
import time
import zipfile
from datetime import datetime, timezone

from telegram import Bot
from telegram.error import Forbidden, RetryAfter, TelegramError

import config
import db

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
                await ctx.bot.send_message(r["id"], b["text"], parse_mode="HTML", disable_notification=False)
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
