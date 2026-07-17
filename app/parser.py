import urllib.parse
import re
from curl_cffi import requests
from dataclasses import dataclass, field

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

    if "Стан" in filters and filters["Стан"]:
        state_mapping = {"Новий": "new", "Вживаний": "used", "На запчастини": "damaged"}
        for idx, cond in enumerate(filters["Стан"]):
            if cond in state_mapping:
                params[f"filter_enum_state[{idx}]"] = state_mapping[cond]

    params["limit"] = 40
    params["offset"] = 0

    if params:
        return f"{base_url}?{urllib.parse.urlencode(params)}"
    return base_url


async def fetch_api(url: str) -> dict | None:
    try:
        async with requests.AsyncSession(impersonate="chrome120") as session:
            headers = {
                "Accept": "application/json",
                "Accept-Language": "uk-UA,uk;q=0.9",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            response = await session.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Помилка API {response.status_code} для {url}")
            return None
    except Exception as e:
        print(f"❌ Помилка завантаження {url}: {e}")
        return None


def parse_api(data: dict) -> list[AdItem]:
    items = []
    if not data or "data" not in data:
        print("❌ API повернув порожню відповідь або немає оголошень.")
        return items

    print(f"📥 API повернув {len(data['data'])} оголошень до локальної фільтрації.")

    for offer in data["data"]:
        try:
            ad_id = str(offer.get("id", ""))
            title = offer.get("title", "Без назви")
            url = offer.get("url", "")

            price = "Ціна не вказана"
            ad_params = {}

            for param in offer.get("params", []):
                key_name = param.get("name", "")
                val_obj = param.get("value", {})
                if isinstance(val_obj, dict):
                    ad_params[key_name] = val_obj.get("label", "")

                if param.get("key") == "price" and isinstance(val_obj, dict):
                    price = val_obj.get("label", "Ціна не вказана")

            image_url = ""
            photos = offer.get("photos", [])
            if photos:
                image_url = photos[0].get("link", "").replace(";s={width}x{height}", "")

            items.append(AdItem(ad_id, title, price, url, image_url, ad_params))
        except Exception as e:
            print(f"❌ Помилка парсингу картки API: {e}")
            continue
    return items


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", "", str(text).lower())


def passes_local_filter(ad: AdItem, filters: dict) -> bool:
    title_lower = ad.title.lower()
    ad_full_text_norm = normalize_text(
        title_lower + " " + " ".join(str(v) for v in ad.params.values())
    )
    params_norm = {normalize_text(k): normalize_text(v) for k, v in ad.params.items()}

    # 1. Model (if specified - search in the title, if not - skip model check)
    if "Модель" in filters and filters["Модель"]:
        model_words = filters["Модель"].lower().split()
        title_norm = normalize_text(title_lower)
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

            if not any(
                syn in title_lower or normalize_text(syn) in title_norm
                for syn in synonyms
            ):
                return False

    # 2. Smart memory filter (RAM and Built-in)
    def check_memory(filter_key, api_keywords):
        if filter_key not in filters or not filters[filter_key]:
            return True  # If filter is not specified - skip

        allowed_nums = []
        for opt in filters[filter_key]:
            allowed_nums.extend(re.findall(r"\d+", opt))

        if not allowed_nums:
            return True

        # Step A: Search for in API
        for api_kw in api_keywords:
            for k, v in params_norm.items():
                if api_kw in k:
                    found_nums = re.findall(r"\d+", v)
                    if found_nums:
                        if not any(num in allowed_nums for num in found_nums):
                            return False  # Memory specified in API is different
                        return True  # Memory specified in API is correct

        # Step B: If not in API, search for numbers near "GB" or with a slash (12/256)
        mem_nums = re.findall(r"(\d+)(?:гб|gb|тб|tb)", ad_full_text_norm)
        for m in re.findall(r"(\d+)/(\d+)", ad_full_text_norm):
            mem_nums.extend(m)

        if mem_nums:
            # Found mentions of memory in the text. Check if ours is among them
            if not any(num in allowed_nums for num in mem_nums):
                return False

        # If memory is not specified anywhere - skip the ad
        return True

    # Keywords for searching in the JSON API
    if not check_memory("Пам'ять (вбудована)", ["пам", "вбудована"]):
        return False
    if not check_memory("ОЗП", ["озп", "оперативна"]):
        return False

    # 3. Keywords
    if "Ключові слова" in filters and filters["Ключові слова"]:
        kw_lower = normalize_text(filters["Ключові слова"].lower())
        if kw_lower not in ad_full_text_norm:
            return False

    # 4. Price (insurance)
    price_num = int(re.sub(r"[^\d]", "", ad.price)) if re.search(r"\d", ad.price) else 0
    if price_num > 0:
        if (
            "Ціна від" in filters
            and filters["Ціна від"]
            and price_num < int(filters["Ціна від"])
        ):
            return False
        if (
            "Ціна до" in filters
            and filters["Ціна до"]
            and price_num > int(filters["Ціна до"])
        ):
            return False

    return True
