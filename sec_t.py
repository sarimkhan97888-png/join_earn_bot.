exec(open("api_t.py").read().split("async def main():")[0])
import hmac, hashlib, urllib.parse
import sec, webapp
FEED = []
extras.feed = lambda t: FEED.append(t)


class Rq(dict):
    app = {"bot": MagicMock()}
    def __init__(s, ip_hdrs=None, path="/api/me", method="GET", remote="45.33.32.9", query=None, **kw):
        super().__init__(**kw)
        s.headers = dict(ip_hdrs or {}); s.path = path; s.method = method; s.remote = remote; s.query = query or {}


def sign(user, age=0, **extra):
    d = {"auth_date": str(int(time.time()) - age), "user": json.dumps(user), **extra}
    s = "\n".join(f"{k}={v}" for k, v in sorted(d.items()))
    secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    d["hash"] = hmac.new(secret, s.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(d)


def fed(sub):
    return any(sub in f for f in FEED)


async def main():
    await db.init(); await db.init()
    config.FORCE_CHANNEL = ""

    # ---- 1. client IP: user ka bheja X-Forwarded-For ka pehla entry nahi chalta ----
    assert sec.client_ip(Rq({"X-Forwarded-For": "6.6.6.6, 1.2.3.4"})) == "1.2.3.4", "spoofed pehla entry"
    assert sec.client_ip(Rq({"X-Forwarded-For": "1.2.3.4"})) == "1.2.3.4"
    assert sec.client_ip(Rq({"CF-Connecting-IP": "5.5.5.5", "X-Forwarded-For": "6.6.6.6, 1.2.3.4"})) == "5.5.5.5", "proxy header pehle"
    assert sec.client_ip(Rq({"CF-Connecting-IP": "not-an-ip", "X-Forwarded-For": "1.2.3.4"})) == "1.2.3.4", "kharab header ignore"
    assert sec.client_ip(Rq({"True-Client-IP": "[2001:db8::1]:443"})) == "2001:db8::1"
    assert sec.client_ip(Rq({"X-Forwarded-For": "1.2.3.4:5555"})) == "1.2.3.4"
    assert sec.client_ip(Rq({})) == "45.33.32.9", "kuch nahi to remote"
    assert sec.client_ip(object()) == "?", "kharab request crash nahi"
    config.IP_HOPS = 2
    assert sec.client_ip(Rq({"X-Forwarded-For": "6.6.6.6, 1.2.3.4, 10.1.1.1"})) == "1.2.3.4", "IP_HOPS=2"
    config.IP_HOPS = 1

    # ---- 2. initData: har wajah alag, crash nahi ----
    usr = {"id": 4242, "first_name": "Z", "username": "z"}
    assert api.check_init_data_why(sign(usr)) == (usr, "")
    assert api.check_init_data(sign(usr)) == usr
    assert api.check_init_data_why("") == (None, "empty")
    assert api.check_init_data_why("auth_date=1&user=%7B%7D") == (None, "nohash")
    assert api.check_init_data_why(sign(usr, age=7 * 3600)) == (None, "old")
    assert api.check_init_data_why(sign(usr, age=-1000)) == (None, "future")
    assert api.check_init_data_why(sign([1, 2])) == (None, "bad"), "user dict nahi"
    assert api.check_init_data_why(sign({"id": "4242"})) == (None, "bad"), "id int nahi"
    bad = sign(usr).rsplit("hash=", 1)[0] + "hash=" + "a" * 64
    assert api.check_init_data_why(bad) == (None, "forged")
    assert api.check_init_data_why("auth_date=1&user=%7B%7D&hash=%C3%A9%C3%A9") == (None, "forged"), "non-ascii hash par 500 nahi"
    assert api._eq("é", "é") and not api._eq("é", "e") and not api._eq(None, "x")

    # ---- 3. auth_mw: valid user chalta hai, IP save hota hai ----
    called = []
    async def handler(r): called.append(r); return "RESP"
    api._watch = lambda *a, **k: None
    class Resp:
        def __init__(s): s.headers = {}
    async def h2(r): called.append(r); return Resp()
    r = Rq({"X-Init-Data": sign(usr), "CF-Connecting-IP": "45.33.33.7"})
    assert await api.auth_mw(r, handler) == "RESP" and called, "valid user ruka"
    assert r["ip"] == "45.33.33.7"
    assert await db.pool.fetchval("SELECT count(*) FROM user_ips WHERE user_id=4242 AND ip='45.33.33.7'") == 1, "IP save nahi hua"
    assert fed("IP header check") and fed("45.33.33.7"), "pehli request par header diagnostic"

    # ---- 4. forged session: feed me IP ke saath, 15 ke baad block ----
    FEED.clear(); ip = "45.33.32.50"
    for i in range(15):
        await api.auth_mw(Rq({"X-Init-Data": bad, "CF-Connecting-IP": ip}), handler)
    assert fed("Nakli request") and fed(ip), FEED[:2]
    assert sec.blocked(ip), "15 nakli requests par block nahi hua"
    assert fed("IP block ho gaya")
    # blocked IP par webapp middleware handler tak jaane hi nahi deta
    called.clear()
    await webapp.sec_mw(Rq({"CF-Connecting-IP": ip}), h2)
    assert not called, "blocked IP handler tak pahuncha"
    await webapp.sec_mw(Rq({"CF-Connecting-IP": "45.33.32.51"}), h2); assert called, "dusra IP bhi block ho gaya"
    # purana (6h+) session nakli nahi maana jaata
    FEED.clear()
    for i in range(20):
        await api.auth_mw(Rq({"X-Init-Data": sign(usr, age=8 * 3600), "CF-Connecting-IP": "45.33.32.60"}), handler)
    assert not sec.blocked("45.33.32.60") and not fed("Nakli request"), "purana session block hua"

    # ---- 5. shared IP (5+ asli users) ya private IP kabhi block nahi ----
    sh = "45.33.32.70"
    for uid in range(5000, 5006):
        await db.ensure_user(U(id=uid, username=f"s{uid}", first_name="S"))
        await sec.track(uid, sh)
    FEED.clear()
    for i in range(30):
        sec.forged(sh, "initData forged", "GET /api/me")
    assert not sec.blocked(sh) and fed("shared IP"), "shared IP block ho gaya (sab user rukte)"
    for i in range(30):
        sec.forged("10.0.0.5", "initData forged", "GET /api/me")
    assert not sec.blocked("10.0.0.5"), "private IP block"

    # ---- 6. ek IP par kai account / ek user ke bahut IP ----
    FEED.clear(); mi = "45.33.32.80"
    for uid in (6001, 6002, 6003):
        await db.ensure_user(U(id=uid, username=f"m{uid}", first_name="M"))
        await sec.track(uid, mi, {"id": uid, "username": f"m{uid}", "first_name": "M"})
    assert fed("Ek IP par 3 account") and fed("6001"), FEED
    assert sorted(await db.ip_others(mi, 6003)) == [6001, 6002]
    assert await db.ip_touch(6001, mi) == (False, 3, 1), "dobara touch naya nahi"
    FEED.clear()
    await db.ensure_user(U(id=6100, username="roamer", first_name="R"))
    for k in range(6):
        await sec.track(6100, f"198.18.0.{k + 1}")
    assert fed("alag IP"), FEED

    # ---- 7. Monetag: galat secret par feed me IP, par secret/attempt kabhi nahi ----
    FEED.clear(); config.MT_SECRET = "s3cr3t-value"; config.MT_ON = True
    for guess in ("nope-guess", "é", ""):
        resp = await api.monetag_postback(Rq({"CF-Connecting-IP": "45.33.32.90"}, path="/ads/monetag", query={"secret": guess, "ymid": "u1_abcd", "telegram_id": "1"}))
    assert fed("galat secret") and fed("45.33.32.90")
    blob = "\n".join(FEED)
    assert "s3cr3t-value" not in blob and "nope-guess" not in blob, "secret feed me leak"
    config.MT_SECRET = ""; config.MT_ON = False

    # ---- 8. admin API par non-admin: deny + feed (user + IP) ----
    FEED.clear(); api.ok = lambda **k: ("ok", k); api.err = lambda m, *a, **k: ("err", m)
    rq = Rq({"CF-Connecting-IP": "45.33.32.91"}, path="/api/admin/stats", u={"id": 77}, tg={"id": 77, "username": "bad", "first_name": "B"}, ip="45.33.32.91")
    assert await api.api_adm_stats(rq) == ("err", "Not allowed")
    assert fed("Non-admin ne ADMIN") and fed("45.33.32.91") and fed("@bad"), FEED
    FEED.clear()
    rq2 = Rq(path="/api/admin/stats", u={"id": 999}, tg={"id": 999}, ip="45.33.32.92")
    api.db.adm_stats = lambda: asyncio.sleep(0, {})
    assert (await api.api_adm_stats(rq2))[0] == "ok" and not FEED, "asli admin par alert"

    # ---- 9. withdraw me badli hui value: feed; normal request par nahi ----
    FEED.clear(); api.cooldown = lambda *a, **k: True
    def bd(d):
        async def b(r): return d
        api.body = b
    u = dict(await db.get_user(4242)); u["device_ok"] = False
    rq3 = Rq(path="/api/withdraw", method="POST", u=u, tg={"id": 4242, "username": "z", "first_name": "Z"}, ip="45.33.32.93")
    bd(dict(coins=1000, method="hackme")); await api.api_withdraw(rq3)
    assert fed("badli hui value") and fed("45.33.32.93") and fed("hackme"), FEED
    FEED.clear(); bd(dict(coins=1000, method="upi")); await api.api_withdraw(rq3); bd(dict(coins=None, method="gplay")); await api.api_withdraw(rq3)
    assert not fed("badli hui value"), "normal UI request par false alert"

    # ---- 10. report_err me IP; withdraw alert me IP + baaki accounts ----
    FEED.clear()
    api.report_err(Rq(path="/api/x", method="POST", ip="45.33.32.94"), "kuch galat", tg={"id": 12, "username": "q", "first_name": "Q"})
    assert fed("45.33.32.94"), "error report me IP nahi"
    sent = []
    async def pa(bot, text, kb, wid=None): sent.append(text)
    api.payouts.alert = pa; api.payouts.admin_kb = lambda *a, **k: None
    await api._after_withdraw(MagicMock(), {"id": 6003, "username": "m", "first_name": "M", "suspect": False}, 1, 1000, 100, 9.0, "a@upi", 0, None, ip=mi)
    assert sent and mi in sent[0] and "2 aur account" in sent[0] and "6001" in sent[0], sent
    assert fed(mi), "withdraw feed me IP nahi"

    # ---- 11. security headers ----
    rs = await webapp.sec_mw(Rq({"CF-Connecting-IP": "45.33.32.99"}), h2)
    assert "Strict-Transport-Security" in rs.headers and rs.headers["X-Content-Type-Options"] == "nosniff", rs.headers
    assert "object-src 'none'" in webapp.FRAME and "frame-ancestors" in webapp.FRAME
    print("SECURITY OK")

asyncio.run(main())
