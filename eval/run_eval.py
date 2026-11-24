"""Run the 30 real shop questions through the same draft code the server uses.

For every question it records: which catalog product was matched, the three
drafts, whether the glasses would show a send button, the price check, a stock
check, seconds per question and the Claude tokens spent.

Usage (from floorhand/):
    server/.venv/bin/python eval/run_eval.py --dry-run     # template drafts, no API calls
    server/.venv/bin/python eval/run_eval.py               # Claude drafts, stops at --max-usd

The questions are the English versions (customers wrote in Ukrainian or
Russian; translations are in questions.json next to the originals).
Prices: the catalog was fetched on 23.11, the manager answers are from 03-20.11,
so a manager price can differ from today's catalog price. Drafts are checked
against the catalog, the manager answer is kept as the human reference.
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("CATALOG_PATH", str(ROOT / "server" / "catalog" / "catalog.json"))

# USD per million tokens, input and output. An assumption, printed in the report.
PRICE_IN = float(os.environ.get("EVAL_PRICE_IN", "3"))
PRICE_OUT = float(os.environ.get("EVAL_PRICE_OUT", "15"))

_IN_STOCK = re.compile(r"\b(in stock|available now|we have it|have it in stock)\b", re.I)
_OUT_STOCK = re.compile(r"\b(out of stock|not in stock|sold out|not available)\b", re.I)


def stock_ok(text: str, status: str) -> bool:
    """A draft must not say 'in stock' for an out-of-stock item or the reverse."""
    out = "out of stock" in status.lower()
    if out and _IN_STOCK.search(text) and not _OUT_STOCK.search(text):
        return False
    if not out and _OUT_STOCK.search(text) and not _IN_STOCK.search(text):
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="template drafts, no Claude calls")
    ap.add_argument("--max-usd", type=float, default=0.45, help="stop before going over this")
    ap.add_argument("--out", default=str(ROOT / "eval" / "results.json"))
    args = ap.parse_args()
    if args.dry_run:
        os.environ["DRAFTS"] = "template"

    from floorhand import config, drafts
    from floorhand.catalog import Catalog

    if not args.dry_run and not config.llm_enabled():
        print("no Claude key or DRAFTS != llm; use --dry-run", file=sys.stderr)
        return 2

    usage = {"in": 0, "out": 0, "calls": 0}
    if not args.dry_run:
        import anthropic.resources.messages as m

        orig = m.Messages.create

        def counted(self, *a, **kw):
            resp = orig(self, *a, **kw)
            usage["in"] += resp.usage.input_tokens
            usage["out"] += resp.usage.output_tokens
            usage["calls"] += 1
            return resp

        m.Messages.create = counted

    def spent() -> float:
        return usage["in"] * PRICE_IN / 1e6 + usage["out"] * PRICE_OUT / 1e6

    catalog = Catalog.load(config.CATALOG_PATH)
    questions = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))
    rows = []
    for q in questions:
        if spent() > args.max_usd:
            print(f"stopped at {q['id']}: spent ~{spent():.3f} USD > {args.max_usd}", file=sys.stderr)
            break
        product, score = catalog.match(q["question_en"])
        t0 = time.time()
        out, mode = drafts.make_drafts(q["question_en"], product, [], use_ai=not args.dry_run)
        secs = round(time.time() - t0, 2)
        status = product.stock_status if product else ""
        rows.append({
            "id": q["id"], "type": q["question_type"], "question_en": q["question_en"],
            "manager_answer_en": q["manager_answer_en"], "manager_minutes": q["manager_minutes"],
            "want_code": q["product_code"], "got_code": product.code if product else None,
            "match_score": round(score, 2), "catalog_price": product.price_uah if product else None,
            "catalog_stock": status, "mode": mode, "seconds": secs, "drafts": out,
            "send_button": out[0]["confident"] if out else False,
            "price_ok": all(drafts._price_ok(d["text"], product) for d in out),
            "stock_ok": all(stock_ok(d["text"], status) for d in out) if product else True,
        })
        print(f"{q['id']} {mode} {secs}s match={rows[-1]['got_code'] == q['product_code']} "
              f"send={rows[-1]['send_button']} ~{spent():.3f}$", flush=True)

    report = {
        "model": config.CLAUDE_MODEL if not args.dry_run else "template",
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "price_assumption_usd_per_mtok": [PRICE_IN, PRICE_OUT],
        "usage": usage, "usd_estimate": round(spent(), 4), "rows": rows,
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(rows)
    if n:
        print(f"\n{n} questions, product match {sum(r['got_code'] == r['want_code'] for r in rows)}/{n}, "
              f"send button {sum(r['send_button'] for r in rows)}/{n}, price ok {sum(r['price_ok'] for r in rows)}/{n}, "
              f"stock ok {sum(r['stock_ok'] for r in rows)}/{n}, median {statistics.median(r['seconds'] for r in rows)} s, "
              f"tokens {usage['in']}+{usage['out']}, ~{spent():.3f} USD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
