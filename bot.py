import asyncio
import datetime
import html
import json
import logging
import re
import secrets
import time

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M, MenuButtonWebApp, Update, WebAppInfo
from telegram.error import Forbidden, TelegramError
from telegram.ext import CallbackQueryHandler, ChatJoinRequestHandler, ChatMemberHandler, CommandHandler, MessageHandler, PreCheckoutQueryHandler, filters

import adminops
import botwork
import config
import db
import engage
import extras
import i18n
import payments
import payouts
import promo
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
    try:
        await set_command_menus(app.bot)
    except Exception:
        log.exception("command menu set nahi hua")


ADMIN_CMDS = [
    ("admin", "👑 Admin panel"), ("pending", "⏳ Pending withdraws"), ("ping", "📡 DB speed check"),
    ("backup", "🗄 Abhi backup bhejo"), ("addbalance", "💰 Apne account me balance"),
    ("bc", "📢 Sab users ko broadcast (text/photo)"), ("snd", "📣 Channel me post: /snd @channel msg"),
    ("send", "✉️ User ko msg: /send USER_ID msg"), ("txid", "💵 USDT TxID bhejo: /txid ID TxHash"),
    ("gpcode", "🎁 Gift code bhejo: /gpcode ID code"), ("assign", "🔗 Fam payment assign"),
    ("uassign", "🔗 USDT payment assign"), ("bwinfo", "🤖 Bot work submission status"),
    ("g", "📺 Ads: Ads Galaxy chalu"), ("m", "📺 Ads: Monetag chalu"), ("feedtest", "🔔 Feed/khabar test"),
    ("promo", "📣 Channel promo abhi / on / off"), ("offer", "🎯 Offer: /offer refer 10 500 24h x10"), ("ai", "🤖 /ai offer Hinglish me likho"), ("owner", "🔒 Task owner check on/off"),
    ("bypass", "✅ Device verify bypass"), ("unbypass", "↩️ Bypass hatao"), ("allowdev", "📱 Device allow"),
    ("resetdev", "♻️ Device reset"), ("ban", "🚫 User ban"), ("unban", "✅ User unban"),
    ("language", "🌐 Bhasha badlo"), ("start", "🏠 Start"),
]
SUPPORT_CMDS = [
    ("bc", "📢 Sab users ko broadcast (text/photo)"), ("snd", "📣 Channel me post: /snd @channel msg"),
    ("txid", "💵 USDT TxID bhejo: /txid ID TxHash"), ("language", "🌐 Bhasha badlo"), ("start", "🏠 Start"),
]


async def set_command_menus(bot):
    """'/' wale command box me list: sirf admin aur support ko dikhti hai (har ek ki apni chat par). Baaki users ke liye kuch nahi badalta."""
    from telegram import BotCommand, BotCommandScopeChat
    for ids, cmds in ((config.ADMIN_IDS, ADMIN_CMDS), (config.SUPPORT_IDS, SUPPORT_CMDS)):
        for uid in ids:
            try:
                await bot.set_my_commands([BotCommand(c, d[:256]) for c, d in cmds], scope=BotCommandScopeChat(uid))
            except TelegramError as e:
                log.warning("command menu %s set nahi hua: %s", uid, e)


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
    if False and left:
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


async def feedtest_cmd(update: Update, ctx):
    """Admin: feed (khabar) kyu nahi aa rahi? Seedha test + wajah bataata hai."""
    uid = update.effective_user.id
    if uid not in config.ADMIN_IDS or not update.message:
        return
    L = [f"ADMIN_FEED = {config.ADMIN_FEED} ({'on' if config.ADMIN_FEED else 'BAND: Render me ADMIN_FEED=1 karo'})",
         f"ADMIN_IDS me tum ho: {'haan' if uid in config.ADMIN_IDS else 'nahi'}"]
    if not config.FEED_BOT_TOKEN:
        L.append("FEED_BOT_TOKEN: khali, feed main bot par aayegi")
    else:
        fb = await extras.feed_bot()
        if not fb:
            L.append("❌ FEED_BOT_TOKEN galat hai (bot start nahi hua). BotFather se token dobara copy karke Render me daalo.")
        else:
            try:
                await fb.send_message(uid, "✅ Feed bot test: ye message aa gaya to feed isi bot par aayegi.")
                L.append(f"✅ Feed bot @{fb.username} se message gaya")
            except Exception as e:
                L.append(f"❌ @{fb.username} se message nahi gaya: {type(e).__name__}: {e}\n→ Us bot ko Telegram me kholo aur /start dabao.")
    extras.feed("🔔 Feed test (queue se, 1-2 sec me aana chahiye)")
    await update.message.reply_text("\n".join(L))


async def promo_cmd(update: Update, ctx):
    """Admin: /promo = abhi ek post, /promo off = band, /promo on = chalu."""
    if update.effective_user.id not in config.ADMIN_IDS or not update.message:
        return
    a = (ctx.args[0].lower() if ctx.args else "")
    if a in ("on", "off"):
        await db.usdt_meta_set("promo_on", "1" if a == "on" else "0")
        return await update.message.reply_text(f"✅ Channel promo {'chalu' if a == 'on' else 'band'}.")
    ok_, info = await promo.post(ctx.bot)
    await update.message.reply_text(f"✅ Channel me post gaya ({info})." if ok_ else f"❌ Post nahi gaya: {info}\nBot ko {config.FORCE_CHANNEL} me Admin banao (Post messages allowed).")


async def _make_offer(ctx, kind, target, bonus, hours, win, wallet):
    who = f"pehle {win} users" if win else "jo bhi"
    where = "Wallet me" if wallet else "Ad Balance me"
    txt = (f"{who} {target} dost refer karke complete karwayenge unko {bonus} coins bonus ({where})" if kind == "refer"
           else f"{who} {target} coins kamayenge unko {bonus} coins bonus ({where})")
    oid = await db.offer_new(kind, target, bonus, hours, win, wallet, txt)
    ok_, info = await promo.post(ctx.bot, force_offer=True)
    return (f"✅ Offer #{oid} chalu ({hours:.1f}h): {txt}.\nBonus apne aap {'Wallet' if wallet else 'Ad Balance'} me jayega, user ko DM aayega. " +
            (f"Channel post ho gaya ({info})." if ok_ else f"❌ Channel post nahi gaya: {info}."))


_AI_OFFER_SYS = ("You convert an admin's Hinglish request into ONE offer as strict JSON, nothing else. Keys: "
                 "kind ('refer' = users must refer N friends, 'coin' = users must earn N coins), target (int N), bonus (int coins), "
                 "winners (int, first-N users limit, 0 if none), wallet (true = bonus to Wallet, false = Ad Balance; use true unless the request says ad balance or ads balance), "
                 "until (end time 'YYYY-MM-DD HH:MM' in IST 24h; 'raat 12 baje' = next 00:00; if no time given use now+24h). "
                 "If the request is not a refer/coin offer, output {\"error\":\"short reason\"}. Never invent numbers not in the request.")


async def ai_cmd(update: Update, ctx):
    """Admin: /ai <hinglish me offer batao> -> AI samajh kar offer bana deta hai. Jaise: /ai aaj raat 12 tak pehle 10 user jo 10 refer karein unko 500 bonus"""
    if update.effective_user.id not in config.ADMIN_IDS or not update.message:
        return
    parts = (update.message.text or "").split(None, 1)
    if len(parts) < 2:
        return await update.message.reply_text("Aise likho:\n/ai ek offer banao aaj 12 baje raat tak, pehle 10 user jo 10 refer karenge unko 500 bonus")
    import ai as _ai
    if not _ai.enabled():
        return await update.message.reply_text("❌ AI key set nahi. Seedha likho: /offer refer 10 500 24h x10")
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now = datetime.datetime.now(ist)
    try:
        raw = await _ai.generate(_AI_OFFER_SYS, f"Now (IST): {now:%Y-%m-%d %H:%M}\nRequest: {parts[1][:500]}", 200, 0)
        j = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        if j.get("error"):
            return await update.message.reply_text(f"❌ Samajh nahi aaya: {j['error']}\nSeedha likho: /offer refer 10 500 24h x10")
        kind = "refer" if j["kind"] == "refer" else "coin"
        target, bonus, win = int(j["target"]), int(j["bonus"]), int(j.get("winners") or 0)
        until = datetime.datetime.strptime(str(j["until"])[:16], "%Y-%m-%d %H:%M").replace(tzinfo=ist)
        hours = (until - now).total_seconds() / 3600
        if not (1 <= target <= 1000000 and 1 <= bonus <= 100000 and 0 <= win <= 100000 and 0.05 <= hours <= 24 * 14):
            raise ValueError("range")
    except Exception as e:
        log.warning("ai offer parse failed: %s", e)
        return await update.message.reply_text("❌ Offer samajh nahi aaya. Thoda saaf likho (kitne refer/coin, kitna bonus, kab tak) ya /offer refer 10 500 24h x10 use karo.")
    await update.message.reply_text(
        f"🤖 Samjha: {kind} {target} → {bonus} coins" + (f", pehle {win} log" if win else "") + f", {until:%d %b %H:%M} IST tak.")
    await update.message.reply_text(await _make_offer(ctx, kind, target, bonus, hours, win, j.get("wallet", True) is not False))


async def offer_cmd(update: Update, ctx):
    """Admin:
    /offer refer 10 500 [24h|2d] [x10] [wallet|ad]  = 10 refer pure karne wale (pehle 10 log) ko 500 coins bonus, apne aap
    /offer coin 500 500 [24h] [x10] [wallet|ad]   = 500 coins kamane wale ko 500 bonus, apne aap
    /offer text...                               = sirf announcement (coins khud dene hain)
    /offer off [id]  = band.  /offer = chalte offers.  Bonus default Wallet me; Ad Balance me dena ho to end me 'ad' likho (jaise /offer refer 10 500 24h x10 ad)."""
    if update.effective_user.id not in config.ADMIN_IDS or not update.message:
        return
    parts = (update.message.text or "").split(None, 1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    if not arg:
        offs = await db.offers_active()
        cur = await promo.active_offer()
        lines = [f"#{o['id']} {o['kind']} {o['target']} → {o['bonus']} coins | winners {o['winners']}" +
                 (f"/{o['max_winners']}" if o['max_winners'] else "") +
                 f" | khatam {time.strftime('%d %b %H:%M', time.gmtime(o['ends_ts'] + 19800))} IST" for o in offs]
        if cur and not offs:
            lines.append(f"(sirf text) {cur[0]}")
        return await update.message.reply_text(
            "\n".join(lines) if lines else
            "Koi offer chalu nahi.\nUsage:\n/offer refer 10 500 24h x10\n/offer coin 500 500 24h x10\n(10 refer / 500 coin kamane par 500 bonus, pehle 10 log)\n/offer off")
    low = arg.lower()
    if low.split()[0] == "off":
        rest = low.split()[1:]
        n = await db.offer_close(int(rest[0]) if rest and rest[0].isdigit() else None)
        await promo.clear_offer()
        return await update.message.reply_text(f"✅ Offer band ({n}).")
    m = re.match(r"^(refer|coin|coins)\s+(\d+)\s+(\d+)(.*)$", arg, re.I)
    if m:
        kind = "refer" if m.group(1).lower() == "refer" else "coin"
        target, bonus, rest = int(m.group(2)), int(m.group(3)), m.group(4).lower()
        hours, win, wallet = 24, 0, True   # default Wallet (withdraw ho sakta hai); "ad" likho to Ad Balance
        for t in rest.split():
            h = re.fullmatch(r"(\d{1,3})([hd])", t)
            w = re.fullmatch(r"x(\d{1,5})", t)
            if h:
                hours = min(int(h.group(1)) * (24 if h.group(2) == "d" else 1), 24 * 14)
            elif w:
                win = int(w.group(1))
            elif t == "wallet":
                wallet = True
            elif t in ("ad", "ads", "adbalance"):
                wallet = False
        if not (1 <= target <= 1000000 and 1 <= bonus <= 100000):
            return await update.message.reply_text("❌ Target/bonus sahi likho. Jaise: /offer refer 10 500 24h x10")
        return await update.message.reply_text(await _make_offer(ctx, kind, target, bonus, hours, win, wallet))
    hours = 24
    m = re.match(r"^(\d{1,3})([hd])\s+(.+)$", arg, re.S | re.I)
    if m:
        hours = min(int(m.group(1)) * (24 if m.group(2).lower() == "d" else 1), 24 * 14)
        arg = m.group(3).strip()
    await promo.set_offer(arg[:400], hours)
    ok_, info = await promo.post(ctx.bot, force_offer=True)
    await update.message.reply_text(
        f"✅ Text offer set ({hours}h). " + (f"Channel me post ho gaya ({info}). " if ok_ else f"❌ Channel post nahi gaya: {info}. ") +
        "⚠️ Ye sirf announcement hai, coins khud dene honge. Apne aap bonus ke liye: /offer refer 10 500 24h x10")


async def job_offer_wins(ctx):
    """Offer jeetne walon ko DM + admin feed."""
    try:
        rows = await db.offer_wins_pending(30)
    except Exception:
        log.exception("offer wins fetch failed")
        return
    for r in rows:
        where = "Wallet" if r["to_wallet"] else "Ad Balance"
        await util.notify(ctx.bot, r["user_id"], f"🎉 Offer jeet liya! Tumhe {r['bonus']} coins bonus mile ({where} me). Aise hi kamate raho 🚀")
        await db.offer_win_mark(r["offer_id"], r["user_id"])
        extras.feed(f"🎯 Offer #{r['offer_id']} winner <code>{r['user_id']}</code> +{r['bonus']} (winners {r['winners']}" +
                    (f"/{r['max_winners']}" if r["max_winners"] else "") + ")")
        await asyncio.sleep(0.05)


async def owner_cmd(update: Update, ctx):
    """Admin: /owner on = task banane wale ko us channel/group ka admin ya owner hona zaroori. /owner off = sirf bot admin ho to chalega."""
    if update.effective_user.id not in config.ADMIN_IDS or not update.message:
        return
    parts = (update.message.text or "").split()
    arg = parts[1].lower() if len(parts) > 1 else ""
    if arg in ("on", "off"):
        await db.usdt_meta_set("owner_check", "1" if arg == "on" else "0")
    on = await db.usdt_meta_get("owner_check") != "0"
    await update.message.reply_text(
        ("🔒 Owner check ON: task banane wala us channel/group ka admin ya owner hona chahiye." if on else
         "🔓 Owner check OFF: sirf bot ka admin hona kaafi hai (banane wala admin ho ya na ho).") + "\n/owner on  ya  /owner off")


async def job_promo(ctx):
    try:
        r = await promo.tick(ctx.bot)
    except Exception:
        log.exception("promo tick failed")
        return
    if r and not r[0]:
        extras.feed(f"⚠️ Channel promo post nahi gaya: {html.escape(r[1][:200])}")


async def ads_src_cmd(update: Update, ctx):
    """Admin: /g = Ads Galaxy, /m = Monetag. Users ko agli baar app kholne par ye provider dikhega (pending callbacks dono ke credit hote rehte hain)."""
    if update.effective_user.id not in config.ADMIN_IDS or not update.message:
        return
    cmd = (update.message.text or "").split()[0].lstrip("/").split("@")[0].lower()
    want = "mt" if cmd == "m" else "gx"
    name = "Monetag" if want == "mt" else "Ads Galaxy"
    if (want == "mt" and not config.MT_ON) or (want == "gx" and not config.ADS_ON):
        return await update.message.reply_text(f"❌ {name} Render env me set nahi hai ({'MONETAG_SECRET' if want == 'mt' else 'ADS_SIGN_SECRET'} khali).")
    await db.ads_src_set(want)
    await update.message.reply_text(f"✅ Ads ab {name} se chalenge. Users ke liye agli baar app kholne par lagu.")


async def bc_cmd(update: Update, ctx):
    """Admin/Support: /bc <text> ya photo (gallery photo, file ya reply) + caption me /bc <text>. Sab users ko DM + app ke Notifications me."""
    m = update.effective_message
    uid = update.effective_user.id
    if (uid not in config.ADMIN_IDS and uid not in config.SUPPORT_IDS) or not m:
        return
    raw = (m.caption_html or m.text_html or "")
    text = re.sub(r"^/bc(@\w+)?\s*", "", raw.strip()).strip()
    photo = None
    for src in (m, m.reply_to_message):  # khud ki photo ya kisi photo ka reply
        if not src:
            continue
        if src.photo:
            photo = src.photo[-1].file_id
        elif src.document and (src.document.mime_type or "").startswith("image/"):
            photo = src.document.file_id
        if photo:
            break
    if not text and not photo:
        return await m.reply_text("Usage: <code>/bc aapka message</code>\nPhoto ke saath: photo bhejo aur caption me <code>/bc message</code> likho (ya photo ko reply karke /bc likho).", parse_mode="HTML")
    nid, n = await db.news_add(text, photo)
    await m.reply_text(f"✅ Broadcast #{nid} queue me hai. ~{n} users ko jayega (thoda time lagta hai) aur app ke 🔔 Notifications me dikhega.")


def _snd_target(tok):
    """@user, t.me/user, https://t.me/user ya -100... id -> chat id/username. None = samajh nahi aaya."""
    t = tok.strip().rstrip("/")
    mm = re.match(r"^(?:https?://)?(?:www\.)?(?:t|telegram)\.me/(?!\+|joinchat)([A-Za-z][\w]{3,})(?:/\d+)?$", t)
    if mm:
        return "@" + mm.group(1)
    if re.match(r"^@[A-Za-z][\w]{3,}$", t):
        return t
    if re.match(r"^-100\d{5,}$", t):
        return int(t)
    return None


async def snd_cmd(update: Update, ctx):
    """Admin/Support: /snd <channel @username ya link> <message>. Photo ke saath: photo bhejo, caption me /snd <channel> <message> (ya photo ko reply karke)."""
    m = update.effective_message
    uid = update.effective_user.id
    if (uid not in config.ADMIN_IDS and uid not in config.SUPPORT_IDS) or not m:
        return
    plain = (m.caption or m.text or "").strip()
    raw = (m.caption_html or m.text_html or "").strip()
    rest = re.sub(r"^/snd(@\w+)?\s*", "", plain)
    parts = rest.split(None, 1)
    tgt = _snd_target(parts[0]) if parts else None
    if tgt is None:
        return await m.reply_text(
            "Usage: <code>/snd @channel_username aapka message</code>\n(ya <code>/snd https://t.me/channel message</code>)\n"
            "Photo ke saath: photo bhejo aur caption me <code>/snd @channel message</code> likho, ya photo ko reply karke /snd likho.\n"
            "Sirf message na likho to default promo jata hai. Private invite link (t.me/+...) se nahi hota, @username ya -100 id do.", parse_mode="HTML")
    body_plain = parts[1] if len(parts) > 1 else ""
    text = re.sub(r"^/snd(@\w+)?\s*", "", raw).strip()
    text = text[len(parts[0]):].strip() if text.startswith(parts[0]) else text.replace(parts[0], "", 1).strip()
    if not body_plain:
        text = ""
    photo = None
    for src in (m, m.reply_to_message):
        if not src:
            continue
        if src.photo:
            photo = src.photo[-1].file_id
        elif src.document and (src.document.mime_type or "").startswith("image/"):
            photo = src.document.file_id
        if photo:
            break
    if not text and not photo:
        text = config.PROMO_TEXT
    bot = util.main_bot or ctx.bot
    try:
        if photo:
            short = len(text) <= 1000
            await bot.send_photo(tgt, photo, caption=text if (short and text) else None, parse_mode="HTML")
            if text and not short:
                await bot.send_message(tgt, text, parse_mode="HTML")
        else:
            await bot.send_message(tgt, text, parse_mode="HTML")
    except TelegramError as e:
        why = str(e)
        if "chat not found" in why.lower():
            why = "channel nahi mila. Username check karo, aur bot ko us channel me add karo (admin, post message right ke saath)."
        elif isinstance(e, Forbidden) or "not enough rights" in why.lower():
            why = "bot ko wahan post karne ka right nahi hai (channel me admin banao)."
        return await m.reply_text(f"❌ Nahi gaya: {why}")
    await m.reply_text(f"✅ {tgt} me bhej diya.")


async def bwinfo_cmd(update: Update, ctx):
    """Admin: /bwinfo <submission_id> -> us bot work submission ki asli status (debug)."""
    if update.effective_user.id not in config.ADMIN_IDS:
        return
    a = ctx.args
    if not a or not a[0].isdigit():
        return await update.message.reply_text("Usage: /bwinfo <submission_id>")
    s = await db.bw_sub(int(a[0]))
    if not s:
        return await update.message.reply_text(f"Submission #{a[0]} database me nahi hai.")
    await update.message.reply_text(
        f"🤖 Submission #{s['id']} (task #{s['bw_id']}: {s['title']})\nStatus: {s['status']} (attempt {s['attempt']})\n"
        f"Poster (owner): {s['owner_id']}\nWorker: {s['worker_id']}\nBani: {s['created_at']:%d %b %H:%M}\n"
        f"Faisla: {s['decided_at'] and format(s['decided_at'], '%d %b %H:%M') or '—'}\nReject reason: {s['reject_reason'] or '—'}")


async def send_cmd(update: Update, ctx):
    """Admin: /send <user_id> <message>. Photo ke saath: photo bhejo, caption me /send <user_id> <message> (ya photo ko reply karke)."""
    m = update.effective_message
    if not m or update.effective_user.id not in config.ADMIN_IDS:
        return
    plain = (m.caption or m.text or "").strip()
    raw = (m.caption_html or m.text_html or "").strip()
    rest = re.sub(r"^/send(@\w+)?\s*", "", plain)
    parts = rest.split(None, 1)
    if not parts or not parts[0].lstrip("-").isdigit():
        return await m.reply_text("Usage: <code>/send USER_ID aapka message</code>\nPhoto ke saath: photo bhejo aur caption me <code>/send USER_ID message</code> likho (ya photo ko reply karke /send USER_ID likho).", parse_mode="HTML")
    uid = int(parts[0])
    text = re.sub(r"^/send(@\w+)?\s*", "", raw).strip()
    text = text[len(parts[0]):].strip() if text.startswith(parts[0]) else text.replace(parts[0], "", 1).strip()
    photo = None
    for src in (m, m.reply_to_message):
        if not src:
            continue
        if src.photo:
            photo = src.photo[-1].file_id
        elif src.document and (src.document.mime_type or "").startswith("image/"):
            photo = src.document.file_id
        if photo:
            break
    if not text and not photo:
        return await m.reply_text("Message ya photo bhi likho: <code>/send USER_ID aapka message</code>", parse_mode="HTML")
    if not await db.pool.fetchval("SELECT 1 FROM users WHERE id=$1", uid):
        return await m.reply_text(f"❌ User {uid} database me nahi hai.")
    bot = util.main_bot or ctx.bot
    try:
        if photo:
            short = len(text) <= 1000
            await bot.send_photo(uid, photo, caption=text if (short and text) else None, parse_mode="HTML")
            if text and not short:
                await bot.send_message(uid, text, parse_mode="HTML")
        else:
            await bot.send_message(uid, text, parse_mode="HTML")
    except Forbidden:
        return await m.reply_text(f"❌ User {uid} ne bot block kar rakha hai.")
    except TelegramError as e:
        return await m.reply_text(f"❌ Nahi gaya: {e}")
    await m.reply_text(f"✅ User {uid} ko bhej diya.")


async def gpcode_cmd(update: Update, ctx):
    """/gpcode <id> <code> (Google Play / Amazon) ya /txid <id> <TxHash> (USDT): user ko bhejo, withdraw paid ho jata hai."""
    uid = update.effective_user.id
    if uid not in config.ADMIN_IDS and uid not in config.SUPPORT_IDS:
        return
    a = ctx.args
    if len(a) < 2 or not a[0].isdigit():
        return await update.message.reply_text("Usage: /gpcode <withdraw_id> <code>  ya  /txid <withdraw_id> <TxHash>")
    if uid not in config.ADMIN_IDS:  # support agent: sirf USDT withdraw
        w0 = await db.wd_get(int(a[0]))
        if not w0 or w0["method"] != "usdt":
            return await update.message.reply_text("Tum sirf USDT withdraw ka TxID bhej sakte ho.")
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
async def _after_leave(bot, uid, rows):
    """Leave par user ko DM (uski bhasha me): kitne coins kate; withdraw cancel hua ho to wo bhi."""
    for r in rows:
        if r.get("reward"):
            await util.notify(bot, uid, f"⚠️ Tumne channel \"{html.escape(r.get('title') or '')}\" leave kiya, isliye <b>{r['reward']}</b> coins kat gaye. "
                                        f"Channel dobara join karoge to coins wapas mil jayenge.")
        for w in r.get("cancelled") or []:
            await util.notify(bot, uid, f"↩️ Tumhara withdraw #{w['id']} cancel ho gaya (channel leave kiya). Coins balance me wapas aa gaye. "
                                        f"Channel dobara join karo.")


async def on_chat_member(update: Update, ctx):
    """Join record. Leave (pehle RECHECK_DAYS din me) par us channel ke coins wapas; rejoin par poore wapas mil jate hain."""
    cm = update.chat_member
    uid = cm.new_chat_member.user.id
    cid = cm.chat.id
    was, now = util.in_chat(cm.old_chat_member), util.in_chat(cm.new_chat_member)
    if now and not was:
        await db.record_join(cid, uid)
        back = await db.unblock(cid, uid)
        if back:
            await util.notify(ctx.bot, uid, f"✅ Channel rejoin ho gaya. <b>+{back}</b> coins wapas mil gaye.")
    elif was and not now:
        await db.pool.execute(
            "UPDATE completions SET left_at=now() WHERE chat_id=$1 AND user_id=$2 AND left_at IS NULL", cid, uid)
        await _after_leave(ctx.bot, uid, await db.revoke_by_chat(cid, uid))


async def on_join_request(update: Update, ctx):
    """Join-request wale channel/group: jis chat ka task chal raha hai, wahan request bot khud approve kar deta hai
    (user turant member banta hai -> auto-check se coin). Banned user approve nahi hota."""
    r = update.chat_join_request
    if not r:
        return
    cid, uid = r.chat.id, r.from_user.id
    try:
        if not await db.task_chat_open(cid) or await db.is_banned_user(uid):
            return
        await ctx.bot.approve_chat_join_request(cid, uid)
        await db.record_join(cid, uid)
    except Exception as e:
        log.warning("join request approve failed chat=%s user=%s: %s", cid, uid, e)


async def on_my_chat_member(update: Update, ctx):
    """Bot ko kisi channel/group me admin banaya (ya hataya): yaad rakho, taaki private chat bhi Add Task me chal sake."""
    m = update.my_chat_member
    if not m or m.chat.type not in ("channel", "group", "supergroup"):
        return
    now_admin = m.new_chat_member.status == "administrator"
    try:
        await db.botchat_set(m.chat.id, m.chat.title, m.chat.type, m.chat.username, m.from_user.id if m.from_user else None, now_admin)
    except Exception:
        log.exception("botchat_set failed")
        return
    if now_admin and m.from_user and m.old_chat_member.status != "administrator":
        await util.notify(ctx.bot, m.from_user.id, f"✅ Bot ko \"{html.escape(m.chat.title or '')}\" me Admin bana diya. Ab app me Add Task me us channel ka link (private ho to invite link) daalo.")


async def on_forward(update: Update, ctx):
    """Private channel/group ka koi message bot ko forward karo: chat pehchan kar yaad rakhta hai (bot admin + user admin ho to)."""
    msg = update.effective_message
    if not msg:
        return
    fo = getattr(msg, "forward_origin", None)
    ch = getattr(fo, "chat", None) or getattr(fo, "sender_chat", None) or getattr(msg, "forward_from_chat", None)
    if not ch or ch.type not in ("channel", "group", "supergroup"):
        return
    uid = update.effective_user.id
    lang = await i18n.lang_of(uid)
    try:
        me = await ctx.bot.get_chat_member(ch.id, ctx.bot.id)
    except TelegramError:
        me = None
    if not me or me.status != "administrator":
        return await msg.reply_text(i18n.tr(f"❌ Bot is chat me Admin nahi hai. @{ctx.bot.username} ko Admin banao (Invite Users permission ke saath).", lang))
    try:
        um = await ctx.bot.get_chat_member(ch.id, uid)
    except TelegramError:
        um = None
    if await db.usdt_meta_get("owner_check") != "0" and (not um or um.status not in ("creator", "administrator")):
        return await msg.reply_text(i18n.tr("❌ Tum is chat ke admin/owner nahi ho.", lang))
    await db.botchat_set(ch.id, ch.title, ch.type, getattr(ch, "username", None), uid, True)
    await msg.reply_text(i18n.tr(f"✅ \"{html.escape(ch.title or '')}\" mil gaya. Ab app me Add Task me wahi private invite link daalo.", lang))


# ---------------- background jobs ----------------
async def _release_one(ctx, r):
    """Purane 'hold' rows (hold hatane se pehle ke) bina penalty ke release."""
    if await db.release(r["id"]):
        await util.notify(ctx.bot, r["user_id"], f"✅ {r['reward']} coins release ho gaye!")


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
    await db.pool.execute("UPDATE completions SET last_checked=now(), left_at=CASE WHEN $2::bool THEN COALESCE(left_at, now()) ELSE left_at END WHERE id=$1",
                          r["id"], st is False)
    if st is False:
        await _after_leave(ctx.bot, r["user_id"], await db.revoke_by_chat(r["chat_id"], r["user_id"]))


async def job_recheck(ctx):
    """Sirf pehle RECHECK_DAYS din tak chupke check: leave mila to coins wapas (revoke)."""
    rows = await db.pool.fetch(
        """SELECT id, chat_id, user_id FROM completions WHERE status='ok' AND left_at IS NULL
           AND created_at > now() - make_interval(days => $1) ORDER BY last_checked LIMIT 200""", config.RECHECK_DAYS)
    await _in_batches(rows, lambda r: _recheck_one(ctx, r))


async def job_leaderboard(ctx):
    """Pichhle mahine ke top-3 ko prize (ek hi baar)."""
    try:
        done = await db.lb_pay_prev(config.LB_PRIZES)
    except Exception:
        log.exception("lb prize failed")
        return
    for uid, board, rank, prize in done:
        nm = "Refer" if board == "refer" else "Coin"
        await util.notify(ctx.bot, uid, f"🏆 Leaderboard ({nm}) me tumhara rank #{rank} raha! "
                                        f"{prize} coins Ad Balance me add ho gaye.")


async def job_welcome(ctx):
    """Welcome bonus (naye + purane users): ek-ek karke coins + DM. Chhote batch, taaki Telegram flood limit na lage."""
    try:
        got = await db.welcome_batch(25)
    except Exception:
        log.exception("welcome bonus failed")
        return
    for uid in got:
        await util.notify(ctx.bot, uid, f"🎁 Welcome bonus! Tumhe {config.WELCOME_COINS} coins free mile hain. Tasks karo aur kamao 🚀",
                          disable_notification=True)
        await asyncio.sleep(0.05)
    if got:
        extras.feed(f"🎁 Welcome bonus diya: {len(got)} user")


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
    await db.history_prune()
    await db.ad_prune()


async def job_support_clean(ctx):
    await db.sup_cleanup()
    await db.ai_cleanup()


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
    app.add_handler(CommandHandler(["g", "m"], ads_src_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("feedtest", feedtest_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("promo", promo_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("offer", offer_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("ai", ai_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("owner", owner_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("bc", bc_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(MessageHandler((filters.PHOTO | filters.Document.IMAGE) & filters.CaptionRegex(r"^/bc") & filters.ChatType.PRIVATE, bc_cmd))
    app.add_handler(CommandHandler("assign", assign_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("gpcode", gpcode_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("txid", gpcode_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("bwinfo", bwinfo_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("send", send_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(MessageHandler((filters.PHOTO | filters.Document.IMAGE) & filters.CaptionRegex(r"^/send") & filters.ChatType.PRIVATE, send_cmd))
    app.add_handler(CommandHandler("snd", snd_cmd, filters=filters.ChatType.PRIVATE))
    app.add_handler(MessageHandler((filters.PHOTO | filters.Document.IMAGE) & filters.CaptionRegex(r"^/snd") & filters.ChatType.PRIVATE, snd_cmd))
    app.add_handler(CallbackQueryHandler(botwork.on_cb, pattern=r"^(bws_|bwa_)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, botwork.on_text))
    app.add_handler(MessageHandler(filters.FORWARDED & filters.ChatType.PRIVATE, on_forward), group=1)
    app.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(ChatJoinRequestHandler(on_join_request))
    app.add_error_handler(on_error)
    app.job_queue.run_repeating(job_release, interval=120, first=60)
    app.job_queue.run_repeating(job_recheck, interval=300, first=120)
    app.job_queue.run_repeating(job_leaderboard, interval=3600, first=180)
    app.job_queue.run_repeating(job_welcome, interval=20, first=30)
    app.job_queue.run_repeating(engage.job_offer_summary, interval=120, first=60)
    app.job_queue.run_repeating(engage.job_streak_remind, interval=300, first=90)
    app.job_queue.run_repeating(engage.job_reengage, interval=300, first=120)
    app.job_queue.run_repeating(engage.job_daily_summary, interval=600, first=150)
    app.job_queue.run_repeating(engage.job_weekly_shoutout, interval=900, first=180)
    app.job_queue.run_repeating(job_offer_wins, interval=15, first=40)
    app.job_queue.run_repeating(job_promo, interval=300, first=150)
    app.job_queue.run_repeating(botwork.job, interval=900, first=180)
    app.job_queue.run_repeating(job_orders, interval=120, first=90)
    app.job_queue.run_repeating(job_refs, interval=60, first=70)
    app.job_queue.run_repeating(job_prem, interval=120, first=80)
    app.job_queue.run_repeating(job_cleanup, interval=86400, first=600)
    app.job_queue.run_repeating(job_support_clean, interval=600, first=120)
    app.job_queue.run_repeating(extras.job_bcast, interval=30, first=40)
    app.job_queue.run_daily(extras.job_backup, time=datetime.time(hour=21, minute=30, tzinfo=datetime.timezone.utc))  # ~3:00 AM IST
    app.job_queue.run_repeating(job_wd_stuck, interval=120, first=45)
    app.job_queue.run_repeating(job_wd_expire, interval=600, first=90)
