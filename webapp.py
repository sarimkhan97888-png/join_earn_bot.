import hashlib
import hmac
import json
import logging
import re
import time
from urllib.parse import parse_qsl

import asyncpg
from aiohttp import web

import config
import db
import gateway

log = logging.getLogger("web")


def check_init_data(init_data: str):
    """Telegram WebApp initData validate karo; user dict return karta hai."""
    data = dict(parse_qsl(init_data, keep_blank_values=True))
    h = data.pop("hash", None)
    if not h:
        return None
    s = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, s.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, h):
        return None
    if time.time() - int(data.get("auth_date", "0")) > 86400:
        return None
    try:
        return json.loads(data["user"])
    except Exception:
        return None


VERIFY_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
body{font-family:system-ui,sans-serif;margin:0;padding:24px;background:var(--tg-theme-bg-color,#fff);color:var(--tg-theme-text-color,#111)}
h2{margin:0 0 6px}p{opacity:.7;margin:0 0 18px}
input{width:100%;box-sizing:border-box;padding:14px;border-radius:12px;border:1px solid #8884;font-size:16px;margin-bottom:14px;background:transparent;color:inherit}
button{width:100%;padding:14px;border:0;border-radius:12px;font-size:16px;background:var(--tg-theme-button-color,#2481cc);color:var(--tg-theme-button-text-color,#fff)}
#m{margin-top:16px;text-align:center}
</style></head><body>
<h2>🔐 Device Verification</h2><p>Apna Gmail daalo. Ek device = ek account.</p>
<input id="g" type="email" placeholder="yourname@gmail.com" autocomplete="email">
<button id="b">Verify</button><div id="m"></div>
<script>
const tg=window.Telegram.WebApp;tg.ready();tg.expand();
async function fp(){
 const c=document.createElement('canvas');const x=c.getContext('2d');x.textBaseline='top';x.font='14px Arial';x.fillText('devfp-v1',2,2);
 let r='';try{const gl=document.createElement('canvas').getContext('webgl');const e=gl&&gl.getExtension('WEBGL_debug_renderer_info');if(e)r=gl.getParameter(e.UNMASKED_RENDERER_WEBGL)}catch(e){}
 const s=[c.toDataURL(),r,navigator.hardwareConcurrency,screen.width+'x'+screen.height,screen.colorDepth,navigator.language,Intl.DateTimeFormat().resolvedOptions().timeZone,navigator.platform].join('|');
 const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s));
 return [...new Uint8Array(b)].map(v=>v.toString(16).padStart(2,'0')).join('');
}
document.getElementById('b').onclick=async()=>{
 const m=document.getElementById('m');m.textContent='Checking...';
 try{
  const res=await fetch('/api/verify',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({initData:tg.initData,gmail:document.getElementById('g').value,fp:await fp()})});
  const d=await res.json();m.textContent=d.msg;
  if(d.ok){setTimeout(()=>tg.close(),1200)}
 }catch(e){m.textContent='Network error, dobara try karo'}
};
</script></body></html>"""


async def health(request):
    return web.Response(text="ok")


async def verify_page(request):
    return web.Response(text=VERIFY_HTML, content_type="text/html")


async def api_verify(request):
    try:
        d = await request.json()
    except Exception:
        return web.json_response({"ok": False, "msg": "Bad request"}, status=400)
    user = check_init_data(d.get("initData", ""))
    if not user:
        return web.json_response({"ok": False, "msg": "Session invalid. Bot se dobara kholo."}, status=403)
    gmail = str(d.get("gmail", "")).strip().lower()
    fp = str(d.get("fp", ""))
    if not re.fullmatch(r"[a-z0-9][a-z0-9.]{4,40}@gmail\.com", gmail):
        return web.json_response({"ok": False, "msg": "Sahi Gmail daalo (@gmail.com)"})
    if not re.fullmatch(r"[a-f0-9]{64}", fp):
        return web.json_response({"ok": False, "msg": "Device check fail hua"})
    u = await db.get_user(user["id"])
    if not u:
        return web.json_response({"ok": False, "msg": "Pehle bot me /start karo"})
    if u["device_ok"]:
        return web.json_response({"ok": True, "msg": "✅ Already verified"})
    try:
        await db.pool.execute("UPDATE users SET gmail=$1, device_hash=$2, device_ok=TRUE WHERE id=$3",
                              gmail, fp, user["id"])
    except asyncpg.UniqueViolationError:
        return web.json_response({"ok": False, "msg": "❌ Ye device ya Gmail kisi aur account se linked hai"})
    try:
        await request.app["bot"].send_message(user["id"], "✅ Device verified! Ab tasks aur withdraw use kar sakte ho.")
    except Exception:
        pass
    return web.json_response({"ok": True, "msg": "✅ Verified!"})


async def gateway_hook(request):
    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")
    parsed = gateway.parse_webhook(request.headers, body)
    if not parsed:
        return web.Response(status=403, text="bad signature")
    order_id, paid, amount = parsed
    if not paid or not order_id:
        return web.Response(text="ignored")
    o = await db.complete_order(order_id, amount)
    if o:
        try:
            if o["kind"] == "deposit":
                msg = f"✅ <b>Deposit successful!</b>\n+{o['coins']} coins ad balance me add ho gaye."
            else:
                msg = f"✅ <b>Premium activated!</b> {config.PREMIUM_DAYS} din ke liye."
            await request.app["bot"].send_message(o["user_id"], msg, parse_mode="HTML")
        except Exception:
            log.exception("notify failed")
    return web.Response(text="ok")


def make_web(ptb_app):
    app = web.Application()
    app["bot"] = ptb_app.bot
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_get("/verify", verify_page)
    app.router.add_post("/api/verify", api_verify)
    app.router.add_post("/webhook/gateway", gateway_hook)
    return app
