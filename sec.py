"""Security helpers: asli client IP, jhoothi/forged request ki ginti + IP block, admin feed me poori detail (IP ke saath),
ek IP par kitne account / ek user ke kitne IP ka track. Koi function kabhi raise nahi karta (security ki wajah se app na ruke)."""
import html
import ipaddress
import logging
import time

import config
import db
import extras

log = logging.getLogger("sec")

_bad = {}        # ip -> [monotonic times] (forged / nakli requests)
_block = {}      # ip -> block khatam hone ka monotonic time
_seen = {}       # (uid, ip) -> last DB write
_ipusers = {}    # ip -> {uid,...}: ek IP par kitne alag asli users (shared proxy / CGNAT pehchanne ke liye)
_dedupe = {}     # alert key -> [time, extra count]
_hdr_noted = [False]


def _valid(v):
    v = (v or "").strip()
    if v.startswith("[") and "]" in v:          # [ipv6]:port
        v = v[1:v.index("]")]
    elif v.count(":") == 1 and "." in v:        # ipv4:port
        v = v.split(":")[0]
    try:
        return str(ipaddress.ip_address(v))
    except ValueError:
        return ""


def client_ip(request):
    """Asli client IP. Pehle proxy ke set kiye header (CF-Connecting-IP / True-Client-IP, env IP_HEADERS), warna X-Forwarded-For
    ka wo entry jo hamare proxy ne joda (daayein se IP_HOPS-wala). Pehla entry kabhi nahi: wo user khud bhej sakta hai."""
    try:
        h = request.headers
        for name in config.IP_HEADERS:
            ip = _valid(h.get(name, ""))
            if ip:
                return ip
        xf = [x for x in (h.get("X-Forwarded-For", "") or "").split(",") if x.strip()]
        if xf:
            ip = _valid(xf[max(len(xf) - config.IP_HOPS, 0)])
            if ip:
                return ip
        return _valid(getattr(request, "remote", "") or "") or "?"
    except Exception:
        return "?"


def _shared(ip):
    """True = ye IP block karne layak nahi: private/loopback, ya isse 5+ alag asli users aa rahe hain (proxy / mobile CGNAT).
    Galat IP-header setting me bhi isse sab users ek saath block nahi honge."""
    try:
        if not ipaddress.ip_address(ip).is_global:
            return True
    except ValueError:
        return True
    return len(_ipusers.get(ip, ())) >= 5


def blocked(ip):
    t = _block.get(ip)
    if not t:
        return False
    if time.monotonic() >= t:
        _block.pop(ip, None)
        return False
    return True


def alert(kind, *, u=None, uid=None, ip="", path="", detail="", every=30, key=None):
    """Admin feed me ek suspicious / jhoothi cheez ki poori detail: kaun, kaunsa IP, kahan, kya galat.
    Same cheez `every` second me dobara aaye to '(+N baar aur)' ke saath ek hi baar. `kind` me sirf apna (safe) text do."""
    try:
        k = key or (kind, ip, uid or (u or {}).get("id"), path)
        now = time.monotonic()
        s = _dedupe.get(k)
        if s and now - s[0] < every:
            s[1] += 1
            return
        more = f" (+{s[1]} baar aur)" if s and s[1] else ""
        if len(_dedupe) > 5000:
            _dedupe.clear()
        _dedupe[k] = [now, 0]
        lines = [f"{kind}{more}"]
        who = None
        if u and u.get("id"):
            who = extras.uname(u)
        elif uid:
            who = f"<code>{int(uid)}</code>"
        if who:
            lines.append("👤 " + who)
        if ip:
            lines.append(f"🌐 IP: <code>{html.escape(str(ip))}</code>")
        if path:
            lines.append(f"📍 <code>{html.escape(str(path)[:120])}</code>")
        if detail:
            lines.append(f"🔎 {html.escape(str(detail)[:300])}")
        extras.feed("\n".join(lines))
    except Exception:
        log.exception("sec alert failed")


def forged(ip, why, path="", detail=""):
    """Nakli / forged request. Ek IP se SEC_BAD_LIMIT se zyada 10 min me => SEC_BLOCK_SECS ke liye block + feed alert."""
    try:
        if not ip or ip == "?":
            return
        now = time.monotonic()
        L = [x for x in _bad.get(ip, []) if now - x < 600]
        L.append(now)
        _bad[ip] = L
        if len(_bad) > 5000:
            for k in [k for k, v in _bad.items() if not v or now - v[-1] > 600]:
                _bad.pop(k, None)
        alert("🚨 <b>Nakli request</b> (hack try?)", ip=ip, path=path, detail=f"{why} {detail}".strip(), every=300, key=("forged", ip))
        if len(L) >= config.SEC_BAD_LIMIT and _shared(ip):
            alert(f"⚠️ {len(L)} nakli requests, par ye <b>shared IP</b> hai (proxy/mobile network) isliye block NAHI kiya", ip=ip, path=path, detail=why,
                  every=1800, key=("sharedbad", ip))
        elif len(L) >= config.SEC_BAD_LIMIT and not blocked(ip):
            _block[ip] = now + config.SEC_BLOCK_SECS
            _bad.pop(ip, None)
            alert(f"🛑 <b>IP block ho gaya</b> ({config.SEC_BLOCK_SECS // 60} min): {len(L)} nakli requests", ip=ip, path=path, detail=why, every=60, key=("block", ip))
    except Exception:
        log.exception("sec forged failed")


async def track(uid, ip, u=None, path=""):
    """User ka IP yaad rakho (naye user+IP jodi par hi DB write). Ek IP par kai account ya ek user ke bahut IP => feed alert."""
    try:
        if not ip or ip == "?" or uid in config.ADMIN_IDS:
            return
        now = time.monotonic()
        S = _ipusers.setdefault(ip, set())
        if len(S) < 50:
            S.add(uid)
        if len(_ipusers) > 50000:
            _ipusers.clear()
        t = _seen.get((uid, ip))
        if t and now - t < 21600:
            return
        if len(_seen) > 50000:
            _seen.clear()
        _seen[(uid, ip)] = now
        new, accs, ips = await db.ip_touch(uid, ip)
        if new and accs >= config.SEC_IP_ACCOUNTS:
            others = await db.ip_others(ip, uid)
            alert(f"👥 <b>Ek IP par {accs} account</b> (multi-account?)", u=u, uid=uid, ip=ip, path=path,
                  detail="baaki ids: " + ", ".join(str(x) for x in others), every=21600, key=("multi", ip))
        if new and ips >= config.SEC_USER_IPS:
            alert(f"🔀 <b>Ek user, 24 ghante me {ips} alag IP</b> (account share / VPN?)", u=u, uid=uid, ip=ip, path=path, every=43200, key=("ips", uid))
    except Exception:
        log.exception("sec track failed")


def note_headers(request, chosen):
    """Boot ke baad pehli request par ek baar: IP kis header se aaya, admin verify kar le (galat ho to Render env IP_HOPS/IP_HEADERS)."""
    try:
        if _hdr_noted[0]:
            return
        _hdr_noted[0] = True
        h = request.headers
        extras.feed("🔧 <b>IP header check</b> (ek baar)\n" + "\n".join(
            f"{n}: <code>{html.escape((h.get(n, '') or '-')[:100])}</code>" for n in ("CF-Connecting-IP", "True-Client-IP", "X-Forwarded-For"))
            + f"\nremote: <code>{html.escape(str(getattr(request, 'remote', '') or '-'))}</code>\n✅ Maine IP liya: <code>{html.escape(chosen)}</code>\n"
              "Ye tumhara/user ka sahi IP na ho to Render env me IP_HOPS (ya IP_HEADERS) badlo.")
    except Exception:
        pass
