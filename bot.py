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
from telegram.ext import CallbackQueryHandler, ChatMemberHandler, CommandHandler, MessageHandler, PreCheckoutQueryHandler, filters

import adminops
import botwork
import config
import db
import extras
import i18n
import payments
import payouts
import util

log = logging.getLogger("bot")


def app_kb(lang="en"):
    return M([[B(i18n.tr("🚀 Open App", lang), web_app=WebAppInfo(url=f"{config.BASE_URL}/app"))]])


async def post_init(app):
    util.main_bot = app.bot
    try:
        await app.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Open App", web_app=WebAppInfo(url=f"{config.BASE_URL}/app")))
    except TelegramError:
        log.warning("menu button set nahi hua")


_last_start = {}

WELCOME = util.WELCOME


async def intro_anim(update):
    """Naye user ke liye ek message jo letter-by-letter 'PROFITIX' banta hai, phir delete. Fail ho to chupchap skip."""
    frames = ["💎", "💎 𝐏𝐑", "💎 𝐏𝐑𝐎𝐅𝐈", "💎 𝐏𝐑𝐎𝐅𝐈𝐓𝐈𝐗", "💰 𝐏𝐑𝐎𝐅𝐈𝐓𝐈𝐗 ✨"]
    try:
        m = await update.message.reply_text(frames[0])
        for f in frames[1:]:
            await asyncio.sleep(0.6)
            await m.edit_text(f)
        await asyncio.sleep(0.8)
        await m.delete()
    except Exception:
        pass


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
    L = u["lang"] or "en"
    i18n.remember(tu.id, u["lang"])
    T = lambda s: i18n.tr(s, L)
    if u["banned"]:
        return await update.message.reply_text(T("🚫 Tumhara account banned hai."))
    if not existed and ctx.args and re.fullmatch(r"r\d{1,15}", ctx.args[0]):
        await db.ref_add(tu.id, int(ctx.args[0][1:]))  # sirf bilkul naya user refer ban sakta hai
    await intro_anim(update)  # har /start par chhota "PROFITIX" animation (naya ho ya purana)
    app = html.escape(config.APP_NAME)
    if left:
        rows = [[B(T(f"➕ Join {r['title'][:28]}"), url=r["link"])] for r in left if r["link"]]
        rows.append([B(T("🚀 Open App"), web_app=WebAppInfo(url=f"{config.BASE_URL}/app"))])
        names = "\n".join("• " + html.escape(r["title"]) for r in left)
        return await update.message.reply_text(
            T(f"🚫 <b>App block hai</b>\nTumne ye channel leave kar diya hai:\n{names}\n\n"
              f"Dobara join karo, phir app me <b>Re-check</b> dabao."), parse_mode="HTML", reply_markup=M(rows))
    if not u["device_ok"]:
        await update.message.reply_text(
            T(f"👋 <b>{app} me welcome!</b>\n\n🔐 Shuru karne se pehle <b>Device Verification</b> zaroori hai "
              f"(ek device = ek account).\nNeeche button dabao, verification page khulega. Pass hone par yahin bot par wapas aa jaoge, phir app khulega."),
            parse_mode="HTML", reply_markup=M([[B(T("🔐 Verify Device"), web_app=WebAppInfo(url=f"{config.BASE_URL}/app?v=1"))]]))
        return
    kb = app_kb(L)
    if tu.id in config.ADMIN_IDS:
        kb = M(kb.inline_keyboard + adminops.panel_kb().inline_keyboard)
    await update.message.reply_text(T(WELCOME), parse_mode="HTML", reply_markup=kb)


async def lang_cmd(update: Update, ctx):
    """/language : bhasha badlo."""
    await update.message.reply_text(util.LANG_PROMPT, parse_mode="HTML", reply_markup=util.lang_kb("langc"))


async def on_lang(update: Update, ctx):
    """lang:xx = verify ke baad pehli baar (phir welcome bhejo), langc:xx = baad me badalna."""
    q = update.callback_query
    kind, _, l = q.data.partition(":")
    if l not in i18n.LANGS:
        return await q.answer()
    uid = q.from_user.id
    await db.set_lang(uid, l)
    i18n.remember(uid, l)
    try:
        await q.answer()
        await q.edit_message_text(f"✅ {util.LANG_NAMES[l]}")
    except TelegramError:
        pass
    if kind == "lang":
        u = await db.get_user(uid)
        kb = app_kb(l)
        if uid in config.ADMIN_IDS:
            kb = M(kb.inline_keyboard + adminops.panel_kb().inline_keyboard)
        await util.notify(ctx.bot, uid, WELCOME + "\n\n👇 Ab app kholo", reply_markup=kb)


async def admin_cmd(update: Update, ctx):
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    await update.message.reply_text("🛠 Admin Panel", reply_markup=adminops.panel_kb())


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
    main = util.main_bot or ctx.bot  # users ko DM hamesha main bot se (callback backup bot par bhi aa sakta hai)
    _, msg = await adminops.wd_act(main, int(wid), act[4:])
    try:
        await q.answer(msg, show_alert=True)
    except TelegramError:
        pass
    try:
        await q.message.delete()  # kaam ho gaya ya pehle ho chuka: ye message hata do
    except TelegramError:
        pass


# ---------------- admin: deposit claims / unmatched ----------------
async def on_admin_claim(update: Update, ctx):
    q = update.callback_query
    if q.from_user.id not in config.ADMIN_IDS:
        return await q.answer("Not allowed", show_alert=True)
    act, cid = q.data.split(":")
    _, msg = await adminops.claim_act(util.main_bot or ctx.bot, int(cid), act == "clm_ok")
    try:
        await q.answer(msg, show_alert=True)
        await q.message.delete()
    except TelegramError:
        pass


async def on_ignore(update: Update, ctx):
    q = update.callback_query
    if q.from_user.id not in config.ADMIN_IDS:
        return await q.answer("Not allowed", show_alert=True)
    _, msg = await adminops.ignore_pay(q.data.split(":", 1)[1])
    try:
        await q.answer(msg, show_alert=True)
        await q.message.delete()
    except TelegramError:
        pass


async def on_usdt_ignore(update: Update, ctx):
    q = update.callback_query
    if q.from_user.id not in config.ADMIN_IDS:
        return await q.answer("Not allowed", show_alert=True)
    prefix = q.data.split(":", 1)[1]
    row = await db.pool.fetchrow("SELECT tx FROM usdt_txs WHERE tx LIKE $1 AND status='unmatched' LIMIT 1", prefix + "%")
    _, msg = await adminops.usdt_ignore(row["tx"]) if row else (False, "Already processed")
    try:
        await q.answer(msg, show_alert=True)
        await q.message.delete()
    except TelegramError:
        pass


async def uassign_cmd(update: Update, ctx):
    """/uassign <tx_hash> <user_id>: unmatched USDT transfer kisi user ke ad balance me."""
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    a = ctx.args
    if len(a) != 2 or not a[1].isdigit():
        return await update.message.reply_text("Usage: /uassign <tx_hash> <user_id>")
    _, msg = await adminops.usdt_assign(util.main_bot or ctx.bot, a[0].lower(), int(a[1]))
    await update.message.reply_text(msg)


async def bc_cmd(update: Update, ctx):
    """Admin: /bc <text> ya photo bhejo jiske caption me /bc <text>. Sab users ko jata hai + app ke Notifications page me dikhta hai."""
    m = update.effective_message
    if update.effective_user.id not in config.ADMIN_IDS or not m:
        return
    raw = (m.caption_html if m.photo else m.text_html) or ""
    text = re.sub(r"^/bc(@\w+)?\s*", "", raw.strip()).strip()
    photo = m.photo[-1].file_id if m.photo else None
    if not text and not photo:
        return await m.reply_text("Usage: <code>/bc aapka message</code>\nPhoto ke saath: photo bhejo aur caption me <code>/bc message</code> likho.", parse_mode="HTML")
    nid, n = await db.news_add(text, photo)
    await m.reply_text(f"✅ Broadcast #{nid} queue me hai. ~{n} users ko jayega (thoda time lagta hai) aur app ke 🔔 Notifications me dikhega.")


async def gpcode_cmd(update: Update, ctx):
    """/gpcode <id> <code> (Google Play / Amazon) ya /txid <id> <TxHash> (USDT): user ko bhejo, withdraw paid ho jata hai."""
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    a = ctx.args
    if len(a) < 2 or not a[0].isdigit():
        return await update.message.reply_text("Usage: /gpcode <withdraw_id> <code>  ya  /txid <withdraw_id> <TxHash>")
    _, msg = await adminops.wd_act(util.main_bot or ctx.bot, int(a[0]), "ok", " ".join(a[1:]))
    await update.message.reply_text(msg)


async def assign_cmd(update: Update, ctx):
    """/assign <txn_id> <user_id>: unmatched payment kisi user ke ad balance me."""
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    a = ctx.args
    if len(a) != 2 or not a[1].isdigit():
        return await update.message.reply_text("Usage: /assign <txn_id> <user_id>")
    _, msg = await adminops.assign(util.main_bot or ctx.bot, a[0].upper(), int(a[1]))
    await update.message.reply_text(msg)


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
    """Purane unpaid Fam / Stars orders band karo."""
    await db.fam_expire_old()
    await db.orders_expire_old()


async def job_refs(ctx):
    """Dost ke 2 task complete hue -> referrer ko coins."""
    for r in await db.ref_ready():
        res = await db.ref_complete(r["referred_id"])
        if res:
            rid, reward, bonus, done = res
            await util.notify(ctx.bot, rid, f"🎉 <b>Refer complete!</b> Tumhare dost ne apne task complete kar liye. "
                                            f"<b>+{reward}</b> coins ad balance me add (ye sirf task banane me use ho sakte hain).")
            if bonus:
                await util.notify(ctx.bot, rid, f"🏆 <b>Milestone bonus!</b> {done} refers complete hone par <b>+{bonus}</b> extra coins ad balance me add.")


async def job_wd_expire(ctx):
    """Pending withdraw WITHDRAW_EXPIRE_HOURS me admin ne na approve kiya na reject: expire + coins wapas."""
    for w in await db.wd_expire_pending(config.WITHDRAW_EXPIRE_HOURS):
        hrs = w["expire_hours"] or config.WITHDRAW_EXPIRE_HOURS
        await util.notify(ctx.bot, w["user_id"],
                          f"⌛ Withdraw #{w['id']} {hrs} ghante me process nahi hua, isliye expire ho gaya.\n"
                          f"<b>{w['coins']}</b> coins (tax samet) tumhare balance me wapas aa gaye. Chaho to dobara withdraw karo.")
        await extras.bk_delete(w["id"])
        extras.feed(f"⌛ Withdraw #{w['id']} <b>expired</b> ({hrs}h, {util.tag(w['level'])}), {w['coins']} coins refund (user <code>{w['user_id']}</code>)")


async def job_prem(ctx):
    """Queue me rakha premium (purana khatam hone ke baad) chalu karo aur user ko batao."""
    for uid, lvl, days in await db.prem_activate_queued():
        await util.notify(ctx.bot, uid, f"⭐ <b>Premium Level {lvl} chalu ho gaya!</b> ({days} din). Purana premium khatam ho gaya tha.")
        extras.feed(f"⭐ Premium L{lvl} queue se chalu (user <code>{uid}</code>)")


async def on_precheckout(update: Update, ctx):
    """Stars invoice: payment se pehle order check (pending, isi user ka, sahi amount). Fail to charge hi nahi hota."""
    q = update.pre_checkout_query
    o = await db.order_row(q.invoice_payload)
    good = (o and o["status"] == "pending" and o["method"] == "stars" and o["user_id"] == q.from_user.id
            and q.currency == "XTR" and q.total_amount == int(o["amount_inr"]))
    try:
        await q.answer(ok=bool(good), error_message=None if good else "Ye order ab valid nahi hai. App se dobara Stars payment shuru karo.")
    except TelegramError:
        pass


async def on_stars_paid(update: Update, ctx):
    sp = update.message.successful_payment
    if sp.currency != "XTR":
        return
    o = await db.order_row(sp.invoice_payload)
    done = await db.complete_order(sp.invoice_payload, None) if o and o["method"] == "stars" and sp.total_amount == int(o["amount_inr"]) else None
    if not done:
        log.error("Stars payment complete nahi hua: payload=%s charge=%s amount=%s", sp.invoice_payload, sp.telegram_payment_charge_id, sp.total_amount)
        extras.feed(f"🚨 Stars payment complete nahi hua! payload <code>{html.escape(str(sp.invoice_payload))}</code> "
                    f"charge <code>{html.escape(str(sp.telegram_payment_charge_id))}</code> — check/refund karo")
        return
    try:
        await db.pool.execute("UPDATE orders SET charge_id=$2 WHERE order_id=$1", sp.invoice_payload, sp.telegram_payment_charge_id)
    except Exception:
        log.exception("charge_id save failed")
    await util.notify(ctx.bot, done["user_id"], payments.premium_msg(done))
    extras.feed(f"⭐ <b>Premium L{done['level']} paid (Stars {sp.total_amount})</b> — user <code>{done['user_id']}</code>")


async def pending_cmd(update: Update, ctx):
    """Admin: pending withdraws, bade level pehle."""
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    rows = await db.wd_pending_list()
    if not rows:
        return await update.message.reply_text("✅ Koi pending withdraw nahi.")
    lines = []
    for w in rows:
        left = float(await db.pool.fetchval(
            "SELECT extract(epoch FROM (created_at + make_interval(hours => COALESCE(expire_hours, $2)) - now()))/3600 FROM withdrawals WHERE id=$1",
            w["id"], config.WITHDRAW_EXPIRE_HOURS))
        lines.append(f"{util.tag(w['level'])} · #{w['id']} · ₹{float(w['amount_inr']):.2f} · user <code>{w['user_id']}</code> · {max(left, 0):.1f}h bache")
    await update.message.reply_text("⏳ <b>Pending withdraws (bada level pehle)</b>\n" + "\n".join(lines), parse_mode="HTML")


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
            txt = (f"⏰ <b>{util.tag(w['level'])} · Withdraw #{w['id']} abhi pending hai</b>\nUser: <code>{w['user_id']}</code>\n"
                   f"₹{float(w['amount_inr']):.2f} → <code>{html.escape(w['upi'])}</code>")
            kb = payouts.admin_kb(w["id"], db.is_code(w["upi"]) or w["method"] == "usdt")
            if w["method"] == "usdt":
                txt = (f"⏰ <b>{util.tag(w['level'])} · USDT Withdraw #{w['id']} pending</b>\nUser: <code>{w['user_id']}</code>\n"
                       f"{w['usdt']} USDT (BEP20) → <code>{html.escape(w['upi'])}</code>\nBhejne ke baad: <code>/txid {w['id']} TXHASH</code>")
            elif w["upi"] == db.AMAZON:
                txt += f"\n🛒 Amazon voucher bhejna hai: <code>/gpcode {w['id']} CODE</code> (ya Admin Panel > Withdraws)"
            elif w["upi"] == db.GPLAY:
                txt += f"\n🎁 Google Play code bhejna hai: <code>/gpcode {w['id']} CODE</code> (ya Admin Panel > Withdraws)"
        else:
            txt = (f"🚨 <b>Withdraw #{w['id']} 'sending' me atka hai</b>\n₹{float(w['amount_inr']):.2f} → "
                   f"<code>{html.escape(w['upi'])}</code>\nPaisa gaya ho to Mark paid, nahi gaya to Refund.")
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
    app.add_handler(CommandHandler("pending", pending_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(on_admin_wd, pattern=r"^adm_"))
    app.add_handler(CallbackQueryHandler(on_admin_claim, pattern=r"^clm_"))
    app.add_handler(CallbackQueryHandler(on_ignore, pattern=r"^ign:"))
    app.add_handler(CommandHandler("assign", assign_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("gpcode", gpcode_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("txid", gpcode_cmd, filters=filters.ChatType.PRIVATE))


def register(app):
    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("gift", gift_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("admin", admin_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("language", lang_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(on_lang, pattern=r"^langc?:"))
    app.add_handler(CommandHandler(["bypass", "unbypass"], bypass_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("allowdev", allowdev_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("ping", ping_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("pending", pending_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(PreCheckoutQueryHandler(on_precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_stars_paid))
    app.add_handler(CommandHandler("backup", backup_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler(["addbalance", "add_balance", "add"], addbal_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("resetdev", resetdev_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(on_support_legacy, pattern=r"^sup_reply:"))
    app.add_handler(CommandHandler(["ban", "unban"], ban_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(on_admin_wd, pattern=r"^adm_"))
    app.add_handler(CallbackQueryHandler(on_admin_claim, pattern=r"^clm_"))
    app.add_handler(CallbackQueryHandler(on_ignore, pattern=r"^ign:"))
    app.add_handler(CallbackQueryHandler(on_usdt_ignore, pattern=r"^uign:"))
    app.add_handler(CommandHandler("uassign", uassign_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("bc", bc_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^/bc") & filters.ChatType.PRIVATE, bc_cmd))
    app.add_handler(CommandHandler("assign", assign_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("gpcode", gpcode_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("txid", gpcode_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(botwork.on_cb, pattern=r"^(bws_|bwa_)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, botwork.on_text))
    app.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_error_handler(on_error)
    app.job_queue.run_repeating(job_release, interval=120, first=60)
    app.job_queue.run_repeating(job_recheck, interval=300, first=120)
    app.job_queue.run_repeating(botwork.job, interval=900, first=180)
    app.job_queue.run_repeating(job_orders, interval=120, first=90)
    app.job_queue.run_repeating(job_refs, interval=60, first=70)
    app.job_queue.run_repeating(job_prem, interval=120, first=80)
    app.job_queue.run_repeating(job_cleanup, interval=86400, first=600)
    app.job_queue.run_repeating(job_support_clean, interval=3600, first=120)
    app.job_queue.run_repeating(extras.job_bcast, interval=30, first=40)
    app.job_queue.run_daily(extras.job_backup, time=datetime.time(hour=21, minute=30, tzinfo=datetime.timezone.utc))  # ~3:00 AM IST
    app.job_queue.run_repeating(job_wd_stuck, interval=120, first=45)
    app.job_queue.run_repeating(job_wd_expire, interval=600, first=90)
