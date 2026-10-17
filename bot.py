import asyncio
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
import gateway
import payments
import payouts
import util

log = logging.getLogger("bot")


def app_kb():
    return M([[B("🚀 Open App", web_app=WebAppInfo(url=f"{config.BASE_URL}/app"))]])


async def post_init(app):
    try:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Open App", web_app=WebAppInfo(url=f"{config.BASE_URL}/app")))
    except TelegramError:
        log.warning("menu button set nahi hua")


async def start(update: Update, ctx):
    """Har /start par DB se check: device verified nahi to pehle verification (app ke andar)."""
    u = await db.ensure_user(update.effective_user)
    if u["banned"]:
        return await update.message.reply_text("🚫 Tumhara account banned hai.")
    app = html.escape(config.APP_NAME)
    if not u["device_ok"]:
        await update.message.reply_text(
            f"👋 <b>{app} me welcome!</b>\n\n🔐 Shuru karne se pehle <b>Device Verification</b> zaroori hai "
            f"(ek device = ek account).\nNeeche button dabao, Gmail daalo aur verify karo.",
            parse_mode="HTML", reply_markup=M([[B("🔐 Verify Device", web_app=WebAppInfo(url=f"{config.BASE_URL}/app"))]]))
        return
    await update.message.reply_text(
        f"👋 <b>{app}</b>\nChannels join karo, coins kamao aur UPI me withdraw karo 💰\n\n"
        f"Naya phone / data clear karoge to app dobara device verify maangega.\nNeeche button se app kholo 👇",
        parse_mode="HTML", reply_markup=app_kb())


async def resetdev_cmd(update: Update, ctx):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    a = ctx.args
    if not a or not a[0].lstrip("-").isdigit():
        return await update.message.reply_text("Usage: /resetdev <user_id>\nUser ka device/Gmail unlink ho jayega, wo dobara verify karega.")
    if await db.reset_device(int(a[0])):
        await update.message.reply_text(f"✅ User {a[0]} ka device reset ho gaya.")
        await util.notify(ctx.bot, int(a[0]), "🔐 Tumhara device reset ho gaya. App kholo aur dobara verify karo.")
    else:
        await update.message.reply_text("User nahi mila.")


# ---------------- admin: support reply ----------------
async def on_support_reply_btn(update: Update, ctx):
    q = update.callback_query
    aid = q.from_user.id
    if aid not in config.ADMIN_IDS:
        return await q.answer("Not allowed", show_alert=True)
    uid = int(q.data.split(":")[1])
    state = ctx.application.bot_data.setdefault("sup_reply", {})
    old = state.get(aid)
    if old:
        try:
            await ctx.bot.delete_message(aid, old["prompt"])
        except TelegramError:
            pass
    await q.answer()
    prompt = await ctx.bot.send_message(
        aid, f"✍️ User <code>{uid}</code> ko reply likho (cancel: /cancel):", parse_mode="HTML")
    state[aid] = {"uid": uid, "prompt": prompt.message_id}


async def on_admin_text(update: Update, ctx):
    aid = update.effective_user.id
    st = ctx.application.bot_data.get("sup_reply", {}).get(aid)
    if aid not in config.ADMIN_IDS or not st:
        return
    text = (update.message.text or "").strip()[:1000]
    if not text:
        return
    uid = st["uid"]
    ctx.application.bot_data["sup_reply"].pop(aid, None)
    await db.sup_add(uid, "admin", text)
    await util.notify(ctx.bot, uid, f"🎧 <b>Support reply</b>\n\n{html.escape(text)}\n\n"
                                    f"Poori chat: App → Profile → Customer service")
    # reply ho gaya: is user ke saare support notifications aur prompt delete
    for r in await db.sup_notif_pop(uid):
        try:
            await ctx.bot.delete_message(r["admin_id"], r["msg_id"])
        except TelegramError:
            pass
    try:
        await ctx.bot.delete_message(aid, st["prompt"])
    except TelegramError:
        pass


async def cancel_cmd(update: Update, ctx):
    aid = update.effective_user.id
    st = ctx.application.bot_data.get("sup_reply", {}).pop(aid, None)
    if st:
        try:
            await ctx.bot.delete_message(aid, st["prompt"])
        except TelegramError:
            pass
        await update.message.reply_text("Cancel ho gaya. Notification abhi bhi upar hai, Reply dobara dabao.")


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
    if act == "adm_no":
        w = await db.wd_move(wid, "pending", "rejected")
        if not w:
            return await ans("Already processed")
        await db.wd_refund(w)
        await ans("Rejected & refunded")
        await util.notify(ctx.bot, w["user_id"], f"❌ Withdraw #{wid} reject hua, coins wapas mil gaye.")
    elif act == "adm_ok":
        if payouts.enabled():
            res = await payouts.send(ctx.bot, wid)
            if res == "skip":
                return await ans("Already processed")
            if res == "processing":
                await ans("✅ Payout bhej diya (2-5 min me user ko milega)")
                w = await db.wd_get(wid)
                await util.notify(ctx.bot, w["user_id"], f"⏳ Withdraw #{wid} approve hua, paisa 2-5 minute me aayega.")
            else:
                await ans("⚠️ Payout nahi gaya, upar ka alert dekho")
        else:
            w = await db.wd_move(wid, "pending", "paid")
            if not w:
                return await ans("Already processed")
            await ans("✅ Approved — UPI par manually pay kar do")
            await util.notify(ctx.bot, w["user_id"],
                              f"✅ Withdraw #{wid} paid: ₹{float(w['amount_inr']):.2f} → {w['upi']} ({tax}% tax kat ke)")
    elif act == "adm_paid":
        w = await db.wd_move(wid, "sending", "paid")
        if not w:
            return await ans("Already processed")
        await ans("✅ Paid mark ho gaya")
        await util.notify(ctx.bot, w["user_id"], f"✅ Withdraw #{wid} paid: ₹{float(w['amount_inr']):.2f} → {w['upi']}")
    elif act == "adm_refund":
        w = await db.wd_move(wid, "sending", "failed")
        if not w:
            return await ans("Already processed")
        await db.wd_refund(w)
        await ans("↩️ User ko refund ho gaya")
        await util.notify(ctx.bot, w["user_id"], f"❌ Withdraw #{wid} fail hua, coins wapas mil gaye.")
    try:
        await q.edit_message_reply_markup(None)
    except TelegramError:
        pass


# ---------------- chat member events ----------------
async def on_chat_member(update: Update, ctx):
    cm = update.chat_member
    uid = cm.new_chat_member.user.id
    cid = cm.chat.id
    was, now = util.in_chat(cm.old_chat_member), util.in_chat(cm.new_chat_member)
    if now and not was:
        await db.record_join(cid, uid)
        if await db.unblock(cid, uid):
            await util.notify(ctx.bot, uid, "✅ Rejoin ho gaya. Agar koi aur channel leave kiya hai to unhe bhi rejoin karo.")
    elif was and not now:
        for r in await db.revoke_by_chat(cid, uid):
            await util.notify(ctx.bot, uid, f"🚫 Tumne channel leave kiya. {r['reward']} coins cut ho gaye aur tasks "
                                            f"block hain jab tak dobara join na karo.")


# ---------------- background jobs ----------------
async def _release_one(ctx, r):
    st = await util.member_status(ctx.bot, r["chat_id"], r["user_id"])
    if st is None:
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
        "SELECT * FROM completions WHERE status='hold' AND release_at<=now() ORDER BY release_at LIMIT 600")
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
           AND created_at > now() - interval '30 days' ORDER BY last_checked LIMIT 200""")
    await _in_batches(rows, lambda r: _recheck_one(ctx, r))


async def job_orders(ctx):
    """Webhook na aaye to bhi pending deposits/premium ko gateway se verify karke credit karo."""
    for o in await db.pending_gateway_orders():
        await payments.settle(ctx.bot, o, min_gap=60)
        await asyncio.sleep(0.2)


async def on_error(update, ctx):
    log.error("Unhandled error", exc_info=ctx.error)


def register(app):
    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("gift", gift_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("cancel", cancel_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("gw", gw_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler(["addbalance", "add_balance", "add"], addbal_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("resetdev", resetdev_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(on_support_reply_btn, pattern=r"^sup_reply:"))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, on_admin_text))
    app.add_handler(CallbackQueryHandler(on_admin_wd, pattern=r"^adm_"))
    app.add_handler(CallbackQueryHandler(botwork.on_cb, pattern=r"^(bws_|bwa_)"))
    app.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_error_handler(on_error)
    app.job_queue.run_repeating(job_release, interval=120, first=60)
    app.job_queue.run_repeating(job_recheck, interval=300, first=120)
    app.job_queue.run_repeating(botwork.job, interval=900, first=180)
    app.job_queue.run_repeating(job_orders, interval=120, first=90)
    app.job_queue.run_repeating(payouts.job, interval=90, first=100)
