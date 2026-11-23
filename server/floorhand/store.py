"""Tiny JSON-file store: customers, tickets (questions waiting for a reply), paired glasses."""
import json
import secrets
import threading
import time
from pathlib import Path

_LOCK = threading.RLock()


class Store:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = {"customers": {}, "tickets": [], "devices": {}, "pair_codes": {}, "next_id": 1}
        if self.path.exists():
            self.state.update(json.loads(self.path.read_text(encoding="utf-8")))

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    # customers and consent
    def customer(self, chat_id: int) -> dict:
        with _LOCK:
            return dict(self.state["customers"].get(str(chat_id), {}))

    def set_customer(self, chat_id: int, **fields) -> None:
        with _LOCK:
            c = self.state["customers"].setdefault(str(chat_id), {})
            c.update(fields)
            self._save()

    def forget(self, chat_id: int) -> int:
        """Delete everything we keep about one customer. Returns removed tickets."""
        with _LOCK:
            self.state["customers"].pop(str(chat_id), None)
            before = len(self.state["tickets"])
            self.state["tickets"] = [t for t in self.state["tickets"] if t["chat_id"] != chat_id]
            self._save()
            return before - len(self.state["tickets"])

    # tickets
    def add_ticket(self, chat_id: int, name: str, text: str) -> dict:
        with _LOCK:
            t = {"id": self.state["next_id"], "chat_id": chat_id, "name": name, "text": text,
                 "created": time.time(), "status": "drafting", "drafts": [], "product": None,
                 "draft_mode": None, "sent_text": None, "sent_at": None}
            self.state["next_id"] += 1
            self.state["tickets"].append(t)
            self._save()
            return dict(t)

    def update_ticket(self, ticket_id: int, **fields) -> dict | None:
        with _LOCK:
            for t in self.state["tickets"]:
                if t["id"] == ticket_id:
                    t.update(fields)
                    self._save()
                    return dict(t)
            return None

    def ticket(self, ticket_id: int) -> dict | None:
        with _LOCK:
            for t in self.state["tickets"]:
                if t["id"] == ticket_id:
                    return dict(t)
            return None

    def waiting(self) -> list[dict]:
        with _LOCK:
            return [dict(t) for t in self.state["tickets"] if t["status"] in ("waiting", "drafting")]

    # pairing: glasses show a code, the shop owner sends /pair CODE to the bot
    def pair_code_for(self, uid: str) -> str:
        with _LOCK:
            for code, owner in self.state["pair_codes"].items():
                if owner == uid:
                    return code
            code = f"{secrets.randbelow(900000) + 100000}"
            self.state["pair_codes"][code] = uid
            self._save()
            return code

    def confirm_pair(self, code: str, owner_chat_id: int) -> str | None:
        with _LOCK:
            uid = self.state["pair_codes"].pop(code, None)
            if uid:
                self.state["devices"][uid] = {"owner_chat_id": owner_chat_id, "paired_at": time.time()}
                self._save()
            return uid

    def is_paired(self, uid: str) -> bool:
        with _LOCK:
            return uid in self.state["devices"]
