"""HTTP API the glasses app calls. Keys stay here, never in the app."""
import time

from fastapi import FastAPI, HTTPException, Request
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
                   allow_headers=["*"])


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


def _own(uid: str, ticket_id: int) -> dict:
    t = next((t for t in _visible(uid) if t["id"] == ticket_id), None)
    if not t:
        raise HTTPException(404, "no such ticket for this device")
    return t


@app.get("/health")
def health() -> dict:
    return {"ok": True, "products": len(catalog.products), "llm": config.llm_enabled(),
            "bot": bool(config.TELEGRAM_BOT_TOKEN)}


@app.get("/api/card")
def card(uid: str) -> dict:
    if not store.is_paired(uid):
        return {"mode": "pair", "code": store.pair_code_for(uid)}
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
    uid: str
    ticket_id: int
    draft: int


@app.post("/api/send")
def send(body: SendBody) -> dict:
    t = _own(body.uid, body.ticket_id)
    if not (0 <= body.draft < len(t["drafts"])):
        raise HTTPException(400, "bad draft index")
    d = t["drafts"][body.draft]
    if not d["confident"]:
        raise HTTPException(409, "low confidence draft: edit by voice or hand off")
    bot.reply(t["id"], d["text"])
    return {"ok": True}


class TicketBody(BaseModel):
    uid: str
    ticket_id: int


@app.post("/api/handoff")
def handoff(body: TicketBody) -> dict:
    t = _own(body.uid, body.ticket_id)
    store.update_ticket(t["id"], status="handed_off")
    return {"ok": True}


@app.post("/api/voice")
async def voice(uid: str, ticket_id: int, request: Request) -> dict:
    t = _own(uid, ticket_id)
    pcm = await request.body()
    from .stt import transcribe_pcm16
    said = transcribe_pcm16(pcm)
    if not said:
        return {"ok": False, "said": ""}
    updated = bot.draft(t["id"], instruction=said)
    return {"ok": True, "said": said, "drafts": updated["drafts"] if updated else []}
