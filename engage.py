"""Users ko wapas laane / bhaagidaari badhane wale jobs:
1) offer khatam hone par winners post (channel)   2) streak tootne se pehle yaad   3) 3+ din se gayab users ko DM
4) raat 10 baje admin ko daily summary            5) hafte me ek baar top referrers ka shoutout (channel)"""
import asyncio
import html
import logging
import time
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import banner
import config
import db
import extras
import promo
import util

log = logging.getLogger("engage")
IST = timezone(timedelta(hours=5, minutes=30))


def _now():
    return datetime.now(IST)


async def _meta(k, d=""):
    return await promo._meta(k, d)


async def _channel_post(bot, head, badge, caption, seed):
    """Banner + caption channel me. Banner na bane to sirf text. True/False."""
    if not config.FORCE_CHANNEL:
        return False
    kb = M([[B(f"🚀 Open {config.APP_NAME}", url=f"https://t.me/{bot.username}")]])
    try:
        img = await asyncio.to_thread(banner.render, head, badge, None, bot.username, config.APP_NAME, seed)
    except Exception as e:
        log.warning("banner failed: %s", e)
        img = None
    try:
        if img:
            await bot.send_photo(config.FORCE_CHANNEL, img, caption=caption[:1024], parse_mode="HTML", reply_markup=kb)
        else:
            await bot.send_message(config.FORCE_CHANNEL, caption[:1024], parse_mode="HTML", reply_markup=kb)
        return True
    except Exception as e:
        log.warning("channel post failed: %s", e)
        return False


# ---------- 1) offer summary ----------
async def job_offer_summary(ctx):
    try:
        rows = await db.offers_to_summarize()
    except Exception:
        log.exception("offer summary fetch")
        return
    for o in rows:
        what = f"{o['target']} refer" if o["kind"] == "refer" else f"{o['target']} coins kamana"
        if o["winners"] > 0:
            cap = (f"<b>🏁 OFFER KHATAM! 🏁</b>\n\n🎯 Offer: <b>{html.escape(what)}</b> → <b>{o['bonus']} coins</b> bonus\n"
                   f"🏆 Jeetne wale: <b>{o['winners']}</b> user\n💰 Bante coins: <b>{o['winners'] * o['bonus']}</b>\n\n"
                   "Bonus sabke account me aa chuka hai ✅\n━━━━━━━━━━━━━━\n🔥 <b>AGLA OFFER MISS MAT KARO</b> 🔥")
            ok = await _channel_post(ctx.bot, "Offer khatam!", f"{o['winners']} WINNERS", cap, o["id"] + 7)
            extras.feed(f"🏁 Offer #{o['id']} khatam: {o['winners']} winners, {o['winners'] * o['bonus']} coins. Channel post: {'ok' if ok else 'fail'}")
        else:
            extras.feed(f"🏁 Offer #{o['id']} khatam: koi winner nahi (channel me post nahi ki)")
        await db.offer_summarized(o["id"])


# ---------- 2) streak yaad ----------
async def job_streak_remind(ctx):
    if not 19 <= _now().hour < 22:   # shaam 7-10 (IST) me hi
        return
    try:
        rows = await db.eng_streak_batch(25)
    except Exception:
        log.exception("streak remind")
        return
    for uid, st in rows:
        await util.notify(ctx.bot, uid, f"🔥 Tumhari {st} din ki streak aaj raat toot sakti hai! Bas 1 task kar lo aur streak bachao 💪",
                          disable_notification=True)
        await asyncio.sleep(0.05)
    if rows:
        extras.feed(f"🔥 Streak reminder gaye: {len(rows)} user")


# ---------- 3) wapas lana ----------
async def job_reengage(ctx):
    if not 10 <= _now().hour < 21:
        return
    try:
        ids = await db.eng_reeng_batch(20)
        offs = await db.offers_active() if ids else []
    except Exception:
        log.exception("reengage")
        return
    for uid in ids:
        if offs:
            txt = f"👋 Kaafi din ho gaye! Naye tasks aur ads tumhara wait kar rahe hain.\n🎯 Abhi offer chal raha hai: {offs[-1]['bonus']} coins bonus!\nAbhi app kholo aur coins kamao 🚀"
        else:
            txt = "👋 Kaafi din ho gaye! Naye tasks aur ads tumhara wait kar rahe hain.\nAbhi app kholo aur coins kamao 🚀"
        await util.notify(ctx.bot, uid, txt, disable_notification=True)
        await asyncio.sleep(0.05)
    if ids:
        extras.feed(f"👋 Wapas-aao DM gaye: {len(ids)} user")


# ---------- 4) raat ki summary ----------
async def job_daily_summary(ctx):
    n = _now()
    if n.hour < 22:
        return
    day = n.strftime("%Y-%m-%d")
    if await _meta("sum_day") == day:
        return
    await db.usdt_meta_set("sum_day", day)
    try:
        s = await db.eng_daily()
    except Exception:
        log.exception("daily summary")
        return
    txt = (f"📊 <b>Aaj ka hisaab</b> ({n:%d %b})\n"
           f"👥 Total users: <b>{s['users']}</b> (naye: <b>{s['new_users']}</b>, aaj active: <b>{s['active']}</b>)\n"
           f"📺 Ads poore dekhe: <b>{s['ads']}</b>\n📣 Channel joins (tasks): <b>{s['joins']}</b>\n"
           f"🪙 Users ko mile coins (approx): <b>{s['coins_out']}</b>\n"
           f"💸 Withdraw requests: <b>{s['wd_n']}</b> (₹{s['wd_inr']:.0f}) | pending abhi: ₹{s['wd_pending_inr']:.0f}\n"
           f"💳 Deposit aaya: ₹{s['dep_inr']:.0f}\n"
           f"🎯 Offer winners: <b>{s['offer_wins']}</b> ({s['offer_coins']} coins)")
    await extras.to_admin(txt)


# ---------- 5) weekly shoutout ----------
def _name(n):
    n = (n or "User").strip()
    return html.escape((n[:2] + "***") if len(n) > 3 else (n[:1] + "**"))


async def job_weekly_shoutout(ctx):
    n = _now()
    if n.weekday() != 6 or not 18 <= n.hour < 22:   # ravivaar shaam
        return
    key = n.strftime("%G-W%V")
    if await _meta("shout_week") == key:
        return
    await db.usdt_meta_set("shout_week", key)
    try:
        top = await db.lb_top("refer", 3)
    except Exception:
        log.exception("shoutout")
        return
    if not top:
        return
    medals = ["🥇", "🥈", "🥉"]
    rows = "\n".join(f"{medals[i]} <b>{_name(r['first_name'])}</b> — {r['score']} refer" for i, r in enumerate(top))
    cap = (f"<b>🏆 TOP REFERRERS 🏆</b>\n\nIs mahine ab tak sabse zyada dost laane wale:\n\n{rows}\n\n"
           "Tum bhi dost laao aur leaderboard me aao 👇\n━━━━━━━━━━━━━━\n🔥 <b>REFER KARO, PRIZE JEETO</b> 🔥")
    await _channel_post(ctx.bot, "Top referrers", f"TOP {len(top)}", cap, n.isocalendar()[1])
