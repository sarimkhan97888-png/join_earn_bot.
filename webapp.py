import html
import logging
import os

from aiohttp import web

import api
import config
import db
import gateway
import payments
import payouts

log = logging.getLogger("web")
INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


async def health(request):
    return web.Response(text="ok")


def load_index():
    """index.html ek baar memory me (har open par disk read nahi), app ka naam andar daal ke."""
    with open(INDEX, encoding="utf-8") as f:
        return f.read().replace("__APP_NAME__", html.escape(config.APP_NAME)).encode("utf-8")


async def app_page(request):
    return web.Response(body=request.app["index"], content_type="text/html", charset="utf-8",
                        headers={"Cache-Control": "no-cache"})


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
    if ref or order_id:
        o = await db.order_lookup(ref, order_id)
        if o:
            await payments.settle(request.app["bot"], o, min_gap=5)
        else:
            w = await db.wd_lookup(ref, order_id)
            if w:
                await payouts.settle(request.app["bot"], w, min_gap=5)
    return web.Response(text="ok")


def make_web(ptb_app):
    app = web.Application(middlewares=[api.auth_mw], client_max_size=8 * 1024 * 1024)
    app["bot"] = ptb_app.bot
    app["index"] = load_index()
    app.add_routes(api.routes)
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_get("/app", app_page)
    app.router.add_get("/webhook/gateway", health)  # kuch gateways URL check GET se karte hain
    app.router.add_post("/webhook/gateway", gateway_hook)
    return app
