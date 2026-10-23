import hashlib
import html
import logging
import os
import time

from aiohttp import web

import api
import config
import db

log = logging.getLogger("web")
INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


async def health(request):
    return web.Response(text="ok")


def load_index():
    """index.html ek baar memory me (har open par disk read nahi), app ka naam andar daal ke."""
    with open(INDEX, encoding="utf-8") as f:
        return f.read().replace("__APP_NAME__", html.escape(config.APP_NAME)).encode("utf-8")


FRAME = "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org"


@web.middleware
async def sec_mw(request, handler):
    """Security headers har response par; API response kabhi cache nahi hoti."""
    try:
        resp = await handler(request)
    except web.HTTPException as e:
        resp = e
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


async def app_page(request):
    body = request.app["index"]
    etag = request.app["index_etag"]
    hdr = {"ETag": etag, "Cache-Control": "no-cache", "Content-Security-Policy": FRAME}
    if request.headers.get("If-None-Match") == etag:  # 304: dobara download nahi, app jaldi khulta hai
        return web.Response(status=304, headers=hdr)
    resp = web.Response(body=body, content_type="text/html", charset="utf-8", headers=hdr)
    resp.enable_compression()
    return resp


def make_web(ptb_app):
    app = web.Application(middlewares=[sec_mw, api.auth_mw], client_max_size=8 * 1024 * 1024)
    app["bot"] = ptb_app.bot
    app["index"] = load_index()
    app["index_etag"] = '"' + hashlib.sha256(app["index"]).hexdigest()[:20] + '"'
    app.add_routes(api.routes)
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_get("/app", app_page)
    app.router.add_get("/verify", app_page)  # device verification page (Mini App), same page verify mode me
    return app
