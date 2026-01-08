import os
import httpx
import pandas as pd
from pathlib import Path
import json
import time
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# Load .env from repo root if available (optional; requires python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
except Exception:
    # python-dotenv not installed or .env missing — environment variables must be set manually
    pass


def google_search(api_key,search_engine_id,query,**params):
    base_url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": search_engine_id,
        "q": query,
        **params
    }
    response = httpx.get(base_url, params=params)
    response.raise_for_status()
    return response.json()

api_key = os.getenv("GOOGLE_API_KEY")
search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
if not api_key or not search_engine_id:
    raise ValueError("GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID must be set in environment variables.")


def fetch_page(url, timeout=10):
    try:
        r = httpx.get(url, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception:
        return ""


def extract_info_from_html(html):
    soup = BeautifulSoup(html, 'lxml')
    text = soup.get_text(' ', strip=True)
    info = {}
    # description
    og_desc = soup.select_one('meta[property="og:description"]')
    if og_desc and og_desc.get('content'):
        info['description'] = og_desc['content'].strip()
    else:
        meta_desc = soup.select_one('meta[name="description"]')
        info['description'] = meta_desc['content'].strip() if meta_desc and meta_desc.get('content') else ''

    # ingredients (look for 'ingredients' heading or label)
    ing = ''
    m = re.search(r'Ingredients[:\s]+([A-Za-z0-9,()\-\. %/]+)', text, re.I)
    if m:
        ing = m.group(1).strip()
    else:
        # try to find a block with the word 'ingredients'
        el = soup.find(lambda t: t.name in ("p", "div", "li") and t.get_text() and 'ingredient' in t.get_text().lower())
        if el:
            ing = el.get_text(' ', strip=True)
    info['ingredients_match'] = ing

    # SKU / barcode
    sku = ''
    m = re.search(r'(?:SKU|sku|UPC|EAN|Barcode)[:#\s]*([A-Z0-9\-]{4,})', text)
    if m:
        sku = m.group(1).strip()
    else:
        m2 = re.search(r'\b(\d{8,13})\b', text)
        if m2:
            sku = m2.group(1)
    info['sku_or_barcode'] = sku

    # country of origin
    country = ''
    m = re.search(r'(?:Made in|Country of Origin)[:\s]*([A-Za-z\s]+)', text, re.I)
    if m:
        country = m.group(1).strip()
    info['country_of_origin'] = country

    return info


def enrich_product(product, api_key, search_engine_id):
    name = product.get('product_name') or ''
    brand = product.get('brand') or ''
    query = f"{name} {brand} official site"

    try:
        res = google_search(api_key=api_key, search_engine_id=search_engine_id, query=query, num=5)
    except Exception as e:
        print(f"Google search failed for '{name}': {e}")
        return {'search_items': [], 'manufacturer_page': '', 'manufacturer_domain': '', 'brand_confirmed': False, 'description': '', 'sku_or_barcode': '', 'country_of_origin': '', 'ingredients_match': ''}

    items = res.get('items', [])
    enriched = {'search_items': items}

    manufacturer_page = ''
    manufacturer_domain = ''
    description = ''
    sku_or_barcode = ''
    country_of_origin = ''
    ingredients_match = ''
    brand_confirmed = False

    # examine top search results
    for item in items[:5]:
        link = item.get('link') or item.get('formattedUrl') or ''
        if not link:
            continue
        # prefer non-merchant domains and external official sites
        parsed = urlparse(link)
        domain = parsed.netloc.lower()

        # fetch the page and extract info
        html = fetch_page(link)
        if not html:
            continue
        info = extract_info_from_html(html)

        # check brand confirmation
        page_text = BeautifulSoup(html, 'lxml').get_text(' ', strip=True).lower()
        if brand and brand.lower() in page_text:
            brand_confirmed = True

        # choose the first external domain as manufacturer candidate (not qudobeauty)
        if 'qudobeauty.com' not in domain and not manufacturer_page:
            manufacturer_page = link
            manufacturer_domain = domain
            description = info.get('description','')
            sku_or_barcode = info.get('sku_or_barcode','')
            country_of_origin = info.get('country_of_origin','')
            ingredients_match = info.get('ingredients_match','')

        # stop early if we have confirmed brand and manufacturer
        if manufacturer_page and brand_confirmed:
            break

    enriched.update({
        'manufacturer_page': manufacturer_page,
        'manufacturer_domain': manufacturer_domain,
        'brand_confirmed': brand_confirmed,
        'description': description,
        'sku_or_barcode': sku_or_barcode,
        'country_of_origin': country_of_origin,
        'ingredients_match': ingredients_match
    })
    return enriched


def main():
    # load scraped products (repo root products.json)
    products_path = Path(__file__).resolve().parents[1] / 'products.json'
    if not products_path.exists():
        raise FileNotFoundError(f"Scraped products file not found at {products_path}. Run day1 scraper first.")

    products = json.loads(products_path.read_text(encoding='utf-8'))

    def is_complete(prod):
        keys = ['product_name', 'brand', 'ingredients', 'size_packaging', 'product_image_url', 'product_page_url']
        return all(prod.get(k) for k in keys)

    complete = [p for p in products if is_complete(p)]
    if len(complete) >= 10:
        to_enrich = complete[:10]
    else:
        print(f"Found {len(complete)} fully complete products; will enrich those and fill up to 10 with other products.")
        remainder = [p for p in products if p not in complete]
        to_enrich = complete + remainder[: max(0, 10 - len(complete))]

    enriched_list = []
    for p in to_enrich:
        print(f"Enriching: {p.get('product_name')}")
        data = enrich_product(p, api_key, search_engine_id)
        combined = {**p, **data}
        enriched_list.append(combined)
        time.sleep(1)  # be polite to API and sites

    # write outputs
    out_json = Path(__file__).resolve().parents[1] / 'day2_enriched_products.json'
    out_csv = Path(__file__).resolve().parents[1] / 'day2_enriched_products.csv'
    out_json.write_text(json.dumps(enriched_list, indent=2, ensure_ascii=False), encoding='utf-8')
    pd.json_normalize(enriched_list).to_csv(out_csv, index=False)
    print(f"Wrote enrichment to {out_json} and {out_csv}")


if __name__ == '__main__':
    main()
