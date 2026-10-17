# Join & Earn Telegram Bot

## Deploy (GitHub + Render)
1. Ye folder GitHub repo me push karo (`.env` push mat karna).
2. Render par **PostgreSQL** banao (Free/Starter) → Internal Database URL copy karo.
3. Render par **New → Web Service** → repo select. Build: `pip install -r requirements.txt`, Start: `python main.py`.
   - Free web service 15 min idle par so jati hai aur bot band ho jata hai. **Starter plan lo** ya UptimeRobot se `/health` ping karo.
4. Environment variables (`.env.example` dekho):
   - `BOT_TOKEN` (@BotFather), `DATABASE_URL`, `BASE_URL` (Render ka URL, bina `/` ke)
   - `ADMIN_IDS` = tumhari Telegram numeric ID (withdraw approve + reports yahin aayenge)
   - `GATEWAY_*` gateway ki details
5. BotFather me: `/setdomain` apna Render domain set karo (Mini App ke liye).
6. Gateway dashboard me webhook URL: `https://<BASE_URL>/webhook/gateway`

## Gateway API jodna
`gateway.py` me 3 functions hain (`create_order`, `parse_webhook`, `payout`). Apni gateway ki docs ke hisaab se
endpoint, auth header, response keys aur signature check wahi badalna hai. Baaki code ko chhuna nahi padega.
Deposit/Premium sirf webhook se credit hota hai (user ke click se nahi).

## Features
- Home / Tasks / Wallet / Profile (reply keyboard)
- Channel join task: 100 coin per join, 24h hold, leave karne par coin cut + block, rejoin par unblock
- Premium Rs 49/month: channel/group task upload (bot admin check), min 10 members, 110 coin per member
- Bot Work (Premium): poster reward set karta hai (min 220), worker screenshot + refer link bhejta hai,
  poster Done/Reject, reject par Report -> admin decide. Poster 48h me review na kare to case admin ke paas.
- Deposit min 10,000 coins (QR gateway se), withdraw min 1,000 coins (100 coin = Rs 1)
- Device verification (Mini App) + Gmail, ek device/Gmail/UPI = ek account
- Withdraw admin approve karne par hi hota hai (`AUTO_PAYOUT=1` karne par gateway se auto payout)

## Zaroori
- Task wale channel me bot ko **Admin** banana hoga (join detect `chat_member` event se hota hai).
- Coins ka ledger `ledger` table me hai, har coin movement ki entry.
