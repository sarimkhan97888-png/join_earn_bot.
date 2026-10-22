import asyncio
import datetime
import html
import json
import logging
import re
import secrets
import time

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M, MenuButtonWebApp, Update, WebAppInfo
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, ChatMemberHandler, CommandHandler, MessageHandler, filters

import botwork
import config
import db
import extras
import gateway
import payments
import payouts
import util

log = logging.getLogger("bot")


def app_kb():
    return M([[B("🚀 Open App", web_app=WebAppInfo(url=f"{config.BASE_URL}/app"))]])


async def post_init(app):
    util.main_bot = app.bot
    try:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Open App", web_app=WebAppInfo(url=f"{config.BASE_URL}/app")))
    except TelegramError:
        log.warning("menu button set nahi hua")


_last_start = {}


async def start(update: Update, ctx):
    """Har /start par DB se check: banned / leave kiya channel / device verify. Refer link bhi yahin pakadte hain."""
    tu = update.effective_user
    # /start spam: 1s ke andar ek hi user ke dobara aaye to ignore, par 'pehla' hamesha jawab pata hai
    t = time.monotonic()
    if t - _last_start.get(tu.id, 0) < 1:
        return
    _last_start[tu.id] = t
    if len(_last_start) > 20000:
        for k in [k for k, v in _last_start.items() if t - v > 60]:
            _last_start.pop(k, None)
    existed, left = await asyncio.gather(db.get_user(tu.id), db.left_chats(tu.id))
    u = await db.ensure_user(tu)  # (existed pehle: refer sirf bilkul naye user ke liye)
    if u["banned"]:
        return await update.message.reply_text("🚫 Tumhara account banned hai.")
    if not existed and ctx.args and re.fullmatch(r"r\d{1,15}", ctx.args[0]):
        await db.ref_add(tu.id, int(ctx.args[0][1:]))  # sirf bilkul naya user refer ban sakta hai
    app = html.escape(config.APP_NAME)
    if left:
        rows = [[B(f"➕ Join {r['title'][:28]}", url=r["link"])] for r in left if r["link"]]
        rows.append([B("🚀 Open App", web_app=WebAppInfo(url=f"{config.BASE_URL}/app"))])
        names = "\n".join("• " + html.escape(r["title"]) for r in left)
        return await update.message.reply_text(
            f"🚫 <b>App block hai</b>\nTumne ye channel leave kar diya hai:\n{names}\n\n"
            f"Dobara join karo, phir app me <b>Re-check</b> dabao.", parse_mode="HTML", reply_markup=M(rows))
    if not u["device_ok"]:
        await update.message.reply_text(
            f"👋 <b>{app} me welcome!</b>\n\n🔐 Shuru karne se pehle <b>Device Verification</b> zaroori hai "
            f"(ek device = ek account).\nNeeche button dabao, verification page khulega. Pass hone par yahin bot par wapas aa jaoge, phir app khulega.",
            parse_mode="HTML", reply_markup=M([[B("🔐 Verify Device", web_app=WebAppInfo(url=f"{config.BASE_URL}/app?v=1"))]]))
        return
    await update.message.reply_text(
        f"👋 <b>{app}</b>\nChannels join karo, coins kamao aur UPI me withdraw karo 💰\n\n"
        f"Naya phone / data clear karoge to app dobara device verify maangega.\nNeeche button se app kholo 👇",
        parse_mode="HTML", reply_markup=app_kb())


async def bypass_cmd(update: Update, ctx):
    """/bypass <id> : device verification ke bina chalne do. /unbypass <id> : wapas normal."""
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    cmd = (update.message.text or "").split()[0].lstrip("/").split("@")[0].lower()
    a = ctx.args
    if not a or not a[0].isdigit():
        return await update.message.reply_text(f"Usage: /{cmd} <user_id>\n/bypass = device verification ki zaroorat nahi, kisi bhi phone se chalega.\n/unbypass = wapas normal verify.")
    on = cmd == "bypass"
    if await db.set_bypass(int(a[0]), on):
        await update.message.reply_text(f"✅ {a[0]}: device verification {'BYPASS (kisi bhi phone se chalega)' if on else 'wapas normal'}.")
        if on:
            await util.notify(ctx.bot, int(a[0]), "✅ Tumhara account verify ho gaya hai. App kholo 👇", reply_markup=app_kb())
    else:
        await update.message.reply_text("User nahi mila (pehle usne bot /start kiya ho).")


async def allowdev_cmd(update: Update, ctx):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    a = ctx.args
    if not a or not a[0].lstrip("-").isdigit():
        return await update.message.reply_text("Usage: /allowdev <user_id>\nSame phone model + same wifi wale asli user ko allow karta hai. Phir /resetdev se uska device reset karke dobara verify karao.")
    if await db.allow_dev(int(a[0])):
        await update.message.reply_text(f"✅ User {a[0]} par fingerprint+IP rok hata di. Ab uska device reset karo: /resetdev {a[0]}")
    else:
        await update.message.reply_text("User nahi mila.")


async def resetdev_cmd(update: Update, ctx):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    a = ctx.args
    if not a or not a[0].lstrip("-").isdigit():
        return await update.message.reply_text("Usage: /resetdev <user_id>\nUser ka device unlink ho jayega, wo dobara verify karega.")
    if await db.reset_device(int(a[0])):
        await update.message.reply_text(f"✅ User {a[0]} ka device reset ho gaya.")
        await util.notify(ctx.bot, int(a[0]), "🔐 Tumhara device reset ho gaya. App kholo aur dobara verify karo.")
    else:
        await update.message.reply_text("User nahi mila.")


# ---------------- support: ab sab Mini App me hota hai ----------------
async def on_support_legacy(update: Update, ctx):
    """Purane notification ka Reply button: ab reply Mini App me hota hai."""
    await update.callback_query.answer("Ab support reply app ke andar hota hai: Profile → Support inbox.", show_alert=True)


async def ban_cmd(update: Update, ctx):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    cmd = (update.message.text or "").split()[0].lstrip("/").split("@")[0].lower()
    a = ctx.args
    if not a or not a[0].isdigit() or int(a[0]) in config.ADMIN_IDS:
        return await update.message.reply_text(f"Usage: /{cmd} <user_id>")
    ban = cmd == "ban"
    if await db.set_ban(int(a[0]), ban):
        await update.message.reply_text(f"{'🚫 Banned' if ban else '✅ Unbanned'}: {a[0]}")
    else:
        await update.message.reply_text("User nahi mila.")


# ---------------- admin: gateway test ----------------
async def gw_cmd(update: Update, ctx):
    uid = update.effective_user.id
    if uid not in config.ADMIN_IDS:
        return
    a = ctx.args
    usage = "Usage:\n/gw balance\n/gw create 10\n/gw status <paymentId>"
    if not a:
        return await update.message.reply_text(usage)
    try:
        if a[0] == "balance":
            raw = await gateway.get_balance()
        elif a[0] == "create":
            amount = int(a[1]) if len(a) > 1 and a[1].isdigit() else 10
            res = await gateway.create_order(f"T{uid}{int(time.time())}", amount, "gwtest")
            raw = {"parsed": {k: v for k, v in res.items() if k != "raw"}, "raw": res["raw"]}
        elif a[0] == "status" and len(a) > 1:
            state, amt, raw0 = await gateway.check_payment(a[1])
            raw = {"parsed_state": state, "parsed_amount": str(amt), "raw": raw0}
        else:
            return await update.message.reply_text(usage)
        text = json.dumps(raw, indent=1, ensure_ascii=False, default=str)
    except Exception as e:
        text = f"Error: {type(e).__name__}: {e}"
    for s in (config.GATEWAY_KEY, config.GATEWAY_SECRET):
        if s:
            text = text.replace(s, "***")
    await update.message.reply_text(text[:3800])


# ---------------- admin: apne account me balance ----------------
async def addbal_cmd(update: Update, ctx):
    """/addbalance 5000 (withdraw balance) ya /addbalance ad 5000 (ad balance). Sirf admin, sirf apne account me."""
    uid = update.effective_user.id
    if uid not in config.ADMIN_IDS:
        return
    a = [x.lower() for x in ctx.args if x.lower() != "balance"]  # "/add balance 500" bhi chalega
    ad = bool(a and a[0] == "ad")
    if ad:
        a = a[1:]
    if len(a) != 1 or not a[0].isdigit() or not (0 < int(a[0]) <= 100_000_000):
        return await update.message.reply_text(
            "Usage:\n/addbalance 5000 → withdraw balance me\n/addbalance ad 5000 → ad balance me")
    await db.ensure_user(update.effective_user)
    v = await db.admin_add(uid, int(a[0]), ad)
    await update.message.reply_text(f"✅ +{int(a[0]):,} coins {'ad balance' if ad else 'balance'} me add. Naya: {v:,}")


# ---------------- admin: gift code ----------------
async def gift_cmd(update: Update, ctx):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    a = ctx.args
    if len(a) < 2 or not a[0].isdigit() or not a[1].isdigit() or int(a[0]) < 1 or int(a[1]) < 1:
        return await update.message.reply_text(
            "Usage: /gift <coins> <kitne log use kar sakte> [CODE]\nExample: /gift 500 100  ya  /gift 500 100 DIWALI")
    code = a[2].upper() if len(a) > 2 else secrets.token_hex(4).upper()
    if not re.fullmatch(r"[A-Z0-9]{4,20}", code):
        return await update.message.reply_text("Code 4-20 letters/numbers ka hona chahiye.")
    if not await db.gift_create(code, int(a[0]), int(a[1])):
        return await update.message.reply_text("Ye code pehle se hai. Dusra code chuno.")
    await update.message.reply_text(
        f"🎁 Gift code ban gaya\nCode: <code>{code}</code>\nCoins: {a[0]} per user\nLimit: {a[1]} users", parse_mode="HTML")


# ---------------- admin: withdraw approve/reject ----------------
async def on_admin_wd(update: Update, ctx):
    q = update.callback_query
    if q.from_user.id not in config.ADMIN_IDS:
        return await q.answer("Not allowed", show_alert=True)
    act, wid = q.data.split(":")
    wid = int(wid)

    async def ans(text):
        try:
            await q.answer(text, show_alert=True)
        except TelegramError:
            pass

    tax = config.WITHDRAW_TAX_PERCENT
    main = util.main_bot or ctx.bot  # users ko DM hamesha main bot se (callback backup bot par bhi aa sakta hai)

    async def stale():  # pehle se process ho chuka: ye puraana message bhi hata do
        await ans("Already processed")
        try:
            await q.message.delete()
        except TelegramError:
            pass

    keep = False
    if act == "adm_no":
        w = await db.wd_move_refund(wid, "pending", "rejected")
        if not w:
            return await stale()
        await ans("Rejected & refunded")
        extras.feed(f"❌ Withdraw #{wid} <b>rejected</b>, {w['coins']} coins refund (user <code>{w['user_id']}</code>)")
        await util.notify(main, w["user_id"], f"❌ Withdraw #{wid} reject hua, coins wapas mil gaye.")
    elif act == "adm_ok":
        if payouts.enabled():
            res = await payouts.send(main, wid)
            if res == "skip":
                return await stale()
            if res == "processing":
                await ans("✅ Payout bhej diya (2-5 min me user ko milega)")
                w = await db.wd_get(wid)
                await util.notify(main, w["user_id"], f"⏳ Withdraw #{wid} approve hua, paisa 2-5 minute me aayega.")
            else:
                keep = True  # payouts.send ne naya alert bhej diya
                await ans("⚠️ Payout nahi gaya, naya alert dekho")
        else:
            w = await db.wd_move(wid, "pending", "paid")
            if not w:
                return await stale()
            await ans("✅ Approved — UPI par manually pay kar do")
            await extras.post_payout(w)
            extras.feed(f"✅ Withdraw #{wid} <b>approved (manual paid)</b> ₹{float(w['amount_inr']):.2f} → <code>{html.escape(w['upi'])}</code> (user <code>{w['user_id']}</code>)")
            await util.notify(main, w["user_id"],
                              f"✅ Withdraw #{wid} paid: ₹{float(w['amount_inr']):.2f} → {w['upi']} (tax {tax}% alag se kata)")
    elif act == "adm_paid":
        w = await db.wd_move(wid, "sending", "paid")
        if not w:
            return await stale()
        await ans("✅ Paid mark ho gaya")
        await extras.post_payout(w)
        extras.feed(f"✅ Withdraw #{wid} <b>paid</b> (manual mark) ₹{float(w['amount_inr']):.2f}")
        await util.notify(main, w["user_id"], f"✅ Withdraw #{wid} paid: ₹{float(w['amount_inr']):.2f} → {w['upi']}")
    elif act == "adm_refund":
        w = await db.wd_move_refund(wid, "sending", "failed")
        if not w:
            return await stale()
        await ans("↩️ User ko refund ho gaya")
        extras.feed(f"↩️ Withdraw #{wid} <b>failed</b>, user ko refund")
        await util.notify(main, w["user_id"], f"❌ Withdraw #{wid} fail hua, coins wapas mil gaye.")
    if not keep:
        await extras.bk_delete(wid)  # admins ke saare alert copies delete
        try:
            await q.message.delete()
        except TelegramError:
            pass


# ---------------- chat member events ----------------
def rejoin_msg(got):
    if got:
        return (f"✅ Rejoin ho gaya. <b>{got}</b> coins ({config.REJOIN_PERCENT}%) {config.HOLD_HOURS}h hold me mile. "
                f"Agar koi aur channel leave kiya hai to unhe bhi rejoin karo.")
    return "✅ Rejoin ho gaya. (Is channel ka reward ek baar hi milta hai.) Agar koi aur channel leave kiya hai to unhe bhi rejoin karo."


async def on_chat_member(update: Update, ctx):
    cm = update.chat_member
    uid = cm.new_chat_member.user.id
    cid = cm.chat.id
    was, now = util.in_chat(cm.old_chat_member), util.in_chat(cm.new_chat_member)
    if now and not was:
        await db.record_join(cid, uid)
        got = await db.unblock(cid, uid)
        if got is not None:
            await util.notify(ctx.bot, uid, rejoin_msg(got))
    elif was and not now:
        for r in await db.revoke_by_chat(cid, uid):
            extras.feed(f"🚪 Channel leave — coins cut {r['reward']} (user <code>{uid}</code>)")
            await util.notify(ctx.bot, uid, f"🚫 Tumne channel leave kiya. {r['reward']} coins cut ho gaye aur tasks "
                                            f"block hain jab tak dobara join na karo. Dobara join karne par sirf "
                                            f"{config.REJOIN_PERCENT}% coins milenge ({config.HOLD_HOURS}h hold me).")


# ---------------- background jobs ----------------
async def _release_one(ctx, r):
    st = await util.member_status(ctx.bot, r["chat_id"], r["user_id"])
    if st is None:
        # verify nahi hua (bot hata / API error): is row ko peeche karo taaki baaki holds na ruken
        await db.pool.execute("UPDATE completions SET last_checked=now() WHERE id=$1", r["id"])
        return
    if st:
        if await db.release(r["id"]):
            await util.notify(ctx.bot, r["user_id"], f"✅ {r['reward']} coins released! Ab withdraw kar sakte ho.")
    elif await db.revoke(r["id"]):
        await util.notify(ctx.bot, r["user_id"], "🚫 Channel leave kiya, coins cut. Rejoin karo.")


async def _in_batches(rows, fn, size=10, pause=0.4):
    """Telegram rate limit (~30/s) ke andar rehke parallel kaam."""
    for i in range(0, len(rows), size):
        res = await asyncio.gather(*(fn(r) for r in rows[i:i + size]), return_exceptions=True)
        for x in res:
            if isinstance(x, Exception):
                log.error("job item failed", exc_info=x)
        await asyncio.sleep(pause)


async def job_release(ctx):
    rows = await db.pool.fetch(
        "SELECT * FROM completions WHERE status='hold' AND release_at<=now() ORDER BY last_checked, release_at LIMIT 600")
    await _in_batches(rows, lambda r: _release_one(ctx, r))


async def _recheck_one(ctx, r):
    st = await util.member_status(ctx.bot, r["chat_id"], r["user_id"])
    await db.pool.execute("UPDATE completions SET last_checked=now() WHERE id=$1", r["id"])
    if st is False and await db.revoke(r["id"]):
        await util.notify(ctx.bot, r["user_id"], "🚫 Tumne channel leave kiya. Coins cut ho gaye, tasks block hain "
                                                 "jab tak rejoin na karo.")


async def job_recheck(ctx):
    rows = await db.pool.fetch(
        """SELECT id, chat_id, user_id FROM completions WHERE status IN ('hold','ok')
           ORDER BY last_checked LIMIT 200""")  # hamesha track: koi time limit nahi
    await _in_batches(rows, lambda r: _recheck_one(ctx, r))


async def job_orders(ctx):
    """Webhook na aaye to bhi pending deposits/premium ko gateway se verify karke credit karo."""
    for o in await db.pending_gateway_orders():
        await payments.settle(ctx.bot, o, min_gap=60)
        await asyncio.sleep(0.2)
    await db.orders_expire_old()


async def job_refs(ctx):
    """Dost ke 2 task complete hue -> referrer ko coins."""
    for r in await db.ref_ready():
        rid = await db.ref_complete(r["referred_id"])
        if rid:
            await util.notify(ctx.bot, rid, f"🎉 <b>Refer complete!</b> Tumhare dost ne apne task complete kar liye. "
                                            f"<b>+{config.REFER_REWARD}</b> coins balance me add.")


async def job_wd_expire(ctx):
    """Pending withdraw WITHDRAW_EXPIRE_HOURS me admin ne na approve kiya na reject: expire + coins wapas."""
    for w in await db.wd_expire_pending(config.WITHDRAW_EXPIRE_HOURS):
        await util.notify(ctx.bot, w["user_id"],
                          f"⌛ Withdraw #{w['id']} {config.WITHDRAW_EXPIRE_HOURS} ghante me process nahi hua, isliye expire ho gaya.\n"
                          f"<b>{w['coins']}</b> coins (tax samet) tumhare balance me wapas aa gaye. Chaho to dobara withdraw karo.")
        await extras.bk_delete(w["id"])
        extras.feed(f"⌛ Withdraw #{w['id']} <b>expired</b> (24h), {w['coins']} coins refund (user <code>{w['user_id']}</code>)")


async def job_cleanup(ctx):
    await db.sup_cleanup()
    await db.ledger_prune()


async def job_support_clean(ctx):
    await db.sup_cleanup()


async def ping_cmd(update: Update, ctx):
    """Admin: DB kitna door/slow hai (ms). 100ms+ ho to DB region Render se door hai."""
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    ts = []
    for _ in range(3):
        t = time.monotonic()
        await db.pool.fetchval("SELECT 1")
        ts.append((time.monotonic() - t) * 1000)
    n = await db.pool.fetchval("SELECT count(*) FROM users")
    await update.message.reply_text(
        f"🏓 DB ping: {', '.join(f'{x:.0f}ms' for x in ts)}\nUsers: {n}\n"
        f"(30ms se kam = best, 100ms+ = DB Render ke region se door, app slow lagega)")


async def backup_cmd(update: Update, ctx):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    if not config.BACKUP_BOT_TOKEN:
        return await update.message.reply_text("BACKUP_BOT_TOKEN env set nahi hai.")
    await update.message.reply_text("⏳ Backup bana raha hu... file backup bot se aayegi (usko /start kiya ho).")
    try:
        ok = await extras.send_backup()
    except Exception as e:  # asli wajah user ko dikhao (token galat / DB error)
        log.exception("backup cmd failed")
        return await update.message.reply_text(f"❌ Backup error: {html.escape(type(e).__name__)}: {html.escape(str(e))[:300]}")
    await update.message.reply_text("✅ Backup bhej diya." if ok else "❌ Nahi gaya. Backup bot ko apne account se /start karo, phir dobara /backup bhejo.")


async def job_wd_stuck(ctx):
    """Restart/crash se jin withdrawals ka admin alert gaya hi nahi ya jo atak gaye: admin ko (dobara) alert."""
    for w in await db.wd_stuck():
        if w["status"] == "pending":
            txt = (f"⏰ <b>Withdraw #{w['id']} abhi pending hai</b>\nUser: <code>{w['user_id']}</code>\n"
                   f"₹{float(w['amount_inr']):.2f} → <code>{html.escape(w['upi'])}</code>")
            kb = payouts.admin_kb(w["id"])
        else:
            txt = (f"🚨 <b>Withdraw #{w['id']} 'sending' me atka hai</b>\n₹{float(w['amount_inr']):.2f} → "
                   f"<code>{html.escape(w['upi'])}</code>\nElite Pay dashboard check karo: paisa gaya ho to Mark paid, "
                   f"nahi gaya to Refund.")
            kb = payouts.fix_kb(w["id"])
        await payouts.alert(ctx.bot, txt, kb, wid=w["id"])


async def on_error(update, ctx):
    log.error("Unhandled error", exc_info=ctx.error)


async def backup_start(update: Update, ctx):
    """Backup bot par /start: admin ke liye alerts/backup chalu."""
    if update.effective_user.id in config.ADMIN_IDS:
        await update.message.reply_text("✅ Backup bot chalu. Withdraw requests (Approve/Reject) aur daily backup yahin aayenge.")


def register_backup(app):
    app.add_handler(CommandHandler("start", backup_start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(on_admin_wd, pattern=r"^adm_"))


def register(app):
    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("gift", gift_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler(["bypass", "unbypass"], bypass_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("allowdev", allowdev_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("ping", ping_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("backup", backup_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("gw", gw_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler(["addbalance", "add_balance", "add"], addbal_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("resetdev", resetdev_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(on_support_legacy, pattern=r"^sup_reply:"))
    app.add_handler(CommandHandler(["ban", "unban"], ban_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(on_admin_wd, pattern=r"^adm_"))
    app.add_handler(CallbackQueryHandler(botwork.on_cb, pattern=r"^(bws_|bwa_)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, botwork.on_text))
    app.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_error_handler(on_error)
    app.job_queue.run_repeating(job_release, interval=120, first=60)
    app.job_queue.run_repeating(job_recheck, interval=300, first=120)
    app.job_queue.run_repeating(botwork.job, interval=900, first=180)
    app.job_queue.run_repeating(job_orders, interval=120, first=90)
    app.job_queue.run_repeating(payouts.job, interval=90, first=100)
    app.job_queue.run_repeating(job_refs, interval=60, first=70)
    app.job_queue.run_repeating(job_cleanup, interval=86400, first=600)
    app.job_queue.run_repeating(job_support_clean, interval=3600, first=120)
    app.job_queue.run_repeating(extras.job_bcast, interval=30, first=40)
    app.job_queue.run_daily(extras.job_backup, time=datetime.time(hour=21, minute=30, tzinfo=datetime.timezone.utc))  # ~3:00 AM IST
    app.job_queue.run_repeating(job_wd_stuck, interval=120, first=45)
    app.job_queue.run_repeating(job_wd_expire, interval=600, first=90)
