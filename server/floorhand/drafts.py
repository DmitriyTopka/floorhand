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

# A price is a whole number, optionally grouped in thousands ("31 499", "31,499"),
# optionally with kopecks, followed by the currency. It may not start inside a
# word, so "RB38C679ES9. 31 499 UAH" reads as 31 499, not 931 499.
_NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:[ \u00a0\u202f,.]\d{3})+|\d+)(?:[.,]\d{1,2})?\s*(?:uah|грн|hryvnia|₴)",
                  re.IGNORECASE)

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
- Use only the facts in PRODUCT FACTS and SHOP POLICY. Never invent a price, stock status, delivery date or spec.
- SHOP POLICY covers every product; use it for delivery, carrying, payment, installments, warranty and returns.
- If the facts do not answer the question, say a colleague will confirm, and set confident to false.
- Each reply at most 160 characters, plain text, no emoji, the customer's language.
- Reply 1: direct answer. Reply 2: answer plus a helpful next step. Reply 3: short and warm.
- confident is true only when the reply is fully backed by the facts."""


_policy_cache: dict[str, tuple[str, set[int]]] = {}


def policy() -> tuple[str, set[int]]:
    """Shop policy text and the UAH amounts it names (fees, per-floor prices)."""
    key = str(config.POLICY_PATH)
    if key not in _policy_cache:
        text = config.POLICY_PATH.read_text(encoding="utf-8") if config.POLICY_PATH.exists() else ""
        amounts = {int(re.sub(r"\D", "", n)) for n in _NUM.findall(text)}
        _policy_cache[key] = (text, amounts)
    return _policy_cache[key]


_OLD_CTX = re.compile(r"(was|old|crossed|before|стара|було|раніше)\W*((price|ціна)\W*)?$", re.IGNORECASE)
_POLICY_CTX = re.compile(r"floor|поверх|envelope|конверт|fee|комісі|prepay|передоплат|cash on delivery|післяплат|"
                         r"installment|payments|credit|кредит|розстроч|minimum|from \d|over \d|up to|до \d", re.IGNORECASE)


def _price_ok(text: str, product: Product | None) -> bool:
    """Every UAH amount must be one of:
    - the catalog price;
    - the crossed-out price, only when it is higher and the words just before say "was" or "old";
    - an amount from the shop policy (per-floor price, fee, credit limit), only next to that kind of wording.
    Anything else, a price the model made up or a policy amount passed off as the item's price, fails."""
    price = int(round(product.price_uah)) if product and product.price_uah else None
    old = int(round(product.price_old_uah)) if product and product.price_old_uah else None
    amounts = policy()[1]
    for m in _NUM.finditer(text):
        value = int(re.sub(r"\D", "", m.group(1)))
        if value == price:
            continue
        before = text[max(0, m.start() - 25):m.start()]
        if old and price and old > price and value == old and _OLD_CTX.search(before.rstrip(" (:,")):
            continue
        around = text[max(0, m.start() - 40):m.end() + 25]
        if value in amounts and _POLICY_CTX.search(around):
            continue
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
    rules = policy()[0] or "No shop policy loaded."
    user = f"SHOP: {config.SHOP_NAME}\nSHOP POLICY:\n{rules}\n\nPRODUCT FACTS:\n{facts}\n\nCONVERSATION:\n{convo}\n\nCUSTOMER'S LAST MESSAGE:\n{question}"
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
