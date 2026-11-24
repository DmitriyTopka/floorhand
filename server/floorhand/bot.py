"""Telegram side: long polling, consent, /forget, /pair, and sending replies."""
import threading
import time

import httpx

from . import config
from .catalog import Catalog
from .drafts import make_drafts
from .store import Store

CONSENT_TEXT = (
    "Hi! Replies in this chat are prepared with AI from the shop's catalog and checked "
    "by a person before they are sent. Is it OK to use AI for drafting?\n\n"
    "Send /forget any time to delete what we keep about you."
)
WELCOME_HUMAN = "Got it, only a person will read and answer your messages. Ask away!"
WELCOME_AI = "Thanks! Ask about any product: price, stock, delivery."


class Bot:
    def __init__(self, store: Store, catalog: Catalog, token: str | None = None):
        self.store = store
        self.catalog = catalog
        self.token = token or config.TELEGRAM_BOT_TOKEN
        self.base = f"https://api.telegram.org/bot{self.token}"
        self.http = httpx.Client(timeout=40)
        self._stop = threading.Event()

    # Telegram API
    def call(self, method: str, **params):
        if config.DEV_FAKE_TELEGRAM:
            print(f"[fake telegram] {method} {params.get('chat_id', '')}: {str(params.get('text', ''))[:80]}")
            return {}
        r = self.http.post(f"{self.base}/{method}", json=params)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"{method}: {data.get('description')}")
        return data["result"]

    def send(self, chat_id: int, text: str, **extra):
        return self.call("sendMessage", chat_id=chat_id, text=text, **extra)

    def ask_consent(self, chat_id: int):
        self.send(chat_id, CONSENT_TEXT, reply_markup={"inline_keyboard": [[
            {"text": "OK, AI may draft", "callback_data": "consent:ai"},
            {"text": "Human only", "callback_data": "consent:human"},
        ]]})

    # incoming
    def handle_update(self, upd: dict) -> None:
        if "callback_query" in upd:
            q = upd["callback_query"]
            chat_id = q["message"]["chat"]["id"]
            choice = q.get("data", "").split(":")[-1]
            if choice in ("ai", "human"):
                self.store.set_customer(chat_id, consent=choice, consent_at=time.time())
                self.call("answerCallbackQuery", callback_query_id=q["id"])
                self.send(chat_id, WELCOME_AI if choice == "ai" else WELCOME_HUMAN)
                pending = self.store.customer(chat_id).get("pending")
                if pending:
                    self.store.set_customer(chat_id, pending=None)
                    self.new_question(chat_id, q["from"].get("first_name", "Customer"), pending)
            return
        msg = upd.get("message")
        if not msg or "text" not in msg:
            return
        chat_id = msg["chat"]["id"]
        text = msg["text"].strip()
        name = msg.get("from", {}).get("first_name", "Customer")
        if text.startswith("/start"):
            self.ask_consent(chat_id)
            return
        if text.startswith("/forget"):
            n = self.store.forget(chat_id)
            self.send(chat_id, f"Done: deleted your consent and {n} message(s) we kept.")
            return
        if text.startswith("/pair"):
            parts = text.split()
            if not config.DEMO_ISOLATION and chat_id not in config.OWNER_CHAT_IDS:
                self.send(chat_id, "Only the shop owner can pair glasses here.")
                return
            if not self.store.pair_attempt_allowed(chat_id):
                self.send(chat_id, "Too many tries. Wait ten minutes and use the code on your glasses.")
                return
            uid = self.store.confirm_pair(parts[1], chat_id) if len(parts) == 2 else None
            self.send(chat_id, "Glasses paired. Questions you send here will show up on them."
                      if uid else "That code did not match. Check the code on your glasses.")
            return
        consent = self.store.customer(chat_id).get("consent")
        if consent is None:
            self.store.set_customer(chat_id, pending=text, name=name)
            self.ask_consent(chat_id)
            return
        self.new_question(chat_id, name, text)

    def new_question(self, chat_id: int, name: str, text: str) -> None:
        ticket = self.store.add_ticket(chat_id, name, text)
        threading.Thread(target=self.draft, args=(ticket["id"],), daemon=True).start()

    def history(self, chat_id: int, before_id: int) -> list[str]:
        lines = []
        for t in self.store.state["tickets"]:
            if t["chat_id"] == chat_id and t["id"] < before_id:
                lines.append(f"Customer: {t['text']}")
                if t.get("sent_text"):
                    lines.append(f"Shop: {t['sent_text']}")
        return lines

    def draft(self, ticket_id: int, instruction: str | None = None) -> dict | None:
        t = self.store.ticket(ticket_id)
        if not t:
            return None
        product, _score = self.catalog.match(t["text"])
        if product is None:
            # look back: the customer may have named the product earlier
            for line in reversed(self.history(t["chat_id"], ticket_id)):
                product, _score = self.catalog.match(line)
                if product:
                    break
        use_ai = self.store.customer(t["chat_id"]).get("consent") == "ai"
        started = time.time()
        drafts, mode = make_drafts(t["text"], product, self.history(t["chat_id"], ticket_id), use_ai, instruction)
        return self.store.update_ticket(
            ticket_id, drafts=drafts, draft_mode=mode, status="waiting",
            product=product.code if product else None, draft_seconds=round(time.time() - started, 2),
            **({"voice_text": instruction} if instruction else {}))

    # outgoing
    def reply(self, ticket_id: int, text: str) -> dict | None:
        t = self.store.ticket(ticket_id)
        if not t:
            return None
        self.send(t["chat_id"], text)
        return self.store.update_ticket(ticket_id, status="sent", sent_text=text, sent_at=time.time())

    # loop
    def run(self) -> None:
        offset = 0
        while not self._stop.is_set():
            try:
                updates = self.call("getUpdates", offset=offset, timeout=30, allowed_updates=["message", "callback_query"])
                for upd in updates:
                    offset = upd["update_id"] + 1
                    try:
                        self.handle_update(upd)
                    except Exception as exc:
                        print(f"update {upd.get('update_id')} failed: {exc!r}")
            except Exception as exc:
                print(f"polling error: {exc!r}")
                time.sleep(3)

    def start(self) -> threading.Thread:
        th = threading.Thread(target=self.run, daemon=True)
        th.start()
        return th
