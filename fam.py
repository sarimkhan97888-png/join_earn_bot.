"""FamPay deposit: user Fam UPI par exact (paise wala) amount bhejta hai, hum Gmail IMAP se Fam ka
"successfully received" mail padhke order auto-confirm karte hain.

Safety:
 - sender domain + DKIM (Gmail ka Authentication-Results) check: nakli mail credit nahi karti
 - transaction id UNIQUE: ek payment do baar credit nahi hoti
 - order amount unique (paise tail): exact matching
 - mail padhna read-only (BODY.PEEK), All Mail + Spam dono folder
"""
import asyncio
import email
import html
import imaplib
import logging
import re
from decimal import Decimal
from email.utils import parseaddr, parsedate_to_datetime
import time

import config
import db
import extras
import payments
import util

log = logging.getLogger("fam")


def enabled():
    return bool(config.FAM_UPI_ID and config.IMAP_USER and config.IMAP_PASS)


# ---------------- mail parsing ----------------
def _domain_ok(domain):
    domain = domain.lower()
    return any(domain == d or domain.endswith("." + d) for d in config.ALLOWED_SENDER_DOMAINS)


def sender_ok(msg):
    _, addr = parseaddr(msg.get("From", ""))
    if "@" not in addr or not _domain_ok(addr.rsplit("@", 1)[1]):
        return False
    if config.REQUIRE_DKIM:
        # Sirf sabse upar wala Authentication-Results (Gmail ka khud ka). Neeche wale koi bhi bana sakta hai.
        hdrs = msg.get_all("Authentication-Results") or []
        if not hdrs:
            return False
        top = str(hdrs[0]).strip().lower()
        if not top.startswith("mx.google.com"):
            return False
        for m in re.finditer(r"dkim=pass[^;]*?header\.(?:i|d)=@?([\w.\-]+)", top):
            if _domain_ok(m.group(1)):
                return True
        return False
    return True


def mail_text(msg):
    html_part = plain_part = None
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype in ("text/html", "text/plain"):
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            s = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            if ctype == "text/html" and html_part is None:
                html_part = s
            elif ctype == "text/plain" and plain_part is None:
                plain_part = s
    s = html_part or plain_part or ""
    s = re.sub(r"(?is)<(style|script).*?>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def to_paise(s):
    return int((Decimal(s.replace(",", "")) * 100).to_integral_value())


_AMT = r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)"


def parse_fam_mail(text):
    """dict(paise, sender, txn, bal) | None (received mail nahi) | "unparsed" (received lagta hai par format samajh nahi aaya)."""
    low = text.lower()
    if "received" not in low:
        return None
    if "successfully received" not in low and "credited" not in low:
        return None
    m = re.search(r"received\s*" + _AMT, text, re.I)
    t = re.search(r"(?:transaction\s*id|txn\s*id|upi\s*ref(?:erence)?(?:\s*no\.?)?|utr)\s*:?\s*([A-Za-z0-9]{8,40})", text, re.I)
    if not m or not t:
        return "unparsed"
    s = re.search(r"from\s+(.+?)\s+(?:transaction\s*id|txn\s*id|upi\s*ref|utr|on\s)", text, re.I)
    b = re.search(r"updated\s*balance\s*:?\s*" + _AMT, text, re.I)
    return {
        "paise": to_paise(m.group(1)),
        "sender": (s.group(1).strip() if s else "-")[:60],
        "txn": t.group(1).upper(),
        "bal": to_paise(b.group(1)) if b else None,
    }


# ---------------- IMAP (blocking, thread me) ----------------
def _q(folder):
    return '"' + folder.replace('"', "") + '"'


def _validity(M):
    try:
        _, d = M.response("UIDVALIDITY")
        return d[0].decode() if d and d[0] else "0"
    except Exception:
        return "0"


def poll_sync(states, M=None):
    """Naye mails padho. states={folder:(validity,last_uid)}. Return ([(folder,validity,uid,raw)], {folder:(validity,uid)} baseline)."""
    own = M is None
    if own:
        M = imaplib.IMAP4_SSL(config.IMAP_HOST, timeout=30)
    out, base = [], {}
    try:
        if own:
            M.login(config.IMAP_USER, config.IMAP_PASS)
        doms = config.ALLOWED_SENDER_DOMAINS
        crit = ["FROM", f'"{doms[0]}"']
        for d in doms[1:]:
            crit = ["OR"] + crit + ["FROM", f'"{d}"']
        for folder in config.IMAP_FOLDERS:
            typ, _ = M.select(_q(folder), readonly=True)
            if typ != "OK":
                log.warning("IMAP folder nahi khula: %s", folder)  # alag language Gmail me naam alag ho sakta hai
                continue
            validity = _validity(M)
            st = states.get(folder)
            if st is None or st[0] != validity:  # pehli baar: purane mails skip, aaj se shuru
                typ, data = M.uid("SEARCH", None, *crit)
                ids = [int(x) for x in (data[0] or b"").split()]
                base[folder] = (validity, max(ids) if ids else 0)
                continue
            last = st[1]
            typ, data = M.uid("SEARCH", None, "UID", f"{last + 1}:*", *crit)
            for uid in sorted(int(x) for x in (data[0] or b"").split()):
                if uid <= last:
                    continue
                typ, d = M.uid("FETCH", str(uid), "(BODY.PEEK[])")
                if typ == "OK" and d and isinstance(d[0], tuple):
                    out.append((folder, validity, uid, d[0][1]))
                else:
                    out.append((folder, validity, uid, b""))
    finally:
        if own:
            try:
                M.logout()
            except Exception:
                pass
    return out, base


# ---------------- processing ----------------
async def handle_raw(raw):
    if not raw:
        return
    msg = email.message_from_bytes(raw)
    text = mail_text(msg)
    if not sender_ok(msg):
        if "successfully received" in text.lower():
            log.warning("rejected mail from %s", msg.get("From"))
            extras.feed("🚨 Shak wala 'received' mail reject hua (sender/DKIM check fail).")
        return
    p = parse_fam_mail(text)
    if p is None:
        return
    if p == "unparsed":
        extras.feed("⚠️ Fam ka mail aaya par samajh nahi aaya (format alag?). Snippet:\n<code>"
                    + html.escape(text[:350]) + "</code>")
        return
    try:
        ts = parsedate_to_datetime(msg["Date"]).timestamp()
    except Exception:
        ts = time.time()
    res = await db.fam_process(p, ts)
    if res is None:
        return  # duplicate mail
    bot = util.main_bot
    rupees = f"₹{p['paise'] / 100:.2f}"
    if res["done"]:
        d = res["done"]
        if bot:
            await util.notify(bot, d["user_id"], payments.paid_msg(d))
        extras.feed(f"💰 <b>{'Deposit' if d['kind'] == 'deposit' else 'Premium L%s' % d.get('level')} paid</b> {rupees} (user <code>{d['user_id']}</code>)")
    elif res["claim_user"]:
        if bot:
            await util.notify(bot, res["claim_user"], f"✅ <b>Deposit successful!</b>\n+{res['claim_coins']} coins ad balance me add ho gaye.")
        extras.feed(f"💰 Claim auto-credit {rupees} (user <code>{res['claim_user']}</code>)")
    elif res["unmatched"]:
        extras.feed(f"❓ <b>Unmatched payment</b> {rupees} from {html.escape(p['sender'])} txn <code>{p['txn']}</code> "
                    f"— Admin Panel > Deposits se user ko assign karo.")
    if res["gap"]:
        extras.feed(f"⚠️ Fam balance mismatch: expected ₹{res['gap'][0] / 100:.2f}, mail me ₹{res['gap'][1] / 100:.2f}. "
                    f"Koi mail miss hui ya Fam se paise kharch hue.")


async def poll_once():
    states = await db.fam_states()
    mails, base = await asyncio.to_thread(poll_sync, states)
    for folder, (v, u) in base.items():
        await db.fam_set_state(folder, v, u)
    for folder, v, uid, raw in mails:
        await handle_raw(raw)  # DB error aaye to raise: state aage nahi badhta, agli poll me dobara (txn id unique hai)
        await db.fam_set_state(folder, v, uid)


async def run():
    """Background loop. Error aaye to backoff; baar baar fail ho to admin ko ek baar batao."""
    fails = 0
    while True:
        try:
            await poll_once()
            fails = 0
        except asyncio.CancelledError:
            raise
        except Exception as e:
            fails += 1
            log.error("fam poll error (#%s): %s: %s", fails, type(e).__name__, e)
            if fails in (3, 40, 400):
                extras.feed(f"🚨 Fam mail padhna fail ho raha hai: <code>{html.escape(type(e).__name__)}</code>. "
                            f"IMAP_USER/IMAP_PASS (App Password) ya IMAP on hai ya nahi check karo. Deposits tab tak claim se honge.")
        await asyncio.sleep(config.FAM_POLL_SECONDS * (1 if fails < 5 else 4))


async def claim_alert(cid, user_id, txn, paise):
    """Admin ko claim approve/reject buttons ke saath (backup bot se)."""
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
    kb = M([[B("✅ Credit karo", callback_data=f"clm_ok:{cid}"), B("❌ Reject", callback_data=f"clm_no:{cid}")]])
    await extras.bk_send(f"🧾 <b>Deposit claim #{cid}</b>\nUser: <code>{user_id}</code>\nAmount: ₹{paise / 100:.2f}\n"
                         f"Txn: <code>{html.escape(txn)}</code>\nFam app me ye payment dekh ke hi Credit dabao.", kb)
