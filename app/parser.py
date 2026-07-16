import urllib.parse
import re
from curl_cffi import requests
from dataclasses import dataclass, field

# Category mapping to OLX category IDs (based on typical OLX UA IDs)
CATEGORY_IDS = {
    "Ноутбук": 89,
    "Телефон": 85,
    "Планшет": 86,
}


@dataclass
class AdItem:
    ad_id: str
    title: str
    price: str
    url: str
    image_url: str
    params: dict = field(default_factory=dict)


def build_url(category: str, filters: dict, brand: str = None) -> str:
    base_url = "https://www.olx.ua/api/v1/offers/"
    params = {}

    if category in CATEGORY_IDS:
        params["category_id"] = CATEGORY_IDS[category]

    search_query = []
    if brand:
        search_query.append(brand)
    if "Модель" in filters and filters["Модель"]:
        search_query.append(filters["Модель"])
    if "Ключові слова" in filters and filters["Ключові слова"]:
        search_query.append(filters["Ключові слова"])

    if search_query:
        params["query"] = " ".join(search_query)

    if "Ціна від" in filters and filters["Ціна від"]:
        params["filter_float_price:from"] = filters["Ціна від"]
    if "Ціна до" in filters and filters["Ціна до"]:
        params["filter_float_price:to"] = filters["Ціна до"]

    if params:
        return f"{base_url}?{urllib.parse.urlencode(params)}"
    return base_url


async def fetch_api(url: str) -> dict | None:
    try:
        # Using a valid browser User-Agent and Chrome impersonation
        async with requests.AsyncSession(impersonate="chrome120") as session:
            # OLX API often checks for standard headers
            headers = {
                "Accept": "application/json",
                "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
            }
            response = await session.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Помилка {response.status_code} для {url}")
            return None
    except Exception as e:
        print(f"Помилка завантаження {url}: {e}")
        return None


def parse_api(data: dict) -> list[AdItem]:
    items = []
    if not data or "data" not in data:
        return items

    for offer in data["data"]:
        try:
            ad_id = str(offer.get("id", ""))
            title = offer.get("title", "Без назви")
            url = offer.get("url", "")

            # Extract price from params or directly if available
            price = "Ціна не вказана"

            # Extract characteristics
            ad_params = {}
            for param in offer.get("params", []):
                key_name = param.get("name", "")
                val_obj = param.get("value", {})
                if isinstance(val_obj, dict):
                    ad_params[key_name] = val_obj.get("label", "")

                if param.get("key") == "price" and isinstance(val_obj, dict):
                    price = val_obj.get("label", "Ціна не вказана")

            # Extract image
            image_url = ""
            photos = offer.get("photos", [])
            if photos:
                # Format the link by removing the sizing placeholder or setting a default size
                image_url = photos[0].get("link", "").replace(";s={width}x{height}", "")

            items.append(AdItem(ad_id, title, price, url, image_url, ad_params))
        except Exception as e:
            print(f"Помилка парсингу картки API: {e}")
            continue
    return items


def normalize_text(text: str) -> str:
    if not text:
        return ""
    # Remove spaces and convert to lowercase for robust matching
    return re.sub(r"\s+", "", text.lower())


def passes_local_filter(ad: AdItem, filters: dict) -> bool:
    title_lower = ad.title.lower()

    # Create a normalized version of ad's parameter values for easy searching
    ad_params_values_norm = [normalize_text(str(v)) for v in ad.params.values()]
    ad_params_all_text_norm = normalize_text(
        " ".join(str(v) for v in ad.params.values())
    )

    # 1. Flexible model check (understands both English and Ukrainian)
    if "Модель" in filters and filters["Модель"]:
        model_words = filters["Модель"].lower().split()
        for word in model_words:
            synonyms = [word]
            if word == "iphone":
                synonyms.append("айфон")
            elif word == "pixel":
                synonyms.append("піксель")
            elif word == "pro":
                synonyms.append("про")
            elif word in ("promax", "pro max"):
                synonyms.extend(["промакс", "про макс"])
            elif word == "samsung":
                synonyms.append("самсунг")
            elif word == "xiaomi":
                synonyms.extend(["сяомі", "ксіомі"])

            if not any(syn in title_lower for syn in synonyms):
                # Also check in params
                if not any(syn in ad_params_all_text_norm for syn in synonyms):
                    return False

    # 2. Strict filtering based on exact properties from JSON
    # We check if any of the allowed options in the filter partially matches any parameter value

    def check_param_match(filter_key, ad_values_norm):
        if filter_key in filters and filters[filter_key]:
            allowed = [normalize_text(opt) for opt in filters[filter_key]]
            # If "Новий" is in allowed, we should match "Новий" or "Нове" etc.
            # Using partial match because OLX labels can be "128 ГБ" while ours is "128 ГБ" etc.
            # But since we normalize by stripping spaces, "128гб" will match "128гб".
            for allowed_val in allowed:
                # E.g. allowed_val "128гб"
                if any(allowed_val in v for v in ad_values_norm):
                    return True
                # Special cases: "Вживаний" vs "Вживане"
                if "вживан" in allowed_val and any(
                    "вживан" in v for v in ad_values_norm
                ):
                    return True
                if "нов" in allowed_val and any("нов" in v for v in ad_values_norm):
                    return True
            return False
        return True  # Filter not active

    if not check_param_match("Пам'ять (вбудована)", ad_params_values_norm):
        return False

    if not check_param_match("ОЗП", ad_params_values_norm):
        return False

    if not check_param_match("Стан", ad_params_values_norm):
        return False

    if not check_param_match("Процесор", ad_params_values_norm):
        return False

    if not check_param_match("ОС", ad_params_values_norm):
        return False

    if "Ключові слова" in filters and filters["Ключові слова"]:
        kw_lower = filters["Ключові слова"].lower()
        if (
            kw_lower not in title_lower
            and normalize_text(kw_lower) not in ad_params_all_text_norm
        ):
            return False

    return True
