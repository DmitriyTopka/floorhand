"""Reply drafts for one customer question.

Two modes:
- template: built only from catalog fields, no AI. Used when the customer chose
  "human only" or DRAFTS=template.
- llm: Claude writes three short replies from the catalog facts we pass in.

Safety rules applied to every draft, whatever wrote it:
- a price that is not the catalog price makes the draft low confidence;
- with no matching product, every draft is low confidence (no send button on the glasses).
"""
import json
import re

from . import config
from .catalog import Product

_NUM = re.compile(r"(\d[\d\s.,]{2,})\s*(?:uah|грн|hryvnia|₴)", re.IGNORECASE)

_SCHEMA = {
    "type": "object",
    "properties": {
        "drafts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "confident": {"type": "boolean"},
                },
                "required": ["text", "confident"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["drafts"],
    "additionalProperties": False,
}

_SYSTEM = """You draft replies for a shop assistant who reads them on smart glasses and sends one with a tap.
Write exactly three different replies to the customer's last message.
Rules:
- Use only the facts in PRODUCT FACTS. Never invent a price, stock status, delivery date or spec.
- If the facts do not answer the question, say a colleague will confirm, and set confident to false.
- Each reply at most 160 characters, plain text, no emoji, the customer's language.
- Reply 1: direct answer. Reply 2: answer plus a helpful next step. Reply 3: short and warm.
- confident is true only when the reply is fully backed by the facts."""


def _price_ok(text: str, product: Product | None) -> bool:
    """Every price mentioned in UAH must equal the catalog price."""
    found = _NUM.findall(text)
    if not found:
        return True
    if not product or not product.price_uah:
        return False
    want = int(round(product.price_uah))
    for raw in found:
        raw = re.sub(r"[.,]\d{2}\s*$", "", raw.strip())
        digits = re.sub(r"\D", "", raw)
        if digits and int(digits) != want:
            return False
    return True


def guard(drafts: list[dict], product: Product | None) -> list[dict]:
    out = []
    for d in drafts[:3]:
        text = d["text"].strip()
        confident = bool(d.get("confident")) and product is not None and _price_ok(text, product)
        out.append({"text": text, "confident": confident})
    return out


def template_drafts(question: str, product: Product | None) -> list[dict]:
    if product is None:
        return [
            {"text": "Thanks for your message! A colleague will check and reply shortly.", "confident": False},
            {"text": "Could you send the product code or a link? Then I can check it right away.", "confident": False},
            {"text": "Got it, checking for you now.", "confident": False},
        ]
    price = f"{product.price_uah:,.0f} UAH".replace(",", " ") if product.price_uah else None
    name = product.name_en or product.name
    stock = product.stock_status
    d1 = f"{name}: {price}. {stock}." if price else f"{name}: {stock}."
    d2 = f"{d1} Want me to reserve it for you?"
    d3 = f"Yes, we have the {name}. {price}." if price and "in stock" in stock.lower() else f"Let me confirm the {name} for you."
    return guard([{"text": d1, "confident": True}, {"text": d2, "confident": True},
                  {"text": d3, "confident": "in stock" in stock.lower()}], product)


def llm_drafts(question: str, product: Product | None, history: list[str], instruction: str | None = None) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    facts = product.facts() if product else "No matching product found in the catalog."
    convo = "\n".join(history[-6:])
    user = f"SHOP: {config.SHOP_NAME}\nPRODUCT FACTS:\n{facts}\n\nCONVERSATION:\n{convo}\n\nCUSTOMER'S LAST MESSAGE:\n{question}"
    if instruction:
        user += f"\n\nTHE ASSISTANT SAID, apply this to all three replies: {instruction}"
    resp = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1200,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}},
    )
    if resp.stop_reason == "refusal":
        return template_drafts(question, product)
    text = "".join(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)
    return guard(data["drafts"], product)


def make_drafts(question: str, product: Product | None, history: list[str], use_ai: bool,
                instruction: str | None = None) -> tuple[list[dict], str]:
    if use_ai and config.llm_enabled():
        try:
            return llm_drafts(question, product, history, instruction), "ai"
        except Exception as exc:  # network, quota, bad JSON: fall back, never block the shop
            print(f"llm_drafts failed, using template: {exc!r}")
    drafts = template_drafts(question, product)
    if instruction:
        drafts = [{"text": f"{d['text']} ({instruction})", "confident": False} for d in drafts]
    return drafts, "template"
