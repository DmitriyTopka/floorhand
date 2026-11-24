import json

import pytest

from floorhand import config
from floorhand.bot import Bot
from floorhand.catalog import Catalog, Product
from floorhand.drafts import guard, template_drafts
from floorhand.store import Store

DEV = "k7Qm2Zp9Xc4Lr8Tv1Wb6Yn3Ha5"
H = {"X-Device-Key": DEV}

FRIDGE = Product(code="200413", name="Холодильник BOSCH KGN39VLEB", name_en="Bosch KGN39VLEB fridge",
                 price_uah=24999, stock_status="In stock", url="https://tt.ua/uk/bosch-kgn39vleb",
                 specs=["No Frost", "203 cm"])
MIXER = Product(code="111111", name="Планетарний міксер ZELMER ZKR 1355", name_en="Zelmer ZKR 1355 stand mixer",
                price_uah=7123, stock_status="Out of stock, can be ordered", url="https://tt.ua/uk/mikser-zelmer-zkr-1355")


def cat():
    return Catalog([FRIDGE, MIXER])


def test_match_by_code_link_and_words():
    c = cat()
    assert c.match("Код 200413 чи є?")[0] is FRIDGE
    assert c.match("https://tt.ua/uk/mikser-zelmer-zkr-1355 is it available?")[0] is MIXER
    assert c.match("do you have the zelmer mixer?")[0] is MIXER
    assert c.match("hello")[0] is None


def test_guard_flags_wrong_price_and_missing_product():
    ok = guard([{"text": "It costs 24 999 UAH and is in stock.", "confident": True}], FRIDGE)
    assert ok[0]["confident"] is True
    bad = guard([{"text": "It costs 19 999 UAH today.", "confident": True}], FRIDGE)
    assert bad[0]["confident"] is False
    none = guard([{"text": "Yes we have it.", "confident": True}], None)
    assert none[0]["confident"] is False


def test_template_drafts_use_catalog_only():
    d = template_drafts("is the fridge in stock?", FRIDGE)
    assert len(d) == 3 and "24 999 UAH" in d[0]["text"] and d[0]["confident"]
    assert all(not x["confident"] for x in template_drafts("hi", None))


class FakeBot(Bot):
    def __init__(self, store, catalog):
        super().__init__(store, catalog, token="test")
        self.sent = []

    def call(self, method, **params):
        self.sent.append((method, params))
        return {}

    def new_question(self, chat_id, name, text):
        t = self.store.add_ticket(chat_id, name, text)
        self.draft(t["id"])


def msg(chat_id, text):
    return {"message": {"chat": {"id": chat_id}, "from": {"first_name": "Anna"}, "text": text}}


def test_consent_then_question_then_reply(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DRAFTS", "template")
    s = Store(tmp_path)
    b = FakeBot(s, cat())
    b.handle_update(msg(42, "Код 200413 is it in stock?"))
    assert s.customer(42)["pending"] and not s.waiting()           # asked consent first, no ticket yet
    b.handle_update({"callback_query": {"id": "q", "data": "consent:human", "message": {"chat": {"id": 42}},
                                        "from": {"first_name": "Anna"}}})
    t = s.waiting()[0]
    assert t["status"] == "waiting" and t["draft_mode"] == "template" and t["product"] == "200413"
    b.reply(t["id"], t["drafts"][0]["text"])
    assert s.ticket(t["id"])["status"] == "sent"
    assert b.sent[-1][1]["chat_id"] == 42


def test_forget_deletes_customer_and_tickets(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DRAFTS", "template")
    s = Store(tmp_path)
    b = FakeBot(s, cat())
    s.set_customer(7, consent="ai")
    b.handle_update(msg(7, "zelmer mixer price?"))
    b.handle_update(msg(7, "/forget"))
    assert s.customer(7) == {} and not s.waiting()
    assert json.loads((tmp_path / "state.json").read_text())["tickets"] == []


def test_pairing_and_isolation(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import floorhand.api as api
    monkeypatch.setattr(config, "DRAFTS", "template")
    s = Store(tmp_path)
    b = FakeBot(s, cat())
    monkeypatch.setattr(api, "store", s)
    monkeypatch.setattr(api, "bot", b)
    monkeypatch.setattr(api, "catalog", b.catalog)
    client = TestClient(api.app)
    code = client.get("/api/card", headers=H).json()["code"]
    b.handle_update(msg(1, f"/pair {code}"))
    for chat in (1, 2):
        s.set_customer(chat, consent="human")
        b.handle_update(msg(chat, "Код 200413 in stock?"))
    card = client.get("/api/card", headers=H).json()
    assert card["mode"] == "card" and card["queue"] == 1           # sees only own question
    tid = card["ticket"]["id"]
    r = client.post("/api/send", json={"ticket_id": tid, "draft": 0}, headers=H)
    assert r.status_code == 200
    assert client.get("/api/card", headers=H).json()["mode"] == "empty"


def test_low_confidence_cannot_be_sent(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import floorhand.api as api
    monkeypatch.setattr(config, "DRAFTS", "template")
    monkeypatch.setattr(config, "DEMO_ISOLATION", False)
    s = Store(tmp_path)
    b = FakeBot(s, cat())
    monkeypatch.setattr(api, "store", s)
    monkeypatch.setattr(api, "bot", b)
    client = TestClient(api.app)
    s.state["devices"][DEV] = {"owner_chat_id": 99, "paired_at": 0}
    s.set_customer(5, consent="human")
    b.handle_update(msg(5, "do you sell lawn mowers?"))
    tid = client.get("/api/card", headers=H).json()["ticket"]["id"]
    assert client.post("/api/send", json={"ticket_id": tid, "draft": 0}, headers=H).status_code == 409


def test_pair_rules(tmp_path):
    s = Store(tmp_path)
    code = s.pair_code_for(DEV)
    assert s.pair_code_for(DEV) == code                       # same device, same code
    assert s.confirm_pair("000000", 1) is None
    assert s.confirm_pair(code, 1) == DEV and s.is_paired(DEV)
    assert s.confirm_pair(code, 1) is None                    # single use
    assert all(s.pair_attempt_allowed(9) for _ in range(5)) and not s.pair_attempt_allowed(9)


def test_short_or_guessable_device_key_rejected():
    from fastapi.testclient import TestClient
    import floorhand.api as api
    assert TestClient(api.app).get("/api/card", headers={"X-Device-Key": "g2-123"}).status_code == 400


def test_pair_codes_flood_only_evicts_the_flooder(tmp_path):
    s = Store(tmp_path)
    s.NEW_DEVICES_PER_IP, s.MAX_CODES = 3, 4
    keys = [f"device-key-number-{i:04d}-abcdef" for i in range(8)]
    victim = s.pair_code_for(keys[0], "9.9.9.9")
    for i in range(1, 4):                            # attacker fills its quota from one IPv6 /64
        s.pair_code_for(keys[i], f"2001:db8::{i}")
    with pytest.raises(Store.PairingBusy):
        s.pair_code_for(keys[4], "2001:db8::99")     # same /64, over its limit
    s.pair_code_for(keys[5], "8.8.8.8")              # table full: attacker's oldest code goes
    assert s.confirm_pair(victim, 1) == keys[0]      # the honest code survived


def test_evicted_code_number_is_never_reissued(tmp_path):
    s = Store(tmp_path)
    s.NEW_DEVICES_PER_IP, s.MAX_CODES = 5, 2
    a = s.pair_code_for("device-key-number-aaaa-abcdef", "1.1.1.1")
    s.pair_code_for("device-key-number-bbbb-abcdef", "1.1.1.1")
    s.pair_code_for("device-key-number-cccc-abcdef", "2.2.2.2")   # evicts a
    assert a in s.state["retired_codes"]
    assert s.confirm_pair(a, 1) is None                              # old number pairs nothing


def test_global_rate_limit_on_new_codes(tmp_path):
    s = Store(tmp_path)
    s.NEW_CODES_PER_MINUTE = 3
    for i in range(3):
        s.pair_code_for(f"device-key-number-{i:04d}-abcdef", f"10.0.0.{i}")
    with pytest.raises(Store.PairingBusy):
        s.pair_code_for("device-key-number-9999-abcdef", "10.0.0.9")


def test_price_check_does_not_glue_model_digits_to_price():
    from floorhand.drafts import _price_ok
    fridge = Product(code="198793", name="Холодильник SAMSUNG RB38C679ES9", name_en="Refrigerator SAMSUNG RB38C679ES9",
                     price_uah=31499, stock_status="In stock", url="https://tt.ua/uk/holodilnik-samsung-rb38c679es9")
    assert _price_ok("Yes, we have the Refrigerator SAMSUNG RB38C679ES9. 31 499 UAH.", fridge)
    assert _price_ok("RB38C679ES9: 31,499.00 UAH", fridge)
    assert _price_ok("It is 31499 грн", fridge)
    assert _price_ok("It is 31 499 ₴", fridge)
    assert not _price_ok("RB38C679ES9. 29 999 UAH", fridge)
    assert not _price_ok("Now 31 999 UAH, was 33 704 UAH", fridge)
    assert not _price_ok("only 999 UAH", fridge)


def test_policy_amounts_and_old_price_pass_the_price_check():
    from floorhand.catalog import delivery_en
    from floorhand.drafts import _price_ok, policy
    text, amounts = policy()
    assert "Pickup points" in text and {20, 150, 1000} <= amounts
    p = Product(code="1", name="x", price_uah=31499, price_old_uah=33704, stock_status="In stock", url="u")
    assert _price_ok("31 499 UAH now, was 33 704 UAH. Carrying up is 150 UAH per floor.", p)
    assert not _price_ok("31 499 UAH now, was 35 000 UAH.", p)
    assert "Old price" in p.facts()
    assert delivery_en("На складі") == "In the warehouse" and delivery_en("Доставка 1-2 дні") == "Delivery 1-2 days"


def test_policy_amount_cannot_pass_as_item_price():
    from floorhand.drafts import _price_ok
    p = Product(code="1", name="x", price_uah=31499, price_old_uah=33704, stock_status="In stock", url="u")
    assert not _price_ok("This fridge is 1000 UAH.", p)
    assert not _price_ok("It costs 150 UAH.", p)
    assert not _price_ok("Today only 33 704 UAH.", p)
    assert _price_ok("31 499 UAH (was 33 704 UAH)", p)
    assert _price_ok("You pay the carrier plus a 2% fee and 20 UAH for the envelope.", p)
    cheap = Product(code="2", name="y", price_uah=500, price_old_uah=400, stock_status="In stock", url="u")
    assert not _price_ok("500 UAH, was 400 UAH", cheap)
