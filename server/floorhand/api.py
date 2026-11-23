"""HTTP API the glasses app calls. Keys stay here, never in the app."""
import time

import re

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config
from .bot import Bot
from .catalog import Catalog
from .store import Store

store = Store(config.DATA_DIR)
catalog = Catalog.load(config.CATALOG_PATH)
bot = Bot(store, catalog)

app = FastAPI(title="Floorhand")
app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type", "X-Device-Key"])


@app.on_event("startup")
def _start_bot() -> None:
    if config.TELEGRAM_BOT_TOKEN:
        bot.start()
    else:
        print("TELEGRAM_BOT_TOKEN not set: bot polling is off")


def _visible(uid: str) -> list[dict]:
    dev = store.state["devices"].get(uid)
    if not dev:
        return []
    tickets = store.waiting()
    if config.DEMO_ISOLATION:
        tickets = [t for t in tickets if t["chat_id"] == dev["owner_chat_id"]]
    return sorted(tickets, key=lambda t: t["created"])


def _own(uid: str | None, ticket_id: int) -> dict:
    uid = _device(uid)
    t = next((t for t in _visible(uid) if t["id"] == ticket_id), None)
    if not t:
        raise HTTPException(404, "no such ticket for this device")
    return t


@app.get("/health")
def health() -> dict:
    return {"ok": True, "products": len(catalog.products), "llm": config.llm_enabled(),
            "bot": bool(config.TELEGRAM_BOT_TOKEN)}


_DEVICE = re.compile(r"^[A-Za-z0-9_-]{22,64}$")
MAX_VOICE_BYTES = 16000 * 2 * 15  # 15 s of 16 kHz 16-bit mono


def _device(uid: str | None) -> str:
    if not uid or not _DEVICE.match(uid):
        raise HTTPException(400, "device key must be 22-64 url-safe characters")
    return uid


@app.get("/api/card")
def card(request: Request, x_device_key: str | None = Header(default=None)) -> dict:
    uid = _device(x_device_key)
    if not store.is_paired(uid):
        try:
            code = store.pair_code_for(uid, request.client.host if request.client else "unknown")
        except Store.PairingBusy as exc:
            raise HTTPException(503, str(exc))
        return {"mode": "pair", "code": code}
    queue = _visible(uid)
    ready = [t for t in queue if t["status"] == "waiting"]
    if not ready:
        return {"mode": "empty", "drafting": len(queue)}
    t = ready[0]
    product = catalog.by_code.get(t["product"]) if t["product"] else None
    return {"mode": "card", "queue": len(queue), "ticket": {
        "id": t["id"], "name": t["name"], "text": t["text"], "drafts": t["drafts"],
        "draft_mode": t["draft_mode"], "waiting_s": int(time.time() - t["created"]),
        "product": {"code": product.code, "name": product.name_en or product.name,
                    "price_uah": product.price_uah, "stock": product.stock_status} if product else None,
    }}


class SendBody(BaseModel):
    ticket_id: int
    draft: int


@app.post("/api/send")
def send(body: SendBody, x_device_key: str | None = Header(default=None)) -> dict:
    t = _own(x_device_key, body.ticket_id)
    if not (0 <= body.draft < len(t["drafts"])):
        raise HTTPException(400, "bad draft index")
    d = t["drafts"][body.draft]
    if not d["confident"]:
        raise HTTPException(409, "low confidence draft: edit by voice or hand off")
    bot.reply(t["id"], d["text"])
    return {"ok": True}


class TicketBody(BaseModel):
    ticket_id: int


@app.post("/api/handoff")
def handoff(body: TicketBody, x_device_key: str | None = Header(default=None)) -> dict:
    t = _own(x_device_key, body.ticket_id)
    store.update_ticket(t["id"], status="handed_off")
    return {"ok": True}


@app.post("/api/voice")
async def voice(ticket_id: int, request: Request, x_device_key: str | None = Header(default=None)) -> dict:
    t = _own(x_device_key, ticket_id)
    declared = int(request.headers.get("content-length") or 0)
    if declared > MAX_VOICE_BYTES:
        raise HTTPException(413, "voice note too long (15 s max)")
    pcm = bytearray()
    async for chunk in request.stream():
        pcm.extend(chunk)
        if len(pcm) > MAX_VOICE_BYTES:
            raise HTTPException(413, "voice note too long (15 s max)")
    from .stt import transcribe_pcm16
    said = await run_in_threadpool(transcribe_pcm16, bytes(pcm))
    if not said:
        return {"ok": False, "said": ""}
    updated = await run_in_threadpool(bot.draft, t["id"], said)
    return {"ok": True, "said": said, "drafts": updated["drafts"] if updated else []}


if config.DEV_FAKE_TELEGRAM:
    class DevMessage(BaseModel):
        chat_id: int
        text: str
        name: str = "Anna"

    @app.post("/dev/customer")
    def dev_customer(body: DevMessage) -> dict:
        """Play a customer writing to the bot (local development only)."""
        bot.handle_update({"message": {"chat": {"id": body.chat_id}, "from": {"first_name": body.name},
                                       "text": body.text}})
        return {"ok": True}

    class DevConsent(BaseModel):
        chat_id: int
        choice: str  # ai | human

    @app.post("/dev/consent")
    def dev_consent(body: DevConsent) -> dict:
        bot.handle_update({"callback_query": {"id": "dev", "data": f"consent:{body.choice}",
                                              "message": {"chat": {"id": body.chat_id}},
                                              "from": {"first_name": "Anna"}}})
        return {"ok": True}

    class DevPair(BaseModel):
        code: str
        chat_id: int

    @app.post("/dev/pair")
    def dev_pair(body: DevPair) -> dict:
        bot.handle_update({"message": {"chat": {"id": body.chat_id}, "from": {"first_name": "Owner"},
                                       "text": f"/pair {body.code}"}})
        return {"ok": True}
