"""Bot Work: poster apne bot ka task banata hai, worker screenshot + refer link bhejta hai,
poster Done/Reject karta hai, reject par worker Report kar sakta hai (admin decide karta hai)."""
import html
import logging
import re

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
from telegram.error import TelegramError

import bot as core  # circular-safe: sirf attribute access, call time par
import config
import db

log = logging.getLogger("botwork")
h = html.escape
URL_RE = re.compile(r"^https?://\S{4,300}$")
CANCEL = M([[B("❌ Cancel", callback_data="cancel")]])
STATUS = {"pending": "⏳ Pending", "approved": "✅ Approved", "rejected": "❌ Rejected",
          "reported": "🚩 Reported", "closed": "🔒 Closed"}
POPUP = ("bw_sub", "bw_ok", "bw_cancel", "bws_", "bwa_")


async def mark(q, suffix):
    try:
        await q.edit_message_caption((q.message.caption_html or "") + suffix, parse_mode="HTML", reply_markup=None)
    except TelegramError:
        pass


# ---------------- screens ----------------
async def list_screen(update, ctx):
    rows = await db.bw_open(update.effective_user.id)
    kb = [[B(f"🤖 {r['title'][:22]} • +{r['reward']}", callback_data=f"bw_open:{r['id']}")] for r in rows]
    kb.append([B("📄 My Submissions", callback_data="bw_mine")])
    kb.append([B("⬅️ Back", callback_data="tasks")])
    text = ("🤖 <b>Bot Work</b>\nBot start karo, uska kaam karo, phir screenshot + us bot ka refer link submit karo. "
            "Owner approve kare to coins seedhe balance me aate hain.")
    if not rows:
        text += "\n\nAbhi koi bot work available nahi."
    await core.show(update, text, M(kb))


async def open_screen(update, ctx, bid):
    b = await db.bw_get(bid)
    if not b or b["status"] != "active":
        return await core.show(update, "Ye bot work ab available nahi.", M([[B("⬅️ Back", callback_data="bw_list")]]))
    text = (f"🤖 <b>{h(b['title'])}</b>\nReward: <b>+{b['reward']}</b> coins ({core.inr(b['reward'])})\n\n"
            "1) Neeche link se bot kholo aur start karo\n"
            "2) Uska kaam poora karo\n"
            "3) Screenshot + us bot ka apna refer link yahan submit karo")
    kb = M([[B("🔗 Open bot", url=b["link"])],
            [B("📤 Submit proof", callback_data=f"bw_sub:{bid}")],
            [B("⬅️ Back", callback_data="bw_list")]])
    await core.show(update, text, kb)


async def mine_screen(update, ctx):
    rows = await db.bw_mine(update.effective_user.id)
    lines, kb = ["📄 <b>My Submissions</b>\n"], []
    for r in rows:
        lines.append(f"#{r['id']} {h(r['title'][:22])} — +{r['reward']} • {STATUS[r['status']]}")
        if r["status"] == "rejected":
            kb.append([B(f"🚩 Report #{r['id']}", callback_data=f"bws_rep:{r['id']}")])
    if not rows:
        lines.append("Abhi koi submission nahi.")
    kb.append([B("⬅️ Back", callback_data="bw_list")])
    await core.show(update, "\n".join(lines), M(kb))


async def my_screen(update, ctx):
    rows = await db.bw_my(update.effective_user.id)
    lines, kb = ["📊 <b>My Bot Works</b>\n"], []
    for r in rows:
        lines.append(f"#{r['id']} {h(r['title'][:22])} — {r['reward']} coins\n"
                     f"   done {r['done']}/{r['target']} • pending {r['pending']} • {r['status']}")
        if r["status"] == "active":
            kb.append([B(f"❌ Cancel #{r['id']} (refund)", callback_data=f"bw_cancel:{r['id']}")])
    if not rows:
        lines.append("Abhi koi bot work nahi banaya.")
    kb.append([B("⬅️ Back", callback_data="prem")])
    await core.show(update, "\n".join(lines), M(kb))


async def send_report(ctx, sid):
    s = await db.bw_sub(sid)
    if not s:
        return
    cap = (f"🚩 <b>Bot Work Report</b> #{sid}\nTask: {h(s['title'])} (#{s['bw_id']})\n"
           f"Poster: <code>{s['owner_id']}</code>\nWorker: <code>{s['worker_id']}</code>\n"
           f"Reward: {s['reward']} coins\nRefer link: {h(s['ref_link'])}\nReason: {h(s['reason'] or '-')}")
    kb = M([[B("✅ Pay worker", callback_data=f"bwa_pay:{sid}"), B("❌ Uphold reject", callback_data=f"bwa_no:{sid}")]])
    for a in config.ADMIN_IDS:
        try:
            await ctx.bot.send_photo(a, s["photo_id"], caption=cap, parse_mode="HTML", reply_markup=kb)
        except TelegramError:
            log.warning("report send failed to admin %s", a)


# ---------------- callbacks ----------------
async def on_cb(update, ctx):
    q = update.callback_query
    d = q.data
    uid = q.from_user.id
    if not d.startswith(POPUP):
        await q.answer()

    if d == "bw_list":
        return await list_screen(update, ctx)
    if d == "bw_mine":
        return await mine_screen(update, ctx)
    if d == "bw_my":
        return await my_screen(update, ctx)
    if d.startswith("bw_open:"):
        return await open_screen(update, ctx, int(d.split(":")[1]))

    if d == "bw_add":
        u = await db.get_user(uid)
        if not core.is_prem(u):
            return await core.premium_screen(update, ctx)
        ctx.user_data["st"] = "bw_title"
        return await core.show(update, "🤖 <b>Add Bot Work</b>\nBot ka naam / title bhejo (e.g. XYZ Bot):", CANCEL)

    if d == "bw_ok":
        n = ctx.user_data.pop("bwn", None)
        u = await db.get_user(uid)
        if not n or "n" not in n:
            return await core.popup(update, "Session expire. Dobara Add Bot Work karo.")
        if not core.is_prem(u):
            return await core.popup(update, "Premium expire ho gaya.")
        bid = await db.bw_create(uid, n["title"], n["link"], n["reward"], n["n"])
        if not bid:
            return await core.popup(update, "❌ Ad balance kam hai. Pehle deposit karo.")
        await core.popup(update, f"✅ Bot work #{bid} live ho gaya!")
        return await my_screen(update, ctx)

    if d.startswith("bw_cancel:"):
        refund = await db.bw_cancel(int(d.split(":")[1]), uid)
        if refund is None:
            return await core.popup(update, "Cancel nahi ho sakta.")
        await core.popup(update, f"✅ Cancelled. {refund} coins refund hue.")
        return await my_screen(update, ctx)

    if d.startswith("bw_sub:"):
        bid = int(d.split(":")[1])
        u = await db.get_user(uid)
        if not u or u["banned"]:
            return await core.popup(update, "🚫 Account banned.")
        if not u["device_ok"]:
            return await core.popup(update, "🔐 Pehle Profile me device verify karo.")
        if await db.is_blocked(uid):
            return await core.popup(update, "🚫 Tum blocked ho. Pehle left channel rejoin karo.")
        b = await db.bw_get(bid)
        if not b or b["status"] != "active":
            return await core.popup(update, "Ye bot work ab available nahi.")
        ctx.user_data["st"] = "bw_photo"
        ctx.user_data["bws"] = {"bid": bid}
        await core.popup(update, "📸 Ab screenshot bhejo.")
        return await update.effective_chat.send_message(
            "📸 Kaam ka <b>screenshot</b> bhejo (photo ke roop me).", parse_mode="HTML", reply_markup=CANCEL)

    if d.startswith("bws_"):
        act, sid = d.split(":")
        sid = int(sid)
        if act in ("bws_ok", "bws_no"):
            approve = act == "bws_ok"
            s = await db.bw_review(sid, uid, approve)
            if not s:
                return await core.popup(update, "Already processed ya tum is task ke owner nahi ho.")
            await core.popup(update, "✅ Done! Worker ko coins mil gaye." if approve else "❌ Reject kar diya.")
            await mark(q, "\n\n✅ <b>Approved</b>" if approve else "\n\n❌ <b>Rejected</b>")
            try:
                if approve:
                    await ctx.bot.send_message(
                        s["worker_id"], f"✅ Bot work approved! <b>+{s['reward']}</b> coins balance me add ho gaye.",
                        parse_mode="HTML")
                else:
                    await ctx.bot.send_message(
                        s["worker_id"],
                        f"❌ Bot work #{sid} reject hua. Agar tumne kaam sahi kiya hai to report kar sakte ho "
                        f"({config.BW_REPORT_HOURS}h ke andar).",
                        reply_markup=M([[B("🚩 Report", callback_data=f"bws_rep:{sid}")]]))
            except TelegramError:
                pass
            return
        if act == "bws_rep":
            r = await db.bw_report(sid, uid, "Worker ne reject ke baad report kiya")
            if not r:
                return await core.popup(update, "Ye report nahi ho sakta (already reported ya time khatam).")
            await core.popup(update, "🚩 Report bhej di gayi. Admin check karke decision lega.")
            await send_report(ctx, sid)
            return await mine_screen(update, ctx)

    if d.startswith("bwa_"):
        if uid not in config.ADMIN_IDS:
            return await core.popup(update, "Not allowed")
        act, sid = d.split(":")
        sid = int(sid)
        pay = act == "bwa_pay"
        s = await db.bw_admin(sid, pay)
        if not s:
            return await core.popup(update, "Already processed")
        await core.popup(update, "✅ Worker ko pay kar diya" if pay else "❌ Reject uphold, poster ko refund mila")
        await mark(q, "\n\n✅ <b>Worker paid</b>" if pay else "\n\n❌ <b>Reject upheld</b>")
        if pay:
            await core.notify(ctx, s["worker_id"], f"✅ Report approve hui. <b>+{s['reward']}</b> coins mil gaye.")
            await core.notify(ctx, s["owner_id"], f"ℹ️ Bot work #{s['bw_id']} ki submission #{sid} admin ne approve ki.")
        else:
            await core.notify(ctx, s["worker_id"], f"❌ Admin ne submission #{sid} ka reject sahi mana.")
            await core.notify(ctx, s["owner_id"], f"ℹ️ Submission #{sid} reject upheld. {s['reward']} coins wapas mile.")


# ---------------- text / photo input ----------------
async def on_text(update, ctx, st):
    m = update.message
    uid = m.from_user.id
    text = (m.text or "").strip()

    if st == "bw_photo":
        if not m.photo:
            return await m.reply_text("❌ Screenshot photo ke roop me bhejo.", reply_markup=CANCEL)
        p = m.photo[-1]
        ctx.user_data.setdefault("bws", {}).update(photo_id=p.file_id, photo_uid=p.file_unique_id)
        ctx.user_data["st"] = "bw_ref"
        return await m.reply_text("✅ Screenshot mil gaya. Ab us bot ka apna <b>refer link</b> bhejo:",
                                  parse_mode="HTML", reply_markup=CANCEL)

    if st == "bw_ref":
        s = ctx.user_data.get("bws") or {}
        if "photo_id" not in s:
            ctx.user_data.clear()
            return await m.reply_text("Session expire. Dobara submit karo.")
        if not URL_RE.match(text):
            return await m.reply_text("❌ Sahi link bhejo (https://...).", reply_markup=CANCEL)
        res, sid, b = await db.bw_submit(s["bid"], uid, s["photo_id"], s["photo_uid"], text)
        ctx.user_data.clear()
        msgs = {"dup": "❌ Tum ye task pehle submit kar chuke ho, ya ye screenshot pehle use ho chuka hai.",
                "own": "❌ Apna hi task nahi kar sakte.", "full": "❌ Is task ke saare slots full ho gaye.",
                "closed": "❌ Ye task ab available nahi."}
        if res != "ok":
            return await m.reply_text(msgs[res])
        await m.reply_text(f"⏳ Submission #{sid} bhej di gayi. Status: <b>Pending</b>\n"
                           f"Owner check karke Done karega to +{b['reward']} coins mil jayenge.", parse_mode="HTML")
        u = m.from_user
        cap = (f"🤖 <b>Bot Work submission</b> #{sid}\nTask: {h(b['title'])}\n"
               f"Worker: {'@' + u.username if u.username else h(u.first_name or '')} (<code>{uid}</code>)\n"
               f"Refer link: {h(text)}\nReward: {b['reward']} coins\n\n"
               "Screenshot dekho. Sahi ho to <b>Done</b>, nahi to Reject.")
        try:
            await ctx.bot.send_photo(
                b["owner_id"], s["photo_id"], caption=cap, parse_mode="HTML",
                reply_markup=M([[B("✅ Done", callback_data=f"bws_ok:{sid}"),
                                 B("❌ Reject", callback_data=f"bws_no:{sid}")]]))
        except TelegramError:
            log.warning("poster %s unreachable, auto-report will handle sub %s", b["owner_id"], sid)
        return

    # ---- poster flow ----
    if st == "bw_title":
        if not (3 <= len(text) <= 40):
            return await m.reply_text("❌ Title 3 se 40 characters ka bhejo.", reply_markup=CANCEL)
        ctx.user_data["bwn"] = {"title": text}
        ctx.user_data["st"] = "bw_link"
        return await m.reply_text("Ab us bot ka <b>refer link</b> bhejo (jis link se log join karenge):",
                                  parse_mode="HTML", reply_markup=CANCEL)

    if st == "bw_link":
        if not URL_RE.match(text):
            return await m.reply_text("❌ Sahi link bhejo (https://...).", reply_markup=CANCEL)
        ctx.user_data["bwn"]["link"] = text
        ctx.user_data["st"] = "bw_reward"
        return await m.reply_text(f"Per user kitne coins doge? Min <b>{config.BW_MIN_REWARD}</b> "
                                  f"(zyada doge to log jaldi karenge).", parse_mode="HTML", reply_markup=CANCEL)

    if st == "bw_reward":
        if not text.isdigit() or not (config.BW_MIN_REWARD <= int(text) <= 100000):
            return await m.reply_text(f"❌ {config.BW_MIN_REWARD} ya usse zyada number bhejo.", reply_markup=CANCEL)
        ctx.user_data["bwn"]["reward"] = int(text)
        ctx.user_data["st"] = "bw_count"
        return await m.reply_text(f"Kitne users chahiye? ({config.BW_MIN_USERS} se {config.BW_MAX_USERS})",
                                  reply_markup=CANCEL)

    if st == "bw_count":
        if not text.isdigit() or not (config.BW_MIN_USERS <= int(text) <= config.BW_MAX_USERS):
            return await m.reply_text(f"❌ {config.BW_MIN_USERS} se {config.BW_MAX_USERS} ke beech number bhejo.",
                                      reply_markup=CANCEL)
        n = int(text)
        bw = ctx.user_data.get("bwn")
        if not bw or "reward" not in bw:
            ctx.user_data.clear()
            return await m.reply_text("Session expire. Dobara try karo.")
        cost = bw["reward"] * n
        u = await db.get_user(uid)
        if u["ad_balance"] < cost:
            ctx.user_data.clear()
            return await m.reply_text(
                f"❌ Coins kam hain.\nChahiye: {cost}\nAd balance: {u['ad_balance']}\nKami: {cost - u['ad_balance']}",
                reply_markup=M([[B("➕ Deposit", callback_data="dep")]]))
        bw["n"] = n
        ctx.user_data.pop("st", None)
        return await m.reply_text(
            f"📝 <b>Confirm Bot Work</b>\nBot: {h(bw['title'])}\nReward: {bw['reward']} coins per user\n"
            f"Users: {n}\nTotal cost: <b>{cost}</b> coins (escrow me lock hoga)",
            parse_mode="HTML",
            reply_markup=M([[B("✅ Confirm", callback_data="bw_ok"), B("❌ Cancel", callback_data="cancel")]]))


# ---------------- background job ----------------
async def job(ctx):
    for r in await db.bw_auto_report(config.BW_REVIEW_HOURS):
        await send_report(ctx, r["id"])
    await db.bw_close_expired(config.BW_REPORT_HOURS)
