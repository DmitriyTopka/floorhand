# Eval: 30 real questions a shop bot could not answer

Run on 24.11.2026 on the demo server, same code path as live (`make_drafts` in `server/floorhand/drafts.py`), model `claude-sonnet-5-5`, no conversation history, English versions of the questions.
Reproduce: `server/.venv/bin/python eval/run_eval.py` (or `--dry-run` for template drafts, no API calls). Two runs: without and with a shop-policy sheet (`server/catalog/shop_policy.md`, copied from the shop's public delivery, payment and warranty pages, not from the manager answers). Raw output: `eval/results.json` (run 1), `eval/results_policy.json` (run 2).

## Where the questions come from

Each one is a real customer message from TechnoTochka (tt.ua, an appliance shop in Ukraine), 03-20.11.2026, where the existing shop bot gave up and called a human manager. Names and phone numbers removed, each paired with the answer the manager actually wrote. So this set is the hard tail on purpose: the easy questions never reached a person.

Mix: 11 availability, 6 specs, 5 delivery, 4 price or installments, 3 comparison, 1 warranty.

## Numbers

| What | Run 1: catalog only | Run 2: catalog + shop policy |
|---|---|---|
| Product found in the 50-item catalog | 23 / 30 | 23 / 30 |
| Drafts with a price that is not the catalog, crossed-out or policy price | 0 / 90 | 0 / 90 with a product (1 question without a product repeated the customer's own prices; it already had no send button) |
| Drafts that contradict the catalog stock status | 0 / 90 | 0 / 90 |
| Questions with a send button on the glasses (Claude fully sure) | 2 / 30 | 4 / 30 |
| Questions where a draft gives a shop rule (pickup, courier, carrier fees, warranty type, installment banks, per-floor price), checked by hand | 0 / 30 | 12 / 30 |
| Time to three drafts, median / max | 2.6 s / 6.6 s | 2.6 s / 3.6 s |
| Claude usage for all 30 | 22 485 in + 5 531 out tokens, about 0.15 USD | 58 520 in + 5 704 out tokens, about 0.26 USD |

The product found count stays 23: the other 7 say "this one" with a photo or an earlier link we do not have.

For comparison, on these 30 the manager's answer came 5.4 min after the customer's message (median). Across all hand-offs that week the median wait was 102 min (`eval/PAIN_STATS.md`); the 30 here are the ones where a manager did answer in the chat, so they skew fast.

## What it means

The glasses never made a fact up. Where the catalog had the answer (price, stock, a spec) the draft used it; where the answer lives in a person's head (delivery date to a city, installment rules, warranty split, why two listings of one hob differ) every draft said a colleague will confirm, and the glasses showed no send button.

That is exactly the job of the seller on the floor: the glasses hand them the half that the shop data already knows in under 3 seconds, and they add the half only a person knows, with one sentence of voice ("say we deliver Thursday"), instead of typing the whole answer.

Run 2 adds the shop's public rules. The send button doubles (2 to 4), and 12 of 30 drafts now carry a real rule, for example "Odesa has free pickup or courier to your entrance, from 3 days. Courier price is on the product page. Need carrying upstairs? It's 100 UAH per floor for this model." (tt-q06, a washer-dryer). The rest still go to a person, and should: the site itself says a manager confirms exact dates per city, carrier size limits, and whether a promo price holds for a given number of payments. Those are the parts the seller adds with one sentence of voice.

## Honest limits

- Catalog prices were fetched 23.11, manager answers are from 03-20.11, so some prices and stock moved in between. Drafts are checked against the catalog, not against the old answer.
- Checks for price and stock are automatic (regex over the drafts); "would a manager send it" was not scored by a second model. The 12 / 30 rule count is a hand check of run 2 drafts.
- Two drafts (tt-q15 in run 2, tt-q26 in both runs) answered in Ukrainian to an English question, probably because the customer's own words or the catalog name are Ukrainian.
- While building this eval we found that the price guard misread "RB38C679ES9. 31 499 UAH" as 931 499 and took the send button away from a correct draft. Fixed before the run, test added (`test_price_check_does_not_glue_model_digits_to_price`).

## Run 3 (24 Nov): one spoken sentence from the seller

For the 26 questions that had no send button in run 2, we passed the fact the manager actually knew as the seller's voice instruction: the first sentence of the manager's real answer, at most 25 words (for example "For Nov 19-20." or "Available in Kyiv for tomorrow."). Same code path as hold-to-talk on the glasses. Script: `eval/run_voice_eval.py`, output: `eval/results_voice.json`.

| | Result |
|---|---|
| Got a send button after one sentence | 12 of 26 (16 of 30 with the 4 that were ready before) |
| Drafts with a wrong stock claim | 0 |
| Price check took the send button away | 4 of 26: the manager's price from early November no longer matched today's catalog, so the glasses would not let it go out |
| Time to three new drafts, median | 2.5 s |
| Claude cost | 0.25 USD |

Limits: the "spoken" sentence is the manager's written words, not a recording, so Whisper is not part of this run (live timing is in the README). A send button means the draft passed the checks and Claude marked it confident; nobody scored the wording. One example of a send-ready draft that a person would still polish: tt-q02, "The WETAIR WAD B 20 L is currently out of stock. For Saturday 07.11 in Kharkiv."
