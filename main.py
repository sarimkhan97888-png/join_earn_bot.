import asyncio
import logging

from aiohttp import web
from telegram.ext import Application

import bot
import config
import db
from webapp import make_web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


async def main():
    await db.init()
    app = Application.builder().token(config.BOT_TOKEN).build()
    bot.register(app)

    runner = web.AppRunner(make_web(app))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.PORT).start()

    await app.initialize()
    await app.start()
    await app.updater.start_polling(
        allowed_updates=["message", "callback_query", "chat_member"], drop_pending_updates=True)
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
