import random
from decimal import Decimal

import asyncpg

import config
import util

pool: asyncpg.Pool = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id BIGINT PRIMARY KEY,
  username TEXT, first_name TEXT,
  gmail TEXT UNIQUE, upi TEXT UNIQUE,
  device_hash TEXT UNIQUE, device_ok BOOLEAN NOT NULL DEFAULT FALSE,
  premium_until TIMESTAMPTZ,
  balance BIGINT NOT NULL DEFAULT 0 CHECK (balance >= 0),
  hold BIGINT NOT NULL DEFAULT 0 CHECK (hold >= 0),
  ad_balance BIGINT NOT NULL DEFAULT 0 CHECK (ad_balance >= 0),
  total_earned BIGINT NOT NULL DEFAULT 0,
  banned BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tasks(
  id SERIAL PRIMARY KEY, owner_id BIGINT NOT NULL, chat_id BIGINT NOT NULL,
  title TEXT, link TEXT, target INT NOT NULL, joined INT NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS completions(
  id SERIAL PRIMARY KEY, task_id INT REFERENCES tasks(id), user_id BIGINT NOT NULL,
  chat_id BIGINT NOT NULL, reward INT NOT NULL, status TEXT NOT NULL DEFAULT 'hold',
  release_at TIMESTAMPTZ, last_checked TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(chat_id, user_id)
);
CREATE TABLE IF NOT EXISTS joins(
  chat_id BIGINT NOT NULL, user_id BIGINT NOT NULL, at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(chat_id, user_id)
);
CREATE TABLE IF NOT EXISTS ledger(
  id BIGSERIAL PRIMARY KEY, user_id BIGINT, kind TEXT, amount BIGINT, ref TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS orders(
  order_id TEXT PRIMARY KEY, user_id BIGINT NOT NULL, kind TEXT NOT NULL,
  coins BIGINT NOT NULL DEFAULT 0, amount_inr INT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS gateway_ref TEXT;
CREATE TABLE IF NOT EXISTS botworks(
  id SERIAL PRIMARY KEY, owner_id BIGINT NOT NULL, title TEXT NOT NULL, link TEXT NOT NULL,
  reward INT NOT NULL, target INT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS bw_subs(
  id SERIAL PRIMARY KEY, bw_id INT NOT NULL REFERENCES botworks(id), worker_id BIGINT NOT NULL,
  photo_id TEXT NOT NULL, photo_uid TEXT NOT NULL UNIQUE, ref_link TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), decided_at TIMESTAMPTZ,
  UNIQUE(bw_id, worker_id)
);
CREATE TABLE IF NOT EXISTS withdrawals(
  id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, coins BIGINT NOT NULL, amount_inr NUMERIC(12,2) NOT NULL,
  fee_coins BIGINT NOT NULL DEFAULT 0,
  upi TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE withdrawals ALTER COLUMN amount_inr TYPE NUMERIC(12,2);
ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS fee_coins BIGINT NOT NULL DEFAULT 0;
ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS code TEXT;
CREATE TABLE IF NOT EXISTS gift_codes(
  code TEXT PRIMARY KEY, coins INT NOT NULL, max_uses INT NOT NULL, used INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS support_msgs(
  id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, sender TEXT NOT NULL, text TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS support_user_idx ON support_msgs(user_id, id);
CREATE TABLE IF NOT EXISTS support_notifs(
  admin_id BIGINT NOT NULL, msg_id BIGINT NOT NULL, user_id BIGINT NOT NULL, PRIMARY KEY(admin_id, msg_id)
);
CREATE TABLE IF NOT EXISTS gift_redeems(
  code TEXT NOT NULL REFERENCES gift_codes(code), user_id BIGINT NOT NULL,
  at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(code, user_id)
);

-- ---- migrations / indexes (har start par safe) ----
ALTER TABLE users ADD COLUMN IF NOT EXISTS fp TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS dev_ver INT NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN IF NOT EXISTS device_changes INT NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS suspect BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS lang TEXT;
UPDATE users SET fp=device_hash WHERE fp IS NULL AND device_hash IS NOT NULL;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS free BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE botworks ADD COLUMN IF NOT EXISTS free BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS gateway_ref TEXT;
CREATE INDEX IF NOT EXISTS comp_user_status ON completions(user_id, status);
CREATE INDEX IF NOT EXISTS comp_hold_release ON completions(release_at) WHERE status='hold';
CREATE INDEX IF NOT EXISTS comp_recheck ON completions(last_checked) WHERE status IN ('hold','ok');
CREATE INDEX IF NOT EXISTS tasks_active ON tasks(created_at) WHERE status='active';
CREATE INDEX IF NOT EXISTS tasks_owner ON tasks(owner_id, id DESC);
CREATE INDEX IF NOT EXISTS ledger_user ON ledger(user_id, id DESC);
CREATE INDEX IF NOT EXISTS orders_user ON orders(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS orders_ref ON orders(gateway_ref);
CREATE INDEX IF NOT EXISTS orders_pending ON orders(created_at) WHERE status='pending';
CREATE INDEX IF NOT EXISTS wd_user ON withdrawals(user_id, id DESC);
CREATE INDEX IF NOT EXISTS wd_status ON withdrawals(status);
CREATE INDEX IF NOT EXISTS bws_bw ON bw_subs(bw_id, status);
CREATE INDEX IF NOT EXISTS bws_worker ON bw_subs(worker_id, id DESC);
CREATE INDEX IF NOT EXISTS bws_status ON bw_subs(status, created_at);
CREATE INDEX IF NOT EXISTS bw_owner ON botworks(owner_id, id DESC);
CREATE TABLE IF NOT EXISTS referrals(
  referred_id BIGINT PRIMARY KEY, referrer_id BIGINT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), done_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ref_referrer ON referrals(referrer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ref_pending ON referrals(status) WHERE status='pending';
ALTER TABLE support_msgs ADD COLUMN IF NOT EXISTS has_photo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE support_msgs ADD COLUMN IF NOT EXISTS has_voice BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE completions ADD COLUMN IF NOT EXISTS rejoin_paid BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS debt BIGINT NOT NULL DEFAULT 0;
ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS last_alert TIMESTAMPTZ;
ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS bk_msgs TEXT;
ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS level SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS expire_hours INT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_level SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS level SMALLINT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS mode TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS method TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS charge_id TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS pay_paise INT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_fam_pending ON orders(pay_paise) WHERE status='pending' AND method='fam';
CREATE TABLE IF NOT EXISTS fam_payments(
  txn_id TEXT PRIMARY KEY, pay_paise INT NOT NULL, sender TEXT, email_ts TIMESTAMPTZ, balance_paise BIGINT,
  status TEXT NOT NULL, order_id TEXT, user_id BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS fam_claims(
  id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, txn_id TEXT NOT NULL, amount_paise INT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fam_claim_pending ON fam_claims(txn_id) WHERE status='pending';
CREATE TABLE IF NOT EXISTS fam_meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS prem_queue(
  id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, level SMALLINT NOT NULL, days INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS prem_queue_user_idx ON prem_queue(user_id, id);
ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE bw_subs ADD COLUMN IF NOT EXISTS report_sent BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS wd_status_idx ON withdrawals(status, id);
ALTER TABLE bw_subs ADD COLUMN IF NOT EXISTS reject_reason TEXT;
ALTER TABLE bw_subs ADD COLUMN IF NOT EXISTS attempt INT NOT NULL DEFAULT 1;
ALTER TABLE bw_subs DROP CONSTRAINT IF EXISTS bw_subs_bw_id_worker_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS bws_bw_worker_attempt ON bw_subs(bw_id, worker_id, attempt);
ALTER TABLE botworks ADD COLUMN IF NOT EXISTS instructions TEXT NOT NULL DEFAULT '';
ALTER TABLE botworks ADD COLUMN IF NOT EXISTS needs_dev BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE bw_subs ADD COLUMN IF NOT EXISTS photo2_id TEXT;
ALTER TABLE bw_subs ADD COLUMN IF NOT EXISTS photo2_uid TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS bws_photo2_uid ON bw_subs(photo2_uid) WHERE photo2_uid IS NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS ip TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS dev_bypass BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS fp_ok BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS notify BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS notified BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE tasks ALTER COLUMN notified SET DEFAULT FALSE;
ALTER TABLE botworks ADD COLUMN IF NOT EXISTS notified BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE botworks ALTER COLUMN notified SET DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS bcast(
  id BIGSERIAL PRIMARY KEY, kind TEXT NOT NULL, text TEXT NOT NULL, last_uid BIGINT NOT NULL DEFAULT 0,
  sent INT NOT NULL DEFAULT 0, done BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
ALTER TABLE support_notifs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE TABLE IF NOT EXISTS support_files(msg_id BIGINT PRIMARY KEY, data BYTEA NOT NULL);
CREATE TABLE IF NOT EXISTS support_threads(
  user_id BIGINT PRIMARY KEY, last_sender TEXT NOT NULL, last_text TEXT, last_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sup_thr_at ON support_threads(last_at DESC);
INSERT INTO support_threads(user_id,last_sender,last_text,last_at)
  SELECT DISTINCT ON (user_id) user_id, sender, left(text,80), created_at FROM support_msgs
  WHERE NOT EXISTS(SELECT 1 FROM support_threads) ORDER BY user_id, id DESC ON CONFLICT DO NOTHING;
CREATE INDEX IF NOT EXISTS users_fp ON users(fp);
"""


class RetryPool:
    """Naye deploy ne table me column joda to purane connections ka cached statement "InvalidCachedStatementError" deta hai.
    Aisa hone par ek baar dobara try (naya statement prepare hota hai). Baaki sab asli pool jaisa."""

    def __init__(self, p):
        self._p = p

    def __getattr__(self, name):
        return getattr(self._p, name)

    def acquire(self, *a, **k):
        return self._p.acquire(*a, **k)

    async def _call(self, name, a, k):
        try:
            return await getattr(self._p, name)(*a, **k)
        except asyncpg.exceptions.InvalidCachedStatementError:
            return await getattr(self._p, name)(*a, **k)

    async def fetch(self, *a, **k):
        return await self._call("fetch", a, k)

    async def fetchrow(self, *a, **k):
        return await self._call("fetchrow", a, k)

    async def fetchval(self, *a, **k):
        return await self._call("fetchval", a, k)

    async def execute(self, *a, **k):
        return await self._call("execute", a, k)


async def init():
    global pool
    pool = RetryPool(await asyncpg.create_pool(config.DATABASE_URL, min_size=config.DB_POOL_MIN, max_size=config.DB_POOL_MAX,
                                               command_timeout=30, max_inactive_connection_lifetime=1800))
    async with pool.acquire() as c:
        await c.execute("SELECT pg_advisory_lock(727001)")  # 2 instance ek saath boot ho to schema DDL takrao nahi
        try:
            await c.execute(SCHEMA)
        finally:
            await c.execute("SELECT pg_advisory_unlock(727001)")


async def led(c, uid, kind, amount, ref=""):
    """Ledger insert + sirf last LEDGER_KEEP entries rakho (purani apne aap delete)."""
    await c.execute(
        """WITH ins AS (INSERT INTO ledger(user_id,kind,amount,ref) VALUES($1,$2,$3,$4) RETURNING id)
           DELETE FROM ledger WHERE user_id=$1 AND id NOT IN
             (SELECT id FROM (SELECT id FROM ledger WHERE user_id=$1 ORDER BY id DESC LIMIT $5::int - 1) k
              UNION SELECT id FROM ins)""",
        uid, kind, amount, str(ref), config.LEDGER_KEEP)


# ---------- users ----------
new_user_hook = None  # extras.feed se set hota hai


async def ensure_user(tu):
    # Har API call par write nahi: sirf naya user ya naam badla ho tabhi UPSERT (1 lakh users par bloat se bachata hai)
    u = await pool.fetchrow("SELECT * FROM users WHERE id=$1", tu.id)
    if u and u["username"] == tu.username and u["first_name"] == tu.first_name:
        return u
    row = await pool.fetchrow(
        """INSERT INTO users(id,username,first_name) VALUES($1,$2,$3)
           ON CONFLICT(id) DO UPDATE SET username=EXCLUDED.username, first_name=EXCLUDED.first_name
           RETURNING *""", tu.id, tu.username, tu.first_name)
    if not u and new_user_hook:
        try:
            new_user_hook(row)
        except Exception:
            pass
    return row


async def get_lang(uid):
    return await pool.fetchval("SELECT lang FROM users WHERE id=$1", uid)


async def set_lang(uid, lang):
    return await pool.fetchval("UPDATE users SET lang=$2 WHERE id=$1 RETURNING id", uid, lang)


async def get_user(uid):
    return await pool.fetchrow("SELECT * FROM users WHERE id=$1", uid)


async def set_upi(uid, upi):
    """False agar UPI kisi aur account ke paas hai."""
    try:
        await pool.execute("UPDATE users SET upi=$1 WHERE id=$2", upi, uid)
        return True
    except asyncpg.UniqueViolationError:
        return False


# ---------- tasks ----------
async def create_task(owner, chat_id, title, link, target, free=False):
    """free=True (sirf admin): ad balance se coin nahi katta, aur cancel par refund bhi nahi milta."""
    cost = target * config.AD_COST
    async with pool.acquire() as c, c.transaction():
        if not free:
            ok = await c.fetchval(
                "UPDATE users SET ad_balance=ad_balance-$1 WHERE id=$2 AND ad_balance>=$1 RETURNING id", cost, owner)
            if not ok:
                return None
        tid = await c.fetchval(
            "INSERT INTO tasks(owner_id,chat_id,title,link,target,free) VALUES($1,$2,$3,$4,$5,$6) RETURNING id",
            owner, chat_id, title, link, target, free)
        if not free:
            await led(c, owner, "task_escrow", -cost, tid)
        return tid


async def cancel_task(tid, owner):
    async with pool.acquire() as c, c.transaction():
        t = await c.fetchrow("SELECT * FROM tasks WHERE id=$1 AND owner_id=$2 FOR UPDATE", tid, owner)
        if not t or t["status"] != "active":
            return None
        refund = 0 if t["free"] else (t["target"] - t["joined"]) * config.AD_COST
        await c.execute("UPDATE tasks SET status='cancelled' WHERE id=$1", tid)
        if refund:
            await c.execute("UPDATE users SET ad_balance=ad_balance+$1 WHERE id=$2", refund, owner)
            await led(c, owner, "task_refund", refund, tid)
        return refund


async def get_task(tid):
    return await pool.fetchrow("SELECT * FROM tasks WHERE id=$1", tid)


async def my_tasks(uid):
    return await pool.fetch("SELECT * FROM tasks WHERE owner_id=$1 ORDER BY id DESC LIMIT 10", uid)


async def open_tasks(uid):
    return await pool.fetch(
        """SELECT t.* FROM tasks t
           WHERE t.status='active' AND t.joined<t.target AND t.owner_id<>$1
             AND NOT EXISTS(SELECT 1 FROM completions c WHERE c.chat_id=t.chat_id AND c.user_id=$1)
           ORDER BY EXISTS(SELECT 1 FROM users o WHERE o.id=t.owner_id AND o.premium_level >= $2 AND o.premium_until > now()) DESC,
                    md5(t.id::text || $1::bigint::text) LIMIT 8""", uid, config.TOP_LEVEL)  # har user ko alag mix: dead task sabke aage na atke


async def claim(task_id, uid):
    async with pool.acquire() as c, c.transaction():
        t = await c.fetchrow("SELECT * FROM tasks WHERE id=$1 FOR UPDATE", task_id)
        if not t or t["status"] != "active" or t["joined"] >= t["target"]:
            return "closed"
        if t["owner_id"] == uid:
            return "own"
        cid = await c.fetchval(
            """INSERT INTO completions(task_id,user_id,chat_id,reward,release_at)
               VALUES($1,$2,$3,$4, now() + make_interval(hours => $5))
               ON CONFLICT(chat_id,user_id) DO NOTHING RETURNING id""",
            task_id, uid, t["chat_id"], config.JOIN_REWARD, config.HOLD_HOURS)
        if cid is None:
            return "dup"
        new_joined = t["joined"] + 1
        await c.execute("UPDATE tasks SET joined=$1, status=$2 WHERE id=$3",
                        new_joined, "done" if new_joined >= t["target"] else "active", task_id)
        await c.execute("UPDATE users SET hold=hold+$1 WHERE id=$2", config.JOIN_REWARD, uid)
        await led(c, uid, "hold", config.JOIN_REWARD, cid)
        if not t["free"]:
            await led(c, 0, "fee", config.AD_COST - config.JOIN_REWARD, cid)
        return "ok"


# ---------- joins / membership ----------
async def record_join(chat_id, uid):
    await pool.execute(
        """INSERT INTO joins(chat_id,user_id) SELECT $1::bigint,$2::bigint
           WHERE EXISTS(SELECT 1 FROM tasks WHERE chat_id=$1::bigint AND status='active')
           ON CONFLICT(chat_id,user_id) DO UPDATE SET at=now()""", chat_id, uid)


async def joined_after(chat_id, uid, since):
    return await pool.fetchval(
        "SELECT EXISTS(SELECT 1 FROM joins WHERE chat_id=$1 AND user_id=$2 AND at>=$3)", chat_id, uid, since)


async def is_blocked(uid):
    return await pool.fetchval("SELECT EXISTS(SELECT 1 FROM completions WHERE user_id=$1 AND status='left')", uid)


async def left_chats(uid):
    return await pool.fetch(
        """SELECT DISTINCT ON (c.chat_id) c.chat_id, t.title, t.link FROM completions c
           JOIN tasks t ON t.id=c.task_id WHERE c.user_id=$1 AND c.status='left'""", uid)


async def unblock(chat_id, uid):
    """Left channel dobara join kiya. Pehli baar sirf REJOIN_PERCENT% coins (24h hold me), aage 0 coins.
    Return coins (int, 0 bhi ho sakta) ya None agar koi 'left' record nahi tha."""
    async with pool.acquire() as c, c.transaction():
        r = await c.fetchrow(
            "SELECT * FROM completions WHERE chat_id=$1 AND user_id=$2 AND status='left' FOR UPDATE", chat_id, uid)
        if not r:
            return None
        if r["rejoin_paid"]:
            await c.execute("UPDATE completions SET status='ok', reward=0, last_checked=now() WHERE id=$1", r["id"])
            return 0
        coins = r["reward"] * config.REJOIN_PERCENT // 100
        await c.execute(
            """UPDATE completions SET status='hold', reward=$2, rejoin_paid=TRUE, last_checked=now(),
               release_at=now() + make_interval(hours => $3) WHERE id=$1""", r["id"], coins, config.HOLD_HOURS)
        if coins:
            await c.execute("UPDATE users SET hold=hold+$1 WHERE id=$2", coins, uid)
            await led(c, uid, "hold", coins, r["id"])
        return coins


async def revoke(comp_id):
    async with pool.acquire() as c, c.transaction():
        r = await c.fetchrow("SELECT * FROM completions WHERE id=$1 FOR UPDATE", comp_id)
        if not r or r["status"] not in ("hold", "ok"):
            return None
        cut = r["reward"]
        if r["status"] == "hold":
            await c.execute("UPDATE users SET hold=GREATEST(hold-$1,0) WHERE id=$2", cut, r["user_id"])
        else:
            # coins pehle hi withdraw ho chuke ho sakte hain: jitna balance me hai utna kaato, baaki "debt" (agli kamai se kategi)
            bal = await c.fetchval("SELECT balance FROM users WHERE id=$1 FOR UPDATE", r["user_id"])
            cut = min(int(bal or 0), r["reward"])
            await c.execute("UPDATE users SET balance=balance-$1, debt=debt+$2 WHERE id=$3",
                            cut, r["reward"] - cut, r["user_id"])
        await c.execute("UPDATE completions SET status='left' WHERE id=$1", comp_id)
        if cut:
            await led(c, r["user_id"], "revoke", -cut, comp_id)
        return r


async def revoke_by_chat(chat_id, uid):
    ids = await pool.fetch(
        "SELECT id FROM completions WHERE chat_id=$1 AND user_id=$2 AND status IN ('hold','ok')", chat_id, uid)
    out = []
    for row in ids:
        r = await revoke(row["id"])
        if r:
            out.append(r)
    return out


async def release(comp_id):
    async with pool.acquire() as c, c.transaction():
        r = await c.fetchrow("SELECT * FROM completions WHERE id=$1 FOR UPDATE", comp_id)
        if not r or r["status"] != "hold":
            return None
        debt = await c.fetchval("SELECT debt FROM users WHERE id=$1 FOR UPDATE", r["user_id"])
        pay = min(int(debt or 0), r["reward"])      # purana leave-debt pehle kat-ta hai
        credit = r["reward"] - pay
        await c.execute(
            """UPDATE users SET hold=GREATEST(hold-$1,0), balance=balance+$2, total_earned=total_earned+$2,
               debt=debt-$3 WHERE id=$4""", r["reward"], credit, pay, r["user_id"])
        await c.execute("UPDATE completions SET status='ok' WHERE id=$1", comp_id)
        if r["reward"]:
            await led(c, r["user_id"], "release", r["reward"], comp_id)
        if pay:
            await led(c, r["user_id"], "debt_pay", -pay, comp_id)
        return r


# ---------- orders ----------
async def new_order(order_id, uid, kind, coins, amount_inr, gateway_ref=None, level=None, mode=None, method=None):
    await pool.execute(
        "INSERT INTO orders(order_id,user_id,kind,coins,amount_inr,gateway_ref,level,mode,method) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        order_id, uid, kind, coins, amount_inr, gateway_ref, level, mode, method)


async def order_row(order_id):
    return await pool.fetchrow("SELECT * FROM orders WHERE order_id=$1", order_id)


async def order_lookup(ref, order_id):
    return await pool.fetchrow(
        "SELECT * FROM orders WHERE gateway_ref=$1::text OR order_id=$2::text ORDER BY created_at DESC LIMIT 1",
        ref, order_id)


async def order_supersede_stars(uid):
    """Naya Stars invoice banne par purane unpaid Stars invoices band (precheckout unhe reject karega)."""
    await pool.execute("UPDATE orders SET status='failed' WHERE user_id=$1 AND method='stars' AND status='pending'", uid)


async def order_set_status(order_id, status):
    await pool.execute("UPDATE orders SET status=$2 WHERE order_id=$1 AND status='pending'", order_id, status)


async def pending_gateway_orders():
    return await pool.fetch(
        """SELECT * FROM orders WHERE status='pending' AND gateway_ref IS NOT NULL
           AND created_at > now() - interval '24 hours' ORDER BY created_at DESC LIMIT 100""")


async def orders_expire_old():
    """24 ghante se purane unpaid orders ab verify nahi hote: DB me bhi Failed kar do."""
    await pool.execute("UPDATE orders SET status='failed' WHERE status='pending' AND created_at < now() - interval '24 hours'")


async def complete_order(order_id, paid_amount):
    async with pool.acquire() as c, c.transaction():
        return await _complete_c(c, order_id, paid_amount)


async def _complete_c(c, order_id, paid_amount):
    """Order credit/premium activate, diye hue connection (transaction) me."""
    if True:
        o = await c.fetchrow("SELECT * FROM orders WHERE order_id=$1 FOR UPDATE", order_id)
        if not o or o["status"] != "pending":
            return None
        if paid_amount is not None and float(paid_amount) + 0.001 < float(o["amount_inr"]):
            await c.execute("UPDATE orders SET status='mismatch' WHERE order_id=$1", order_id)
            return None
        await c.execute("UPDATE orders SET status='paid' WHERE order_id=$1", order_id)
        if o["kind"] == "deposit":
            await c.execute("UPDATE users SET ad_balance=ad_balance+$1 WHERE id=$2", o["coins"], o["user_id"])
            await led(c, o["user_id"], "deposit", o["coins"], order_id)
            return dict(o, outcome="deposit")
        # premium: level kharida. Active nahi / same level = turant (same level me din jud jaate hain);
        # active aur alag level: mode 'now' = turant badlo, 'later' = purana khatam hone ke baad (queue)
        lvl = int(o["level"] or 1)
        days = config.PLANS[lvl]["days"]
        u = await c.fetchrow("SELECT premium_level, (premium_until IS NOT NULL AND premium_until > now()) AS active "
                             "FROM users WHERE id=$1 FOR UPDATE", o["user_id"])
        active = bool(u and u["active"])
        cur = max(1, int(u["premium_level"] or 0)) if active else 0
        mode = o["mode"] if o["mode"] in ("now", "later") else "now"
        if active and lvl != cur and (mode == "later" or lvl < cur):
            await c.execute("INSERT INTO prem_queue(user_id,level,days) VALUES($1,$2,$3)", o["user_id"], lvl, days)
            outcome = "queued"
        elif active and lvl == cur:
            await c.execute("UPDATE users SET premium_until=premium_until+make_interval(days => $1) WHERE id=$2", days, o["user_id"])
            outcome = "extended"
        else:
            await c.execute("UPDATE users SET premium_level=$3, premium_until=now()+make_interval(days => $1) WHERE id=$2",
                            days, o["user_id"], lvl)
            outcome = "activated"
        await led(c, o["user_id"], "premium", 0, order_id)
        return dict(o, outcome=outcome, level=lvl)


# ---------- Fam mail deposits ----------
async def fam_states():
    """{folder: (uidvalidity, last_uid)} jo pehle padh chuke hain."""
    out = {}
    for r in await pool.fetch("SELECT k, v FROM fam_meta WHERE k LIKE 'uid:%'"):
        val, _, last = r["v"].partition(":")
        out[r["k"][4:]] = (val, int(last or 0))
    return out


async def fam_set_state(folder, validity, uid):
    await pool.execute("INSERT INTO fam_meta(k,v) VALUES($1,$2) ON CONFLICT(k) DO UPDATE SET v=EXCLUDED.v",
                       "uid:" + folder, f"{validity}:{uid}")


async def fam_expire_old():
    """Fam order TTL + grace + 1 min ke baad 'failed' (amount ka unique slot bhi khali)."""
    await pool.execute(
        "UPDATE orders SET status='failed' WHERE method='fam' AND status='pending' "
        "AND created_at < now() - make_interval(secs => $1)", config.FAM_TTL + config.FAM_GRACE + 60)


async def fam_order_counts(uid):
    r = await pool.fetchrow(
        """SELECT count(*) FILTER (WHERE status='pending') AS pending,
                  count(*) AS hour FROM orders
           WHERE user_id=$1 AND method='fam' AND created_at > now() - interval '1 hour'""", uid)
    return r["pending"], r["hour"]


async def fam_new_order(order_id, uid, kind, coins, base_paise, level=None, mode=None):
    """Unique amount (base + 1..99 paise) ka pending order. Return pay_paise ya None (busy)."""
    await fam_expire_old()
    for _ in range(4):
        used = {r["pay_paise"] for r in await pool.fetch(
            "SELECT pay_paise FROM orders WHERE method='fam' AND status='pending' AND pay_paise BETWEEN $1 AND $2",
            base_paise + 1, base_paise + 99)}
        free = [x for x in range(base_paise + 1, base_paise + 100) if x not in used]
        if not free:
            return None
        pay = random.choice(free)
        try:
            await pool.execute(
                "INSERT INTO orders(order_id,user_id,kind,coins,amount_inr,level,mode,method,pay_paise) "
                "VALUES($1,$2,$3,$4,$5,$6,$7,'fam',$8)",
                order_id, uid, kind, coins, base_paise // 100, level, mode, pay)
            return pay
        except asyncpg.UniqueViolationError:
            continue  # race: kisi aur ne wahi amount le liya
    return None


async def fam_process(p, ts):
    """Ek 'received' mail: order match -> credit; ya claim match; ya unmatched. Sab ek transaction me.
    Return None (duplicate mail) ya dict(done, claim_user, claim_coins, unmatched, gap)."""
    out = {"done": None, "claim_user": None, "claim_coins": 0, "unmatched": False, "gap": None}
    async with pool.acquire() as c, c.transaction():
        got = await c.fetchval(
            "INSERT INTO fam_payments(txn_id,pay_paise,sender,email_ts,balance_paise,status) "
            "VALUES($1,$2,$3,to_timestamp($4),$5,'unmatched') ON CONFLICT DO NOTHING RETURNING txn_id",
            p["txn"], p["paise"], p["sender"], float(ts), p["bal"])
        if not got:
            return None
        order = await c.fetchrow(
            """SELECT order_id FROM orders WHERE status='pending' AND method='fam' AND pay_paise=$1
               AND created_at - interval '30 seconds' <= to_timestamp($2)
               AND to_timestamp($2) <= created_at + make_interval(secs => $3) FOR UPDATE""",
            p["paise"], float(ts), config.FAM_TTL + config.FAM_GRACE)
        if order:
            done = await _complete_c(c, order["order_id"], p["paise"] / 100)
            if done:
                await c.execute("UPDATE fam_payments SET status='credited', order_id=$2, user_id=$3 WHERE txn_id=$1",
                                p["txn"], order["order_id"], done["user_id"])
                out["done"] = done
        if not out["done"]:
            cl = await c.fetchrow(
                "SELECT * FROM fam_claims WHERE status='pending' AND txn_id=$1 AND amount_paise=$2 FOR UPDATE",
                p["txn"], p["paise"])
            if cl:
                await c.execute("UPDATE fam_claims SET status='approved' WHERE id=$1", cl["id"])
                await c.execute("UPDATE fam_payments SET status='claimed', user_id=$2 WHERE txn_id=$1", p["txn"], cl["user_id"])
                await c.execute("UPDATE users SET ad_balance=ad_balance+$1 WHERE id=$2", p["paise"], cl["user_id"])
                await led(c, cl["user_id"], "deposit", p["paise"], p["txn"])
                out["claim_user"], out["claim_coins"] = cl["user_id"], p["paise"]
            else:
                out["unmatched"] = True
        if p["bal"] is not None:  # balance gap: mail miss hui ho sakti hai (ya Fam se paise kharch hue)
            last = await c.fetchval("SELECT v FROM fam_meta WHERE k='last_balance'")
            if last is not None and int(last) + p["paise"] != p["bal"]:
                out["gap"] = (int(last) + p["paise"], p["bal"])
            await c.execute("INSERT INTO fam_meta(k,v) VALUES('last_balance',$1) ON CONFLICT(k) DO UPDATE SET v=EXCLUDED.v", str(p["bal"]))
    return out


async def fam_claim(uid, txn, paise):
    """User: 'paid but credit nahi hua'. Return (status, extra): credited/pending/used/dup/limit."""
    async with pool.acquire() as c, c.transaction():
        n = await c.fetchval("SELECT count(*) FROM fam_claims WHERE user_id=$1 AND created_at > now() - interval '1 hour'", uid)
        if n >= config.MAX_CLAIMS_PER_HOUR:
            return "limit", None
        pay = await c.fetchrow("SELECT * FROM fam_payments WHERE txn_id=$1 FOR UPDATE", txn)
        if pay:
            if pay["status"] == "unmatched" and pay["pay_paise"] == paise:
                await c.execute("UPDATE fam_payments SET status='claimed', user_id=$2 WHERE txn_id=$1", txn, uid)
                await c.execute("UPDATE users SET ad_balance=ad_balance+$1 WHERE id=$2", paise, uid)
                await led(c, uid, "deposit", paise, txn)
                return "credited", paise
            return "used", None
        if await c.fetchval("SELECT 1 FROM fam_claims WHERE txn_id=$1 AND status='pending'", txn):
            return "dup", None
        cid = await c.fetchval("INSERT INTO fam_claims(user_id,txn_id,amount_paise) VALUES($1,$2,$3) RETURNING id", uid, txn, paise)
        return "pending", cid


async def fam_claim_get(cid):
    return await pool.fetchrow("SELECT * FROM fam_claims WHERE id=$1", cid)


async def fam_claim_approve(cid):
    """Admin manually credit. Return claim row ya None."""
    async with pool.acquire() as c, c.transaction():
        cl = await c.fetchrow("SELECT * FROM fam_claims WHERE id=$1 AND status='pending' FOR UPDATE", cid)
        if not cl:
            return None
        if await c.fetchval("SELECT 1 FROM fam_payments WHERE txn_id=$1", cl["txn_id"]):
            return None  # mail aa chuki: wo process ho chuki / manual assign se hoga
        await c.execute(
            "INSERT INTO fam_payments(txn_id,pay_paise,sender,status,user_id) VALUES($1,$2,'manual','claimed',$3)",
            cl["txn_id"], cl["amount_paise"], cl["user_id"])
        await c.execute("UPDATE users SET ad_balance=ad_balance+$1 WHERE id=$2", cl["amount_paise"], cl["user_id"])
        await led(c, cl["user_id"], "deposit", cl["amount_paise"], cl["txn_id"])
        await c.execute("UPDATE fam_claims SET status='approved' WHERE id=$1", cid)
        return cl


async def fam_claim_reject(cid):
    return await pool.fetchrow("UPDATE fam_claims SET status='rejected' WHERE id=$1 AND status='pending' RETURNING *", cid)


async def fam_assign(txn, uid):
    """Admin: unmatched payment kisi user ko do. Return payment row ya None."""
    async with pool.acquire() as c, c.transaction():
        pay = await c.fetchrow("SELECT * FROM fam_payments WHERE txn_id=$1 AND status='unmatched' FOR UPDATE", txn)
        if not pay or not await c.fetchval("SELECT 1 FROM users WHERE id=$1", uid):
            return None
        await c.execute("UPDATE fam_payments SET status='claimed', user_id=$2 WHERE txn_id=$1", txn, uid)
        await c.execute("UPDATE users SET ad_balance=ad_balance+$1 WHERE id=$2", pay["pay_paise"], uid)
        await led(c, uid, "deposit", pay["pay_paise"], txn)
        return pay


async def fam_review():
    claims = await pool.fetch("SELECT * FROM fam_claims WHERE status='pending' ORDER BY id LIMIT 50")
    unmatched = await pool.fetch("SELECT * FROM fam_payments WHERE status='unmatched' ORDER BY created_at DESC LIMIT 50")
    return claims, unmatched


async def prem_activate_queued():
    """Purana premium khatam: queue me rakha agla level chalu. Return [(user_id, level, days)]."""
    rows = await pool.fetch(
        """SELECT q.id, q.user_id, q.level, q.days FROM prem_queue q JOIN users u ON u.id=q.user_id
           WHERE u.premium_until IS NULL OR u.premium_until <= now() ORDER BY q.id LIMIT 200""")
    out, seen = [], set()
    for r in rows:
        if r["user_id"] in seen:
            continue
        seen.add(r["user_id"])
        async with pool.acquire() as c, c.transaction():
            gone = await c.fetchval("DELETE FROM prem_queue WHERE id=$1 RETURNING id", r["id"])
            if not gone:
                continue
            await c.execute("UPDATE users SET premium_level=$2, premium_until=now()+make_interval(days => $3) WHERE id=$1",
                            r["user_id"], r["level"], r["days"])
        out.append((r["user_id"], r["level"], r["days"]))
    return out


async def prem_queued(uid):
    return await pool.fetch("SELECT level, days FROM prem_queue WHERE user_id=$1 ORDER BY id", uid)


IST_DAY = "date_trunc('day', now() AT TIME ZONE 'Asia/Kolkata') AT TIME ZONE 'Asia/Kolkata'"


async def created_today(uid):
    """Aaj (IST) bane channel/group + bot work tasks (premium roz limit ke liye)."""
    return await pool.fetchval(
        f"""SELECT (SELECT count(*) FROM tasks WHERE owner_id=$1 AND created_at >= {IST_DAY})
                 + (SELECT count(*) FROM botworks WHERE owner_id=$1 AND created_at >= {IST_DAY})""", uid)


async def wd_today(uid):
    """Aaj (IST) ke withdraw requests (reject/expire/fail wale nahi gine jaate)."""
    return await pool.fetchval(
        f"SELECT count(*) FROM withdrawals WHERE user_id=$1 AND created_at >= {IST_DAY} "
        "AND status NOT IN ('rejected','expired','failed')", uid)


# ---------- withdrawals ----------
async def tasks_done(uid):
    """Complete hue tasks: channel joins (hold/ok, left nahi) + approved bot works."""
    return await pool.fetchval(
        """SELECT (SELECT count(*) FROM completions WHERE user_id=$1 AND status IN ('hold','ok'))
                + (SELECT count(*) FROM bw_subs WHERE worker_id=$1 AND status='approved')""", uid)


def wd_fee(coins, pct=None):
    """Tax withdraw ki rakam ke UPAR lagta hai: 1000 coins ka paisa chahiye to 100 tax, kul 1100 katenge. pct premium level se."""
    return coins * (config.WITHDRAW_TAX_PERCENT if pct is None else pct) // 100


GPLAY = "Google Play Code"


async def request_withdraw(uid, coins, pct=None, level=0, hours=None, max_day=None, gplay=False):
    """coins = jitne ka paisa user ko milega. Tax upar se: balance se coins + tax kat-ta hai.
    Return (wid, upi, fee_coins, net_inr). withdrawals.coins = kul kata hua (coins+fee) taaki refund poora ho."""
    fee = wd_fee(coins, pct)
    total = coins + fee
    net_inr = Decimal(coins) / Decimal(config.COIN_PER_INR)
    async with pool.acquire() as c, c.transaction():
        if max_day is not None:  # user row lock: do parallel request me bhi roz ki limit pakki
            await c.fetchval("SELECT id FROM users WHERE id=$1 FOR UPDATE", uid)
            n = await c.fetchval(
                f"SELECT count(*) FROM withdrawals WHERE user_id=$1 AND created_at >= {IST_DAY} "
                "AND status NOT IN ('rejected','expired','failed')", uid)
            if n >= max_day:
                return "limit"
        u = await c.fetchrow(
            """UPDATE users SET balance=balance-$1 WHERE id=$2 AND balance>=$1
               AND device_ok AND NOT banned AND debt=0 AND upi IS NOT NULL RETURNING upi""", total, uid)
        if not u:
            return None
        wid = await c.fetchval(
            "INSERT INTO withdrawals(user_id,coins,amount_inr,fee_coins,upi,level,expire_hours) VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING id",
            uid, total, net_inr, fee, GPLAY if gplay else u["upi"], level, hours)
        await led(c, uid, "withdraw", -total, wid)
        if fee:
            await led(c, 0, "tax", fee, wid)
        return wid, (GPLAY if gplay else u["upi"]), fee, net_inr


async def wd_get(wid):
    return await pool.fetchrow("SELECT * FROM withdrawals WHERE id=$1", wid)


async def wd_pay_code(wid, code):
    """Google Play withdraw: pending -> paid + code save (ek hi baar)."""
    return await pool.fetchrow(
        "UPDATE withdrawals SET status='paid', code=$2, updated_at=now() WHERE id=$1 AND status='pending' AND upi=$3 RETURNING *",
        wid, code, GPLAY)


async def wd_move(wid, frm, to):
    return await pool.fetchrow(
        "UPDATE withdrawals SET status=$3, updated_at=now() WHERE id=$1 AND status=$2 RETURNING *", wid, frm, to)


async def wd_move_refund(wid, frm, to):
    """Status change + coins refund EK transaction me (beech me crash hone par coins zaya nahi hote)."""
    async with pool.acquire() as c, c.transaction():
        w = await c.fetchrow(
            "UPDATE withdrawals SET status=$3, updated_at=now() WHERE id=$1 AND status=$2 RETURNING *", wid, frm, to)
        if not w:
            return None
        await c.execute("UPDATE users SET balance=balance+$1 WHERE id=$2", w["coins"], w["user_id"])
        await led(c, w["user_id"], "withdraw_refund", w["coins"], w["id"])
        return w


async def wd_expire_pending(hours):
    """Admin ne 'hours' ghante me approve/reject nahi kiya: withdraw 'expired' + coins wapas. Return [withdraw rows]."""
    ids = await pool.fetch(
        "SELECT id FROM withdrawals WHERE status='pending' "
        "AND created_at < now() - make_interval(hours => COALESCE(expire_hours, $1)) ORDER BY id LIMIT 50", hours)
    out = []
    for r in ids:
        w = await wd_move_refund(r["id"], "pending", "expired")
        if w:
            out.append(w)
    return out


async def wd_set_msgs(wid, txt):
    await pool.execute("UPDATE withdrawals SET bk_msgs=$2 WHERE id=$1", wid, txt)


async def wd_pop_msgs(wid):
    """Admin alert ke message ids nikalo aur column khali karo (sirf ek caller ko milta hai). Return json text ya None."""
    raw = await pool.fetchval("SELECT bk_msgs FROM withdrawals WHERE id=$1", wid)
    if not raw:
        return None
    got = await pool.fetchval("UPDATE withdrawals SET bk_msgs=NULL WHERE id=$1 AND bk_msgs=$2 RETURNING id", wid, raw)
    return raw if got else None


async def wd_touch_alert(wid):
    await pool.execute("UPDATE withdrawals SET last_alert=now() WHERE id=$1", wid)


async def wd_stuck(limit=20):
    """Jinka admin alert shayad gaya hi nahi (restart/crash) ya jo atak gaye: pending >5min, sending >10min,
    aur pichla alert 3 ghante se purana (reminder bhi)."""
    return await pool.fetch(
        """SELECT * FROM withdrawals
           WHERE ((status='pending' AND created_at < now() - interval '5 minutes')
               OR (status='sending' AND updated_at < now() - interval '10 minutes'))
             AND (last_alert IS NULL OR last_alert < now() - interval '3 hours')
           ORDER BY level DESC, id LIMIT $1""", limit)


async def wd_pending_list(limit=25):
    """Pending withdraws: bada level pehle, phir purana."""
    return await pool.fetch(
        """SELECT * FROM withdrawals WHERE status='pending' ORDER BY level DESC, id LIMIT $1""", limit)


async def admin_add(uid, coins, ad=False):
    """Admin apne account me coins jodta hai. Return naya balance (ya None)."""
    col = "ad_balance" if ad else "balance"
    async with pool.acquire() as c, c.transaction():
        v = await c.fetchval(f"UPDATE users SET {col}={col}+$1 WHERE id=$2 RETURNING {col}", coins, uid)
        if v is None:
            return None
        await led(c, uid, "admin_add", coins, "ad" if ad else "bal")
        return v


async def wd_get(wid):
    return await pool.fetchrow("SELECT * FROM withdrawals WHERE id=$1", wid)


async def wd_set_ref(wid, ref):
    return await pool.fetchrow(
        "UPDATE withdrawals SET status='processing', gateway_ref=$2, updated_at=now() WHERE id=$1 AND status='sending' RETURNING *",
        wid, ref)


async def wd_lookup(ref, reference):
    return await pool.fetchrow(
        """SELECT * FROM withdrawals WHERE gateway_ref=$1::text
           OR ($2::text IS NOT NULL AND ($2::text = 'WD' || id::text OR $2::text LIKE 'WD' || id::text || '-%'))
           LIMIT 1""", ref, reference)


async def wd_processing(limit=50):
    return await pool.fetch(
        "SELECT * FROM withdrawals WHERE status='processing' AND gateway_ref IS NOT NULL ORDER BY id LIMIT $1", limit)


async def wd_recent_count(uid, hours=24):
    return await pool.fetchval(
        """SELECT count(*) FROM withdrawals WHERE user_id=$1 AND status NOT IN ('rejected','failed')
           AND created_at > now() - make_interval(hours => $2)""",
        uid, hours)


async def wd_refund(w):
    async with pool.acquire() as c, c.transaction():
        await c.execute("UPDATE users SET balance=balance+$1 WHERE id=$2", w["coins"], w["user_id"])
        await led(c, w["user_id"], "withdraw_refund", w["coins"], w["id"])


# ---------- bot work ----------
# Escrow: poster ke ad_balance se reward*target pehle hi kat jata hai.
# Slot "used" = us task ki har submission jo 'closed' nahi hai.
async def bw_create(owner, title, link, reward, n, free=False, instructions="", needs_dev=False):
    cost = reward * n
    async with pool.acquire() as c, c.transaction():
        if not free:
            ok = await c.fetchval(
                "UPDATE users SET ad_balance=ad_balance-$1 WHERE id=$2 AND ad_balance>=$1 RETURNING id", cost, owner)
            if not ok:
                return None
        bid = await c.fetchval(
            "INSERT INTO botworks(owner_id,title,link,reward,target,free,instructions,needs_dev) VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id",
            owner, title, link, reward, n, free, instructions, bool(needs_dev))
        if not free:
            await led(c, owner, "bw_escrow", -cost, bid)
        return bid


async def bw_get(bid):
    return await pool.fetchrow("SELECT * FROM botworks WHERE id=$1", bid)


async def _bw_used(c, bid):
    return await c.fetchval("SELECT count(*) FROM bw_subs WHERE bw_id=$1 AND status NOT IN ('closed','retried')", bid)


async def bw_cancel(bid, owner):
    async with pool.acquire() as c, c.transaction():
        b = await c.fetchrow("SELECT * FROM botworks WHERE id=$1 AND owner_id=$2 FOR UPDATE", bid, owner)
        if not b or b["status"] != "active":
            return None
        used = await _bw_used(c, bid)
        refund = 0 if b["free"] else (b["target"] - used) * b["reward"]
        await c.execute("UPDATE botworks SET status='cancelled', target=$2 WHERE id=$1", bid, used)
        if refund > 0:
            await c.execute("UPDATE users SET ad_balance=ad_balance+$1 WHERE id=$2", refund, owner)
            await led(c, owner, "bw_refund", refund, bid)
        return refund


async def bw_my(uid):
    return await pool.fetch(
        """SELECT b.*,
             (SELECT count(*) FROM bw_subs s WHERE s.bw_id=b.id AND s.status NOT IN ('closed','retried')) AS used,
             (SELECT count(*) FROM bw_subs s WHERE s.bw_id=b.id AND s.status='approved') AS done,
             (SELECT count(*) FROM bw_subs s WHERE s.bw_id=b.id AND s.status='pending') AS pending
           FROM botworks b WHERE b.owner_id=$1 ORDER BY b.id DESC LIMIT 10""", uid)


async def bw_open(uid):
    """Worker ko dikhne wale tasks. Jis task me pehli submission reject hui aur try baaki hai wo bhi dikhta hai (retry)."""
    return await pool.fetch(
        """SELECT b.*,
             (SELECT count(*) FROM bw_subs s WHERE s.bw_id=b.id AND s.worker_id=$1) AS my_attempts,
             (SELECT s.reject_reason FROM bw_subs s WHERE s.bw_id=b.id AND s.worker_id=$1
                ORDER BY s.attempt DESC LIMIT 1) AS my_reason
           FROM botworks b
           WHERE b.status='active' AND b.owner_id<>$1
             AND NOT EXISTS(SELECT 1 FROM bw_subs s WHERE s.bw_id=b.id AND s.worker_id=$1
                            AND s.status NOT IN ('rejected','retried'))
             AND (SELECT count(*) FROM bw_subs s WHERE s.bw_id=b.id AND s.worker_id=$1) < $2
             AND (b.target > (SELECT count(*) FROM bw_subs s WHERE s.bw_id=b.id AND s.status NOT IN ('closed','retried'))
                  OR EXISTS(SELECT 1 FROM bw_subs s WHERE s.bw_id=b.id AND s.worker_id=$1 AND s.status='rejected'))
           ORDER BY (SELECT count(*) FROM bw_subs s WHERE s.bw_id=b.id AND s.worker_id=$1) DESC,
                    EXISTS(SELECT 1 FROM users o WHERE o.id=b.owner_id AND o.premium_level >= $3 AND o.premium_until > now()) DESC,
                    b.reward DESC, b.id LIMIT 8""",
        uid, config.BW_MAX_ATTEMPTS, config.TOP_LEVEL)


async def bw_submit(bid, worker, photo_id, photo_uid, ref_link, photo2_uid=None):
    """Return (result, sid, botwork_row). result: ok / closed / own / full / dup / locked.
    Reject ke baad ek retry allowed (BW_MAX_ATTEMPTS tak): purani rejected row 'retried' ho jati hai aur
    uska slot nayi submission ko transfer ho jata hai. Uske baad bhi reject ho to 'locked'."""
    try:
        async with pool.acquire() as c, c.transaction():
            b = await c.fetchrow("SELECT * FROM botworks WHERE id=$1 FOR UPDATE", bid)
            if not b or b["status"] != "active":
                return "closed", None, None
            if b["owner_id"] == worker:
                return "own", None, None
            prev = await c.fetch("SELECT id, status, attempt FROM bw_subs WHERE bw_id=$1 AND worker_id=$2 ORDER BY attempt", bid, worker)
            attempt = 1
            if prev:
                if any(r["status"] not in ("rejected", "retried") for r in prev):
                    return "dup", None, None
                if len(prev) >= config.BW_MAX_ATTEMPTS:
                    return "locked", None, None
                attempt = len(prev) + 1
                await c.execute("UPDATE bw_subs SET status='retried' WHERE id=$1 AND status='rejected'", prev[-1]["id"])
            elif await _bw_used(c, bid) >= b["target"]:
                return "full", None, None
            sid = await c.fetchval(
                """INSERT INTO bw_subs(bw_id,worker_id,photo_id,photo_uid,ref_link,photo2_uid,attempt)
                   VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
                bid, worker, photo_id, photo_uid, ref_link, photo2_uid, attempt)
            return "ok", sid, b
    except asyncpg.UniqueViolationError:
        return "dup", None, None


async def bw_sub(sid):
    return await pool.fetchrow(
        """SELECT s.*, b.title, b.owner_id, b.reward, b.link FROM bw_subs s
           JOIN botworks b ON b.id=s.bw_id WHERE s.id=$1""", sid)


async def bw_mine(uid):
    return await pool.fetch(
        """SELECT s.id, s.status, s.attempt, s.reject_reason, b.title, b.reward FROM bw_subs s JOIN botworks b ON b.id=s.bw_id
           WHERE s.worker_id=$1 AND s.status<>'retried' ORDER BY s.id DESC LIMIT 10""", uid)


async def _bw_lock(c, sid):
    return await c.fetchrow(
        """SELECT s.*, b.owner_id, b.reward, b.title, b.free FROM bw_subs s JOIN botworks b ON b.id=s.bw_id
           WHERE s.id=$1 FOR UPDATE OF s""", sid)


async def _bw_pay(c, s):
    await c.execute("UPDATE users SET balance=balance+$1, total_earned=total_earned+$1 WHERE id=$2",
                    s["reward"], s["worker_id"])
    await c.execute("UPDATE bw_subs SET status='approved', decided_at=now() WHERE id=$1", s["id"])
    await led(c, s["worker_id"], "bw_reward", s["reward"], s["id"])


async def _bw_close(c, s):
    await c.execute("UPDATE bw_subs SET status='closed', decided_at=now() WHERE id=$1", s["id"])
    await c.execute("UPDATE botworks SET target=target-1 WHERE id=$1", s["bw_id"])
    if not s["free"]:
        await c.execute("UPDATE users SET ad_balance=ad_balance+$1 WHERE id=$2", s["reward"], s["owner_id"])
        await led(c, s["owner_id"], "bw_refund", s["reward"], s["id"])


async def bw_review(sid, owner, approve, reason=None):
    """Poster ka Done / Reject (reject par reason zaroori, worker ko dikhta hai). Sirf pending submission par chalega."""
    async with pool.acquire() as c, c.transaction():
        s = await _bw_lock(c, sid)
        if not s or s["owner_id"] != owner or s["status"] != "pending":
            return None
        if approve:
            await _bw_pay(c, s)
        else:
            await c.execute("UPDATE bw_subs SET status='rejected', decided_at=now(), reject_reason=$2 WHERE id=$1",
                            sid, (reason or "")[:200] or None)
        return s


async def bw_report(sid, worker, reason):
    return await pool.fetchrow(
        """UPDATE bw_subs SET status='reported', reason=$3
           WHERE id=$1 AND worker_id=$2 AND status='rejected' RETURNING id""", sid, worker, reason)


async def bw_admin(sid, pay):
    """Admin decision on reported submission: pay worker ya reject uphold (poster ko refund)."""
    async with pool.acquire() as c, c.transaction():
        s = await _bw_lock(c, sid)
        if not s or s["status"] != "reported":
            return None
        if pay:
            await _bw_pay(c, s)
        else:
            await _bw_close(c, s)
        return s


async def bw_auto_report(hours):
    return await pool.fetch(
        """UPDATE bw_subs SET status='reported', reason='Poster ne time par review nahi kiya'
           WHERE status='pending' AND created_at < now() - make_interval(hours => $1) RETURNING id""", hours)


async def bw_mark_report_sent(sid):
    await pool.execute("UPDATE bw_subs SET report_sent=TRUE WHERE id=$1", sid)


async def bw_unsent_reports(limit=20):
    return await pool.fetch(
        "SELECT id FROM bw_subs WHERE status='reported' AND NOT report_sent ORDER BY id LIMIT $1", limit)


async def bw_close_expired(hours):
    """Reject ke baad report window nikal gayi: slot band, coins poster ko wapas."""
    rows = await pool.fetch(
        "SELECT id FROM bw_subs WHERE status='rejected' AND decided_at < now() - make_interval(hours => $1)", hours)
    n = 0
    for r in rows:
        async with pool.acquire() as c, c.transaction():
            s = await _bw_lock(c, r["id"])
            if s and s["status"] == "rejected":
                await _bw_close(c, s)
                n += 1
    return n


# ---------- mini app helpers ----------
async def recent_ledger(uid, n=10):
    return await pool.fetch(
        "SELECT kind, amount, created_at FROM ledger WHERE user_id=$1 ORDER BY id DESC LIMIT $2", uid, n)


async def wd_history(uid):
    return await pool.fetch(
        """SELECT id, coins, amount_inr, fee_coins, upi, status, code, created_at FROM withdrawals
           WHERE user_id=$1 ORDER BY id DESC LIMIT 30""", uid)


async def order_history(uid):
    return await pool.fetch(
        """SELECT order_id, kind, coins, amount_inr, created_at,
                  CASE WHEN status='pending' AND created_at < now() - make_interval(mins => $2) THEN 'failed'
                       ELSE status END AS status
           FROM orders WHERE user_id=$1 ORDER BY created_at DESC LIMIT 10""", uid, config.ORDER_EXPIRY_MIN)


async def order_get(order_id, uid):
    return await pool.fetchrow("SELECT status FROM orders WHERE order_id=$1 AND user_id=$2", order_id, uid)


async def pending_orders(uid):
    return await pool.fetchval(
        "SELECT count(*) FROM orders WHERE user_id=$1 AND status='pending' AND created_at > now() - interval '1 hour'",
        uid)


async def set_device(uid, dev_hash, fp, ip=""):
    """Telegram ID + device bind. Return 'ok' / 'taken'.
    'taken' = device token kisi aur account ka, YA (STRICT_FP) wahi fingerprint + wahi IP kisi aur verified account ka.
    Sirf fingerprint match (IP alag) to suspect flag lagta hai (withdraw manual review)."""
    try:
        async with pool.acquire() as c, c.transaction():
            me = await c.fetchrow("SELECT fp_ok FROM users WHERE id=$1", uid)
            dups = await c.fetch("SELECT id, ip FROM users WHERE fp=$1 AND id<>$2 AND device_ok", fp, uid)
            if config.STRICT_FP and ip and not (me and me["fp_ok"]) and any(d["ip"] == ip for d in dups):
                return "taken"
            await c.execute(
                """UPDATE users SET device_hash=$1, fp=$2, ip=$5, device_ok=TRUE, dev_ver=2, suspect=(suspect OR $3)
                   WHERE id=$4""", dev_hash, fp, bool(dups), uid, ip or None)
        return "ok"
    except asyncpg.UniqueViolationError:
        return "taken"


async def set_bypass(uid, on):
    """Admin: user ko device check se chhoot (koi bhi phone/device chalega). on=False se wapas normal verify."""
    if on:
        return await pool.fetchval("UPDATE users SET dev_bypass=TRUE, device_ok=TRUE, suspect=FALSE WHERE id=$1 RETURNING id", uid)
    return await pool.fetchval(
        "UPDATE users SET dev_bypass=FALSE, device_ok=(device_hash IS NOT NULL) WHERE id=$1 RETURNING id", uid)


async def allow_dev(uid):
    """Admin: is user par fingerprint+IP wali rok nahi lagegi (jaise ek ghar me same phone model)."""
    return await pool.fetchval("UPDATE users SET fp_ok=TRUE WHERE id=$1 RETURNING id", uid)


async def rebind_device(uid, dev_hash, fp, counted=True):
    """Verified user ka device badla (ya legacy migration). False agar ye device kisi aur account ka hai."""
    try:
        await pool.execute(
            """UPDATE users SET device_hash=$2, fp=$3, dev_ver=2, device_changes=device_changes+$4
               WHERE id=$1 AND device_ok""", uid, dev_hash, fp, 1 if counted else 0)
        return True
    except asyncpg.UniqueViolationError:
        return False


async def device_owner(dev_hash):
    return await pool.fetchval("SELECT id FROM users WHERE device_hash=$1", dev_hash)


async def flag_suspect(uid):
    await pool.execute("UPDATE users SET suspect=TRUE WHERE id=$1 AND NOT suspect", uid)


async def reset_device(uid):
    return await pool.fetchval(
        """UPDATE users SET device_ok=FALSE, device_hash=NULL, gmail=NULL, fp=NULL, ip=NULL, dev_bypass=FALSE, device_changes=0,
           suspect=FALSE, dev_ver=2 WHERE id=$1 RETURNING id""", uid)


async def bw_set_photo(sid, file_id, file2_id=None):
    await pool.execute("UPDATE bw_subs SET photo_id=$2, photo2_id=COALESCE($3, photo2_id) WHERE id=$1", sid, file_id, file2_id)


async def bw_drop(sid):
    await pool.execute("DELETE FROM bw_subs WHERE id=$1 AND status='pending'", sid)


# ---------- gift codes ----------
async def gift_create(code, coins, uses):
    try:
        await pool.execute("INSERT INTO gift_codes(code,coins,max_uses) VALUES($1,$2,$3)", code, coins, uses)
        return True
    except asyncpg.UniqueViolationError:
        return False


async def gift_redeem(uid, code):
    """Return (result, coins). result: ok / invalid / used_up / dup"""
    try:
        async with pool.acquire() as c, c.transaction():
            g = await c.fetchrow("SELECT * FROM gift_codes WHERE code=$1 FOR UPDATE", code)
            if not g:
                return "invalid", 0
            if g["used"] >= g["max_uses"]:
                return "used_up", 0
            await c.execute("INSERT INTO gift_redeems(code,user_id) VALUES($1,$2)", code, uid)
            await c.execute("UPDATE gift_codes SET used=used+1 WHERE code=$1", code)
            await c.execute("UPDATE users SET balance=balance+$1, total_earned=total_earned+$1 WHERE id=$2",
                            g["coins"], uid)
            await led(c, uid, "gift", g["coins"], code)
            return "ok", g["coins"]
    except asyncpg.UniqueViolationError:
        return "dup", 0


# ---------- support chat ----------
async def sup_add(uid, sender, text, photo=None, voice=None):
    """Support message (text aur/ya photo ya voice). Thread summary bhi update hoti hai (admin inbox ke liye)."""
    async with pool.acquire() as c, c.transaction():
        mid = await c.fetchval(
            "INSERT INTO support_msgs(user_id,sender,text,has_photo,has_voice) VALUES($1,$2,$3,$4,$5) RETURNING id",
            uid, sender, text, photo is not None, voice is not None)
        blob = photo if photo is not None else voice
        if blob is not None:
            await c.execute("INSERT INTO support_files(msg_id,data) VALUES($1,$2)", mid, blob)
        await c.execute(
            """INSERT INTO support_threads(user_id,last_sender,last_text,last_at) VALUES($1,$2,$3,now())
               ON CONFLICT(user_id) DO UPDATE SET last_sender=EXCLUDED.last_sender,
               last_text=EXCLUDED.last_text, last_at=now()""",
            uid, sender, (text or ("🎤 Voice" if voice is not None else "📷 Photo"))[:80])
        return mid


async def sup_list(uid, limit=60):
    rows = await pool.fetch(
        "SELECT id, sender, text, has_photo, has_voice, created_at FROM support_msgs WHERE user_id=$1 ORDER BY id DESC LIMIT $2",
        uid, limit)
    return list(reversed(rows))


async def sup_file(mid):
    return await pool.fetchrow(
        "SELECT f.data, m.user_id FROM support_files f JOIN support_msgs m ON m.id=f.msg_id WHERE f.msg_id=$1", mid)


async def sup_recent_photos(uid, hours=1):
    return await pool.fetchval(
        """SELECT count(*) FROM support_msgs WHERE user_id=$1 AND sender='user' AND (has_photo OR has_voice)
           AND created_at > now() - make_interval(hours => $2)""", uid, hours)


async def sup_threads(limit=40):
    return await pool.fetch(
        """SELECT t.user_id, t.last_sender, t.last_text, t.last_at, u.username, u.first_name,
                  CASE WHEN u.premium_until > now() THEN GREATEST(u.premium_level, 1) ELSE 0 END AS lvl
           FROM support_threads t LEFT JOIN users u ON u.id=t.user_id
           ORDER BY (t.last_sender='user') DESC, CASE WHEN u.premium_until > now() THEN GREATEST(u.premium_level, 1) ELSE 0 END DESC,
                    t.last_at DESC LIMIT $1""", limit)


async def sup_notif_recent(uid):
    return await pool.fetchval(
        """SELECT EXISTS(SELECT 1 FROM support_notifs WHERE user_id=$1
           AND created_at > now() - interval '30 minutes')""", uid)


async def sup_cleanup():
    """Support text/photo/voice SUPPORT_KEEP_HOURS ke baad delete; purani joins/ledger bhi saaf."""
    h = config.SUPPORT_KEEP_HOURS
    await pool.execute("DELETE FROM support_files WHERE msg_id IN (SELECT id FROM support_msgs WHERE created_at < now() - make_interval(hours => $1))", h)
    await pool.execute("DELETE FROM support_msgs WHERE created_at < now() - make_interval(hours => $1)", h)
    await pool.execute("DELETE FROM support_threads WHERE last_at < now() - make_interval(hours => $1)", h)
    await pool.execute("DELETE FROM support_notifs WHERE created_at < now() - interval '2 days'")
    # joins: jinka completion ban chuka hai unki row ki zaroorat nahi
    await pool.execute("""DELETE FROM joins j WHERE EXISTS(
        SELECT 1 FROM completions c WHERE c.user_id=j.user_id AND c.chat_id=j.chat_id)""")
    await pool.execute("DELETE FROM bcast WHERE done AND created_at < now() - interval '3 days'")


async def ledger_prune():
    """Safety net: kisi user ke LEDGER_KEEP se zyada rows hon to purani hata do."""
    await pool.execute(
        """DELETE FROM ledger WHERE id IN (SELECT id FROM (SELECT id, row_number() OVER
           (PARTITION BY user_id ORDER BY id DESC) rn FROM ledger) q WHERE rn > $1)""", config.LEDGER_KEEP)


# ---------- referrals ----------
async def ref_add(referred, referrer):
    """Naya user referrer ke link se aaya. True agar record bana."""
    if referred == referrer:
        return False
    r = await pool.fetchval(
        """INSERT INTO referrals(referred_id,referrer_id)
           SELECT $1::bigint, $2::bigint WHERE EXISTS(SELECT 1 FROM users WHERE id=$2::bigint AND NOT banned)
           ON CONFLICT DO NOTHING RETURNING referred_id""", referred, referrer)
    return r is not None


async def ref_ready(limit=100):
    """Refer pending hai aur dost ne MIN_TASKS_FOR_REFER task poore kar liye hain (channel reward 24h hold se
    nikal chuka ho ya bot work approved) aur dost banned nahi hai."""
    return await pool.fetch(
        """SELECT r.referred_id FROM referrals r
           JOIN users u ON u.id=r.referred_id AND NOT u.banned
           WHERE r.status='pending' AND
             ((SELECT count(*) FROM completions c WHERE c.user_id=r.referred_id AND c.status='ok')
            + (SELECT count(*) FROM bw_subs s WHERE s.worker_id=r.referred_id AND s.status='approved')) >= $2
           LIMIT $1""", limit, max(1, config.MIN_TASKS_FOR_REFER))


async def ref_complete(referred):
    """Refer complete: referrer ko uske level ka reward. Return (referrer_id, reward) ya None agar pehle ho chuka."""
    async with pool.acquire() as c, c.transaction():
        r = await c.fetchrow(
            "UPDATE referrals SET status='done', done_at=now() WHERE referred_id=$1 AND status='pending' RETURNING referrer_id",
            referred)
        if not r:
            return None
        ru = await c.fetchrow("SELECT id, banned, premium_level, premium_until FROM users WHERE id=$1", r["referrer_id"])
        if not ru or ru["banned"] is not False:
            await c.execute("UPDATE referrals SET status='void' WHERE referred_id=$1", referred)  # banned/gayab referrer
            return None
        reward = util.plan(ru)["ref"]  # referrer ke premium level ke hisaab se (L3 = 200)
        await c.execute("UPDATE users SET balance=balance+$1, total_earned=total_earned+$1 WHERE id=$2",
                        reward, r["referrer_id"])
        await led(c, r["referrer_id"], "referral", reward, referred)
        return r["referrer_id"], reward


async def ref_stats(uid):
    return await pool.fetchrow(
        """SELECT count(*) AS total, count(*) FILTER (WHERE status='done') AS done
           FROM referrals WHERE referrer_id=$1""", uid)


async def ref_list(uid, limit=20):
    return await pool.fetch(
        """SELECT r.status, r.created_at, u.first_name FROM referrals r LEFT JOIN users u ON u.id=r.referred_id
           WHERE r.referrer_id=$1 ORDER BY r.created_at DESC LIMIT $2""", uid, limit)


async def set_ban(uid, flag):
    return await pool.fetchval("UPDATE users SET banned=$2 WHERE id=$1 RETURNING id", uid, flag)


async def sup_recent_count(uid):
    return await pool.fetchval(
        "SELECT count(*) FROM support_msgs WHERE user_id=$1 AND sender='user' AND created_at > now() - interval '1 hour'",
        uid)


async def sup_notif_add(admin_id, msg_id, uid):
    await pool.execute(
        "INSERT INTO support_notifs(admin_id,msg_id,user_id) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",
        admin_id, msg_id, uid)


async def sup_notif_pop(uid):
    """Is user ke saare admin notifications ki list de aur DB se hata de (delete karne ke liye)."""
    return await pool.fetch("DELETE FROM support_notifs WHERE user_id=$1 RETURNING admin_id, msg_id", uid)


# ---------- notifications (naya task/bot work aaya) ----------
async def bc_enqueue():
    """Naye (notified=false) tasks / bot works ko EK broadcast me jodo. Return broadcast id ya None."""
    async with pool.acquire() as c, c.transaction():
        t = await c.fetch("UPDATE tasks SET notified=TRUE WHERE NOT notified RETURNING id, title, status")
        b = await c.fetch("UPDATE botworks SET notified=TRUE WHERE NOT notified RETURNING id, title, reward, status")
        t = [x for x in t if x["status"] == "active"]
        b = [x for x in b if x["status"] == "active"]
        if not t and not b:
            return None
        parts = []
        if t:
            parts.append(f"📢 <b>{len(t)} naya channel task</b>: join karo aur coins kamao!" if len(t) > 1 else
                         f"📢 <b>Naya channel task</b>: {_esc(t[0]['title'])}\nJoin karo, {config.JOIN_REWARD} coins kamao!")
        if b:
            parts.append(f"🤖 <b>{len(b)} naya Bot Work</b> add hua!" if len(b) > 1 else
                         f"🤖 <b>Naya Bot Work</b>: {_esc(b[0]['title'])}\nReward: {b[0]['reward']} coins")
        return await c.fetchval("INSERT INTO bcast(kind,text) VALUES('task',$1) RETURNING id", "\n\n".join(parts) + "\n\n👇 App kholo")


def _esc(x):
    import html
    return html.escape(x or "")


async def bc_next():
    return await pool.fetchrow("SELECT * FROM bcast WHERE NOT done ORDER BY id LIMIT 1")


async def bc_users(last_uid, limit=100):
    return await pool.fetch(
        "SELECT id, lang FROM users WHERE id>$1 AND notify AND NOT banned ORDER BY id LIMIT $2", last_uid, limit)


async def bc_progress(bid, last_uid, sent, done=False):
    await pool.execute("UPDATE bcast SET last_uid=$2, sent=sent+$3, done=$4 WHERE id=$1", bid, last_uid, sent, done)


async def set_notify(uid, on):
    await pool.execute("UPDATE users SET notify=$2 WHERE id=$1", uid, bool(on))


# ---------- Admin Panel ----------
async def adm_stats():
    r = await pool.fetchrow(
        """SELECT
          (SELECT count(*) FROM users) AS users,
          (SELECT count(*) FROM users WHERE created_at > now() - interval '24 hours') AS new24,
          (SELECT count(*) FROM users WHERE device_ok) AS verified,
          (SELECT count(*) FROM users WHERE banned) AS banned,
          (SELECT count(*) FROM users WHERE premium_until > now()) AS prem,
          (SELECT coalesce(sum(balance),0) FROM users) AS bal_sum,
          (SELECT coalesce(sum(ad_balance),0) FROM users) AS ad_sum,
          (SELECT count(*) FROM withdrawals WHERE status='pending') AS wd_pending,
          (SELECT coalesce(sum(amount_inr),0) FROM withdrawals WHERE status='pending') AS wd_pending_inr,
          (SELECT coalesce(sum(amount_inr),0) FROM withdrawals WHERE status='paid' AND created_at > now() - interval '24 hours') AS wd_paid24,
          (SELECT count(*) FROM fam_claims WHERE status='pending') AS claims,
          (SELECT count(*) FROM fam_payments WHERE status='unmatched') AS unmatched,
          (SELECT coalesce(sum(amount_inr),0) FROM orders WHERE status='paid' AND created_at > now() - interval '24 hours') AS paid24,
          (SELECT count(*) FROM tasks WHERE status='active') AS tasks,
          (SELECT count(*) FROM botworks WHERE status='active') AS bws""")
    return {k: (float(v) if k in ("wd_pending_inr", "wd_paid24", "paid24") else int(v)) for k, v in dict(r).items()}


_ULIST = "id, username, first_name, balance, ad_balance, banned, premium_level, premium_until, device_ok, created_at"


async def adm_users(q):
    q = (q or "").strip().lstrip("@")[:40]
    if not q:
        return await pool.fetch(f"SELECT {_ULIST} FROM users ORDER BY created_at DESC LIMIT 20")
    like = "%" + q.replace("\\", "").replace("%", "").replace("_", "") + "%"
    return await pool.fetch(
        f"""SELECT {_ULIST} FROM users WHERE id::text=$1 OR username ILIKE $2 OR first_name ILIKE $2 OR upi ILIKE $2
            ORDER BY created_at DESC LIMIT 20""", q, like)


async def adm_user(uid):
    u = await pool.fetchrow(
        f"""SELECT {_ULIST}, upi, gmail, hold, total_earned, debt, suspect, dev_bypass FROM users WHERE id=$1""", uid)
    if not u:
        return None
    d = dict(u)
    d["tasks_done"] = await tasks_done(uid)
    d["refs"] = await pool.fetchval("SELECT count(*) FROM referrals WHERE referrer_id=$1", uid)
    d["wds"] = [dict(r) for r in await pool.fetch(
        "SELECT id, coins, amount_inr, status, created_at FROM withdrawals WHERE user_id=$1 ORDER BY id DESC LIMIT 5", uid)]
    d["ledger"] = [dict(r) for r in await pool.fetch(
        "SELECT kind, amount, created_at FROM ledger WHERE user_id=$1 ORDER BY id DESC LIMIT 8", uid)]
    return d


async def adm_wd_list():
    pend = await wd_pending_list(50)
    rec = await pool.fetch("SELECT * FROM withdrawals WHERE status<>'pending' ORDER BY id DESC LIMIT 20")
    return pend, rec


async def adm_tasks():
    ch = await pool.fetch(
        """SELECT t.id, t.owner_id, t.title, t.target, t.joined, u.username FROM tasks t LEFT JOIN users u ON u.id=t.owner_id
           WHERE t.status='active' ORDER BY t.id DESC LIMIT 40""")
    bw = await pool.fetch(
        """SELECT b.id, b.owner_id, b.title, b.target, b.reward, u.username FROM botworks b LEFT JOIN users u ON u.id=b.owner_id
           WHERE b.status='active' ORDER BY b.id DESC LIMIT 40""")
    return ch, bw


async def adm_cancel(kind, tid):
    """Admin kisi bhi user ka task cancel kare: refund owner ko. Return refund ya None."""
    if kind == "ch":
        owner = await pool.fetchval("SELECT owner_id FROM tasks WHERE id=$1", tid)
        return None if owner is None else await cancel_task(tid, owner)
    owner = await pool.fetchval("SELECT owner_id FROM botworks WHERE id=$1", tid)
    return None if owner is None else await bw_cancel(tid, owner)
