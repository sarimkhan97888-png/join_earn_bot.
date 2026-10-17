import logging
import os

from aiohttp import web

import api
import db
import gateway
import payments

log = logging.getLogger("web")
INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


async def health(request):
    return web.Response(text="ok")


async def app_page(request):
    return web.FileResponse(INDEX, headers={"Cache-Control": "no-cache"})


async def gateway_hook(request):
    """Webhook sirf trigger hai. Payload par bharosa nahi: order dhoondh ke gateway ke status API se verify karte hain."""
    try:
        data = await request.json()
    except Exception:
        try:
            data = dict(await request.post())
        except Exception:
            data = {}
    order_id, ref = gateway.parse_webhook(request.headers, data)
    o = await db.order_lookup(ref, order_id)
    if o:
        await payments.settle(request.app["bot"], o)
    return web.Response(text="ok")


def make_web(ptb_app):
    app = web.Application(middlewares=[api.auth_mw], client_max_size=8 * 1024 * 1024)
    app["bot"] = ptb_app.bot
    app.add_routes(api.routes)
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_get("/app", app_page)
    app.router.add_get("/webhook/gateway", health)  # kuch gateways URL check GET se karte hain
    app.router.add_post("/webhook/gateway", gateway_hook)
    return app
