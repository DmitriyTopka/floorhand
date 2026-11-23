"""Tiny JSON-file store: customers, tickets (questions waiting for a reply), paired glasses."""
import json
import secrets
import threading
import time
from pathlib import Path

_LOCK = threading.RLock()


def _network(ip: str) -> str:
    """IPv4 as is, IPv6 grouped by /64 (one home or one VPS usually owns a /64)."""
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return ip


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

    # pairing: glasses show a code, the shop owner sends /pair CODE to the bot.
    # The device id is a 128-bit random key the glasses app creates itself, so
    # it works as the device's secret; codes expire and attempts are limited.
    CODE_TTL = 600
    MAX_CODES = 500

    NEW_DEVICES_PER_IP = 20  # per CODE_TTL window

    class PairingBusy(Exception):
        pass

    def pair_code_for(self, device: str, ip: str = "local") -> str:
        with _LOCK:
            now = time.time()
            codes = self.state["pair_codes"]
            for code in [c for c, v in codes.items() if now - v["at"] > self.CODE_TTL]:
                codes.pop(code)
            # numbers of evicted codes stay retired until their TTL runs out, so a
            # code someone is about to type can never point to another device
            retired = self.state.setdefault("retired_codes", {})
            for code in [c for c, at in retired.items() if now - at > self.CODE_TTL]:
                retired.pop(code)
            for code, v in codes.items():
                if v["device"] == device:
                    return code
            # One address (an IPv6 /64 counts as one) holds at most
            # NEW_DEVICES_PER_IP pending codes. When the table is full, the
            # oldest code of the address holding the most codes goes, so a
            # flood from a few addresses only pushes out its own codes.
            net = _network(ip)
            if sum(1 for v in codes.values() if v.get("net") == net) >= self.NEW_DEVICES_PER_IP:
                raise Store.PairingBusy("too many new devices from this address")
            while len(codes) >= self.MAX_CODES:
                counts: dict[str, int] = {}
                for v in codes.values():
                    counts[v.get("net", "")] = counts.get(v.get("net", ""), 0) + 1
                heavy = max(counts, key=counts.get)
                oldest = min((c for c, v in codes.items() if v.get("net", "") == heavy), key=lambda c: codes[c]["at"])
                retired[oldest] = codes.pop(oldest)["at"]
            while True:
                code = f"{secrets.randbelow(900000) + 100000}"
                if code not in codes and code not in retired:
                    break
            codes[code] = {"device": device, "at": now, "net": net}
            self._save()
            return code

    def pair_attempt_allowed(self, chat_id: int, limit: int = 5, window: int = 600) -> bool:
        with _LOCK:
            now = time.time()
            tries = [t for t in self.state.setdefault("pair_tries", {}).get(str(chat_id), []) if now - t < window]
            allowed = len(tries) < limit
            tries.append(now)
            self.state["pair_tries"][str(chat_id)] = tries
            self._save()
            return allowed

    def confirm_pair(self, code: str, owner_chat_id: int) -> str | None:
        with _LOCK:
            entry = self.state["pair_codes"].pop(code, None)
            if not entry or time.time() - entry["at"] > self.CODE_TTL:
                self._save()
                return None
            self.state["devices"][entry["device"]] = {"owner_chat_id": owner_chat_id, "paired_at": time.time()}
            self._save()
            return entry["device"]

    def is_paired(self, device: str) -> bool:
        with _LOCK:
            return device in self.state["devices"]
