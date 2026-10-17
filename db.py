from decimal import Decimal

import asyncpg

import config

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
CREATE INDEX IF NOT EXISTS users_fp ON users(fp);
"""


async def init():
    global pool
    pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=2, max_size=config.DB_POOL_MAX,
                                     command_timeout=30, max_inactive_connection_lifetime=300)
    async with pool.acquire() as c:
        await c.execute(SCHEMA)


async def led(c, uid, kind, amount, ref=""):
    await c.execute("INSERT INTO ledger(user_id,kind,amount,ref) VALUES($1,$2,$3,$4)", uid, kind, amount, str(ref))


# ---------- users ----------
async def ensure_user(tu):
    # Har API call par write nahi: sirf naya user ya naam badla ho tabhi UPSERT (1 lakh users par bloat se bachata hai)
    u = await pool.fetchrow("SELECT * FROM users WHERE id=$1", tu.id)
    if u and u["username"] == tu.username and u["first_name"] == tu.first_name:
        return u
    return await pool.fetchrow(
        """INSERT INTO users(id,username,first_name) VALUES($1,$2,$3)
           ON CONFLICT(id) DO UPDATE SET username=EXCLUDED.username, first_name=EXCLUDED.first_name
           RETURNING *""", tu.id, tu.username, tu.first_name)


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
           ORDER BY t.created_at LIMIT 8""", uid)


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
        "INSERT INTO joins(chat_id,user_id) VALUES($1,$2) ON CONFLICT(chat_id,user_id) DO UPDATE SET at=now()",
        chat_id, uid)


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
    r = await pool.execute(
        "UPDATE completions SET status='rejoined' WHERE chat_id=$1 AND user_id=$2 AND status='left'", chat_id, uid)
    return r.endswith("1")


async def revoke(comp_id):
    async with pool.acquire() as c, c.transaction():
        r = await c.fetchrow("SELECT * FROM completions WHERE id=$1 FOR UPDATE", comp_id)
        if not r or r["status"] not in ("hold", "ok"):
            return None
        if r["status"] == "hold":
            await c.execute("UPDATE users SET hold=GREATEST(hold-$1,0) WHERE id=$2", r["reward"], r["user_id"])
        else:
            await c.execute("UPDATE users SET balance=GREATEST(balance-$1,0) WHERE id=$2", r["reward"], r["user_id"])
        await c.execute("UPDATE completions SET status='left' WHERE id=$1", comp_id)
        await led(c, r["user_id"], "revoke", -r["reward"], comp_id)
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
        await c.execute(
            """UPDATE users SET hold=GREATEST(hold-$1,0), balance=balance+$1, total_earned=total_earned+$1
               WHERE id=$2""", r["reward"], r["user_id"])
        await c.execute("UPDATE completions SET status='ok' WHERE id=$1", comp_id)
        await led(c, r["user_id"], "release", r["reward"], comp_id)
        return r


# ---------- orders ----------
async def new_order(order_id, uid, kind, coins, amount_inr, gateway_ref=None):
    await pool.execute(
        "INSERT INTO orders(order_id,user_id,kind,coins,amount_inr,gateway_ref) VALUES($1,$2,$3,$4,$5,$6)",
        order_id, uid, kind, coins, amount_inr, gateway_ref)


async def order_row(order_id):
    return await pool.fetchrow("SELECT * FROM orders WHERE order_id=$1", order_id)


async def order_lookup(ref, order_id):
    return await pool.fetchrow(
        "SELECT * FROM orders WHERE gateway_ref=$1::text OR order_id=$2::text ORDER BY created_at DESC LIMIT 1",
        ref, order_id)


async def order_set_status(order_id, status):
    await pool.execute("UPDATE orders SET status=$2 WHERE order_id=$1 AND status='pending'", order_id, status)


async def pending_gateway_orders():
    return await pool.fetch(
        """SELECT * FROM orders WHERE status='pending' AND gateway_ref IS NOT NULL
           AND created_at > now() - interval '24 hours' ORDER BY created_at LIMIT 50""")


async def complete_order(order_id, paid_amount):
    async with pool.acquire() as c, c.transaction():
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
        else:
            await c.execute(
                """UPDATE users SET premium_until = GREATEST(COALESCE(premium_until, now()), now())
                   + make_interval(days => $1) WHERE id=$2""", config.PREMIUM_DAYS, o["user_id"])
            await led(c, o["user_id"], "premium", 0, order_id)
        return o


# ---------- withdrawals ----------
async def request_withdraw(uid, coins):
    """Return (wid, upi, fee_coins, net_inr). Tax coins me kat-ta hai, user ko net amount milta hai."""
    fee = coins * config.WITHDRAW_TAX_PERCENT // 100
    net_inr = Decimal(coins - fee) / Decimal(config.COIN_PER_INR)
    async with pool.acquire() as c, c.transaction():
        u = await c.fetchrow(
            """UPDATE users SET balance=balance-$1 WHERE id=$2 AND balance>=$1
               AND device_ok AND NOT banned AND upi IS NOT NULL RETURNING upi""", coins, uid)
        if not u:
            return None
        wid = await c.fetchval(
            "INSERT INTO withdrawals(user_id,coins,amount_inr,fee_coins,upi) VALUES($1,$2,$3,$4,$5) RETURNING id",
            uid, coins, net_inr, fee, u["upi"])
        await led(c, uid, "withdraw", -coins, wid)
        if fee:
            await led(c, 0, "tax", fee, wid)
        return wid, u["upi"], fee, net_inr


async def wd_move(wid, frm, to):
    return await pool.fetchrow("UPDATE withdrawals SET status=$3 WHERE id=$1 AND status=$2 RETURNING *", wid, frm, to)


async def wd_get(wid):
    return await pool.fetchrow("SELECT * FROM withdrawals WHERE id=$1", wid)


async def wd_set_ref(wid, ref):
    return await pool.fetchrow(
        "UPDATE withdrawals SET status='processing', gateway_ref=$2 WHERE id=$1 AND status='sending' RETURNING *",
        wid, ref)


async def wd_lookup(ref, reference):
    return await pool.fetchrow(
        "SELECT * FROM withdrawals WHERE gateway_ref=$1::text OR ('WD' || id::text)=$2::text LIMIT 1", ref, reference)


async def wd_processing(limit=50):
    return await pool.fetch(
        "SELECT * FROM withdrawals WHERE status='processing' AND gateway_ref IS NOT NULL ORDER BY id LIMIT $1", limit)


async def wd_recent_count(uid, hours=24):
    return await pool.fetchval(
        "SELECT count(*) FROM withdrawals WHERE user_id=$1 AND created_at > now() - make_interval(hours => $2)",
        uid, hours)


async def wd_refund(w):
    async with pool.acquire() as c, c.transaction():
        await c.execute("UPDATE users SET balance=balance+$1 WHERE id=$2", w["coins"], w["user_id"])
        await led(c, w["user_id"], "withdraw_refund", w["coins"], w["id"])


# ---------- bot work ----------
# Escrow: poster ke ad_balance se reward*target pehle hi kat jata hai.
# Slot "used" = us task ki har submission jo 'closed' nahi hai.
async def bw_create(owner, title, link, reward, n, free=False):
    cost = reward * n
    async with pool.acquire() as c, c.transaction():
        if not free:
            ok = await c.fetchval(
                "UPDATE users SET ad_balance=ad_balance-$1 WHERE id=$2 AND ad_balance>=$1 RETURNING id", cost, owner)
            if not ok:
                return None
        bid = await c.fetchval(
            "INSERT INTO botworks(owner_id,title,link,reward,target,free) VALUES($1,$2,$3,$4,$5,$6) RETURNING id",
            owner, title, link, reward, n, free)
        if not free:
            await led(c, owner, "bw_escrow", -cost, bid)
        return bid


async def bw_get(bid):
    return await pool.fetchrow("SELECT * FROM botworks WHERE id=$1", bid)


async def _bw_used(c, bid):
    return await c.fetchval("SELECT count(*) FROM bw_subs WHERE bw_id=$1 AND status<>'closed'", bid)


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
             (SELECT count(*) FROM bw_subs s WHERE s.bw_id=b.id AND s.status<>'closed') AS used,
             (SELECT count(*) FROM bw_subs s WHERE s.bw_id=b.id AND s.status='approved') AS done,
             (SELECT count(*) FROM bw_subs s WHERE s.bw_id=b.id AND s.status='pending') AS pending
           FROM botworks b WHERE b.owner_id=$1 ORDER BY b.id DESC LIMIT 10""", uid)


async def bw_open(uid):
    return await pool.fetch(
        """SELECT b.* FROM botworks b
           WHERE b.status='active' AND b.owner_id<>$1
             AND b.target > (SELECT count(*) FROM bw_subs s WHERE s.bw_id=b.id AND s.status<>'closed')
             AND NOT EXISTS(SELECT 1 FROM bw_subs s WHERE s.bw_id=b.id AND s.worker_id=$1)
           ORDER BY b.reward DESC, b.id LIMIT 8""", uid)


async def bw_submit(bid, worker, photo_id, photo_uid, ref_link):
    """Return (result, sid, botwork_row). result: ok / closed / own / full / dup"""
    try:
        async with pool.acquire() as c, c.transaction():
            b = await c.fetchrow("SELECT * FROM botworks WHERE id=$1 FOR UPDATE", bid)
            if not b or b["status"] != "active":
                return "closed", None, None
            if b["owner_id"] == worker:
                return "own", None, None
            if await _bw_used(c, bid) >= b["target"]:
                return "full", None, None
            sid = await c.fetchval(
                """INSERT INTO bw_subs(bw_id,worker_id,photo_id,photo_uid,ref_link)
                   VALUES($1,$2,$3,$4,$5) RETURNING id""", bid, worker, photo_id, photo_uid, ref_link)
            return "ok", sid, b
    except asyncpg.UniqueViolationError:
        return "dup", None, None


async def bw_sub(sid):
    return await pool.fetchrow(
        """SELECT s.*, b.title, b.owner_id, b.reward, b.link FROM bw_subs s
           JOIN botworks b ON b.id=s.bw_id WHERE s.id=$1""", sid)


async def bw_mine(uid):
    return await pool.fetch(
        """SELECT s.id, s.status, b.title, b.reward FROM bw_subs s JOIN botworks b ON b.id=s.bw_id
           WHERE s.worker_id=$1 ORDER BY s.id DESC LIMIT 10""", uid)


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


async def bw_review(sid, owner, approve):
    """Poster ka Done / Reject. Sirf pending submission par chalega."""
    async with pool.acquire() as c, c.transaction():
        s = await _bw_lock(c, sid)
        if not s or s["owner_id"] != owner or s["status"] != "pending":
            return None
        if approve:
            await _bw_pay(c, s)
        else:
            await c.execute("UPDATE bw_subs SET status='rejected', decided_at=now() WHERE id=$1", sid)
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
async def recent_ledger(uid, n=15):
    return await pool.fetch(
        "SELECT kind, amount, created_at FROM ledger WHERE user_id=$1 ORDER BY id DESC LIMIT $2", uid, n)


async def wd_history(uid):
    return await pool.fetch(
        """SELECT id, coins, amount_inr, fee_coins, upi, status, created_at FROM withdrawals
           WHERE user_id=$1 ORDER BY id DESC LIMIT 10""", uid)


async def order_history(uid):
    return await pool.fetch(
        """SELECT order_id, kind, coins, amount_inr, status, created_at FROM orders
           WHERE user_id=$1 ORDER BY created_at DESC LIMIT 10""", uid)


async def order_get(order_id, uid):
    return await pool.fetchrow("SELECT status FROM orders WHERE order_id=$1 AND user_id=$2", order_id, uid)


async def pending_orders(uid):
    return await pool.fetchval(
        "SELECT count(*) FROM orders WHERE user_id=$1 AND status='pending' AND created_at > now() - interval '1 hour'",
        uid)


async def set_device(uid, gmail, dev_hash, fp):
    """Naya device bind. Return 'ok' / 'taken' (device ya Gmail kisi aur account se linked).
    Agar same fingerprint kisi aur verified account ka hai to suspect flag lagta hai (withdraw manual review)."""
    try:
        async with pool.acquire() as c, c.transaction():
            dup = await c.fetchval("SELECT EXISTS(SELECT 1 FROM users WHERE fp=$1 AND id<>$2 AND device_ok)", fp, uid)
            await c.execute(
                """UPDATE users SET gmail=$1, device_hash=$2, fp=$3, device_ok=TRUE, dev_ver=2, suspect=$4
                   WHERE id=$5""", gmail, dev_hash, fp, bool(dup), uid)
        return "ok"
    except asyncpg.UniqueViolationError:
        return "taken"


async def rebind_device(uid, dev_hash, fp, counted=True):
    """Verified user ka device badla (ya legacy migration). False agar ye device kisi aur account ka hai."""
    try:
        await pool.execute(
            """UPDATE users SET device_hash=$2, fp=$3, dev_ver=2, device_changes=device_changes+$4
               WHERE id=$1 AND device_ok""", uid, dev_hash, fp, 1 if counted else 0)
        return True
    except asyncpg.UniqueViolationError:
        return False


async def reset_device(uid):
    return await pool.fetchval(
        """UPDATE users SET device_ok=FALSE, device_hash=NULL, gmail=NULL, fp=NULL, device_changes=0,
           suspect=FALSE, dev_ver=2 WHERE id=$1 RETURNING id""", uid)


async def bw_set_photo(sid, file_id):
    await pool.execute("UPDATE bw_subs SET photo_id=$2 WHERE id=$1", sid, file_id)


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
async def sup_add(uid, sender, text):
    return await pool.fetchval(
        "INSERT INTO support_msgs(user_id,sender,text) VALUES($1,$2,$3) RETURNING id", uid, sender, text)


async def sup_list(uid, limit=60):
    rows = await pool.fetch(
        "SELECT sender, text, created_at FROM support_msgs WHERE user_id=$1 ORDER BY id DESC LIMIT $2", uid, limit)
    return list(reversed(rows))


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
