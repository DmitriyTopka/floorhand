"""Shop catalog: load products and find the one a customer is asking about."""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_WORD = re.compile(r"[\w']+", re.UNICODE)
_CODE = re.compile(r"\b(\d{6})\b")
_STOP = {"the", "a", "an", "do", "you", "have", "is", "it", "in", "of", "and", "for", "how", "much",
         "what", "there", "this", "that", "with", "to", "on", "i", "me", "my", "can", "please"}


@dataclass
class Product:
    code: str
    name: str
    price_uah: float | None
    stock_status: str
    url: str
    category: str = ""
    specs: list[str] = field(default_factory=list)
    name_en: str = ""

    def facts(self) -> str:
        price = f"{self.price_uah:,.0f} UAH".replace(",", " ") if self.price_uah else "price not listed"
        lines = [f"{self.name_en or self.name} (code {self.code})", f"Price: {price}", f"Stock: {self.stock_status}"]
        lines += [f"- {s}" for s in self.specs[:5]]
        lines.append(f"Link: {self.url}")
        return "\n".join(lines)


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text) if len(w) > 1 and w.lower() not in _STOP}


class Catalog:
    def __init__(self, products: list[Product]):
        self.products = products
        self.by_code = {p.code: p for p in products}

    @classmethod
    def load(cls, path: Path) -> "Catalog":
        if not path.exists():
            return cls([])
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw["products"] if isinstance(raw, dict) else raw
        products = []
        for it in items:
            products.append(Product(
                code=str(it.get("code", "")), name=it.get("name", ""), name_en=it.get("name_en", ""),
                price_uah=it.get("price_uah"), stock_status=it.get("stock_status", "unknown"),
                url=it.get("url", ""), category=it.get("category", ""), specs=list(it.get("specs", [])),
            ))
        return cls(products)

    def match(self, text: str) -> tuple[Product | None, float]:
        """Best product for a message and a 0..1 score. Codes and links win outright."""
        for code in _CODE.findall(text):
            if code in self.by_code:
                return self.by_code[code], 1.0
        for p in self.products:
            if p.url and p.url.rstrip("/") in text:
                return p, 1.0
        asked = _tokens(text)
        if not asked:
            return None, 0.0
        best, best_score = None, 0.0
        for p in self.products:
            name = _tokens(f"{p.name} {p.name_en}")
            if not name:
                continue
            hit = len(asked & name)
            score = hit / min(len(name), 4)
            if score > best_score:
                best, best_score = p, score
        if best_score < 0.5:
            return None, best_score
        return best, min(best_score, 0.95)
