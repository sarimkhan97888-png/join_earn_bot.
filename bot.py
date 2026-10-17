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
    await db.ensure_user(update.effective_user)
    await update.message.reply_text(
        "👋 <b>Welcome!</b>\nChannels join karo, coins kamao aur UPI me withdraw karo 💰\n\nNeeche button se app kholo 👇",
        parse_mode="HTML", reply_markup=app_kb())


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
    if act == "adm_no":
        w = await db.wd_move(wid, "pending", "rejected")
        if not w:
            return await q.answer("Already processed", show_alert=True)
        await db.wd_refund(w)
        await q.answer("Rejected & refunded", show_alert=True)
        await util.notify(ctx.bot, w["user_id"], f"❌ Withdraw #{wid} reject hua, coins wapas mil gaye.")
    else:
        w = await db.wd_move(wid, "pending", "processing")
        if not w:
            return await q.answer("Already processed", show_alert=True)
        done = True
        if config.AUTO_PAYOUT:
            try:
                done = await gateway.payout(w["upi"], float(w["amount_inr"]), f"WD{wid}")
            except Exception:
                log.exception("payout failed")
                done = False
        if not done:
            await db.wd_move(wid, "processing", "pending")
            return await q.answer("❌ Payout fail hua. Dobara try karo.", show_alert=True)
        await db.wd_move(wid, "processing", "paid")
        await q.answer("✅ Approved" + ("" if config.AUTO_PAYOUT else " — UPI par manually pay kar do"),
                       show_alert=True)
        await util.notify(ctx.bot, w["user_id"],
                          f"✅ Withdraw #{wid} paid: ₹{float(w['amount_inr']):.2f} → {w['upi']} (10% tax kat ke)")
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
async def job_release(ctx):
    rows = await db.pool.fetch("SELECT * FROM completions WHERE status='hold' AND release_at<=now() LIMIT 200")
    for r in rows:
        st = await util.member_status(ctx.bot, r["chat_id"], r["user_id"])
        if st is None:
            continue
        if st:
            if await db.release(r["id"]):
                await util.notify(ctx.bot, r["user_id"], f"✅ {r['reward']} coins released! Ab withdraw kar sakte ho.")
        elif await db.revoke(r["id"]):
            await util.notify(ctx.bot, r["user_id"], "🚫 Channel leave kiya, coins cut. Rejoin karo.")
        await asyncio.sleep(0.05)


async def job_recheck(ctx):
    rows = await db.pool.fetch(
        """SELECT id, chat_id, user_id FROM completions WHERE status IN ('hold','ok')
           AND created_at > now() - interval '30 days' ORDER BY last_checked LIMIT 100""")
    for r in rows:
        st = await util.member_status(ctx.bot, r["chat_id"], r["user_id"])
        await db.pool.execute("UPDATE completions SET last_checked=now() WHERE id=$1", r["id"])
        if st is False and await db.revoke(r["id"]):
            await util.notify(ctx.bot, r["user_id"], "🚫 Tumne channel leave kiya. Coins cut ho gaye, tasks block hain "
                                                     "jab tak rejoin na karo.")
        await asyncio.sleep(0.05)


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
    app.add_handler(CallbackQueryHandler(on_support_reply_btn, pattern=r"^sup_reply:"))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, on_admin_text))
    app.add_handler(CallbackQueryHandler(on_admin_wd, pattern=r"^adm_"))
    app.add_handler(CallbackQueryHandler(botwork.on_cb, pattern=r"^(bws_|bwa_)"))
    app.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_error_handler(on_error)
    app.job_queue.run_repeating(job_release, interval=300, first=60)
    app.job_queue.run_repeating(job_recheck, interval=600, first=120)
    app.job_queue.run_repeating(botwork.job, interval=900, first=180)
    app.job_queue.run_repeating(job_orders, interval=120, first=90)
