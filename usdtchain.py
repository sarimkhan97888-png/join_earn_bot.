"""USDT (BEP20) deposits: user tumhare wallet par unique amount bhejta hai, bot blockchain (BSC RPC) scan karke match karta hai.
Koi payment gateway / API key nahi. Sirf USDT_WALLET env chahiye."""
import asyncio
import html
import json
import logging
from decimal import Decimal

import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config
import db
import extras
import payments
import util

log = logging.getLogger("usdtchain")
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
CHUNK = 2000          # ek getLogs me itne blocks (BSC ~3s/block)
POLL = 15
_sess = None
_rpc_i = [0]


def enabled():
    return config.USDT_ON


def _session():
    global _sess
    if _sess is None or _sess.closed:
        _sess = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
    return _sess


async def rpc(method, params):
    """Public BSC nodes me se chalta hua use karo; ek fail ho to agla."""
    last = None
    n = len(config.USDT_RPCS)
    for k in range(n):
        url = config.USDT_RPCS[(_rpc_i[0] + k) % n]
        try:
            async with _session().post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}) as r:
                d = json.loads(await r.text())
            if "error" in d:
                raise RuntimeError(str(d["error"])[:150])
            _rpc_i[0] = (_rpc_i[0] + k) % n
            return d["result"]
        except Exception as e:
            last = e
    raise RuntimeError(f"all rpc failed: {last}")


def _topic_addr(a):
    return "0x" + "0" * 24 + a.lower()[2:]


async def get_logs(frm, to):
    res = await rpc("eth_getLogs", [{"fromBlock": hex(frm), "toBlock": hex(to), "address": config.USDT_CONTRACT,
                                     "topics": [TRANSFER, None, _topic_addr(config.USDT_WALLET)]}])
    out = []
    for l in res:
        amt = (Decimal(int(l["data"], 16)) / Decimal(10 ** 18)).quantize(Decimal("0.000001"))
        out.append((l["transactionHash"], int(l["logIndex"], 16), amt, "0x" + l["topics"][1][-40:], int(l["blockNumber"], 16)))
    return out


async def _admins(bot, text, kb=None):
    for a in config.ADMIN_IDS:
        await util.notify(bot, a, text, **({"reply_markup": kb} if kb else {}))


async def handle(bot, tx, idx, amt, sender, block):
    r = await db.usdt_process(tx, idx, amt, sender, block)
    if not r:
        return
    if r["done"]:
        d = r["done"]
        extras.feed(f"💵 USDT payment ✅ {amt} USDT — user <code>{d['user_id']}</code> ({d['kind']}) tx <code>{tx}</code>")
        await util.notify(bot, d["user_id"], payments.paid_msg(d))
    elif amt >= config.USDT_MIN:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🙈 Ignore (mera paisa)", callback_data=f"uign:{tx[:56]}")]])
        await _admins(bot, f"❓ <b>Unmatched USDT</b> {amt} USDT\nFrom: <code>{sender}</code>\nTx: <code>{tx}</code>\n\n"
                           f"Kisi user ka deposit hai to <code>/uassign {tx} USER_ID</code> (coins rate se mil jayenge). "
                           f"Tumhara apna paisa hai to Ignore dabao.", kb)


async def scan_once(bot):
    latest = int(await rpc("eth_blockNumber", []), 16) - config.USDT_CONFIRMS
    last = await db.usdt_meta_get("usdt_block")
    start = int(last) + 1 if last else latest - 300      # pehli baar: pichle ~15 min
    start = max(start, latest - 60000)                    # bahut purana nahi (RPC limit)
    for _ in range(6):
        if start > latest:
            return
        end = min(start + CHUNK - 1, latest)
        for tx, idx, amt, sender, block in await get_logs(start, end):
            await handle(bot, tx, idx, amt, sender, block)
        await db.usdt_meta_set("usdt_block", end)
        start = end + 1


async def run():
    fails = 0
    while True:
        try:
            if util.main_bot:
                await scan_once(util.main_bot)
            fails = 0
        except asyncio.CancelledError:
            raise
        except Exception as e:
            fails += 1
            log.warning("usdt scan fail %s: %s", fails, e)
            if fails == 20 and util.main_bot:  # ~5 min lagatar fail: admin ko ek baar batao
                try:
                    await _admins(util.main_bot, "⚠️ USDT blockchain scan fail ho raha hai (RPC). Deposits auto credit nahi ho rahe. "
                                                 "Env USDT_RPCS me aur RPC daal sakte ho.")
                except Exception:
                    pass
        await asyncio.sleep(POLL if not fails else min(POLL * (1 + fails), 120))
