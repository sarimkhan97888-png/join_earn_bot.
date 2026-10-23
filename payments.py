"""Payment ke baad user ko bhejne wale messages (Fam / Stars)."""
import config


def premium_msg(done):
    p = config.PLANS[int(done["level"])]
    how = {"activated": "Turant chalu ho gaya 🎉", "extended": f"Purane premium me {p['days']} din jud gaye 🎉",
           "queued": "Purana premium khatam hone ke baad apne aap chalu ho jayega ⏭️"}.get(done.get("outcome"), "")
    return f"✅ <b>Premium Level {done['level']} mil gaya!</b> ({p['days']} din)\n{how}"


def paid_msg(done):
    if done["kind"] == "deposit":
        return f"✅ <b>Deposit successful!</b>\n+{done['coins']} coins ad balance me add ho gaye."
    return premium_msg(done)
