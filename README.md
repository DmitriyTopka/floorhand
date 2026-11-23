# Floorhand

Answer your shop's Telegram customers from Even Realities G2 glasses with one tap, while your hands are busy.

Built for **Heads Up: Even Realities Hackathon** (DoraHacks, 23-29 Nov 2026), Track 01 Messaging & News.

> Status: build week in progress. This README grows with the code.

## What existed before Nov 23

Only a written plan (problem, scope, judging map). No code, no repository. This repository was created on 23 Nov 2026 after kickoff, and every commit is from build week. Third-party code we start from:

- `even-realities/evenhub-templates/asr` (official Even Hub template), copied into `app/` on 23 Nov as the starting point for the glasses app.

## Repository layout

- `app/` glasses web app (Vite + TypeScript + Even Hub SDK)
- `server/` backend: Telegram bot webhook, catalog lookup, drafts, speech-to-text (added during the week)
- `FEATURE_REQUESTS.md` what the APIs we used were missing
