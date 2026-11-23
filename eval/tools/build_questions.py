"""Step 2: build eval/questions.json from the private selection file.

The selection (keyed chat hashes and the hand-checked translations) is kept
outside the repository; pass its path as the first argument.

For each selected case the script finds, in the merged chat history:
  * the answer = first MANAGER message containing a_match[0], plus the next
    manager messages containing a_match[1:];
  * the question = client message(s) containing each q_match string, the
    latest one before the answer (or the earliest one if first_occurrence).
Texts are taken verbatim from the log, then cleaned of button noise
("💬 Консультація", "Поділитися контактом", "/start"), tracking params and
the "[МЕНЕДЖЕР ТТ]: " prefix, then PII-masked (pii.mask).
manager_minutes = answer ts - ts of the last question message.
first_reply_minutes = first manager message of any kind after the question.
Usage: build_questions.py SELECTION.json CATALOG.json OUT.json
"""
import json
import re
import sys

from tt_logs import load_days, merge_chats, kyiv
from find_candidates import cid
from pii import mask, has_pii

NOISE = re.compile(r"^\s*(💬 Консультація|Поділитися контактом|/start|Задати питання без номера)\s*$")


def clean(text):
    text = text.replace("[МЕНЕДЖЕР ТТ]: ", "").replace("[МЕНЕДЖЕР ТТ]:", "")
    text = re.sub(r"(https?://tt\.ua/[^\s?]+)\?\S*", r"\1", text)
    text = re.sub(r"💬 Консультація|Поділитися контактом", "", text)
    lines = [l.rstrip() for l in mask(text).split("\n")]
    lines = [l for l in lines if l.strip() and not NOISE.match(l) and l.strip() != "[phone]"]
    return "\n".join(lines).strip()


def main(sel_path, cat_path, out_path):
    sel = json.load(open(sel_path, encoding="utf-8"))
    catalog = {}
    try:
        for p in json.load(open(cat_path, encoding="utf-8")):
            catalog[p["url"].rstrip("/").rsplit("/", 1)[-1]] = p
            if p.get("code"):
                catalog["code:" + str(p["code"])] = p
    except FileNotFoundError:
        pass
    chats = {cid(k): v for k, v in merge_chats(load_days()).items()}
    out = []
    for n, s in enumerate(sel, 1):
        h = chats[s["hash"]]["history"]
        ans_idx = [i for i, x in enumerate(h) if x["author"] == "manager" and s["a_match"][0] in x["content"]]
        assert ans_idx, ("answer not found", s["hash"], s["a_match"][0])
        a0 = ans_idx[0]
        a_msgs = [h[a0]]
        for frag in s["a_match"][1:]:
            nxt = [x for x in h[a0 + 1:a0 + 15] if x["author"] == "manager" and frag in x["content"]]
            assert nxt, ("answer part not found", s["hash"], frag)
            a_msgs.append(nxt[0])
        q_msgs = []
        for frag in s["q_match"]:
            cands = [x for x in h[:a0] if x["author"] == "client" and frag in x["content"]]
            assert cands, ("question not found", s["hash"], frag)
            q_msgs.append(cands[0] if s.get("first_occurrence") else cands[-1])
        q_msgs = sorted({id(x): x for x in q_msgs}.values(), key=lambda x: float(x["ts"]))
        q_ts = float(q_msgs[-1]["ts"])
        first_mgr = next(x for x in h if x["author"] == "manager" and float(x["ts"]) > q_ts)
        q_text = "\n".join(clean(x["content"]) for x in q_msgs)
        a_text = "\n".join(clean(x["content"]) for x in a_msgs)
        slug = s.get("slug")
        prod = catalog.get(slug) if slug else None
        if not prod and s.get("code"):
            prod = catalog.get("code:" + s["code"])
        if not prod and s.get("search"):
            prod = next((p for p in catalog.values() if p.get("search_query") == s["search"]), None)
        url = prod["url"] if prod else (f"https://tt.ua/uk/{slug}" if slug else None)
        code = (prod or {}).get("code") or s.get("code")
        rec = {
            "id": f"tt-q{n:02d}",
            "date": kyiv(q_ts).strftime("2026-%m-%d"),
            "product_code": str(code) if code else None,
            "product_url": url,
            "city": s.get("city"),
            "question_uk": q_text,
            "question_en": s["q_en"],
            "manager_answer_uk": a_text,
            "manager_answer_en": s["a_en"],
            "manager_minutes": round((float(a_msgs[0]["ts"]) - q_ts) / 60, 1),
            "first_reply_minutes": round((float(first_mgr["ts"]) - q_ts) / 60, 1),
            "question_type": s["type"],
            "related_codes": s.get("related_codes", []),
            "bot_replied_before_manager": any(x["author"] == "bot" and q_ts < float(x["ts"]) < float(a_msgs[0]["ts"]) for x in h),
        }
        for k in ("question_uk", "manager_answer_uk"):
            assert not has_pii(rec[k]), (rec["id"], k)
        out.append(rec)
    json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("questions:", len(out))


if __name__ == "__main__":
    main(*sys.argv[1:4])
