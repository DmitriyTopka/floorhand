"""Count tt.ua product links across all November dialogs (unique chats that
mention the link), print top N as JSON. Usage: popular_links.py [N]"""
import json
import re
import sys
from tt_logs import load_days, merge_chats

LINK = re.compile(r"tt\.ua/(?:uk/|ru/)?([a-z0-9][a-z0-9-]+)")
SKIP = {"tochki-vidachi", "dostavka-i-oplata", "garantiya-i-vozvrat", "special", "search", "image", "vigodniy-kredit-1"}


def slug_counts():
    chats = merge_chats(load_days())
    cnt = {}
    for c in chats.values():
        seen = set()
        for h in c["history"]:
            for s in LINK.findall(h.get("content") or ""):
                if s not in SKIP and not s.startswith("image"):
                    seen.add(s)
        for s in seen:
            cnt[s] = cnt.get(s, 0) + 1
    return sorted(cnt.items(), key=lambda x: -x[1])


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    print(json.dumps(slug_counts()[:n], ensure_ascii=False, indent=0))
