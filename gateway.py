"""Elite Pay adapter (https://elitepay.co.in/api/public/v1).

Auth: headers X-Api-Key + X-Api-Secret. Key/token URL me nahi daalte (logs me leak na ho).
Env: GATEWAY_URL, GATEWAY_KEY (ep_live_...), GATEWAY_SECRET (eps_live_... token).

Deposit safety: kisi bhi webhook ya client par bharosa nahi. Coins tabhi milte hain jab
check_payment() (gateway ka authenticated status API) payment ko 'paid' bataye.
"""
import logging
from decimal import Decimal, InvalidOperation

import httpx

import config

log = logging.getLogger("gateway")

PAID = {"paid", "success", "succeeded", "successful", "completed", "complete", "credited", "confirmed"}
FAILED = {"failed", "expired", "cancelled", "canceled", "rejected", "declined", "refunded"}


def _headers():
    return {"X-Api-Key": config.GATEWAY_KEY, "X-Api-Secret": config.GATEWAY_SECRET}


def _first(d, keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", False):
            return v
    return None


def _flat(raw):
    """Response ke nested data/payment/result dict aur top-level fields ko ek dict me milao (nested pehle)."""
    out = {}
    if isinstance(raw, dict):
        for k in ("data", "payment", "result"):
            if isinstance(raw.get(k), dict):
                out.update(raw[k])
        for k, v in raw.items():
            if not isinstance(v, (dict, list)):
                out.setdefault(k, v)
    return out


def interpret_create(raw):
    """Create-payment response se ref / qr_url / upi_url / pay_url nikalo (alag naam handle karta hai)."""
    d = _flat(raw)
    ref = _first(d, ("paymentId", "payment_id", "id", "txId", "tx_id", "transactionId", "transaction_id",
                     "orderId", "order_id"))
    qr = _first(d, ("qrUrl", "qr_url", "qrImage", "qr_image", "qrCode", "qr_code", "qr"))
    upi = _first(d, ("upiUrl", "upi_url", "upiLink", "upi_link", "upiIntent", "upi_intent", "upi"))
    pay = _first(d, ("paymentUrl", "payment_url", "payUrl", "pay_url", "checkoutUrl", "checkout_url",
                     "paymentLink", "payment_link", "url", "link"))
    qr, upi, pay = (str(x) if x else None for x in (qr, upi, pay))
    if qr and qr.lower().startswith("upi:"):
        upi, qr = upi or qr, None
    if pay and pay.lower().startswith("upi:"):
        upi, pay = upi or pay, None
    if upi and upi.lower().startswith("http"):
        pay, upi = pay or upi, None
    if qr and not qr.lower().startswith(("http", "data:")):
        qr = "data:image/png;base64," + qr if len(qr) > 100 else None
    return {"ref": str(ref) if ref else None, "qr_url": qr, "upi_url": upi, "pay_url": pay}


def interpret_status(raw):
    """Return (state, amount). state: paid / failed / pending / unknown"""
    d = _flat(raw)
    st = str(_first(d, ("paymentStatus", "payment_status", "status", "state")) or "").strip().lower()
    amt = _first(d, ("paidAmount", "paid_amount", "amountPaid", "receivedAmount", "amount"))
    try:
        amt = Decimal(str(amt)) if amt is not None else None
    except InvalidOperation:
        amt = None
    if st in PAID:
        return "paid", amt
    if st in FAILED:
        return "failed", amt
    return ("pending" if st else "unknown"), amt


async def _get(path, **params):
    async with httpx.AsyncClient(timeout=25) as cl:
        r = await cl.get(f"{config.GATEWAY_URL}{path}", headers=_headers(), params=params)
    if r.status_code >= 400:
        log.error("gateway %s -> %s %s", path, r.status_code, r.text[:200])
        r.raise_for_status()
    return r.json()


async def create_order(order_id: str, amount_inr: int, note: str) -> dict:
    """Payment banao. order_id description me jata hai (webhook se match karne ke liye)."""
    raw = await _get("/payments", amount=amount_inr, currency="INR", description=str(order_id)[:120])
    out = interpret_create(raw)
    out["raw"] = raw
    return out


async def check_payment(ref: str):
    """Return (state, amount, raw). Authenticated status API se asli sach."""
    raw = await _get(f"/payments/{ref}")
    state, amt = interpret_status(raw)
    return state, amt, raw


async def get_balance():
    return await _get("/balance")


def parse_webhook(headers, body):
    """Webhook sirf trigger hai: (order_id, gateway_ref) nikalo. Verification check_payment() se hoti hai."""
    d = _flat(body) if isinstance(body, dict) else {}
    ref = _first(d, ("payoutId", "payout_id", "paymentId", "payment_id", "id", "txId", "tx_id"))
    desc = _first(d, ("description", "reference", "order_id", "orderId", "comment"))
    return (str(desc).strip() if desc else None), (str(ref) if ref else None)


async def check_payout(ref: str):
    """Return (state, raw) — payout ka asli status Elite Pay se."""
    raw = await _get(f"/payouts/{ref}")
    state, _ = interpret_status(raw)
    return state, raw


async def payout(upi: str, amount_inr, ref: str) -> dict:
    """UPI payout. Return dict: ok, ref(payoutId), receive, error, definite.
    definite=True matlab request reject hui / bheji hi nahi gayi (paisa nahi kata). definite=False matlab
    pata nahi (timeout / 5xx): is case me dobara try NAHI karna, admin check karega (double payment se bachne ke liye)."""
    params = {"upiId": upi, "amount": f"{Decimal(str(amount_inr)):.2f}", "reference": str(ref)[:40],
              "comment": "Withdraw"}
    try:
        async with httpx.AsyncClient(timeout=30) as cl:
            r = await cl.post(f"{config.GATEWAY_URL}/payouts/upi", params=params,
                              headers={**_headers(), "Idempotency-Key": str(ref)[:64]})
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return {"ok": False, "definite": True, "error": "gateway_unreachable"}
    except httpx.HTTPError as e:
        return {"ok": False, "definite": False, "error": type(e).__name__}
    try:
        j = r.json()
        j = j if isinstance(j, dict) else {}
    except Exception:
        j = {}
    if r.status_code in (200, 201, 202) and j.get("success") is not False:
        pid = _first(_flat(j), ("payoutId", "payout_id", "id"))
        if not pid:
            return {"ok": False, "definite": False, "error": "no_payout_id"}
        try:
            recv = float(_first(_flat(j), ("receiveAmount", "receive_amount")) or 0)
        except (TypeError, ValueError):
            recv = 0.0
        return {"ok": True, "ref": str(pid), "receive": recv}
    err = str(j.get("error") or j.get("message") or f"http_{r.status_code}")[:120]
    return {"ok": False, "definite": 400 <= r.status_code < 500, "error": err}
