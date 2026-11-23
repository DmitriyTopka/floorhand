"""Step 4: escalation pain stats for TT bot dialogs, 13-20.11.2026.

Source: daily_review_2026-11-13 .. 2026-11-20 raw/dump.json (the same dialogs
as raw/<chat_id>.md, checked 1:1 by chat id). Each day's dump covers one
Kyiv calendar day window, with the full history of every chat active that day.

Definitions
* dialog-day: one item of one day's dump. unique dialog: unique chat_id.
* escalated: item whose "escalations" list is non-empty.
* escalation event: unique (chat_id, escalated_at), escalated_at inside
  13.11 00:00 .. 21.11 00:00 Kyiv (UTC+2).
* t_client: ts of the last client message with ts <= escalated_at.
* t_manager: first MANAGER message with ts > t_client, ignoring the promo
  broadcast "Ви вже зверталися до консультанта ТехноТочки..." (not an answer).
* wait = t_manager - t_client, minutes. Events without any manager reply in
  the data are counted separately (censored), not dropped silently.
Percentiles: linear interpolation (numpy-style "linear"), done by hand.
Usage: pain_stats.py OUT_JSON
"""
import json
import sys
from datetime import datetime

from tt_logs import load_days, merge_chats, KYIV, kyiv

DAYS = [f"2026-11-{d}" for d in range(13, 21)]
START = datetime(2026, 11, 13, tzinfo=KYIV).timestamp()
END = datetime(2026, 11, 21, tzinfo=KYIV).timestamp()
QUESTIONS = __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "questions.json")
PROMO = "Ви вже зверталися до консультанта ТехноТочки"


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def is_work(ts):
    d = kyiv(ts)
    if d.weekday() == 6:
        return False
    close = 18 if d.weekday() == 5 else 19
    return 9 <= d.hour < close


def main(out):
    days = load_days(DAYS)
    assert sorted(days) == DAYS, sorted(days)
    dialog_days = sum(len(v) for v in days.values())
    esc_days = sum(1 for v in days.values() for it in v if it["escalations"])
    chats = merge_chats(days)
    uniq = len(chats)
    uniq_esc = sum(1 for c in chats.values() if c["escalations"])
    with_mgr = sum(1 for c in chats.values() if any(h["author"] == "manager" for h in c["history"]))

    events, out_of_window, no_client, promo_skipped = [], 0, 0, 0
    for chat_id, c in chats.items():
        for e in c["escalations"]:
            ea = float(e["escalated_at"])
            if not (START <= ea < END):
                out_of_window += 1
                continue
            h = c["history"]
            cl = [x for x in h if x["author"] == "client" and float(x["ts"]) <= ea]
            if not cl:
                no_client += 1
                continue
            tc = float(cl[-1]["ts"])
            mg = None
            for x in h:
                if x["author"] == "manager" and float(x["ts"]) > tc:
                    if PROMO in (x.get("content") or ""):
                        promo_skipped += 1
                        continue
                    mg = x
                    break
            events.append({
                "t_client": tc, "escalated_at": ea,
                "client_to_escalation_min": (ea - tc) / 60,
                "wait_min": (float(mg["ts"]) - tc) / 60 if mg else None,
                "escalation_to_manager_min": (float(mg["ts"]) - ea) / 60 if mg else None,
                "work_hours": is_work(tc),
                "reminders_sent": e.get("reminders_sent"),
                "last_client_has_qmark": "?" in (cl[-1].get("content") or ""),
                "within_24h_of_data_end": END - ea < 24 * 3600,
            })
    answered = [e for e in events if e["wait_min"] is not None]
    w = [e["wait_min"] for e in answered]
    w_work = [e["wait_min"] for e in answered if e["work_hours"]]
    w_off = [e["wait_min"] for e in answered if not e["work_hours"]]
    ce = [e["client_to_escalation_min"] for e in events]
    em = [e["escalation_to_manager_min"] for e in answered]

    def r1(x):
        return None if x is None else round(x, 1)

    def summ(xs):
        return {"n": len(xs), "median": r1(pct(xs, 50)), "p75": r1(pct(xs, 75)), "p90": r1(pct(xs, 90)),
                "min": r1(min(xs)) if xs else None, "max": r1(max(xs)) if xs else None}

    res = {
        "window": "13.11.2026 00:00 - 21.11.2026 00:00 Europe/Kyiv (UTC+2)",
        "dialog_days": dialog_days, "dialog_days_escalated": esc_days,
        "unique_dialogs": uniq, "unique_dialogs_escalated": uniq_esc,
        "unique_dialogs_with_any_manager_msg": with_mgr,
        "escalation_events_in_window": len(events),
        "escalation_records_outside_window": out_of_window,
        "events_without_client_msg_before": no_client,
        "promo_broadcasts_skipped": promo_skipped,
        "events_answered": len(answered), "events_unanswered_in_data": len(events) - len(answered),
        "wait_client_to_manager_min": summ(w),
        "wait_work_hours_min": summ(w_work), "wait_off_hours_min": summ(w_off),
        "client_to_escalation_min": summ(ce),
        "escalation_to_manager_min": summ(em),
        "unanswered_last_client_msg_has_qmark": sum(1 for e in events if e["wait_min"] is None and e["last_client_has_qmark"]),
        "unanswered_escalated_less_than_24h_before_data_end": sum(1 for e in events if e["wait_min"] is None and e["within_24h_of_data_end"]),
        "answered_within_30": sum(x <= 30 for x in w),
        "share_wait_over_30": round(sum(x > 30 for x in w) / len(w), 3) if w else None,
        "share_wait_over_60": round(sum(x > 60 for x in w) / len(w), 3) if w else None,
        "share_wait_over_180": round(sum(x > 180 for x in w) / len(w), 3) if w else None,
    }
    try:
        qs = json.load(open(QUESTIONS, encoding="utf-8"))
        res["sample30_manager_minutes"] = summ([q["manager_minutes"] for q in qs])
        res["sample30_bot_replied_first"] = sum(q["bot_replied_before_manager"] for q in qs)
    except FileNotFoundError:
        pass
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
