"""
Scraper de veille concurrentielle VO - Guyane
Fetch le stock Motork/CarkSpark, cherche les prix concurrents et génère un dashboard HTML.
"""

import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from urllib.parse import quote_plus
import time
import os
import sys

XML_URL = "https://carspark.dealerk.fr/myPortalXML/index?myPortalXMLkey=19eda390-14aa-4b91-b2af-69c30f534da7"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# ─────────────────────────────────────────────
# 1. FETCH & PARSE STOCK XML
# ─────────────────────────────────────────────

def fetch_stock():
    print("📦 Récupération du stock XML...")
    resp = requests.get(XML_URL, timeout=30, headers=HEADERS)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    vehicles = []
    for car in root.findall(".//car"):
        status = car.findtext("status", "")
        if status != "FREE":
            continue

        make_el = car.find("make")
        model_el = car.find("model")
        if make_el is None or model_el is None:
            continue

        def txt(tag):
            el = car.find(tag)
            return el.text.strip() if el is not None and el.text else ""

        price_raw = txt("priceB2c")
        km_raw = txt("km")
        hp_raw = txt("hp")

        photos = [img.text.strip() for img in car.findall(".//photos/photo") if img.text]

        vehicles.append({
            "id": car.get("id", ""),
            "externalId": car.get("externalId", ""),
            "make": make_el.text.strip() if make_el.text else "",
            "model": model_el.text.strip() if model_el.text else "",
            "version": txt("version"),
            "bodyType": txt("bodyType"),
            "fuelType": txt("fuelType"),
            "registrationDate": txt("registrationDate"),
            "color": car.findtext(".//exterior/color", ""),
            "price": float(price_raw) if price_raw else None,
            "km": int(km_raw) if km_raw else None,
            "hp": int(hp_raw) if hp_raw else None,
            "photo": photos[0] if photos else "",
            "competitors": [],
        })

    print(f"   → {len(vehicles)} véhicules trouvés")
    return vehicles


# ─────────────────────────────────────────────
# 2. SCRAPERS PAR SOURCE
# ─────────────────────────────────────────────

def parse_price(text):
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", text.replace("\xa0", "").replace(" ", ""))
    return int(cleaned) if cleaned else None


def parse_km(text):
    if not text:
        return None
    nums = re.findall(r"\d+", text.replace("\xa0", "").replace(" ", ""))
    return int(nums[0]) if nums else None


def search_cyphoma(make, model):
    results = []
    query = quote_plus(f"{make} {model}")
    url = f"https://www.cyphoma.com/guyane/annonces/voitures?search[title]={query}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        for card in soup.select("div.ad-container, div.annonce, article, li.ad"):
            link_el = card.select_one("a[href*='annonces/voitures']")
            if not link_el:
                link_el = card.select_one("a")
            if not link_el:
                continue

            title = link_el.get_text(separator=" ", strip=True)
            if not any(w.lower() in title.lower() for w in [make.lower(), model.lower()]):
                continue

            # Exclure nos propres annonces ("Les Occasions by Guyane Automobile")
            card_text = card.get_text(" ", strip=True).lower()
            href = link_el.get("href", "")
            if "guyane automobile" in card_text or "occasions by guyane" in card_text:
                continue
            if "guyane-automobile" in href.lower():
                continue

            if not href.startswith("http"):
                href = "https://www.cyphoma.com" + href

            price_el = card.select_one(".price, .prix, span.ad-price, strong")
            km_el = card.select_one(".km, .mileage, [class*='km']")

            results.append({
                "source": "Cyphoma",
                "title": title[:80],
                "price": parse_price(price_el.get_text() if price_el else ""),
                "km": parse_km(km_el.get_text() if km_el else ""),
                "url": href,
            })

    except Exception as e:
        print(f"   ⚠ Cyphoma [{make} {model}]: {e}")

    return results


def search_leboncoin(page, make, model):
    results = []
    query = quote_plus(f"{make} {model}")
    url = f"https://www.leboncoin.fr/cl/voitures/rp_guyane?text={query}"

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)

        # Accept cookies banner
        for btn_text in ["Tout accepter", "Accepter et fermer", "Accepter"]:
            try:
                btn = page.locator(f"button:has-text('{btn_text}')").first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    page.wait_for_timeout(1000)
                    break
            except Exception:
                pass

        cards = page.locator("a[data-qa-id='aditem_container']").all()

        for card in cards[:12]:
            try:
                title = card.locator("[data-qa-id='aditem_title']").inner_text(timeout=2000)
                price_raw = card.locator("span[aria-label*='€'], [data-qa-id='aditem_price']").first.inner_text(timeout=2000)
                href = card.get_attribute("href") or ""
                if not href.startswith("http"):
                    href = "https://www.leboncoin.fr" + href

                if not any(w.lower() in title.lower() for w in [make.lower(), model.lower()]):
                    continue

                # Try to get km from attributes row
                km_raw = ""
                try:
                    attrs = card.locator("[data-qa-id='aditem_detail']").inner_text(timeout=1000)
                    km_match = re.search(r"([\d\s]+)\s*km", attrs, re.IGNORECASE)
                    if km_match:
                        km_raw = km_match.group(1)
                except Exception:
                    pass

                results.append({
                    "source": "LeBonCoin",
                    "title": title.strip()[:80],
                    "price": parse_price(price_raw),
                    "km": parse_km(km_raw),
                    "url": href,
                })
            except Exception:
                continue

    except Exception as e:
        print(f"   ⚠ LeBonCoin [{make} {model}]: {e}")

    return results


def search_guyaneoccasions(page, make, model):
    results = []

    try:
        # Try search via query string
        query = quote_plus(f"{make} {model}")
        url = f"https://guyaneoccasions.com/?s={query}&post_type=vehicule"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        cards = page.locator("article, .vehicle-item, .car-item, .listing-item, .post").all()

        for card in cards[:12]:
            try:
                title_el = card.locator("h2, h3, .title, .vehicle-title").first
                title = title_el.inner_text(timeout=1000).strip()

                if not any(w.lower() in title.lower() for w in [make.lower(), model.lower()]):
                    continue

                price_raw = ""
                try:
                    price_raw = card.locator(".price, .prix, [class*='price']").first.inner_text(timeout=1000)
                except Exception:
                    pass

                href = ""
                try:
                    href = card.locator("a").first.get_attribute("href") or ""
                except Exception:
                    pass

                results.append({
                    "source": "GuyaneOccasions",
                    "title": title[:80],
                    "price": parse_price(price_raw),
                    "km": None,
                    "url": href,
                })
            except Exception:
                continue

    except Exception as e:
        print(f"   ⚠ GuyaneOccasions [{make} {model}]: {e}")

    return results


# ─────────────────────────────────────────────
# 3. ORCHESTRATION
# ─────────────────────────────────────────────

def run_scraping(vehicles):
    from playwright.sync_api import sync_playwright

    pairs = list({(v["make"], v["model"]) for v in vehicles})
    cache = {}

    print(f"\n🔍 Recherche concurrents pour {len(pairs)} marque/modèles...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="fr-FR",
            viewport={"width": 1280, "height": 800},
        )
        lbc_page = context.new_page()
        guo_page = context.new_page()

        for i, (make, model) in enumerate(pairs, 1):
            key = f"{make}|{model}"
            print(f"   [{i}/{len(pairs)}] {make} {model}")

            comps = []
            comps += search_cyphoma(make, model)
            comps += search_leboncoin(lbc_page, make, model)
            comps += search_guyaneoccasions(guo_page, make, model)

            cache[key] = comps
            time.sleep(1.5)

        browser.close()

    for v in vehicles:
        key = f"{v['make']}|{v['model']}"
        v["competitors"] = cache.get(key, [])

    return vehicles


# ─────────────────────────────────────────────
# 4. GÉNÉRATION HTML
# ─────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Veille Prix VO – Guyane</title>
<style>
:root{
  --bg:#0f172a;--surface:#1e293b;--border:#334155;
  --text:#e2e8f0;--muted:#94a3b8;--accent:#6366f1;
  --green:#22c55e;--red:#ef4444;--yellow:#f59e0b;
  --blue:#38bdf8;--tag-bg:#0f2942;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:14px;line-height:1.5}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}

/* HEADER */
header{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:100}
header h1{font-size:18px;font-weight:700;color:#fff;flex:1}
header .meta{font-size:12px;color:var(--muted)}
.badge{display:inline-block;background:var(--accent);color:#fff;font-size:11px;font-weight:600;padding:2px 8px;border-radius:99px;margin-left:8px}

/* FILTERS */
.filters{padding:16px 24px;display:flex;gap:12px;flex-wrap:wrap;background:var(--bg);border-bottom:1px solid var(--border)}
.filters input,.filters select{background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:7px 12px;font-size:13px;outline:none}
.filters input:focus,.filters select:focus{border-color:var(--accent)}
.filters input{width:220px}

/* STATS BAR */
.stats{padding:10px 24px;display:flex;gap:24px;border-bottom:1px solid var(--border);background:var(--bg)}
.stat{display:flex;flex-direction:column;gap:2px}
.stat .val{font-size:20px;font-weight:700;color:#fff}
.stat .lbl{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}

/* TABLE */
.table-wrap{overflow-x:auto;padding:16px 24px}
table{width:100%;border-collapse:collapse;min-width:900px}
th{background:var(--surface);color:var(--muted);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;padding:10px 12px;text-align:left;border-bottom:1px solid var(--border);cursor:pointer;white-space:nowrap;user-select:none}
th:hover{color:var(--text)}
th .sort-icon{margin-left:4px;opacity:.4}th.asc .sort-icon::after{content:'↑'}th.desc .sort-icon::after{content:'↓'}
tr.vehicle-row{transition:background .15s}
tr.vehicle-row:hover{background:rgba(255,255,255,.03)}
tr.vehicle-row td{padding:12px 12px;border-bottom:1px solid var(--border);vertical-align:middle}
tr.comp-row{display:none}
tr.comp-row.open{display:table-row}
tr.comp-row td{padding:0 0 0 48px;border-bottom:1px solid var(--border);background:rgba(15,23,42,.8)}

/* VEHICLE CELL */
.vehicle-thumb{width:60px;height:45px;object-fit:cover;border-radius:4px;background:var(--surface);display:block}
.make-model{font-weight:600;color:#fff;font-size:13px}
.version{font-size:11px;color:var(--muted);margin-top:2px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
.tag{background:var(--tag-bg);color:var(--blue);font-size:10px;padding:1px 6px;border-radius:4px}

/* PRICE CELL */
.our-price{font-size:16px;font-weight:700;color:#fff}
.km-val{font-size:11px;color:var(--muted)}

/* COMPETITORS MINI */
.comp-count{display:inline-flex;align-items:center;gap:5px;cursor:pointer;font-size:12px;padding:4px 10px;border-radius:6px;border:1px solid var(--border);background:var(--surface);transition:all .15s}
.comp-count:hover{border-color:var(--accent);color:var(--accent)}
.comp-count .n{font-weight:700;font-size:14px}
.comp-count.expanded{border-color:var(--accent);color:var(--accent)}

/* DIFF BADGE */
.diff{display:inline-block;font-size:11px;font-weight:600;padding:2px 7px;border-radius:5px}
.diff.cheaper{background:rgba(34,197,94,.15);color:var(--green)}
.diff.pricier{background:rgba(239,68,68,.15);color:var(--red)}
.diff.similar{background:rgba(245,158,11,.15);color:var(--yellow)}
.diff.nodata{background:rgba(148,163,184,.1);color:var(--muted)}

/* COMPETITOR TABLE */
.comp-table{width:100%;border-collapse:collapse;padding:12px 12px 12px 0}
.comp-table td{padding:8px 12px;font-size:12px;border-bottom:1px solid rgba(51,65,85,.5);vertical-align:middle}
.comp-table td:first-child{width:100px}
.src-badge{display:inline-block;font-size:10px;font-weight:600;padding:2px 7px;border-radius:4px}
.src-lbc{background:#d1231b22;color:#ff6b6b}
.src-cyphoma{background:#0ea5e922;color:#38bdf8}
.src-guyane{background:#22c55e22;color:#4ade80}

/* EMPTY */
.no-comp{padding:16px 12px;font-size:12px;color:var(--muted);font-style:italic}

/* BEST PRICE INDICATOR */
.best-marker{color:var(--green);font-size:10px;margin-left:4px;vertical-align:middle}

/* RESPONSIVE */
@media(max-width:768px){.filters input{width:100%}.stats{flex-wrap:wrap}}
</style>
</head>
<body>

<header>
  <h1>🚗 Veille Prix VO — Guyane</h1>
  <span class="meta">Actualisé le <strong id="updated-date">__UPDATED__</strong></span>
</header>

<div class="filters">
  <input type="text" id="search" placeholder="🔎 Marque, modèle, version…" oninput="filterTable()">
  <select id="filter-make" onchange="filterTable()"><option value="">Toutes les marques</option>__MAKES__</select>
  <select id="filter-fuel" onchange="filterTable()">
    <option value="">Tous carburants</option>
    <option>essence</option><option>diesel</option><option>électrique</option>
    <option>Hybride Rechargeable</option>
  </select>
  <select id="filter-comp" onchange="filterTable()">
    <option value="">Toutes concurrences</option>
    <option value="with">Avec concurrents trouvés</option>
    <option value="without">Sans concurrent trouvé</option>
    <option value="cheaper">Nous sommes moins chers</option>
    <option value="pricier">Nous sommes plus chers</option>
    <option value="src-Cyphoma">Source : Cyphoma</option>
    <option value="src-LeBonCoin">Source : LeBonCoin</option>
    <option value="src-GuyaneOccasions">Source : GuyaneOccasions</option>
  </select>
</div>

<div class="stats">
  <div class="stat"><span class="val" id="stat-total">__TOTAL__</span><span class="lbl">Véhicules en stock</span></div>
  <div class="stat"><span class="val" id="stat-with-comp">__WITH_COMP__</span><span class="lbl">Avec prix concurrent</span></div>
  <div class="stat"><span class="val green" id="stat-cheaper" style="color:var(--green)">__CHEAPER__</span><span class="lbl">Nous moins chers</span></div>
  <div class="stat"><span class="val" id="stat-pricier" style="color:var(--red)">__PRICIER__</span><span class="lbl">Nous plus chers</span></div>
</div>

<div class="table-wrap">
<table id="main-table">
<thead>
  <tr>
    <th style="width:70px"></th>
    <th onclick="sortTable(1)">Véhicule <span class="sort-icon"></span></th>
    <th onclick="sortTable(2)">Km <span class="sort-icon"></span></th>
    <th onclick="sortTable(3)">1ère MEC <span class="sort-icon"></span></th>
    <th onclick="sortTable(4)">Notre prix <span class="sort-icon"></span></th>
    <th onclick="sortTable(5)">Concurrents <span class="sort-icon"></span></th>
    <th>Prix min concurrent</th>
    <th>Écart</th>
  </tr>
</thead>
<tbody id="tbody">
__ROWS__
</tbody>
</table>
</div>

<script>
const DATA = __DATA_JSON__;

function toggleComp(id){
  const row=document.getElementById('comp-'+id);
  const btn=document.getElementById('btn-'+id);
  if(row.classList.contains('open')){
    row.classList.remove('open');
    btn.classList.remove('expanded');
  } else {
    row.classList.add('open');
    btn.classList.add('expanded');
  }
}

function filterTable(){
  const search=document.getElementById('search').value.toLowerCase();
  const make=document.getElementById('filter-make').value.toLowerCase();
  const fuel=document.getElementById('filter-fuel').value.toLowerCase();
  const comp=document.getElementById('filter-comp').value;

  document.querySelectorAll('tr.vehicle-row').forEach(tr=>{
    const vid=tr.dataset.id;
    const v=DATA[vid];
    if(!v){return;}

    let show=true;
    if(search && !`${v.make} ${v.model} ${v.version}`.toLowerCase().includes(search)) show=false;
    if(make && v.make.toLowerCase()!==make) show=false;
    if(fuel && v.fuelType.toLowerCase()!==fuel) show=false;
    if(comp==='with' && v.competitors.length===0) show=false;
    if(comp==='without' && v.competitors.length>0) show=false;
    if(comp==='cheaper'){
      const minP=minPrice(v);
      if(minP===null||v.price===null||v.price<=minP) show=false;
    }
    if(comp==='pricier'){
      const minP=minPrice(v);
      if(minP===null||v.price===null||v.price>minP) show=false;
    }
    if(comp.startsWith('src-')){
      const src=comp.replace('src-','');
      const comps=v.competitors||[];
      if(!comps.some(c=>(c.source||'')===src)) show=false;
    }

    tr.style.display=show?'':'none';
    const cr=document.getElementById('comp-'+vid);
    if(cr&&!show) cr.style.display='none';
  });
}

function minPrice(v){
  const prices=v.competitors.map(c=>c.price).filter(p=>p&&p>1000);
  return prices.length?Math.min(...prices):null;
}

let sortCol=-1,sortDir=1;
function sortTable(col){
  const tbody=document.getElementById('tbody');
  const pairs=[...document.querySelectorAll('tr.vehicle-row')].map(tr=>{
    const cr=document.getElementById('comp-'+tr.dataset.id);
    return {main:tr,comp:cr};
  });
  if(sortCol===col) sortDir*=-1; else{sortCol=col;sortDir=1;}
  document.querySelectorAll('th').forEach((th,i)=>{
    th.classList.remove('asc','desc');
    if(i===col){th.classList.add(sortDir===1?'asc':'desc');}
  });
  pairs.sort((a,b)=>{
    const va=a.main.dataset['sort'+col]||'';
    const vb=b.main.dataset['sort'+col]||'';
    const na=parseFloat(va),nb=parseFloat(vb);
    if(!isNaN(na)&&!isNaN(nb)) return (na-nb)*sortDir;
    return va.localeCompare(vb,'fr')*sortDir;
  });
  pairs.forEach(({main,comp})=>{
    tbody.appendChild(main);
    if(comp) tbody.appendChild(comp);
  });
}
</script>
</body>
</html>
"""


def source_badge_class(source):
    s = source.lower()
    if "leboncoin" in s:
        return "src-lbc"
    if "cyphoma" in s:
        return "src-cyphoma"
    return "src-guyane"


def diff_badge(our_price, comp_prices):
    if not our_price:
        return '<span class="diff nodata">—</span>'
    valid = [p for p in comp_prices if p and p > 1000]
    if not valid:
        return '<span class="diff nodata">Pas de donnée</span>'
    min_p = min(valid)
    diff = our_price - min_p
    pct = round(diff / min_p * 100)
    if diff < -500:
        return f'<span class="diff cheaper">Moins cher de {abs(pct)}%</span>'
    elif diff > 500:
        return f'<span class="diff pricier">Plus cher de {pct}%</span>'
    else:
        return '<span class="diff similar">Prix similaire</span>'


def generate_html(data):
    vehicles = data["vehicles"]
    updated = datetime.fromisoformat(data["updated_at"]).strftime("%d/%m/%Y à %Hh%M")

    makes_set = sorted({v["make"] for v in vehicles if v["make"]})
    makes_html = "".join(f'<option value="{m.lower()}">{m}</option>' for m in makes_set)

    total = len(vehicles)
    with_comp = sum(1 for v in vehicles if v["competitors"])
    cheaper = 0
    pricier = 0
    for v in vehicles:
        prices = [c["price"] for c in v["competitors"] if c.get("price") and c["price"] > 1000]
        if prices and v["price"]:
            if v["price"] < min(prices):
                cheaper += 1
            elif v["price"] > min(prices):
                pricier += 1

    data_index = {v["id"]: v for v in vehicles}

    rows_html = ""
    for v in vehicles:
        vid = v["id"]
        comps = v["competitors"]
        comp_prices = [c["price"] for c in comps if c.get("price") and c["price"] > 1000]
        min_comp = min(comp_prices) if comp_prices else None
        n_comps = len(comps)

        photo_html = (
            f'<img class="vehicle-thumb" src="{v["photo"]}" loading="lazy" alt="">'
            if v["photo"]
            else '<div class="vehicle-thumb"></div>'
        )

        fuel_tag = f'<span class="tag">{v["fuelType"]}</span>' if v["fuelType"] else ""
        body_tag = f'<span class="tag">{v["bodyType"]}</span>' if v["bodyType"] else ""

        price_fmt = f'{int(v["price"]):,}€'.replace(",", " ") if v["price"] else "—"
        km_fmt = f'{int(v["km"]):,} km'.replace(",", " ") if v["km"] else "—"
        min_comp_fmt = f'{int(min_comp):,}€'.replace(",", " ") if min_comp else "—"

        comp_btn_html = (
            f'<button class="comp-count" id="btn-{vid}" onclick="toggleComp(\'{vid}\')">'
            f'<span class="n">{n_comps}</span> annonce{"s" if n_comps > 1 else ""} ▾</button>'
            if n_comps > 0
            else '<span style="color:var(--muted);font-size:12px">Aucun</span>'
        )

        diff_html = diff_badge(v["price"], comp_prices)

        # Sort data attributes: col2=km, col3=1ère MEC
        sort2 = v["km"] or 0
        sort3 = v["registrationDate"] or ""
        sort4 = v["price"] or 0
        sort5 = n_comps

        rows_html += f"""
<tr class="vehicle-row" data-id="{vid}" data-sort1="{v['make']} {v['model']}" data-sort2="{sort2}" data-sort3="{sort3}" data-sort4="{sort4}" data-sort5="{sort5}">
  <td>{photo_html}</td>
  <td>
    <div class="make-model">{v['make']} {v['model']}</div>
    <div class="version" title="{v['version']}">{v['version']}</div>
    <div class="tags">{fuel_tag}{body_tag}</div>
  </td>
  <td style="white-space:nowrap">{km_fmt}</td>
  <td style="white-space:nowrap">{v['registrationDate'] or '—'}</td>
  <td><div class="our-price">{price_fmt}</div></td>
  <td>{comp_btn_html}</td>
  <td><span style="font-weight:600;color:#fff">{min_comp_fmt}</span></td>
  <td>{diff_html}</td>
</tr>"""

        # Competitor detail row
        if comps:
            comp_rows = ""
            for c in comps:
                price_c = f'{int(c["price"]):,}€'.replace(",", " ") if c.get("price") else "—"
                km_c = f'{int(c["km"]):,} km'.replace(",", " ") if c.get("km") else "—"
                best = "⭐" if c.get("price") and c["price"] == min_comp else ""
                badge_cls = source_badge_class(c["source"])
                link_html = (
                    f'<a href="{c["url"]}" target="_blank" rel="noopener">{c["title"][:60]}</a>'
                    if c.get("url")
                    else c.get("title", "")[:60]
                )
                comp_rows += f"""
<tr>
  <td><span class="src-badge {badge_cls}">{c['source']}</span></td>
  <td>{link_html}{best}</td>
  <td style="white-space:nowrap">{km_c}</td>
  <td style="white-space:nowrap;font-weight:600">{price_c}</td>
</tr>"""

            rows_html += f"""
<tr class="comp-row" id="comp-{vid}">
  <td colspan="8">
    <table class="comp-table">
      <thead><tr>
        <th style="font-size:11px;color:var(--muted);padding:6px 12px">Source</th>
        <th style="font-size:11px;color:var(--muted)">Annonce</th>
        <th style="font-size:11px;color:var(--muted)">Km</th>
        <th style="font-size:11px;color:var(--muted)">Prix</th>
      </tr></thead>
      <tbody>{comp_rows}</tbody>
    </table>
  </td>
</tr>"""
        else:
            rows_html += f'<tr class="comp-row" id="comp-{vid}"><td colspan="8"><div class="no-comp">Aucune annonce concurrente trouvée pour ce modèle.</div></td></tr>'

    data_js = json.dumps({v["id"]: v for v in vehicles}, ensure_ascii=False)

    html = (
        HTML_TEMPLATE
        .replace("__UPDATED__", updated)
        .replace("__MAKES__", makes_html)
        .replace("__TOTAL__", str(total))
        .replace("__WITH_COMP__", str(with_comp))
        .replace("__CHEAPER__", str(cheaper))
        .replace("__PRICIER__", str(pricier))
        .replace("__ROWS__", rows_html)
        .replace("__DATA_JSON__", data_js)
    )

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Dashboard généré : index.html ({len(html)//1024} Ko)")


# ─────────────────────────────────────────────
# 5. MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    skip_scrape = "--no-scrape" in sys.argv

    vehicles = fetch_stock()

    if not skip_scrape:
        vehicles = run_scraping(vehicles)
    else:
        print("⏩ Scraping ignoré (--no-scrape)")

    data = {
        "updated_at": datetime.now().isoformat(),
        "vehicles": vehicles,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("💾 data.json sauvegardé")

    generate_html(data)
