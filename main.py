import asyncio
import logging

from aiohttp import web
from telegram.ext import Application

import bot
import config
import db
import extras
from webapp import make_web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
# httpx har request ka poora URL INFO me log karta hai (bot token / gateway key leak ho sakti hai). Band karo.
for _n in ("httpx", "httpcore"):
    logging.getLogger(_n).setLevel(logging.WARNING)


async def main():
    await db.init()
    try:
        import time
        t = time.monotonic()
        await db.pool.fetchval('SELECT 1')
        logging.getLogger('main').info('DB ping %.0f ms (30 se kam best, 100+ = DB door hai)', (time.monotonic() - t) * 1000)
    except Exception:
        pass
    app = (Application.builder().token(config.BOT_TOKEN).concurrent_updates(32)
           .connection_pool_size(64).pool_timeout(10).connect_timeout(10).read_timeout(15).write_timeout(15)
           .get_updates_connection_pool_size(2).get_updates_read_timeout(30).build())
    bot.register(app)

    await app.initialize()
    await bot.post_init(app)

    runner = web.AppRunner(make_web(app))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.PORT).start()

    # Backup bot: withdraw Approve/Reject ke button callbacks yahi receive karta hai
    bk = None
    if config.BACKUP_BOT_TOKEN:
        try:
            bk = Application.builder().token(config.BACKUP_BOT_TOKEN).concurrent_updates(8).build()
            bot.register_backup(bk)
            await bk.initialize()
            extras._bk["bot"] = bk.bot
        except Exception:
            logging.getLogger("main").exception("backup bot start nahi hua (token galat?)")
            bk = None

    await app.start()
    if bk:
        await bk.start()
        await bk.updater.start_polling(allowed_updates=["message", "callback_query"], drop_pending_updates=True)
    await app.updater.start_polling(
        allowed_updates=["message", "callback_query", "chat_member", "pre_checkout_query"], drop_pending_updates=False)  # deploy ke beech ke join/leave events na khoyen
    try:
        await asyncio.Event().wait()
    finally:
        if bk:
            await bk.updater.stop()
            await bk.stop()
            await bk.shutdown()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
