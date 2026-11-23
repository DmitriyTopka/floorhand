"""Shared loader for TT bot daily review dumps.

Reads memory/tt-bot/daily_review_2026-11-*/raw/dump.json (same dialogs as the
per-chat *.md files in raw/, checked 1:1 by chat id), merges every chat across
days and de-duplicates messages by (ts, author, content).
Nothing here writes personal data anywhere; masking lives in pii.py.
"""
import glob
import json
import os
from datetime import datetime, timezone, timedelta

# Private shop logs, never in this repository. Point TT_LOGS_DIR at the folder
# that holds daily_review_*/raw/dump.json.
RAW_GLOB = os.path.join(os.environ.get("TT_LOGS_DIR", "./private_logs"), "daily_review_2026-11-*/raw/dump.json")

KYIV = timezone(timedelta(hours=2))  # November 2026: EET, UTC+2, no DST


def day_of(path):
    return os.path.basename(os.path.dirname(os.path.dirname(path)))[len("daily_review_"):]


def load_days(days=None):
    """Return {day: [item, ...]} with items exactly as in dump.json."""
    out = {}
    for f in sorted(glob.glob(RAW_GLOB)):
        d = day_of(f)
        if days and d not in days:
            continue
        out[d] = json.load(open(f, encoding="utf-8"))["items"]
    return out


def merge_chats(days_items):
    """chat_id -> {'history': sorted unique msgs, 'escalations': unique, 'days': set}."""
    chats = {}
    for d, items in days_items.items():
        for it in items:
            c = chats.setdefault(it["chat_id"], {"history": {}, "escalations": {}, "days": set()})
            c["days"].add(d)
            for h in it["history"]:
                key = (round(float(h.get("ts") or 0), 3), h.get("author"), h.get("content"))
                c["history"][key] = h
            for e in it["escalations"] or []:
                c["escalations"][(e.get("escalated_at"))] = e
    for c in chats.values():
        c["history"] = sorted(c["history"].values(), key=lambda h: float(h.get("ts") or 0))
        c["escalations"] = sorted(c["escalations"].values(), key=lambda e: e.get("escalated_at") or 0)
    return chats


def kyiv(ts):
    return datetime.fromtimestamp(float(ts), KYIV)
