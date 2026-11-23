"""Step 3: read public tt.ua product pages and write eval/catalog.json.

Read-only GETs, one request at a time, >= 2.5 s apart, ordinary browser
User-Agent. Raw HTML is cached in CACHE_DIR (outside eval/) so a re-run does
not hit the site again. A page that fails is recorded with "error", never
filled in by hand.
Input: targets.json, list of {"slug": ...} | {"code": ...} | {"search": ...}.
Usage: scrape_catalog.py targets.json CACHE_DIR OUT.json
"""
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
DELAY = 2.5
_last = [0.0]

TYPE_EN = [
    ("Вбудований холодильник", "Built-in refrigerator"), ("Холодильник", "Refrigerator"),
    ("Прально-сушильна машина", "Washer-dryer"), ("Пральна машина", "Washing machine"),
    ("Сушильна машина", "Tumble dryer"), ("Вбудована посудомийна машина", "Built-in dishwasher"),
    ("Посудомийна машина", "Dishwasher"), ("Осушувач повітря", "Dehumidifier"),
    ("Робот-пилосос", "Robot vacuum"), ("Пилосос", "Vacuum cleaner"),
    ("Зарядна станція", "Portable power station"), ("Планетарний міксер", "Stand mixer"),
    ("Міксер", "Mixer"), ("Варильна поверхня", "Hob"), ("Плита комбінована", "Dual-fuel cooker"),
    ("Плита газова", "Gas cooker"), ("Плита", "Cooker"), ("Плитка електрична", "Electric hotplate"),
    ("Слайсер", "Slicer"), ("Ломтерізка", "Slicer"), ("Мультимейкер", "Multi-maker"),
    ("Праска", "Iron"), ("Мультипіч", "Air fryer oven"), ("Витяжка", "Cooker hood"),
    ("Духова шафа", "Oven"), ("Духовка", "Oven"), ("Водонагрівач", "Water heater"),
    ("З'єднувальна планка", "Stacking kit"), ("Кавоварка", "Coffee maker"), ("Телевізор", "TV"),
]


def name_en(name):
    for uk, en in TYPE_EN:
        if name.startswith(uk):
            rest = name[len(uk):].strip()
            rest = rest.replace("вбуд.", "built-in").replace("вбудований", "built-in").replace("вбудована", "built-in")
            rest = rest.replace("похила", "angled").replace("телескопічна", "telescopic").replace("газова", "gas")
            rest = rest.replace("електрична", "electric").replace("індукційна", "induction").replace("чорний", "black")
            rest = rest.replace("комбінована", "combined").replace("повновбудовувана", "fully built-in")
            return f"{en} {rest}".strip()
    return name


def fetch(url, cache):
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    path = os.path.join(cache, key + ".html")
    if os.path.exists(path):
        return 200, open(path, encoding="utf-8").read(), "cache"
    wait = DELAY - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "uk-UA,uk;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            code = r.status
            final = r.geturl()
    except urllib.error.HTTPError as e:
        _last[0] = time.time()
        return e.code, "", url
    except Exception as e:  # network error
        _last[0] = time.time()
        return 0, str(e), url
    _last[0] = time.time()
    open(path, "w", encoding="utf-8").write(body)
    return code, body, final


def txt(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def parse(body, url):
    h1 = re.search(r'<h1 class="product-page__head--title">(.*?)</h1>', body, re.S)
    if not h1:
        return None
    meta = dict(re.findall(r'<meta itemprop="(sku|category|price|availability|brand)" content\s*=\s*"([^"]*)"', body))
    label = re.search(r'product-main__labels--item (?:in-stock|out-of-stock|preorder|[a-z-]*stock[a-z-]*|order[a-z-]*)"[^>]*>(.*?)</span>', body, re.S)
    if not label:
        label = re.search(r'product-main__labels--item (?!delivery)[a-z-]+"[^>]*>(.*?)</span>', body, re.S)
    deliv = re.search(r'product-main__labels--item delivery">(.*?)</span>', body, re.S)
    old = re.search(r'<div class="product-main__info-main ?"> <div class="price"> <span class="price_old">([^<]*)</span>',
                    re.sub(r"\s+", " ", body))
    crumbs = [txt(x) for x in re.findall(r'<span itemprop="name">(.*?)</span>', body, re.S)]
    specs = []
    for chunk in body.split('product-page__specification--item">')[1:]:
        m = re.match(r'\s*<span class="head">(.*?)</span>\s*<div class="value[^"]*">(.*)', chunk, re.S)
        if not m:
            continue
        val = re.split(r'<div class="custom-tooltip"|</div>', m.group(2), 1)[0]
        item = f"{txt(m.group(1))}: {txt(val)}"
        if item not in specs:
            specs.append(item)
    return {
        "code": meta.get("sku"),
        "name": txt(h1.group(1)),
        "price_uah": int(float(meta["price"])) if meta.get("price") else None,
        "price_old_uah": int(re.sub(r"\D", "", old.group(1))) if old and re.sub(r"\D", "", old.group(1)) else None,
        "stock_status": txt(label.group(1)) if label else None,
        "stock_schema": meta.get("availability"),
        "delivery_label": txt(re.sub(r"<svg.*?</svg>", "", deliv.group(1), flags=re.S)) if deliv else None,
        "category": meta.get("category"),
        "category_path": crumbs[1:-1],
        "specs_all": specs,
    }


def pick_specs(specs, n=5):
    skip = ("Країна", "Виробник", "Колір", "Гарантія від", "Комплектація")
    good = [s for s in specs if not s.startswith(skip)]
    return (good or specs)[:n]


def main(targets_path, cache, out_path):
    os.makedirs(cache, exist_ok=True)
    targets = json.load(open(targets_path, encoding="utf-8"))
    out = []
    for t in targets:
        rec = {"target": t, "source": t.get("from"), "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if t.get("slug"):
            url = "https://tt.ua/uk/" + t["slug"]
        else:
            q = t.get("code") or t.get("search")
            surl = "https://tt.ua/uk/search?keyword=" + urllib.parse.quote(q)
            code, body, _ = fetch(surl, cache)
            cards = re.findall(r'href="(https://tt\.ua/uk/[a-z0-9-]+)"[^>]*class="product-card__name">(.*?)</a>', body)
            if code != 200 or not cards:
                rec["error"] = f"search '{q}': http {code}, {len(cards)} results"
                out.append(rec)
                print("FAIL", rec["error"])
                continue
            url = cards[0][0]
            rec["search_query"] = q
            rec["search_first_result"] = txt(cards[0][1])
        code, body, final = fetch(url, cache)
        p = parse(body, url) if code == 200 else None
        if not p:
            rec["url"] = url
            rec["error"] = f"http {code}, product block not found" if code == 200 else f"http {code}"
            out.append(rec)
            print("FAIL", url, rec["error"])
            continue
        if t.get("code") and p["code"] != str(t["code"]):
            rec["warning"] = f"searched code {t['code']}, page sku {p['code']}"
        if t.get("search"):
            toks = [x for x in re.split(r"[\s/]+", t["search"].upper()) if len(x) > 2]
            hit = sum(tok in p["name"].upper().replace(" ", "") or tok in p["name"].upper() for tok in toks)
            if hit < len(toks) - 1:
                rec["warning"] = f"search '{t['search']}' first result is '{p['name']}', may be a different model"
        rec = {k: v for k, v in rec.items() if k != "target"}
        rec.update({
            "code": p["code"], "name": p["name"], "name_en": name_en(p["name"]),
            "price_uah": p["price_uah"], "price_old_uah": p["price_old_uah"],
            "stock_status": p["stock_status"], "stock_schema": p["stock_schema"],
            "delivery_label": p["delivery_label"], "url": url,
            "category": p["category"], "category_path": p["category_path"],
            "specs": pick_specs(p["specs_all"]),
        })
        out.append(rec)
        print("OK", p["code"], p["price_uah"], p["stock_status"], "|", p["name"])
    json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("written", len(out), "ok", sum("error" not in r for r in out))


if __name__ == "__main__":
    main(*sys.argv[1:4])
