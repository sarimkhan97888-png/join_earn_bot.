"""Admin ke kaam (bot buttons aur Admin Panel dono yahi use karte hain, ek hi logic)."""
import html

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M, WebAppInfo

import config
import db
import extras
import util


async def wd_act(main, wid, act):
    """act: ok (approve=manual paid) | no (reject+refund) | paid (sending->paid) | refund (sending->failed). Return (ok, msg)."""
    tax = config.WITHDRAW_TAX_PERCENT
    if act == "no":
        w = await db.wd_move_refund(wid, "pending", "rejected")
        if not w:
            return False, "Already processed"
        extras.feed(f"❌ Withdraw #{wid} <b>rejected</b>, {w['coins']} coins refund (user <code>{w['user_id']}</code>)")
        await util.notify(main, w["user_id"], f"❌ Withdraw #{wid} reject hua, coins wapas mil gaye.")
        msg = "Rejected & refunded"
    elif act == "ok":
        w = await db.wd_move(wid, "pending", "paid")
        if not w:
            return False, "Already processed"
        await extras.post_payout(w)
        extras.feed(f"✅ Withdraw #{wid} <b>approved (manual paid)</b> ₹{float(w['amount_inr']):.2f} → <code>{html.escape(w['upi'])}</code> (user <code>{w['user_id']}</code>)")
        await util.notify(main, w["user_id"],
                          f"✅ Withdraw #{wid} paid: ₹{float(w['amount_inr']):.2f} → {w['upi']} (tax {tax}% alag se kata)")
        msg = "✅ Approved — UPI par manually pay kar do"
    elif act == "paid":
        w = await db.wd_move(wid, "sending", "paid")
        if not w:
            return False, "Already processed"
        await extras.post_payout(w)
        extras.feed(f"✅ Withdraw #{wid} <b>paid</b> (manual mark) ₹{float(w['amount_inr']):.2f}")
        await util.notify(main, w["user_id"], f"✅ Withdraw #{wid} paid: ₹{float(w['amount_inr']):.2f} → {w['upi']}")
        msg = "✅ Paid mark ho gaya"
    elif act == "refund":
        w = await db.wd_move_refund(wid, "sending", "failed")
        if not w:
            return False, "Already processed"
        extras.feed(f"↩️ Withdraw #{wid} <b>failed</b>, user ko refund")
        await util.notify(main, w["user_id"], f"❌ Withdraw #{wid} fail hua, coins wapas mil gaye.")
        msg = "↩️ User ko refund ho gaya"
    else:
        return False, "Galat action"
    await extras.bk_delete(wid)  # admins ke saare alert copies delete
    return True, msg


async def claim_act(main, cid, approve):
    if approve:
        cl = await db.fam_claim_approve(cid)
        if not cl:
            return False, "Already processed / mail aa chuki"
        extras.feed(f"✅ Claim #{cid} approved: ₹{cl['amount_paise'] / 100:.2f} (user <code>{cl['user_id']}</code>)")
        await util.notify(main, cl["user_id"], f"✅ <b>Deposit successful!</b>\n+{cl['amount_paise']} coins ad balance me add ho gaye.")
        return True, "✅ Credit ho gaya"
    cl = await db.fam_claim_reject(cid)
    if not cl:
        return False, "Already processed"
    await util.notify(main, cl["user_id"], "❌ Tumhara deposit claim verify nahi ho paya. Galti ho to Support me batao.")
    return True, "❌ Reject ho gaya"


async def assign(main, txn, uid):
    pay = await db.fam_assign(txn, uid)
    if not pay:
        return False, "Nahi hua: txn unmatched nahi hai ya user nahi mila."
    await util.notify(main, uid, f"✅ <b>Deposit successful!</b>\n+{pay['pay_paise']} coins ad balance me add ho gaye.")
    extras.feed(f"✅ Unmatched ₹{pay['pay_paise'] / 100:.2f} assign hua (user <code>{uid}</code>)")
    return True, f"✅ ₹{pay['pay_paise'] / 100:.2f} → user {uid} ke ad balance me."


async def user_act(main, uid, act, amount=0):
    """ban | unban | resetdev | addbal | addad. Admin accounts par ban/reset nahi."""
    if act in ("ban", "unban"):
        if uid in config.ADMIN_IDS:
            return False, "Admin ko ban nahi kar sakte."
        if not await db.set_ban(uid, act == "ban"):
            return False, "User nahi mila."
        return True, "🚫 Banned" if act == "ban" else "✅ Unbanned"
    if act == "resetdev":
        if not await db.reset_device(uid):
            return False, "User nahi mila."
        await util.notify(main, uid, "🔐 Tumhara device reset ho gaya. App kholo aur dobara verify karo.")
        return True, "✅ Device reset ho gaya"
    if act in ("addbal", "addad"):
        if not (0 < amount <= 100_000_000):
            return False, "Amount 1 se 10 crore coins ke beech daalo."
        v = await db.admin_add(uid, amount, act == "addad")
        if v is None:
            return False, "User nahi mila."
        extras.feed(f"👑 Admin ne user <code>{uid}</code> ko +{amount:,} coins ({'ad balance' if act == 'addad' else 'balance'}) diye")
        return True, f"✅ +{amount:,} coins add. Naya: {v:,}"
    return False, "Galat action"


def panel_row():
    """'Open Panel' button row (backup bot ke alerts me): main bot ka Mini App seedha admin panel par khulta hai."""
    mb = util.main_bot
    un = getattr(mb, "username", None) if mb else None
    return [B("🛠 Open Panel", url=f"https://t.me/{un}?startapp=admin")] if un else []


def panel_kb():
    return M([[B("🛠 Admin Panel", web_app=WebAppInfo(url=f"{config.BASE_URL}/app?admin=1"))]])
