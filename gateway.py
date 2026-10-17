"""
Payment gateway adapter.
Tumhari gateway ki API docs ke hisaab se NEECHE ke 3 functions adapt karne hain:
  create_order  -> QR / UPI link banana
  parse_webhook -> webhook payload se (order_id, paid, amount) nikalna + signature check
  payout        -> UPI payout (sirf AUTO_PAYOUT=1 ho tab use hota hai)
"""
import hmac

import httpx

import config


async def create_order(order_id: str, amount_inr: int, note: str) -> dict:
    """Return dict with any of: qr_url (image link), upi_url (upi://pay?...), pay_url (page link)."""
    async with httpx.AsyncClient(timeout=20) as cl:
        r = await cl.post(
            f"{config.GATEWAY_URL}/create-order",                     # TODO: apna endpoint
            headers={"Authorization": f"Bearer {config.GATEWAY_KEY}"},  # TODO: apna auth
            json={
                "order_id": order_id,
                "amount": amount_inr,
                "note": note,
                "webhook_url": f"{config.BASE_URL}/webhook/gateway",
            },
        )
        r.raise_for_status()
        d = r.json()
    # TODO: apni response keys ke naam yahan map karo
    return {"qr_url": d.get("qr_url"), "upi_url": d.get("upi_url"), "pay_url": d.get("payment_url")}


def parse_webhook(headers, body: dict):
    """Return (order_id, paid: bool, amount) ya None agar signature galat ho."""
    # TODO: gateway ke hisaab se signature verify karo. Abhi simple shared-secret header hai.
    if not hmac.compare_digest(headers.get("X-Webhook-Secret", ""), config.GATEWAY_SECRET):
        return None
    order_id = body.get("order_id")
    paid = str(body.get("status", "")).lower() in ("paid", "success", "completed", "credit")
    amount = body.get("amount")
    return order_id, paid, amount


async def payout(upi: str, amount_inr: int, ref: str) -> bool:
    async with httpx.AsyncClient(timeout=30) as cl:
        r = await cl.post(
            f"{config.GATEWAY_URL}/payout",                          # TODO
            headers={"Authorization": f"Bearer {config.GATEWAY_KEY}"},
            json={"upi": upi, "amount": amount_inr, "reference": ref},
        )
        return r.status_code == 200 and str(r.json().get("status", "")).lower() in ("success", "queued", "processing")
