"""PII masking for TT dialog snippets. Regex pass; the 30 selected cases were
also read by eye and any leftover names were masked in selection.json."""
import re

RULES = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[email]"),
    (re.compile(r"(?<!\d)\+?3?8?\s?\(?0\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)"), "[phone]"),
    (re.compile(r"(?<!\d)\+?380\d{9}(?!\d)"), "[phone]"),
    (re.compile(r"…\d{3,4}"), "[phone]"),
    (re.compile(r"(?<!\d)20\d{12}(?!\d)"), "[ttn]"),          # Nova Poshta TTN
    (re.compile(r"(?<!\d)5\d{13}(?!\d)"), "[ttn]"),
    (re.compile(r"(№|N|номер|замовлення|заказ|заказа|замовленні|замовленню)\s*№?\s*\d{4,7}", re.I), r"\1 [order]"),
    (re.compile(r"(?<!\d)7[0-9]{5}(?!\d)"), "[order]"),       # bare order ids 76xxxx-77xxxx
    (re.compile(r"(Мене звати|Меня зовут|з вами|на зв'язку|на звʼязку)\s+[А-ЯЇІЄҐ][а-яїієґ']+", re.I), r"\1 [name]"),
    (re.compile(r"(вул\.?|вулиця|улица|ул\.|просп\.?|проспект|бульвар|пров\.?)\s+[^,\n]{2,40}(,\s*(буд\.?|б\.)?\s*\d+[а-я]?)?(,\s*(кв\.?|під'?їзд|подъезд)\s*\d+)*", re.I), "[address]"),
    (re.compile(r"(кв\.?|квартира)\s*\d+", re.I), "[address]"),
]

PHONE_CHECK = re.compile(r"\+?380[0-9 ]{9,}|(?<!\d)0[0-9]{9}(?!\d)")
EMAIL_CHECK = re.compile(r"@[a-z0-9.-]+\.[a-z]{2,}", re.I)


def mask(text):
    if not text:
        return text
    for rx, rep in RULES:
        text = rx.sub(rep, text)
    return text


def has_pii(text):
    return bool(PHONE_CHECK.search(text or "") or EMAIL_CHECK.search(text or ""))
