"""Force-join channel me har ~1 ghante AI se naya promotion / offer post (har baar alag topic + alag style).
Offer admin /offer se deta hai: refer/coin offers ka bonus db.offer_track se apne aap milta hai."""
import asyncio
import html
import json
import logging
import random
import re
import time

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M

import ai
import banner
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
        return t, float(o["ends_ts"]), f"+{o['bonus']} COINS"
    t = await _meta("offer_text")
    try:
        until = float(await _meta("offer_until", "0"))
    except ValueError:
        until = 0
    return (t, until, None) if t and until > time.time() else None


async def set_offer(text, hours):
    await db.usdt_meta_set("offer_text", text)
    await db.usdt_meta_set("offer_until", time.time() + hours * 3600)


async def clear_offer():
    await db.usdt_meta_set("offer_text", "")
    await db.usdt_meta_set("offer_until", 0)


BADGES = {"welcome": "{wb} COINS FREE", "refer": "+{ref} COINS / REFER", "tasks": "JOIN & EARN", "ads": "+{ar} COINS / AD", "withdraw": "MIN {mw} COINS",
          "streak": "DAILY STREAK", "lb": "MONTHLY PRIZES", "addtask": "REAL MEMBERS", "premium": "FROM Rs {p1}", "rules": "FAIR PLAY",
          "howto": "3 SIMPLE STEPS", "deposit": "UPI DEPOSIT"}
FRAMES = ["◇💎◇", "✨", "🚀", "🔥", "💫"]
DOTS = ["💸", "🎯", "👥", "🎁", "💰", "📣"]


def _txt(s, n=90):
    """AI ke ek field ko saaf plain text: markdown/emoji-html hatao, jhoote daave/links dikhe to ValueError."""
    t = re.sub(r"[*_`#<>]+", "", str(s or "")).strip()
    t = re.sub(r"\s+", " ", t)
    if len(t) > n or _BAD.search(t):
        raise ValueError("ai field rejected")
    return t


def _split(tmpl):
    """Template ("<b>head</b>\nbody") -> (headline, [points])."""
    head, _, rest = tmpl.partition("\n")
    head = re.sub(r"<[^>]+>", "", head).strip()
    pts = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", re.sub(r"<[^>]+>", "", rest)) if s.strip()][:3]
    return head, pts


def _fallback(idx, offer):
    f = _facts()
    f["ss2"] = 2 * f["ss"]
    if offer:
        return {"headline": "🎯 Aaj ka offer", "badge": None, "points": [offer], "cta": f"{f['name']} kholo, hissa lo"}
    k, _, tmpl = ANGLES[idx % len(ANGLES)]
    head, pts = _split(tmpl.format(**f))
    return {"headline": head, "badge": BADGES[k].format(**f), "points": pts, "cta": f"Abhi {f['name']} kholo"}


async def compose(idx, offer=None, badge=None):
    """Return (dict(headline, badge, points[], cta), 'ai' | 'fallback')."""
    if not ai.enabled():
        r = _fallback(idx, offer)
        if offer:
            r["badge"] = badge
        return r, "fallback"
    f = _facts()
    k, angle_t, _ = ANGLES[idx % len(ANGLES)]
    angle = angle_t.format(**f)
    try:
        hist = json.loads(await _meta("promo_hist", "[]"))
    except ValueError:
        hist = []
    style = random.choice(STYLES)
    system = (f"You write ONE Telegram channel post in Hinglish (Hindi in Roman letters + simple English) for \"{f['name']}\", "
              "an earn-by-tasks Telegram Mini App. Output STRICT JSON only, no other text:\n"
              '{"headline": "max 5 words, catchy", "badge": "max 3 words, only if a number/fact is given, else empty", '
              '"points": ["3 short lines, each max 12 words"], "cta": "max 6 words call to action"}\n'
              "Rules:\n- Use ONLY the facts given. Never invent numbers, payouts, testimonials, names, deadlines or income claims.\n"
              "- Never promise guaranteed/easy/daily income. Never say best, no.1, 100%, pakka, lakhs, crores.\n"
              "- Plain text in every field: no emoji, no markdown, no hashtags, no links, no @mentions, no OTP/password/PIN talk.\n"
              "- Be fresh and not boring: do NOT reuse the headline or wording of the previous posts listed.")
    prompt = f"FACTS:\n{angle}\n\nSTYLE: {style}\n"
    if offer:
        prompt = (f"MAIN POINT (must be in the post, keep every number and condition exactly as written, add nothing new): {offer}\n\n"
                  f"EXTRA FACT you may use: {angle}\n\nSTYLE: {style}\n")
    if hist:
        prompt += "\nPREVIOUS POSTS (do not repeat their wording):\n" + "\n".join("- " + h for h in hist[-6:])
    try:
        raw = await ai.generate(system, prompt, max_tokens=300)
        j = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        pts = [_txt(x, 110) for x in (j.get("points") or [])][:3]
        out = {"headline": _txt(j.get("headline"), 50), "badge": _txt(j.get("badge"), 22) or None, "points": [x for x in pts if x],
               "cta": _txt(j.get("cta"), 45)}
        if not out["headline"] or not out["points"]:
            raise ValueError("empty")
        if offer:   # offer ke saare numbers post me hone chahiye, nahi to AI ne badal diya: template
            allt = " ".join([out["headline"], out["badge"] or "", out["cta"]] + out["points"])
            if any(n not in allt for n in re.findall(r"\d+", offer)):
                raise ValueError("offer numbers changed")
            out["badge"] = badge or out["badge"]
        elif not out["badge"]:
            out["badge"] = BADGES[k].format(**f)
        return out, "ai"
    except Exception as e:
        log.warning("promo ai failed, template: %s", e)
        r = _fallback(idx, offer)
        if offer:
            r["badge"] = badge
        return r, "fallback"


def caption(c, bot_username, until=None, idx=0):
    """Post ka sundar HTML caption. 5 alag design (har post alag), sab me headline, bot, points, CTA."""
    e = html.escape
    H = e(re.sub(r"\s+", " ", c["headline"]).upper())
    h = e(re.sub(r"\s+", " ", c["headline"]))
    cta = e((c["cta"] or "Abhi shuru karo").upper())
    pts = [e(x) for x in c["points"]]
    bot = "@" + e(bot_username)
    dots = DOTS[idx % len(DOTS):] + DOTS[:idx % len(DOTS)]
    off = f"⏳ <b>Offer {time.strftime('%d %b', time.gmtime(until + 19800))} tak</b>" if until else ""
    st = idx % 5
    if st == 0:     # box header + bullets (user ka sample jaisa)
        L = [f"<b>◇💎◇ {H} ◇💎◇</b>", "", f"🤖 <b>BOT:</b> {bot}", ""] + [f"{dots[i % 6]} {x}" for i, x in enumerate(pts)]
        L += ([""] + [off] if off else []) + ["", "━━━━━━━━━━━━━━", f"🔥 <b>{cta}</b> 🔥"]
    elif st == 1:   # sparkle + tick
        L = [f"✨ <b>{h}</b> ✨", ""] + [f"✅ {x}" for x in pts] + ([""] + [off] if off else []) + ["", f"👉 <b>{cta}</b>", f"🤖 {bot}"]
    elif st == 2:   # bars header
        L = ["▰▰▰▰▰▰▰▰▰▰▰▰", f"<b>{H}</b>", "▰▰▰▰▰▰▰▰▰▰▰▰", ""] + [f"▸ {x}" for x in pts] + ([""] + [off] if off else []) + ["", f"🚀 <b>{cta}</b>", f"🤖 {bot}"]
    elif st == 3:   # alert style
        L = [f"🚨 <b>{H}</b> 🚨", ""] + [f"{dots[i % 6]} <i>{x}</i>" for i, x in enumerate(pts)] + ([""] + [off] if off else []) + ["", "┈┈┈┈┈┈┈┈┈┈┈┈┈┈", f"💥 <b>{cta}</b> 💥", bot]
    else:           # quote style
        L = [f"💬 <b>{h}</b>", ""] + [f"┃ {x}" for x in pts] + ([""] + [off] if off else []) + ["", f"🎯 <b>{cta}</b> → {bot}"]
    return "\n".join(L)[:1024]


async def post(bot, force_offer=False):
    """Channel me ek post (banner image + caption). Return (ok, info)."""
    if not config.FORCE_CHANNEL:
        return False, "FORCE_CHANNEL set nahi"
    n = int(await _meta("promo_n", "0") or 0)
    off = await active_offer()
    use_offer = bool(off) and (force_offer or n % 2 == 1)   # offer chalu ho to har doosra post offer ka
    c, src = await compose(n, off[0] if use_offer else None, off[2] if use_offer else None)
    cap = caption(c, bot.username, off[1] if use_offer else None, n)
    await db.usdt_meta_set("promo_n", n + 1)
    await db.usdt_meta_set("promo_last", time.time())
    kb = M([[B(f"🚀 Open {config.APP_NAME}", url=f"https://t.me/{bot.username}")]])
    img = None
    try:
        img = await asyncio.to_thread(banner.render, c["headline"], c["badge"], c["points"][0] if use_offer else None, bot.username, config.APP_NAME, n)
    except Exception as e:
        log.warning("banner render failed, text post: %s", e)
    try:
        if img:
            await bot.send_photo(config.FORCE_CHANNEL, img, caption=cap, parse_mode="HTML", reply_markup=kb)
        else:
            await bot.send_message(config.FORCE_CHANNEL, cap, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        log.warning("promo post failed: %s", e)
        return False, f"{type(e).__name__}: {e}"
    try:
        hist = json.loads(await _meta("promo_hist", "[]"))
    except ValueError:
        hist = []
    hist.append((c["headline"] + " | " + " ".join(c["points"]))[:110])
    await db.usdt_meta_set("promo_hist", json.dumps(hist[-6:]))
    return True, f"{src}{' + offer' if use_offer else ''}{'' if img else ' (text)'}"


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
