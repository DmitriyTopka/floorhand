"""What one spoken sentence from the seller adds.

For every question where the plain run (results_policy.json) gave no send button,
we take the fact the manager actually knew (the first sentence of the manager's
real answer, at most 25 words) and pass it as the seller's voice instruction,
the same way the glasses' hold-to-talk does. Then we count how many replies
become ready to send, and keep the price and stock checks.

Honest limit: the "spoken" sentence is the manager's own written words, not a
recording; real speech goes through Whisper first (see README for its timing).

Usage (from floorhand/):  server/.venv/bin/python eval/run_voice_eval.py
"""
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "eval"))
os.environ.setdefault("CATALOG_PATH", str(ROOT / "server" / "catalog" / "catalog.json"))

from run_eval import PRICE_IN, PRICE_OUT, stock_ok  # noqa: E402

MAX_USD = float(os.environ.get("MAX_USD", "0.40"))


def seller_sentence(answer: str) -> str:
    first = re.split(r"(?<=[.!?])\s+", answer.strip())[0]
    words = first.split()
    return " ".join(words[:25])


def main() -> int:
    from floorhand import config, drafts
    from floorhand.catalog import Catalog
    import anthropic.resources.messages as m

    if not config.llm_enabled():
        print("no Claude key", file=sys.stderr)
        return 2
    usage = {"in": 0, "out": 0, "calls": 0}
    orig = m.Messages.create

    def counted(self, *a, **kw):
        resp = orig(self, *a, **kw)
        usage["in"] += resp.usage.input_tokens
        usage["out"] += resp.usage.output_tokens
        usage["calls"] += 1
        return resp

    m.Messages.create = counted
    spent = lambda: usage["in"] * PRICE_IN / 1e6 + usage["out"] * PRICE_OUT / 1e6  # noqa: E731

    catalog = Catalog.load(config.CATALOG_PATH)
    questions = {q["id"]: q for q in json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))}
    base = json.loads((ROOT / "eval" / "results_policy.json").read_text(encoding="utf-8"))["rows"]
    rows = []
    for b in base:
        if b["send_button"]:
            continue
        if spent() > MAX_USD:
            print(f"stopped at {b['id']}: ~{spent():.3f} USD", file=sys.stderr)
            break
        q = questions[b["id"]]
        say = seller_sentence(q["manager_answer_en"])
        product, _ = catalog.match(q["question_en"])
        t0 = time.time()
        out, mode = drafts.make_drafts(q["question_en"], product, [], use_ai=True, instruction=say)
        secs = round(time.time() - t0, 2)
        status = product.stock_status if product else ""
        price_ok = all(drafts._price_ok(d["text"], product) for d in out)
        rows.append({
            "id": q["id"], "type": q["question_type"], "question_en": q["question_en"], "seller_says": say,
            "mode": mode, "seconds": secs, "drafts": out,
            "send_button": bool(out and out[0]["confident"]), "price_ok": price_ok,
            "stock_ok": all(stock_ok(d["text"], status) for d in out) if product else True,
        })
        print(f"{q['id']} send={rows[-1]['send_button']} price_ok={price_ok} {secs}s ~{spent():.3f}$", flush=True)

    n = len(rows)
    ready = sum(r["send_button"] for r in rows)
    report = {"model": config.CLAUDE_MODEL, "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "price_assumption_usd_per_mtok": [PRICE_IN, PRICE_OUT], "usage": usage,
              "usd_estimate": round(spent(), 4), "questions": n, "ready_after_one_sentence": ready, "rows": rows}
    (ROOT / "eval" / "results_voice.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if n:
        print(f"\n{n} questions without a send button before; ready after one sentence {ready}/{n}; "
              f"price ok {sum(r['price_ok'] for r in rows)}/{n}; stock ok {sum(r['stock_ok'] for r in rows)}/{n}; "
              f"median {statistics.median(r['seconds'] for r in rows)} s; ~{spent():.3f} USD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
