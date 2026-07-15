import urllib.parse
from bs4 import BeautifulSoup
from curl_cffi import requests
from dataclasses import dataclass

# Exact category paths on OLX Ukraine
CATEGORY_URLS = {
    "Ноутбук": "https://www.olx.ua/uk/elektronika/noutbuki-i-aksesuary/noutbuki/",
    "Телефон": "https://www.olx.ua/uk/elektronika/telefony-i-aksesuary/mobilnye-telefony-smartfony/",
    "Планшет": "https://www.olx.ua/uk/elektronika/planshety-el-knigi-i-aksesuary/planshety/",
}


def build_url(category: str, filters: dict) -> str:
    """Generates a search URL based on the category and basic filters."""
    base_url = CATEGORY_URLS.get(category, "https://www.olx.ua/uk/list/")
    params = {}

    # Text search (Model + Keywords)
    search_query = []
    if "Модель" in filters and filters["Модель"]:
        search_query.append(filters["Модель"])
    if "Ключові слова" in filters and filters["Ключові слова"]:
        search_query.append(filters["Ключові слова"])

    if search_query:
        params["q"] = " ".join(search_query)

    # Price filters (passed as GET parameters)
    if "Ціна від" in filters and filters["Ціна від"]:
        params["search[filter_float_price:from]"] = filters["Ціна від"]
    if "Ціна до" in filters and filters["Ціна до"]:
        params["search[filter_float_price:to]"] = filters["Ціна до"]

    # If there are parameters, add them to the URL
    if params:
        query_string = urllib.parse.urlencode(params)
        return f"{base_url}?{query_string}"

    return base_url


async def fetch_html(url: str) -> BeautifulSoup | None:
    """Downloads the page, simulating Chrome browser, and returns a BeautifulSoup object."""
    try:
        # impersonate="chrome120" bypasses basic bot protection
        async with requests.AsyncSession(impersonate="chrome120") as session:
            response = await session.get(url, timeout=15)

            if response.status_code == 200:
                return BeautifulSoup(response.text, "html.parser")
            else:
                print(f"Помилка доступу до {url}: Статус {response.status_code}")
                return None
    except Exception as e:
        print(f"Помилка завантаження {url}: {e}")
        return None


@dataclass
class AdItem:
    """A structure for storing data for a single ad."""

    ad_id: str
    title: str
    price: str
    url: str
    image_url: str


def parse_html(soup: BeautifulSoup) -> list[AdItem]:
    """Extracts a list of ads from the page's HTML code."""
    items = []
    # OLX places ads in blocks with the data-cy="l-card" attribute
    cards = soup.find_all("div", attrs={"data-cy": "l-card"})

    for card in cards:
        try:
            link_tag = card.find("a")
            if not link_tag or not link_tag.get("href"):
                continue

            url = link_tag.get("href")
            if url.startswith("/"):
                url = f"https://www.olx.ua{url}"

            # Extract the unique ad ID (needed for the database)
            # Example URL: .../noutbuk-hp-ID12345.html
            ad_id = "unknown"
            if "-ID" in url:
                ad_id = url.split("-ID")[-1].split(".")[0]
            else:
                ad_id = url.split("/")[-1].split(".")[0]

            # Find the title (usually in the h6 tag)
            title_tag = card.find("h6")
            title = title_tag.text.strip() if title_tag else "Без назви"

            # Find the price
            price_tag = card.find("p", attrs={"data-testid": "ad-price"})
            price = price_tag.text.strip() if price_tag else "Ціна не вказана"

            # Find the image
            img_tag = card.find("img")
            image_url = img_tag.get("src") if img_tag else ""

            items.append(
                AdItem(
                    ad_id=ad_id, title=title, price=price, url=url, image_url=image_url
                )
            )
        except Exception as e:
            print(f"Помилка парсингу картки оголошення: {e}")
            continue

    return items
