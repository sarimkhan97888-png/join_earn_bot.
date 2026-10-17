import asyncio
import io
import logging
import re
import time
from datetime import datetime, timezone

import qrcode
from telegram import (InlineKeyboardButton as B, InlineKeyboardMarkup as M, LinkPreviewOptions,
                      ReplyKeyboardMarkup, Update, WebAppInfo)
from telegram.error import BadRequest, TelegramError
from telegram.ext import (ApplicationHandlerStop, CallbackQueryHandler, ChatMemberHandler, CommandHandler,
                          ContextTypes, MessageHandler, TypeHandler, filters)

import config
import db
import botwork
import gateway

log = logging.getLogger("bot")

MENU = ReplyKeyboardMarkup([["🏠 Home", "📋 Tasks"], ["💰 Wallet", "👤 Profile"]], resize_keyboard=True)
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
UPI_RE = re.compile(r"^[a-zA-Z0-9.\-_]{2,}@[a-zA-Z]{2,}$")
POPUP_PREFIX = ("chk:", "tk_ok", "tk_cancel", "wd_go", "adm_", "rechk")


def inr(coins):
    return f"₹{coins / config.COIN_PER_INR:,.2f}"


def is_prem(u):
    return bool(u["premium_until"] and u["premium_until"] > datetime.now(timezone.utc))


async def popup(update, text):
    await update.callback_query.answer(text, show_alert=True)


async def show(update, text, kb=None):
    q = update.callback_query
    if q and q.message and not q.message.photo:
        try:
            await q.edit_message_text(text, reply_markup=kb, parse_mode="HTML", link_preview_options=NO_PREVIEW)
            return
        except BadRequest as e:
            if "not modified" in str(e).lower():
                return
    await update.effective_chat.send_message(text, reply_markup=kb, parse_mode="HTML",
                                             link_preview_options=NO_PREVIEW)


async def member_status(bot, chat_id, uid):
    """True = member, False = nahi, None = verify nahi ho paya."""
    try:
        m = await bot.get_chat_member(chat_id, uid)
    except TelegramError:
        return None
    return m.status in ("member", "administrator", "creator") or (m.status == "restricted" and m.is_member)


# ---------------- anti-spam ----------------
_hits = {}


async def throttle(update: Update, ctx):
    if update.chat_member or not update.effective_user:
        return
    uid = update.effective_user.id
    t = time.monotonic()
    L = [x for x in _hits.get(uid, []) if t - x < 10]
    L.append(t)
    _hits[uid] = L
    if len(L) > 8:
        if update.callback_query:
            try:
                await update.callback_query.answer("⏳ Thoda slow chalo", show_alert=True)
            except TelegramError:
                pass
        raise ApplicationHandlerStop


# ---------------- screens ----------------
async def home(update, ctx):
    u = await db.ensure_user(update.effective_user)
    prem = is_prem(u)
    text = (f"🏠 <b>Home</b>\n\n"
            f"💰 Balance: <b>{u['balance']}</b> coins ({inr(u['balance'])})\n"
            f"⏳ Hold (24h): <b>{u['hold']}</b> coins\n"
            f"📈 Total earned: <b>{u['total_earned']}</b> coins ({inr(u['total_earned'])})")
    label = "💎 Premium ✅ Active" if prem else f"💎 Get Premium – ₹{config.PREMIUM_PRICE}/month"
    kb = M([[B(label, callback_data="prem")], [B("🔄 Refresh", callback_data="home")]])
    await show(update, text, kb)


async def tasks_screen(update, ctx):
    uid = update.effective_user.id
    u = await db.ensure_user(update.effective_user)
    if u["banned"]:
        return await show(update, "🚫 Account banned.")
    if not u["device_ok"]:
        return await show(update, "🔐 Tasks ke liye pehle <b>Profile → Verify device</b> karo.",
                          M([[B("👤 Profile", callback_data="profile")]]))
    left = await db.left_chats(uid)
    if left:
        kb = [[B(f"➕ Rejoin: {r['title'][:24]}", url=r["link"])] for r in left]
        kb.append([B("🔄 Re-check", callback_data="rechk")])
        return await show(update, "🚫 <b>Tasks blocked</b>\nTumne channel leave kiya. In sabko dobara join karo, "
                                  "phir Re-check dabao:", M(kb))
    rows = await db.open_tasks(uid)
    kb = []
    for t in rows:
        kb.append([B(f"➕ {t['title'][:22]}", url=t["link"]), B("✅ Check", callback_data=f"chk:{t['id']}")])
    kb.append([B("🤖 Bot Work", callback_data="bw_list")])
    kb.append([B("🔄 Refresh", callback_data="tasks")])
    text = (f"📋 <b>Tasks</b>\nChannel join karo → ✅ Check dabao → <b>+{config.JOIN_REWARD} coins</b> "
            f"({config.HOLD_HOURS}h hold).\n⚠️ Channel leave kiya to coins cut + block.")
    if not rows:
        text += "\n\nAbhi koi task available nahi. Thodi der baad dekho."
    await show(update, text, M(kb))


async def wallet_screen(update, ctx):
    u = await db.ensure_user(update.effective_user)
    text = (f"💰 <b>Wallet</b>\n\n"
            f"Earnings: <b>{u['balance']}</b> coins ({inr(u['balance'])})\n"
            f"Hold: {u['hold']} coins\n"
            f"Ad balance (deposit): <b>{u['ad_balance']}</b> coins\n\n"
            f"100 coins = ₹1 • Min withdraw: {config.MIN_WITHDRAW_COINS} coins")
    kb = M([[B("➕ Deposit", callback_data="dep"), B("➖ Withdraw", callback_data="wd")]])
    await show(update, text, kb)


async def profile_screen(update, ctx):
    tu = update.effective_user
    u = await db.ensure_user(tu)
    text = (f"👤 <b>Profile</b>\n\n"
            f"Name: {tu.first_name}\n"
            f"Username: {'@' + tu.username if tu.username else '—'}\n"
            f"Gmail: {u['gmail'] or '—'}\n"
            f"UPI: {u['upi'] or '—'}\n"
            f"Device: {'✅ Verified' if u['device_ok'] else '❌ Not verified'}\n"
            f"Premium: {'✅ till ' + u['premium_until'].strftime('%d %b %Y') if is_prem(u) else '—'}")
    kb = M([[B("✅ Device verified" if u["device_ok"] else "🔐 Verify device",
               web_app=WebAppInfo(url=f"{config.BASE_URL}/verify"))],
            [B("⚙️ Settings", callback_data="settings"), B("🎧 Support", url=config.SUPPORT_URL)]])
    if update.callback_query:
        try:
            await update.callback_query.message.delete()
        except TelegramError:
            pass
    try:
        ph = await ctx.bot.get_user_profile_photos(tu.id, limit=1)
        if ph.total_count:
            await update.effective_chat.send_photo(ph.photos[0][-1].file_id, caption=text,
                                                   parse_mode="HTML", reply_markup=kb)
            return
    except TelegramError:
        pass
    await update.effective_chat.send_message(text, parse_mode="HTML", reply_markup=kb)


async def premium_screen(update, ctx):
    u = await db.ensure_user(update.effective_user)
    if not is_prem(u):
        text = (f"💎 <b>Premium – ₹{config.PREMIUM_PRICE}/month</b>\n\n"
                f"• Apna channel/group promote karo (Task upload)\n"
                f"• Min {config.MIN_TASK_MEMBERS} members, {config.AD_COST} coins per member\n"
                f"• Real users join karte hain, tumhara channel grow hota hai")
        return await show(update, text, M([[B(f"💳 Pay ₹{config.PREMIUM_PRICE} (QR)", callback_data="prem_buy")],
                                           [B("⬅️ Back", callback_data="home")]]))
    text = (f"💎 <b>Premium Active</b> till {u['premium_until'].strftime('%d %b %Y')}\n\n"
            f"Ad balance: <b>{u['ad_balance']}</b> coins\n"
            f"Per member cost: {config.AD_COST} coins • Min {config.MIN_TASK_MEMBERS} members")
    kb = M([[B("➕ Add Task", callback_data="task_add"), B("📊 My Tasks", callback_data="tk_my")],
            [B("🤖 Add Bot Work", callback_data="bw_add"), B("📊 My Bot Works", callback_data="bw_my")],
            [B("➕ Deposit coins", callback_data="dep")], [B("⬅️ Back", callback_data="home")]])
    await show(update, text, kb)


async def my_tasks_screen(update, ctx):
    rows = await db.my_tasks(update.effective_user.id)
    if not rows:
        return await show(update, "📊 Abhi tumne koi task nahi banaya.", M([[B("⬅️ Back", callback_data="prem")]]))
    lines, kb = ["📊 <b>My Tasks</b>\n"], []
    for t in rows:
        lines.append(f"#{t['id']} {t['title'][:24]} — {t['joined']}/{t['target']} • {t['status']}")
        if t["status"] == "active":
            kb.append([B(f"❌ Cancel #{t['id']} (refund)", callback_data=f"tk_cancel:{t['id']}")])
    kb.append([B("⬅️ Back", callback_data="prem")])
    await show(update, "\n".join(lines), M(kb))


async def send_qr(chat, res, caption):
    if res.get("qr_url"):
        await chat.send_photo(res["qr_url"], caption=caption, parse_mode="HTML")
    elif res.get("upi_url"):
        bio = io.BytesIO()
        qrcode.make(res["upi_url"]).save(bio, "PNG")
        bio.seek(0)
        await chat.send_photo(bio, caption=caption, parse_mode="HTML")
    else:
        await chat.send_message(f"{caption}\n\n{res.get('pay_url', '')}", parse_mode="HTML")


async def start_order(update, ctx, kind, coins, amount):
    uid = update.effective_user.id
    order_id = f"{kind[0].upper()}{uid}{int(time.time())}"
    try:
        res = await gateway.create_order(order_id, amount, f"{kind} {uid}")
    except Exception:
        log.exception("gateway create_order failed")
        return await update.effective_chat.send_message("❌ Payment gateway abhi available nahi. Baad me try karo.")
    await db.new_order(order_id, uid, kind, coins, amount)
    cap = f"💳 <b>Pay ₹{amount}</b>\nOrder: <code>{order_id}</code>\nPayment hote hi automatically confirm ho jayega."
    await send_qr(update.effective_chat, res, cap)


# ---------------- commands / menu ----------------
async def start(update: Update, ctx):
    await db.ensure_user(update.effective_user)
    ctx.user_data.clear()
    await update.message.reply_text("👋 Welcome! Channels join karo aur coins kamao 💰", reply_markup=MENU)
    await home(update, ctx)


async def on_menu(update: Update, ctx):
    ctx.user_data.clear()
    t = update.message.text
    await {"🏠 Home": home, "📋 Tasks": tasks_screen, "💰 Wallet": wallet_screen, "👤 Profile": profile_screen}[t](update, ctx)


# ---------------- callbacks ----------------
async def on_cb(update: Update, ctx):
    q = update.callback_query
    d = q.data
    uid = q.from_user.id
    if d.startswith(("bw_", "bws_", "bwa_")):
        return await botwork.on_cb(update, ctx)
    if not d.startswith(POPUP_PREFIX):
        await q.answer()

    if d == "home":
        ctx.user_data.clear()
        return await home(update, ctx)
    if d == "tasks":
        return await tasks_screen(update, ctx)
    if d == "wallet":
        return await wallet_screen(update, ctx)
    if d == "profile":
        return await profile_screen(update, ctx)
    if d == "prem":
        return await premium_screen(update, ctx)
    if d == "cancel":
        ctx.user_data.clear()
        return await home(update, ctx)
    if d == "tk_my":
        return await my_tasks_screen(update, ctx)

    if d == "prem_buy":
        return await start_order(update, ctx, "premium", 0, config.PREMIUM_PRICE)

    if d == "settings":
        u = await db.get_user(uid)
        return await show(update, f"⚙️ <b>Settings</b>\n\nUPI: {u['upi'] or '—'}",
                          M([[B("✏️ Set / Change UPI", callback_data="set_upi")],
                             [B("⬅️ Back", callback_data="profile")]]))
    if d == "set_upi":
        ctx.user_data["st"] = "set_upi"
        return await show(update, "UPI ID bhejo (e.g. name@upi):", M([[B("❌ Cancel", callback_data="cancel")]]))

    if d == "dep":
        ctx.user_data["st"] = "dep"
        return await show(
            update,
            f"➕ <b>Deposit</b>\nKitne coins chahiye? Min <b>{config.MIN_DEPOSIT_COINS}</b> coins "
            f"({inr(config.MIN_DEPOSIT_COINS)}), 100 ke multiple me.\nJitne coins, utna hi QR banega.",
            M([[B("❌ Cancel", callback_data="cancel")]]))

    if d == "wd":
        u = await db.get_user(uid)
        if not u["device_ok"]:
            return await show(update, "🔐 Withdraw ke liye pehle device verify karo.",
                              M([[B("👤 Profile", callback_data="profile")]]))
        if await db.is_blocked(uid):
            return await show(update, "🚫 Tum blocked ho. Pehle Tasks me left channels rejoin karo.",
                              M([[B("📋 Tasks", callback_data="tasks")]]))
        if u["balance"] < config.MIN_WITHDRAW_COINS:
            return await show(update, f"❌ Min withdraw {config.MIN_WITHDRAW_COINS} coins. "
                                      f"Tumhare paas {u['balance']} hain.", M([[B("⬅️ Back", callback_data="wallet")]]))
        ctx.user_data["st"] = "wd"
        return await show(update, f"➖ <b>Withdraw</b>\nBalance: {u['balance']} coins\nKitne coins? "
                                  f"(min {config.MIN_WITHDRAW_COINS}, 100 ke multiple me)",
                          M([[B("❌ Cancel", callback_data="cancel")]]))

    if d == "task_add":
        u = await db.get_user(uid)
        if not is_prem(u):
            return await premium_screen(update, ctx)
        ctx.user_data["st"] = "task_chat"
        return await show(
            update,
            "➕ <b>Add Task</b>\n1) Bot ko apne channel/group me <b>Admin</b> banao (Invite Users permission ke saath)\n"
            "2) Channel ka <code>@username</code> bhejo ya channel ka koi post forward karo.",
            M([[B("❌ Cancel", callback_data="cancel")]]))

    if d == "tk_ok":
        tk = ctx.user_data.pop("tk", None)
        if not tk or "n" not in tk:
            return await popup(update, "Session expire. Dobara Add Task karo.")
        tid = await db.create_task(uid, tk["chat_id"], tk["title"], tk["link"], tk["n"])
        if not tid:
            return await popup(update, "❌ Ad balance kam hai. Pehle deposit karo.")
        await popup(update, f"✅ Task #{tid} live ho gaya!")
        return await my_tasks_screen(update, ctx)

    if d.startswith("tk_cancel:"):
        refund = await db.cancel_task(int(d.split(":")[1]), uid)
        if refund is None:
            return await popup(update, "Task cancel nahi ho sakta.")
        await popup(update, f"✅ Task cancelled. {refund} coins refund hue.")
        return await my_tasks_screen(update, ctx)

    if d.startswith("chk:"):
        return await do_check(update, ctx, int(d.split(":")[1]))

    if d == "rechk":
        fixed = 0
        for r in await db.left_chats(uid):
            if await member_status(ctx.bot, r["chat_id"], uid):
                fixed += await db.unblock(r["chat_id"], uid)
        await popup(update, "✅ Unblocked!" if fixed else "❌ Abhi bhi kuch channels join nahi kiye.")
        return await tasks_screen(update, ctx)

    if d == "wd_go":
        coins = ctx.user_data.pop("wd", None)
        if not coins:
            return await popup(update, "Session expire. Dobara try karo.")
        r = await db.request_withdraw(uid, coins)
        if not r:
            return await popup(update, "❌ Withdraw nahi ho paya (balance/verification check karo).")
        wid, upi = r
        await popup(update, "✅ Withdraw request bhej di gayi!")
        await show(update, f"✅ Withdraw #{wid} submitted\n{coins} coins → {inr(coins)} to <code>{upi}</code>\n"
                           f"Status: pending")
        for a in config.ADMIN_IDS:
            try:
                await ctx.bot.send_message(
                    a, f"💸 Withdraw #{wid}\nUser: <code>{uid}</code>\n{inr(coins)} → <code>{upi}</code>",
                    parse_mode="HTML",
                    reply_markup=M([[B("✅ Approve", callback_data=f"adm_ok:{wid}"),
                                     B("❌ Reject", callback_data=f"adm_no:{wid}")]]))
            except TelegramError:
                pass
        return

    if d.startswith("adm_"):
        if uid not in config.ADMIN_IDS:
            return await popup(update, "Not allowed")
        act, wid = d.split(":")
        wid = int(wid)
        if act == "adm_no":
            w = await db.wd_move(wid, "pending", "rejected")
            if not w:
                return await popup(update, "Already processed")
            await db.wd_refund(w)
            await popup(update, "Rejected & refunded")
            await notify(ctx, w["user_id"], f"❌ Withdraw #{wid} reject hua, coins wapas mil gaye.")
        else:
            w = await db.wd_move(wid, "pending", "processing")
            if not w:
                return await popup(update, "Already processed")
            ok = True
            if config.AUTO_PAYOUT:
                try:
                    ok = await gateway.payout(w["upi"], w["amount_inr"], f"WD{wid}")
                except Exception:
                    log.exception("payout failed")
                    ok = False
            if not ok:
                await db.wd_move(wid, "processing", "pending")
                return await popup(update, "❌ Payout fail hua. Dobara try karo.")
            await db.wd_move(wid, "processing", "paid")
            await popup(update, "✅ Approved" + ("" if config.AUTO_PAYOUT else " — UPI par manually pay kar do"))
            await notify(ctx, w["user_id"], f"✅ Withdraw #{wid} paid: {inr(w['coins'])} → {w['upi']}")
        try:
            await q.edit_message_reply_markup(None)
        except TelegramError:
            pass


async def notify(ctx, uid, text):
    try:
        await ctx.bot.send_message(uid, text, parse_mode="HTML")
    except TelegramError:
        pass


async def do_check(update, ctx, tid):
    q = update.callback_query
    uid = q.from_user.id
    u = await db.ensure_user(q.from_user)
    if u["banned"]:
        return await popup(update, "🚫 Account banned.")
    if not u["device_ok"]:
        return await popup(update, "🔐 Pehle Profile me device verify karo.")
    if await db.is_blocked(uid):
        return await popup(update, "🚫 Tum blocked ho. Pehle left channel rejoin karo.")
    t = await db.get_task(tid)
    if not t or t["status"] != "active":
        await popup(update, "Ye task ab available nahi.")
        return await tasks_screen(update, ctx)
    st = await member_status(ctx.bot, t["chat_id"], uid)
    if st is None:
        return await popup(update, "⚠️ Verify nahi ho paya. Thodi der baad try karo.")
    if not st:
        return await popup(update, "❌ Pehle channel join karo, phir Check dabao.")
    if not await db.joined_after(t["chat_id"], uid, t["created_at"]):
        return await popup(update, "❌ Join record nahi mila. Channel leave karke fir se join karo, phir Check dabao.")
    res = await db.claim(tid, uid)
    msgs = {"ok": f"✅ Join verified! +{config.JOIN_REWARD} coins ({config.HOLD_HOURS}h hold me)",
            "dup": "Ye task tum pehle kar chuke ho.", "own": "Apna channel join karke coin nahi mil sakta.",
            "closed": "Task full ho gaya."}
    await popup(update, msgs[res])
    await tasks_screen(update, ctx)


# ---------------- text input states ----------------
async def on_text(update: Update, ctx):
    st = ctx.user_data.get("st")
    if not st:
        return
    m = update.message
    uid = m.from_user.id
    text = (m.text or "").strip()
    cancel_kb = M([[B("❌ Cancel", callback_data="cancel")]])

    if st.startswith("bw_"):
        return await botwork.on_text(update, ctx, st)

    if st == "task_chat":
        ident = None
        fo = m.forward_origin
        if fo is not None and getattr(fo, "chat", None) is not None:
            ident = fo.chat.id
        elif text.startswith("@"):
            ident = text
        elif "t.me/" in text:
            slug = text.split("t.me/")[-1].split("/")[0].split("?")[0]
            ident = "@" + slug if slug and not slug.startswith("+") else None
        elif text.lstrip("-").isdigit():
            ident = int(text)
        if ident is None:
            return await m.reply_text("❌ @username bhejo ya channel ka post forward karo.", reply_markup=cancel_kb)
        try:
            chat = await ctx.bot.get_chat(ident)
        except TelegramError:
            return await m.reply_text("❌ Chat nahi mili. Bot ko pehle admin banao.", reply_markup=cancel_kb)
        if chat.type not in ("channel", "group", "supergroup"):
            return await m.reply_text("❌ Sirf channel ya group allowed hai.", reply_markup=cancel_kb)
        try:
            me = await ctx.bot.get_chat_member(chat.id, ctx.bot.id)
        except TelegramError:
            me = None
        if not me or me.status != "administrator":
            return await m.reply_text("❌ Bot is chat me <b>admin</b> nahi hai. Admin banao, phir dobara bhejo.",
                                      parse_mode="HTML", reply_markup=cancel_kb)
        try:
            um = await ctx.bot.get_chat_member(chat.id, uid)
        except TelegramError:
            um = None
        if not um or um.status not in ("creator", "administrator"):
            return await m.reply_text("❌ Tum is chat ke admin/owner nahi ho.", reply_markup=cancel_kb)
        if chat.username:
            link = f"https://t.me/{chat.username}"
        else:
            try:
                link = (await ctx.bot.create_chat_invite_link(chat.id)).invite_link
            except TelegramError:
                return await m.reply_text("❌ Invite link nahi ban paya. Bot ko 'Invite Users' permission do.",
                                          reply_markup=cancel_kb)
        ctx.user_data["tk"] = {"chat_id": chat.id, "title": chat.title or str(chat.id), "link": link}
        ctx.user_data["st"] = "task_count"
        return await m.reply_text(
            f"✅ <b>{chat.title}</b> verified (bot admin ✔).\nKitne members chahiye? Min {config.MIN_TASK_MEMBERS}.\n"
            f"Cost: {config.AD_COST} coins per member.", parse_mode="HTML", reply_markup=cancel_kb)

    if st == "task_count":
        if not text.isdigit() or not (config.MIN_TASK_MEMBERS <= int(text) <= config.MAX_TASK_MEMBERS):
            return await m.reply_text(f"❌ {config.MIN_TASK_MEMBERS} se {config.MAX_TASK_MEMBERS} ke beech number bhejo.",
                                      reply_markup=cancel_kb)
        n = int(text)
        cost = n * config.AD_COST
        u = await db.get_user(uid)
        if u["ad_balance"] < cost:
            ctx.user_data.pop("st", None)
            return await m.reply_text(
                f"❌ Coins kam hain.\nChahiye: {cost}\nAd balance: {u['ad_balance']}\nKami: {cost - u['ad_balance']}",
                reply_markup=M([[B("➕ Deposit", callback_data="dep")]]))
        ctx.user_data["tk"]["n"] = n
        ctx.user_data.pop("st", None)
        tk = ctx.user_data["tk"]
        return await m.reply_text(
            f"📝 <b>Confirm Task</b>\nChat: {tk['title']}\nMembers: {n}\nCost: {cost} coins",
            parse_mode="HTML",
            reply_markup=M([[B("✅ Confirm", callback_data="tk_ok"), B("❌ Cancel", callback_data="cancel")]]))

    if st == "dep":
        if not text.isdigit():
            return await m.reply_text("❌ Sirf number bhejo.", reply_markup=cancel_kb)
        coins = int(text)
        if coins < config.MIN_DEPOSIT_COINS or coins % config.COIN_PER_INR:
            return await m.reply_text(f"❌ Min {config.MIN_DEPOSIT_COINS} coins aur 100 ke multiple me.",
                                      reply_markup=cancel_kb)
        ctx.user_data.pop("st", None)
        return await start_order(update, ctx, "deposit", coins, coins // config.COIN_PER_INR)

    if st == "wd":
        u = await db.get_user(uid)
        if not text.isdigit():
            return await m.reply_text("❌ Sirf number bhejo.", reply_markup=cancel_kb)
        coins = int(text)
        if coins < config.MIN_WITHDRAW_COINS or coins % config.COIN_PER_INR or coins > u["balance"]:
            return await m.reply_text(
                f"❌ Min {config.MIN_WITHDRAW_COINS}, 100 ke multiple me, aur max {u['balance']}.",
                reply_markup=cancel_kb)
        ctx.user_data["wd"] = coins
        if not u["upi"]:
            ctx.user_data["st"] = "wd_upi"
            return await m.reply_text("UPI ID bhejo (e.g. name@upi):", reply_markup=cancel_kb)
        ctx.user_data.pop("st", None)
        return await m.reply_text(
            f"Confirm withdraw: {coins} coins → {inr(coins)}\nUPI: <code>{u['upi']}</code>", parse_mode="HTML",
            reply_markup=M([[B("✅ Confirm", callback_data="wd_go"), B("❌ Cancel", callback_data="cancel")]]))

    if st in ("wd_upi", "set_upi"):
        if not UPI_RE.match(text):
            return await m.reply_text("❌ UPI ID sahi nahi hai (e.g. name@upi).", reply_markup=cancel_kb)
        if not await db.set_upi(uid, text.lower()):
            return await m.reply_text("❌ Ye UPI kisi aur account se linked hai.", reply_markup=cancel_kb)
        if st == "set_upi":
            ctx.user_data.clear()
            return await m.reply_text("✅ UPI save ho gaya.")
        ctx.user_data.pop("st", None)
        coins = ctx.user_data.get("wd", 0)
        return await m.reply_text(
            f"Confirm withdraw: {coins} coins → {inr(coins)}\nUPI: <code>{text.lower()}</code>", parse_mode="HTML",
            reply_markup=M([[B("✅ Confirm", callback_data="wd_go"), B("❌ Cancel", callback_data="cancel")]]))


# ---------------- chat member events ----------------
def _in(cm):
    return cm.status in ("member", "administrator", "creator") or (cm.status == "restricted" and cm.is_member)


async def on_chat_member(update: Update, ctx):
    cm = update.chat_member
    uid = cm.new_chat_member.user.id
    cid = cm.chat.id
    was, now = _in(cm.old_chat_member), _in(cm.new_chat_member)
    if now and not was:
        await db.record_join(cid, uid)
        if await db.unblock(cid, uid):
            await notify(ctx, uid, "✅ Rejoin ho gaya. Agar koi aur channel leave kiya hai to unhe bhi rejoin karo.")
    elif was and not now:
        for r in await db.revoke_by_chat(cid, uid):
            await notify(ctx, uid, f"🚫 Tumne channel leave kiya. {r['reward']} coins cut ho gaye aur tasks block hain "
                                   f"jab tak dobara join na karo.")


# ---------------- background jobs ----------------
async def job_release(ctx):
    rows = await db.pool.fetch("SELECT * FROM completions WHERE status='hold' AND release_at<=now() LIMIT 200")
    for r in rows:
        st = await member_status(ctx.bot, r["chat_id"], r["user_id"])
        if st is None:
            continue
        if st:
            if await db.release(r["id"]):
                await notify(ctx, r["user_id"], f"✅ {r['reward']} coins released! Ab withdraw kar sakte ho.")
        else:
            if await db.revoke(r["id"]):
                await notify(ctx, r["user_id"], "🚫 Channel leave kiya, coins cut. Rejoin karo.")
        await asyncio.sleep(0.05)


async def job_recheck(ctx):
    rows = await db.pool.fetch(
        """SELECT id, chat_id, user_id FROM completions WHERE status IN ('hold','ok')
           AND created_at > now() - interval '30 days' ORDER BY last_checked LIMIT 100""")
    for r in rows:
        st = await member_status(ctx.bot, r["chat_id"], r["user_id"])
        await db.pool.execute("UPDATE completions SET last_checked=now() WHERE id=$1", r["id"])
        if st is False and await db.revoke(r["id"]):
            await notify(ctx, r["user_id"], "🚫 Tumne channel leave kiya. Coins cut ho gaye, tasks block hain "
                                            "jab tak rejoin na karo.")
        await asyncio.sleep(0.05)


async def on_error(update, ctx):
    log.error("Unhandled error", exc_info=ctx.error)


def register(app):
    app.add_handler(TypeHandler(Update, throttle), group=-1)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(r"^(🏠 Home|📋 Tasks|💰 Wallet|👤 Profile)$"), on_menu))
    app.add_handler(CallbackQueryHandler(on_cb))
    app.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    app.job_queue.run_repeating(job_release, interval=300, first=60)
    app.job_queue.run_repeating(job_recheck, interval=600, first=120)
    app.job_queue.run_repeating(botwork.job, interval=900, first=180)
