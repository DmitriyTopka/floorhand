"""Step 1: list candidate (client question -> manager answer) pairs about a
concrete product. Output goes to a local scratch file for manual review
(masked text only). Usage: python3 find_candidates.py OUT.txt"""
import hashlib
import re
import sys

from tt_logs import load_days, merge_chats, kyiv
from pii import mask

KW = re.compile(r"наявн|наличи|ціна|цена|скільки|сколько|чи є|є в|есть ли|доставк|характерист|різниц|разниц|порівн|сравн|підійде|подойдет|розмір|размер|гарант|колір|цвет|відрізня|отлича|кредит|розстрочк|рассрочк|самовивіз|самовывоз|забрати|забрать", re.I)
PROD = re.compile(r"tt\.ua/|[Кк]од\s*\d{5,6}|\b[A-Z][A-Z0-9-]{3,}\b|\b(?:BOSCH|Samsung|LG|Tefal|Philips|Electrolux|Gorenje|Beko|Whirlpool|Xiaomi|Ardesto|Candy|Indesit|Zanussi|AEG|Miele|Siemens|Hotpoint|Liebherr|Sharp|Sony|Delonghi|De'?Longhi|Braun|Rowenta|Moulinex|Kenwood|Vitek|Dyson)\b", re.I)


def cid(chat_id):
    """Keyed hash of a chat id. The key lives outside the repository
    (FLOORHAND_EVAL_KEY), so the ids can't be recovered from published files."""
    import hmac
    import os
    key = os.environ.get("FLOORHAND_EVAL_KEY")
    if not key:
        sys.exit("set FLOORHAND_EVAL_KEY (kept outside the repo) to run this script")
    return hmac.new(key.encode(), str(chat_id).encode(), hashlib.sha256).hexdigest()[:12]


def main(out):
    chats = merge_chats(load_days())
    n = 0
    with open(out, "w", encoding="utf-8") as fh:
        for chat_id, c in chats.items():
            h = c["history"]
            i = 0
            while i < len(h):
                if h[i]["author"] != "client":
                    i += 1
                    continue
                j = i
                while j + 1 < len(h) and h[j + 1]["author"] == "client":
                    j += 1
                # first manager msg after the client group, before next client group
                k = j + 1
                bots = []
                while k < len(h) and h[k]["author"] == "bot":
                    bots.append(h[k])
                    k += 1
                if k < len(h) and h[k]["author"] == "manager":
                    q = "\n".join(x["content"] for x in h[i:j + 1])
                    ctx = "\n".join(x["content"] for x in h[max(0, i - 4):i])
                    if KW.search(q) and (PROD.search(q) or PROD.search(ctx)):
                        mans = []
                        m = k
                        while m < len(h) and h[m]["author"] == "manager" and len(mans) < 3:
                            mans.append(h[m]["content"])
                            m += 1
                        mins = (float(h[k]["ts"]) - float(h[j]["ts"])) / 60
                        n += 1
                        fh.write(f"===== CAND {cid(chat_id)} qts={h[j]['ts']} {kyiv(h[j]['ts']):%d.%m %H:%M} wait={mins:.1f}m bots={len(bots)}\n")
                        fh.write("--ctx: " + mask(ctx)[-500:].replace("\n", " | ") + "\n")
                        fh.write("--Q: " + mask(q)[:800] + "\n")
                        for b in bots:
                            fh.write("--BOT: " + mask(b["content"])[:300].replace("\n", " | ") + "\n")
                        for a in mans:
                            fh.write("--MGR: " + mask(a)[:700] + "\n")
                i = j + 1
    print("candidates:", n)


if __name__ == "__main__":
    main(sys.argv[1])
