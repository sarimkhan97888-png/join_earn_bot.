# Join & Earn: Telegram Mini App

Bot sirf `/start` par "Open App" button deta hai. Poori UI Mini App (`index.html`) me hai: Home, Tasks, Wallet, Profile,
Premium Studio, popups, QR payment. Backend `api.py` me hai.

## Files (sab GitHub repo ke root me, kisi folder me nahi)
main.py, bot.py, botwork.py, api.py, webapp.py, db.py, gateway.py, util.py, config.py, index.html,
requirements.txt, render.yaml, README.md, .gitignore, .env.example

## Deploy (GitHub + Render)
1. Saari files GitHub repo (Private) me upload karo.
2. Render par PostgreSQL banao (free 30 din me expire hota hai; asli use ke liye paid ya Neon) -> Internal Database URL copy karo.
3. Render par Web Service: Build `pip install -r requirements.txt`, Start `python main.py`, Health check `/health`.
   Free web service so jati hai, Starter plan lo.
4. Environment: BOT_TOKEN, DATABASE_URL, BASE_URL (Render ka URL, bina `/`), ADMIN_IDS, SUPPORT_URL, GATEWAY_URL,
   GATEWAY_KEY, GATEWAY_SECRET, AUTO_PAYOUT=0, PYTHON_VERSION=3.11.9
5. Gateway dashboard me webhook: `https://<BASE_URL>/webhook/gateway`
6. Bot me `/start` bhejo -> "Open App" dabao. Menu button bhi apne aap set ho jata hai.

## Gateway API jodna
`gateway.py` me 3 functions hain (`create_order`, `parse_webhook`, `payout`). Apni gateway ke docs ke hisaab se badlo.
Deposit/Premium sirf webhook se credit hota hai.

## Rules (config.py me badal sakte ho)
- 100 coins = Rs 1, join reward 100, hold 24h, channel leave -> coins cut + block, rejoin -> unblock
- Premium Rs 49/month: channel task (min 10 members, 110 coins per member) aur Bot Work (min reward 220)
- Min deposit 10,000 coins, min withdraw 1,000 coins, withdraw admin approve par
- Bot Work: worker screenshot + refer link bhejta hai, owner ko Telegram me Done/Reject milta hai,
  reject par Report -> admin. Owner 48h me review na kare to case admin ke paas.
- Task wale channel me bot ko Admin banana zaroori hai.
