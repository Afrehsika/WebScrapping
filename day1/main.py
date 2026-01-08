import requests
from requests.exceptions import RequestException
from bs4 import BeautifulSoup
import pandas as pd
import time
from urllib.parse import urljoin

BASE_URL = "https://qudobeauty.com"
SHOP_URL = f"{BASE_URL}/shop/"

# Safety limits
MAX_PAGES = 100
MAX_PRODUCTS = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/85.0"
}

def get_soup(url):
    """Fetch and parse HTML."""
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")

def get_product_links():
    """Collect product links by crawling known category pages and paginating them.

    The site's shop listing is structured by category pages (e.g. /cat/wholesale-face-care/)
    which contain links to individual product pages under /product/. This function
    visits a set of categories and paginates through them to find product URLs.
    """
    links = set()

    # seed category pages known to contain skincare/face-care products
    categories = [
        f"{BASE_URL}/cat/wholesale-face-care/",
        f"{BASE_URL}/cat/wholesale-face-care/cleanser/",
        f"{BASE_URL}/cat/wholesale-face-care/serums/",
        f"{BASE_URL}/cat/wholesale-face-care/face-masks-beauty/",
    ]

    for cat in categories:
        for page in range(1, 6):  # limit per-category pages to avoid long runs
            url = cat if page == 1 else cat.rstrip('/') + f"/page/{page}/"
            print(f"Loading category page: {url}")
            try:
                soup = get_soup(url)
            except RequestException as e:
                print(f"Request failed for {url}: {e}")
                break

            # find links that point to product pages
            for a in soup.select('a[href*="/product/"]'):
                href = a.get('href')
                if not href:
                    continue
                full = urljoin(BASE_URL, href)
                if full.startswith(BASE_URL) and '/product/' in full:
                    links.add(full.split('?')[0])

            time.sleep(0.8)

            if len(links) >= MAX_PRODUCTS * 2:  # gather a buffer, we'll trim later
                break

        if len(links) >= MAX_PRODUCTS * 2:
            break

    print(f"Total product URLs found: {len(links)}")
    return list(links)


def parse_product(product_url):
    """Scrape product details from a product page."""
    print(f"Scraping: {product_url}")
    soup = get_soup(product_url)

    # Product name (try several fallbacks)
    title = soup.select_one("h1.product_title")
    if title and title.text.strip():
        name = title.text.strip()
    else:
        og_title = soup.select_one('meta[property="og:title"]')
        if og_title and og_title.get('content'):
            name = og_title['content'].strip()
        else:
            name = (soup.title.string or "").strip()

    # Featured image: try gallery image, then other common selectors, then meta/link fallbacks
    img = soup.select_one(
        "figure.woocommerce-product-gallery__wrapper img, div.woocommerce-product-gallery__image img, img.wp-post-image"
    )
    image_url = ""
    if img:
        image_url = img.get("src") or img.get("data-src") or img.get("data-large_image") or ""
    if not image_url:
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get('content'):
            image_url = og['content'].strip()
    if not image_url:
        link_img = soup.select_one('link[rel="image_src"]')
        if link_img and link_img.get('href'):
            image_url = link_img['href'].strip()

    # Category/type (posted_in or breadcrumbs)
    categories = [c.text.strip() for c in soup.select("span.posted_in a")]
    if not categories:
        # try breadcrumbs
        crumbs = [c.text.strip() for c in soup.select("nav.woocommerce-breadcrumb a")]
        categories = crumbs[:-1] if len(crumbs) > 1 else crumbs
    category = ", ".join(categories)
    # infer brand candidate from category tokens (used as fallback)
    inferred_brand = ""
    if categories:
        last = categories[-1].strip()
        low = last.lower()
        stopwords = {"wholesale", "products", "under", "makeup", "skincare"}
        if low and not any(sw in low for sw in stopwords) and len(last) < 40:
            inferred_brand = last

    # Ingredients & other info (if available)
    ingredients = ""
    size_packaging = ""
    brand = ""

    # WooCommerce product attributes (table)
    rows = soup.select("table.shop_attributes tr")
    for row in rows:
        th = row.select_one("th")
        td = row.select_one("td")
        if not th or not td:
            continue
        header = th.text.strip().lower()
        val = td.text.strip()

        if "ingredients" in header:
            ingredients = val
        if "size" in header or "volume" in header:
            size_packaging = val
        if "brand" in header:
            brand = val

    # If ingredients still empty, look for headings titled 'Ingredients' and grab following text
    if not ingredients:
        heading = soup.find(
            lambda t: t.name in ("h2", "h3", "h4", "strong", "b") and t.text and "ingredient" in t.text.lower()
        )
        if heading:
            # try next sibling paragraphs or lists
            sib = heading.find_next_sibling()
            if sib and sib.get_text(strip=True):
                ingredients = sib.get_text(" ", strip=True)
            else:
                # look inside tabs or description areas
                tab = soup.select_one(
                    '#tab-ingredients, #tab-ingredient, #tab-description, .woocommerce-Tabs-panel, .product-description, .woocommerce-product-details__short-description'
                )
                if tab and tab.get_text(strip=True):
                    ingredients = tab.get_text(" ", strip=True)
                else:
                    ingredients = heading.parent.get_text(" ", strip=True)
    # As a last resort, search the page for 'Ingredients:' label
    if not ingredients:
        import re
        text = soup.get_text(" ", strip=True)
        m = re.search(r"Ingredients[:\s]+([A-Za-z0-9,()\-\.% \/]+)", text)
        if m:
            ingredients = m.group(1).strip()

    # If still empty, try tab-description or short description
    if not ingredients:
        tab = soup.select_one('#tab-description') or soup.select_one('.woocommerce-product-details__short-description')
        if tab and tab.get_text(strip=True):
            ingredients = tab.get_text(" ", strip=True)

    # If brand empty, try meta, JSON-LD, or brand-like links
    if not brand:
        brand_meta = soup.select_one('meta[name="brand"]') or soup.select_one('meta[property="product:brand"]')
        if brand_meta and brand_meta.get('content'):
            brand = brand_meta['content'].strip()
    if not brand:
        import json
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                obj = json.loads(script.string or "{}")
            except Exception:
                continue
            items = obj if isinstance(obj, list) else [obj]
            for it in items:
                if not isinstance(it, dict):
                    continue
                b = it.get('brand')
                if isinstance(b, dict) and b.get('name'):
                    brand = b['name'].strip()
                    break
                if isinstance(b, str):
                    brand = b.strip()
                    break
            if brand:
                break
    if not brand:
        a = soup.select_one('a[href*="/brand/"]') or soup.select_one('a[rel="tag"]')
        if a and a.text.strip():
            brand = a.text.strip()
    if not brand and inferred_brand:
        brand = inferred_brand

    # Size/packaging: if not found in attributes, regex search in page text
    if not size_packaging:
        import re
        text = soup.get_text(" ", strip=True)
        m = re.search(r"\b\d+[\s-]?(?:ml|mL|g|kg|oz|oz\.|l|L)\b", text)
        if m:
            size_packaging = m.group(0)

    return {
        "product_name": name,
        "brand": brand,
        "category": category,
        "ingredients": ingredients,
        "size_packaging": size_packaging,
        "product_image_url": image_url,
        "product_page_url": product_url
    }


def main():
    product_links = get_product_links()

    products = []
    for i, link in enumerate(product_links[:MAX_PRODUCTS]):
        try:
            data = parse_product(link)
            products.append(data)
            time.sleep(1)  # be respectful
        except Exception as e:
            print(f"Error scraping {link}: {e}")

    # Save to CSV or JSON
    df = pd.DataFrame(products)
    df.to_csv("products.csv", index=False)
    df.to_json("products.json", orient="records", indent=2)

    print("Scraping complete! Data saved.")


if __name__ == "__main__":
    main()
