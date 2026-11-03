"""Force-join channel me har ~1 ghante AI se naya promotion / offer post (har baar alag topic + alag style).
Offer admin /offer se deta hai: refer/coin offers ka bonus db.offer_track se apne aap milta hai."""
import html
import json
import logging
import random
import re
import time

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import ai
import config
import db

log = logging.getLogger("promo")

# Ye words AI ke output me aaye to post nahi jaati (jhoote / income ke daave), template jaati hai
_BAD = re.compile(r"guarantee|100\s?%|pakka|risk[\s-]?free|lakh|crore|best app|no\.?\s?1\b|otp|password|\bpin\b|https?://|@\w|t\.me", re.I)

STYLES = [
    "chhota aur punchy (2-3 line)",
    "sawal se shuru karo, phir jawab",
    "3 chhote bullet points (• se)",
    "mini kahani jaisa (2-3 line, 'ek dost ne...' jaisa nahi, bas flow)",
    "emoji wali headline + 2 line detail",
    "myth vs fact style (sirf sachchi baatein)",
    "aaj ka tip jaisa",
    "friendly dost ki tarah baat, halka masti wala tone",
    "step-by-step 1-2-3",
]


def _facts():
    c = config
    inr = c.COIN_PER_INR
    pl = c.PLANS
    fee3 = c.WITHDRAW_TAX_PERCENT if pl[3]["fee"] is None else pl[3]["fee"]
    lbr, lbc = c.LB_PRIZES["refer"], c.LB_PRIZES["coin"]
    return {
        "wb": c.WELCOME_COINS, "mw": c.MIN_WITHDRAW_COINS, "mwr": c.MIN_WITHDRAW_COINS // inr, "tax": c.WITHDRAW_TAX_PERCENT,
        "ref": pl[1]["ref"], "mt": c.MIN_TASKS_FOR_REFER, "ar": c.ADS_REWARD, "ad": c.ADS_DAILY, "ss": c.STREAK_STEP, "sd": c.STREAK_DAYS,
        "p1": pl[1]["price"], "p2": pl[2]["price"], "p3": pl[3]["price"], "d1": pl[1]["days"], "d2": pl[2]["days"], "d3": pl[3]["days"], "fee3": fee3,
        "lbr": "/".join(map(str, lbr)), "lbc": "/".join(map(str, lbc)), "mtm": c.MIN_TASK_MEMBERS, "name": c.APP_NAME,
        "ms": ", ".join(f"{k} refer = +{v} coins" for k, v in sorted(c.REF_BONUSES.items())),
    }


# (key, AI ko di jaane wali sachchi baat, fallback template)
ANGLES = [
    ("welcome", "Naye user ko {wb} coins welcome bonus free milta hai (100 coins = Rs 1).",
     "🎁 <b>{wb} coins free!</b>\nNaye ho? {name} kholo, welcome bonus seedha wallet me. Phir channels join karke aur coins badhao."),
    ("refer", "Dost ko refer karo: dost {mt} task complete kare to {ref} coins milte hain. Milestone bonus: {ms}.",
     "🤝 <b>Dost laao, coins pao</b>\nDost ke {mt} task complete hote hi {ref} coins. Milestone bonus: {ms}."),
    ("tasks", "Channels join karke reward milta hai, reward join ke baad turant balance me aata hai. Tasks tab me naye tasks.",
     "📣 <b>Join karo, reward lo</b>\nTasks tab me channel join karo, reward turant balance me. Roz naye tasks check karte raho."),
    ("ads", "Watch ad button: har ad poora dekhne par +{ar} coins, roz {ad} ads tak.",
     "📺 <b>Ad dekho, coins pao</b>\nTasks tab me 'Watch ad': har poori ad par +{ar} coins (roz {ad} tak)."),
    ("withdraw", "UPI par withdraw: minimum {mw} coins (Rs {mwr}), tax {tax}% (Premium L3 par {fee3}%). Withdraw ke liye kam se kam 2 task zaroori.",
     "💸 <b>Withdraw simple hai</b>\nMinimum {mw} coins (Rs {mwr}). Kam se kam 2 task karo aur UPI se nikalo."),
    ("streak", "Daily streak: roz kam se kam 1 task karo. Day N = N x {ss} coins, Day {sd} tak, phir dobara Day 1.",
     "🔥 <b>Streak mat todo</b>\nRoz 1 task karo: Day 1 = {ss}, Day 2 = {ss2} ... Day {sd} tak badhta jayega."),
    ("lb", "Monthly leaderboard: har mahine top 3 ko prize. Refer board: {lbr} coins, Coin board: {lbc} coins (Ad Balance me).",
     "🏆 <b>Is mahine ka leaderboard</b>\nTop 3 ko prize: Refer board {lbr} coins, Coin board {lbc} coins. App me Home se dekho."),
    ("addtask", "Apna channel ya bot promote karna ho to Add Task se real members mil sakte hain (min {mtm} members).",
     "📈 <b>Apna channel grow karo</b>\nAdd Task se apne channel/bot ke liye real members lao. Min {mtm} members."),
    ("premium", "Premium plans: L1 Rs {p1} ({d1} din), L2 Rs {p2} ({d2} din), L3 Rs {p3} ({d3} din). Zyada tasks aur kam withdraw tax (L3 par {fee3}%).",
     "💎 <b>Premium lo</b>\nL1 Rs {p1}, L2 Rs {p2}, L3 Rs {p3}. Zyada tasks aur kam tax (L3 par {fee3}%)."),
    ("rules", "Ek device = ek account. Fake ya multiple account ban ho jate hain. Sach me kamao, simple rule.",
     "✅ <b>Fair play</b>\nEk device, ek account. Fake accounts ban hote hain. Seedha rasta apnao."),
    ("howto", "3 step: bot kholo, tasks karo (channel join / watch ad), jab {mw} coins ho jaye to UPI par withdraw.",
     "🚀 <b>Shuru kaise karein?</b>\n1) Bot kholo  2) Tasks karo  3) {mw} coins hone par withdraw."),
    ("deposit", "Advertiser ho? Wallet me UPI se deposit karke apne tasks ke liye coins add karo, payment automatic credit hoti hai.",
     "📣 <b>Advertiser ho?</b>\nUPI se deposit karo, coins automatic add. Phir apne channel ke liye task banao."),
]


async def _meta(k, default=""):
    v = await db.usdt_meta_get(k)
    return default if v is None else v


async def active_offer():
    """(text, until_epoch) ya None. Pehle /offer refer|coin wale (db), phir sirf-text offer."""
    try:
        offs = await db.offers_active()
    except Exception:
        offs = []
    if offs:
        o = offs[-1]
        t = o["text"] or (f"{o['target']} {o['kind']} par {o['bonus']} coins bonus")
        if o["max_winners"]:
            t += f" (sirf {o['max_winners'] - o['winners']} jagah baaki)"
        return t, float(o["ends_ts"])
    t = await _meta("offer_text")
    try:
        until = float(await _meta("offer_until", "0"))
    except ValueError:
        until = 0
    return (t, until) if t and until > time.time() else None


async def set_offer(text, hours):
    await db.usdt_meta_set("offer_text", text)
    await db.usdt_meta_set("offer_until", time.time() + hours * 3600)


async def clear_offer():
    await db.usdt_meta_set("offer_text", "")
    await db.usdt_meta_set("offer_until", 0)


def _clean(txt):
    """AI ka text safe HTML banao: markdown hatao, pehli line bold. Galat/ jhoote daave dikhe to ValueError."""
    t = re.sub(r"[*_`#]+", "", txt).strip()
    t = re.sub(r"^(post|text|output)\s*:\s*", "", t, flags=re.I).strip()
    if not t or len(t) > 700 or _BAD.search(t):
        raise ValueError("ai post rejected")
    head, _, rest = t.partition("\n")
    return f"<b>{html.escape(head.strip())}</b>" + (f"\n{html.escape(rest.strip())}" if rest.strip() else "")


def _fallback(idx, offer):
    f = _facts()
    f["ss2"] = 2 * f["ss"]
    if offer:
        return f"🎯 <b>Aaj ka offer</b>\n{html.escape(offer)}\n\n{f['name']} bot kholo aur hissa lo."
    return ANGLES[idx % len(ANGLES)][2].format(**f)


async def compose(idx, offer=None):
    """Return (html_text, 'ai' | 'fallback')."""
    if not ai.enabled():
        return _fallback(idx, offer), "fallback"
    f = _facts()
    angle = ANGLES[idx % len(ANGLES)][1].format(**f)
    try:
        hist = json.loads(await _meta("promo_hist", "[]"))
    except ValueError:
        hist = []
    style = random.choice(STYLES)
    system = (f"You write ONE short Telegram channel post in Hinglish (Hindi written in Roman letters mixed with simple English) for \"{f['name']}\", "
              "an earn-by-tasks Telegram Mini App.\nRules:\n"
              "- Use ONLY the facts given. Never invent numbers, payouts, testimonials, names, deadlines or income claims.\n"
              "- Never promise guaranteed/easy/daily income. Never say best, no.1, 100%, pakka, lakhs, crores.\n"
              "- 30 to 70 words. Line 1 is a catchy headline (max 8 words, with 1 emoji). Then the body. Max 5 emojis in total.\n"
              "- Plain text only: no markdown, no asterisks, no hashtags, no links, no @mentions, no OTP/password/PIN talk.\n"
              "- End with a short call to action to open the bot (a button is attached automatically; never write a link).\n"
              "- Be fresh and not boring: do NOT reuse the headline, wording or emoji pattern of the previous posts listed.\n"
              "Output ONLY the post text.")
    prompt = f"FACTS:\n{angle}\n\nSTYLE: {style}\n"
    if offer:
        prompt = (f"MAIN POINT (must be in the post, keep every number and condition exactly as written, add nothing new): {offer}\n\n"
                  f"EXTRA FACT you may use: {angle}\n\nSTYLE: {style}\n")
    if hist:
        prompt += "\nPREVIOUS POSTS (do not repeat their wording):\n" + "\n".join("- " + h for h in hist[-6:])
    try:
        out = _clean(await ai.generate(system, prompt))
        if offer:   # offer ke saare numbers post me hone chahiye, nahi to AI ne badal diya: template
            plain = re.sub(r"<[^>]+>", "", out)
            if any(n not in plain for n in re.findall(r"\d+", offer)):
                raise ValueError("offer numbers changed")
        return out, "ai"
    except Exception as e:
        log.warning("promo ai failed, template: %s", e)
        return _fallback(idx, offer), "fallback"


async def post(bot, force_offer=False):
    """Channel me ek post. Return (ok, info)."""
    if not config.FORCE_CHANNEL:
        return False, "FORCE_CHANNEL set nahi"
    n = int(await _meta("promo_n", "0") or 0)
    off = await active_offer()
    use_offer = bool(off) and (force_offer or n % 2 == 1)   # offer chalu ho to har doosra post offer ka
    text, src = await compose(n, off[0] if use_offer else None)
    if use_offer:
        text += f"\n\n⏳ Offer {time.strftime('%d %b', time.gmtime(off[1] + 19800))} tak"
    await db.usdt_meta_set("promo_n", n + 1)
    await db.usdt_meta_set("promo_last", time.time())
    try:
        await bot.send_message(config.FORCE_CHANNEL, text, parse_mode="HTML",
                               reply_markup=M([[B(f"🚀 Open {config.APP_NAME}", url=f"https://t.me/{bot.username}")]]))
    except Exception as e:
        log.warning("promo post failed: %s", e)
        return False, f"{type(e).__name__}: {e}"
    try:
        hist = json.loads(await _meta("promo_hist", "[]"))
    except ValueError:
        hist = []
    hist.append(re.sub(r"<[^>]+>", "", text).replace("\n", " ")[:110])
    await db.usdt_meta_set("promo_hist", json.dumps(hist[-6:]))
    return True, f"{src}{' + offer' if use_offer else ''}"


async def tick(bot):
    """Har 5 min: ghanta ho gaya aur promo on ho to post. Return (ok, info) ya None."""
    if not config.FORCE_CHANNEL:
        return None
    if await _meta("promo_on", "1" if config.PROMO_ON else "0") != "1":
        return None
    try:
        last = float(await _meta("promo_last", "0"))
    except ValueError:
        last = 0
    if time.time() - last < config.PROMO_EVERY_MIN * 60 - 30:
        return None
    return await post(bot)
