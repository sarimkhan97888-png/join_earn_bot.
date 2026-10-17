import logging
import os

from aiohttp import web

import api
import config
import db
import gateway
import util

log = logging.getLogger("web")
INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


async def health(request):
    return web.Response(text="ok")


async def app_page(request):
    return web.FileResponse(INDEX, headers={"Cache-Control": "no-cache"})


async def gateway_hook(request):
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="bad json")
    parsed = gateway.parse_webhook(request.headers, data)
    if not parsed:
        return web.Response(status=403, text="bad signature")
    order_id, paid, amount = parsed
    if not paid or not order_id:
        return web.Response(text="ignored")
    o = await db.complete_order(order_id, amount)
    if o:
        if o["kind"] == "deposit":
            msg = f"✅ <b>Deposit successful!</b>\n+{o['coins']} coins ad balance me add ho gaye."
        else:
            msg = f"✅ <b>Premium activated!</b> {config.PREMIUM_DAYS} din ke liye."
        await util.notify(request.app["bot"], o["user_id"], msg)
    return web.Response(text="ok")


def make_web(ptb_app):
    app = web.Application(middlewares=[api.auth_mw], client_max_size=8 * 1024 * 1024)
    app["bot"] = ptb_app.bot
    app.add_routes(api.routes)
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_get("/app", app_page)
    app.router.add_post("/webhook/gateway", gateway_hook)
    return app
