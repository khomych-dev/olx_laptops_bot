import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi import requests
from dataclasses import dataclass

CATEGORY_URLS = {
    "Ноутбук": "https://www.olx.ua/uk/elektronika/noutbuki-i-aksesuary/noutbuki/",
    "Телефон": "https://www.olx.ua/uk/elektronika/telefony-i-aksesuary/mobilnye-telefony-smartfony/",
    "Планшет": "https://www.olx.ua/uk/elektronika/planshety-el-knigi-i-aksesuary/planshety/",
}


@dataclass
class AdItem:
    ad_id: str
    title: str
    price: str
    url: str
    image_url: str


def build_url(category: str, filters: dict, brand: str = None) -> str:
    """Generates a URL by passing the brand and other text parameters to the OLX search."""
    base_url = CATEGORY_URLS.get(category, "https://www.olx.ua/uk/list/")
    params = {}

    search_query = []
    # Add the brand to the OLX search query
    if brand:
        search_query.append(brand)
    if "Модель" in filters and filters["Модель"]:
        search_query.append(filters["Модель"])
    if "Ключові слова" in filters and filters["Ключові слова"]:
        search_query.append(filters["Ключові слова"])

    if search_query:
        params["q"] = " ".join(search_query)

    if "Ціна від" in filters and filters["Ціна від"]:
        params["search[filter_float_price:from]"] = filters["Ціна від"]
    if "Ціна до" in filters and filters["Ціна до"]:
        params["search[filter_float_price:to]"] = filters["Ціна до"]

    if params:
        return f"{base_url}?{urllib.parse.urlencode(params)}"
    return base_url


async def fetch_html(url: str) -> BeautifulSoup | None:
    try:
        async with requests.AsyncSession(impersonate="chrome120") as session:
            response = await session.get(url, timeout=15)
            if response.status_code == 200:
                return BeautifulSoup(response.text, "html.parser")
            return None
    except Exception as e:
        print(f"Помилка завантаження {url}: {e}")
        return None


def parse_html(soup: BeautifulSoup) -> list[AdItem]:
    items = []
    cards = soup.find_all("div", attrs={"data-cy": "l-card"})

    for card in cards:
        try:
            link_tag = card.find("a")
            if not link_tag or not link_tag.get("href"):
                continue

            url = link_tag.get("href")
            if url.startswith("/"):
                url = f"https://www.olx.ua{url}"

            ad_id = (
                url.split("-ID")[-1].split(".")[0]
                if "-ID" in url
                else url.split("/")[-1].split(".")[0]
            )

            # Improved Title Search
            title_tag = card.find("h6")
            if title_tag:
                title = title_tag.text.strip()
            else:
                # If h6 is not found, extract text from the entire link block
                title = " ".join(link_tag.text.split()) if link_tag else "Без назви"

            price_tag = card.find("p", attrs={"data-testid": "ad-price"})
            price = price_tag.text.strip() if price_tag else "Ціна не вказана"

            # We retrieve the actual image, ignoring the empty placeholders
            img_tag = card.find("img")
            image_url = ""
            if img_tag:
                image_url = img_tag.get("src") or img_tag.get("data-src") or ""
                # If the URL is not a valid link, discard it
                if not image_url.startswith("http"):
                    image_url = ""

            items.append(AdItem(ad_id, title, price, url, image_url))
        except Exception as e:
            print(f"Помилка парсингу картки: {e}")
            continue
    return items


def passes_local_filter(ad: AdItem, filters: dict) -> bool:
    """
    We've removed the strict brand check.
    OLX will find the necessary brands itself through the URL.
    """
    return True
