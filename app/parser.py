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


def passes_local_filter(ad: AdItem, filters: dict) -> bool:
    title_lower = ad.title.lower()
    ad_full_text_lower = (
        title_lower + " " + " ".join(str(v).lower() for v in ad.params.values())
    )

    # 1. 100% MODEL CHECK IN TITLE
    model_digits = []
    if "Модель" in filters and filters["Модель"]:
        # Normalize 'pro max' to prevent .split() from breaking it
        model_str = filters["Модель"].lower()
        model_str = model_str.replace("pro max", "promax").replace(
            "про макс", "промакс"
        )

        model_words = model_str.split()
        model_digits = re.findall(r"\d+", filters["Модель"])

        for word in model_words:
            synonyms = [word]
            if word == "iphone":
                synonyms.append("айфон")
            elif word == "pixel":
                synonyms.append("піксель")
            elif word == "pro":
                synonyms.append("про")
            elif word in ("promax", "промакс"):
                synonyms.extend(["pro max", "про макс", "промакс", "promax"])
            elif word == "samsung":
                synonyms.append("самсунг")
            elif word == "xiaomi":
                synonyms.extend(["сяомі", "ксіомі"])

            matched = False
            for syn in synonyms:
                syn_esc = re.escape(syn)
                # Strict boundaries: ensure the word/digit is not surrounded by other alphanumeric or Cyrillic characters
                # This prevents "10" from matching "100" or "iphone10", but successfully matches "10" in "10/256"
                if re.search(
                    rf"(?<![a-zа-я0-9ієїґ]){syn_esc}(?![a-zа-я0-9ієїґ])", title_lower
                ):
                    matched = True
                    break

            if not matched:
                return False

    # 2. INTERSECTION RULE FOR MEMORY & LAZY SELLER
    def check_memory_exact(filter_key, typical_values):
        if filter_key not in filters or not filters[filter_key]:
            return True

        allowed_nums = []
        for opt in filters[filter_key]:
            allowed_nums.extend(re.findall(r"\d+", opt))

        if not allowed_nums:
            return True

        # Extract all standalone digits from the entire ad
        all_ad_nums = set(re.findall(r"\d+", ad_full_text_lower))

        # Scenario 1: Exact match found anywhere in the ad
        if any(num in all_ad_nums for num in allowed_nums):
            return True

        # Scenario 2: No exact match. Check if seller specified a DIFFERENT typical memory size
        nums_to_check = [n for n in all_ad_nums if n not in model_digits]

        if any(num in nums_to_check for num in typical_values):
            # Seller indicated a memory size, but it doesn't match what we want
            return False

        # Scenario 3: Lazy seller (no typical memory sizes found in the ad at all)
        return True

    typical_ram = ["2", "3", "4", "6", "8", "12", "16", "24", "32"]
    typical_storage = ["64", "128", "256", "512", "1000", "1024", "2000", "2048"]

    if not check_memory_exact("Пам'ять (вбудована)", typical_storage):
        return False
    if not check_memory_exact("ОЗП", typical_ram):
        return False

    # 3. KEYWORDS
    if "Ключові слова" in filters and filters["Ключові слова"]:
        kw_lower = re.sub(r"\s+", "", filters["Ключові слова"].lower())
        ad_raw = re.sub(r"\s+", "", ad_full_text_lower)
        if kw_lower not in ad_raw:
            return False

    # 4. STATUS
    if "Стан" in filters and filters["Стан"]:
        allowed_opts = [re.sub(r"\s+", "", opt.lower()) for opt in filters["Стан"]]
        found_val = None
        for k, v in ad.params.items():
            if "стан" in k.lower():
                found_val = str(v).lower()
                break

        if found_val:
            matched = False
            for opt in allowed_opts:
                if "нов" in opt and "нов" in found_val:
                    matched = True
                if "вживан" in opt and "вживан" in found_val:
                    matched = True
                if "запчастини" in opt and "запчастини" in found_val:
                    matched = True
            if not matched:
                return False

    # 5. PRICE
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
