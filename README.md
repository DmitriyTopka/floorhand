# Floorhand

A shop assistant answers the shop's Telegram customers from Even Realities G2 glasses, while their hands are busy with someone in front of them. The glasses show the customer's question and a reply built from the shop's own catalog, with the price and stock in it. One tap sends it. If the catalog does not back the answer, there is no send button: the seller says one sentence ("say we deliver Thursday") and the reply is rewritten.

Built for **Heads Up: Even Realities Hackathon** (DoraHacks, 23-29 Nov 2026). Tracks: **01 Messaging & News (Telegram)** and **04 AI Assistants (Claude)**, joined in one flow: a Telegram question goes in, Claude drafts from the catalog, the reply goes back to Telegram.

Demo video: *(link added on submission day)*

![Card on the glasses: question, catalog reply, tap to send](docs/evidence/2411_voice_edit_monday.png)

## The moment it is for

TechnoTochka (tt.ua) sells home appliances in five Ukrainian cities and already runs a Telegram bot. We read eight days of its logs (13-20 Nov 2026, `eval/PAIN_STATS.md`):

- 267 conversations, **37% ended with the bot calling a human**;
- after that, the customer waited **102 minutes for the first reply (median)**, 13.5 hours at the 75th percentile;
- 30 of 66 hand-offs got no reply in the chat at all.

The people who know the answers are on the shop floor, helping the customer in front of them. Taking out a phone to type means turning away from that customer. Floorhand puts the waiting question in the corner of their eye with an answer half-ready.

## How it works

1. A customer writes to the shop's Telegram bot. The first time, the bot asks whether AI may draft replies (**OK, AI may draft** / **Human only**). `/forget` deletes everything we keep about them.
2. The server finds the product (code, link or name) in the catalog and asks Claude for three short replies, using only the catalog facts and the shop's public policy (delivery, payment, warranty).
3. The glasses show: who is waiting and for how long, the question, reply 1 of 3, and where the facts came from (`from catalog 210455`).
4. Gestures:
   - **tap**: send the reply to the customer in Telegram (or hand the question off, if the reply is NOT SURE);
   - **swipe**: next reply;
   - **hold**: talk, release to rewrite all three replies with what you said;
   - **double tap**: exit.
5. Safety on every draft, whatever wrote it: a price that is not the catalog price takes the send button away, and with no matching product nothing can be sent from the glasses.

## Try it yourself in 2 minutes

You need Telegram and Node.js 18+. The demo server and bot are live until prizes are paid (about 10 Dec 2026).

1. Start the glasses simulator on our server:
   ```bash
   npx @evenrealities/evenhub-simulator@0.9.5 https://2-27-41-223.sslip.io
   ```
2. The glasses show a 6-digit code. In Telegram, open **[@evenrelist_bot](https://t.me/evenrelist_bot)** ("Floorhand demo shop") and send `/pair 123456` with your code.
3. In the same chat, ask about a product as a customer would, for example:
   `Is the Samsung RB38C679ES9 fridge in stock?` or `Hi! LG F2R5FG6J washer-dryer, when can you deliver to Odesa?`
   Press **OK, AI may draft** the first time.
4. In 3 to 5 seconds the card appears on the glasses. Click in the simulator to send, scroll to switch replies. The reply arrives in your Telegram chat.

Every visitor sees only the questions they sent themselves, so you will not see other judges' messages. The catalog is 50 real tt.ua products (fetched 23 Nov); ask about anything else and you will see the NOT SURE path.

## Does it work on real questions?

We took 30 real customer questions where the shop's current bot gave up and called a manager, with the answer the manager actually wrote (names and phones removed), and ran them through the same code the server uses. Full table and method: [`eval/RESULTS.md`](eval/RESULTS.md).

| | Catalog only | Catalog + shop policy |
|---|---|---|
| Drafts with a wrong price or wrong stock | 0 of 90 | 0 of 90 |
| Questions with a send button (fully backed) | 2 of 30 | 4 of 30 |
| Drafts that carry a shop rule (pickup, courier, carrier fee, warranty type, installments) | 0 of 30 | 12 of 30 |
| Time to three drafts, median | 2.6 s | 2.6 s |
| Claude cost for all 30 | 0.15 USD | 0.26 USD |

This set is the hard tail on purpose: the easy questions never reached a person. The managers answered with things no catalog holds ("to Odesa on Monday", "won't fit your branch, it is 203 cm"). Floorhand never made those up; it gave the seller the price and stock in under 3 seconds and left the rest to them, which is what the voice edit is for.

Voice edit, checked live on 24 Nov with the simulator and a real microphone: a 6.3 s phrase, transcribed on our server in 3.75 s, three new drafts from Claude in 3.6 s.

## Safety and privacy

- **Consent first.** No customer text reaches Claude without an explicit tap on "OK, AI may draft". "Human only" customers get template drafts built from the catalog, no AI. `/forget` deletes consent and messages. This follows Telegram's Bot Platform Developer Terms, 4.3: user-submitted data may be used with clear notice and explicit, revocable consent.
- **No invented prices.** Every UAH amount in a draft must be the catalog price, the crossed-out price (only after "was" or "old"), or an amount from the shop policy next to its own wording. Anything else takes the send button away. Tests: `server/tests/test_core.py`.
- **Customer text cannot pose as staff.** Customer messages reach Claude only as JSON string values; the seller's spoken words go into the system prompt, and only the voice endpoint, behind a paired device key, can put them there.
- **Keys stay on the server.** The glasses app holds no Telegram token and no Claude key. Glasses authenticate with a random 128-bit device key, paired through a 6-digit code that works for 10 minutes and is rate limited.
- **Voice stays with the shop.** Speech is transcribed on our own server (faster-whisper), audio is not stored and not sent to third parties.
- More than ten rounds of automated security review during the week, each finding fixed or reasoned about: [`SECURITY_NOTES.md`](SECURITY_NOTES.md).

## Even Hub SDK: what we used

- `createStartUpPageContainer` with four text containers (header, question, reply, footer) laid out for the 576 x 288 display; `textContainerUpgrade` repaints only the block that changed.
- `onEvenHubEvent` for all five gestures: click, double click, scroll up and down, long press and release.
- `audioControl` and `audioEvent.audioPcm` for push-to-talk: 16 kHz PCM from the G2 microphone, sent to our server only while the seller holds.
- `shutDownPageContainer` on double tap; `FOREGROUND_ENTER_EVENT` to refresh when the app comes back.
- `app.json` declares only `g2-microphone`. Packaged with `evenhub pack`.

What we missed in the SDK and in Telegram: [`FEATURE_REQUESTS.md`](FEATURE_REQUESTS.md).

## Architecture

```
Customer (Telegram)  ->  Telegram Bot API (long polling)
                              |
                     server/ (FastAPI, Python)
                     - consent, /forget, /pair
                     - catalog match (code, link, name)
                     - drafts: Claude (claude-sonnet-5-5) or catalog templates
                     - price guard, confidence gate
                     - speech to text (faster-whisper, on the server)
                              |  HTTPS, device key header
                     app/ (Vite + TypeScript + Even Hub SDK 0.0.16)
                              |
                     Even Realities G2 glasses
```

- `app/` glasses web app, started from the official `even-realities/evenhub-templates/asr` template.
- `server/` backend. `server/catalog/` holds the 50-product catalog and the shop policy sheet.
- `eval/` the 30-question evaluation, its scripts and results.

## Run your own copy

Server (Python 3.11+):
```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-stt.txt
cp .env.example .env   # add TELEGRAM_BOT_TOKEN and ANTHROPIC_API_KEY
.venv/bin/python main.py   # listens on 127.0.0.1:8790
.venv/bin/python -m pytest -q
```
Put it behind HTTPS (we use Caddy) and add the glasses app origin to `ALLOWED_ORIGINS`.

Glasses app:
```bash
cd app
npm install
VITE_API_BASE=https://your-server npm run build   # or npm run dev for local work
npm run simulate
npm run pack   # builds the .ehpk
```

Without a Claude key, set `DRAFTS=template`: replies are built from the catalog only.

## What existed before Nov 23

Only a written plan (problem, scope, judging map). No code, no repository. This repository was created on 23 Nov 2026 after kickoff, and every commit is from build week. Third-party code we started from: `even-realities/evenhub-templates/asr` (official Even Hub template), copied into `app/` on 23 Nov. The evaluation set was built from anonymized TechnoTochka bot logs during the week, with the shop's permission.

## AI tools used

- **Claude (claude-sonnet-5-5)** is part of the product: it writes the three reply drafts.
- **Claude Code** was the coding assistant during the week: code, tests, security reviews and this README were written with it, and checked by running them.
- **faster-whisper** (open model, runs on our server) for speech to text.

## Known limits

- Tested in the official simulator with a real microphone, not on physical G2 glasses (we don't have a pair).
- Handing off marks the question as taken by staff; the customer is not told yet.
- The demo shop speaks English. Real customers wrote in Ukrainian and Russian; drafts follow the customer's language, the voice edit is set to English.
- In the simulator the app can pause after a long press while its window is in the background; any gesture wakes it.
- The catalog is a 50-product snapshot, not a live feed. A real shop would connect its stock system.

## Judging criteria map

| Criterion | Where to look |
|---|---|
| Usefulness on G2 (30%) | The moment above; the card shows who waits and for how long, one glance |
| Read and write (25%) | Tap sends a catalog-backed reply; hold and say one sentence to rewrite; no long dictation |
| Technical (20%) | Live end to end on Telegram; 17 tests; eval on 30 real questions |
| Display and voice UX (15%) | Four text blocks for 576 x 288, source of facts on screen, NOT SURE label, push-to-talk |
| Business and safety (10%) | Real shop data and pain numbers; consent, /forget, price guard, keys on the server |
