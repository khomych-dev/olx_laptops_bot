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

    # Remove Android/iOS versions to prevent the bot from mistaking "Android 12" for 12 GB of RAM
    ad_full_text_lower = re.sub(r"(android|ios)\s*\d+", "", ad_full_text_lower)

    # 1. 100% MODEL CHECK IN TITLE
    if "Модель" in filters and filters["Модель"]:
        model_words = filters["Модель"].lower().split()

        # Remove memory from the title (e.g., "10/256" or "128gb"), so "10" from memory doesn't count as Pixel 10
        clean_title = re.sub(r"\d+/\d+", "", title_lower)
        clean_title = re.sub(r"\d+\s*(gb|гб|tb|тб)", "", clean_title)

        title_words = re.findall(r"[a-zа-яіїєґ0-9]+", clean_title)
        title_raw = re.sub(r"\s+", "", clean_title)

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

            matched = False
            for syn in synonyms:
                if syn.isdigit():
                    # If it's a digit (10), it must be a separate word
                    if syn in title_words:
                        matched = True
                        break
                else:
                    if syn in clean_title or syn.replace(" ", "") in title_raw:
                        matched = True
                        break

            if not matched:
                return False  # Model does not match 100% - reject!

    # 2. MEMORY INTERSECTION RULE
    def check_memory_intersection(filter_key, api_keywords, typical_values):
        if filter_key not in filters or not filters[filter_key]:
            return True

        # What we are looking for (e.g., [256, 512])
        allowed_nums = []
        for opt in filters[filter_key]:
            allowed_nums.extend(re.findall(r"\d+", opt))

        if not allowed_nums:
            return True

        # What is specified in the ad
        found_memory_nums = set()

        # A) Search in API characteristics
        for api_kw in api_keywords:
            for k, v in ad.params.items():
                if api_kw in k.lower():
                    found_memory_nums.update(re.findall(r"\d+", v))

        # B) Search in the text (formats like 128gb or 12/256)
        found_memory_nums.update(
            re.findall(r"\b(\d{1,4})\s*(?:гб|gb|тб|tb)\b", ad_full_text_lower)
        )
        for m1, m2 in re.findall(r"\b(\d{1,2})/(\d{2,4})\b", ad_full_text_lower):
            if filter_key == "ОЗП":
                found_memory_nums.add(m1)
            else:
                found_memory_nums.add(m2)

        # Additionally: if a single digit typical of memory is present (e.g., "256")
        all_text_nums = re.findall(r"\b\d+\b", ad_full_text_lower)
        for num in all_text_nums:
            if num in typical_values:
                found_memory_nums.add(num)

        # LOGIC:
        if not found_memory_nums:
            # Scenario: Memory is not specified at all -> SKIP
            return True

        # Scenario: Memory is specified. Check if there is an INTERSECTION with our filter
        if any(num in allowed_nums for num in found_memory_nums):
            # The ad lists 128 and 256. We're looking for 256. Match found! -> SKIP
            return True

        # Scenario: The value in the cauldron is 128. We're looking for 256. No match -> REJECT
        return False

    typical_ram = ["1", "2", "3", "4", "6", "8", "12", "16", "24", "32", "64"]
    typical_storage = [
        "16",
        "32",
        "64",
        "128",
        "256",
        "512",
        "1000",
        "1024",
        "2000",
        "2048",
    ]

    if not check_memory_intersection(
        "Пам'ять (вбудована)", ["пам", "вбудована"], typical_storage
    ):
        return False
    if not check_memory_intersection("ОЗП", ["озп", "оперативна"], typical_ram):
        return False

    # 3. Keywords
    if "Ключові слова" in filters and filters["Ключові слова"]:
        kw_lower = re.sub(r"\s+", "", filters["Ключові слова"].lower())
        ad_raw = re.sub(r"\s+", "", ad_full_text_lower)
        if kw_lower not in ad_raw:
            return False

    # 4. Status
    if "Стан" in filters and filters["Стан"]:
        allowed_opts = [re.sub(r"\s+", "", opt.lower()) for opt in filters["Стан"]]
        found_val = None
        for k, v in ad.params.items():
            if "стан" in k.lower():
                found_val = v.lower()
                break

        if found_val:
            matched = False
            for opt in allowed_opts:
                if "нов" in opt and "нов" in found_val:
                    matched = True
                if "вживан" in opt and "вживан" in found_val:
                    matched = True
            if not matched:
                return False

    # 5. Price (additional insurance)
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
