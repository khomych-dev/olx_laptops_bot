import urllib.parse
import re
from curl_cffi import requests
from dataclasses import dataclass, field

CATEGORY_IDS = {
    "Ноутбук": 80,
    "Телефон": 85,
    "Планшет": 3731,
}

brand_synonyms = {
    "apple": [
        "apple",
        "macbook",
        "iphone",
        "ipad",
        "айфон",
        "макбук",
        "айпад",
        "екпл",
        "епл",
    ],
    "samsung": ["samsung", "самсунг"],
    "xiaomi": ["xiaomi", "сяомі", "ксіомі", "ксиоми"],
    "google": ["google", "pixel", "гугл", "піксель"],
    "asus": ["asus", "асус"],
    "acer": ["acer", "асер", "ейсер"],
    "lenovo": ["lenovo", "леново"],
    "hp": ["hp", "хп", "ашпі"],
    "dell": ["dell", "делл"],
    "huawei": ["huawei", "хуавей"],
    "motorola": ["motorola", "моторола"],
    "oneplus": ["oneplus", "ванплас", "ванплюс"],
    "oppo": ["oppo", "оппо"],
    "realme": ["realme", "реалмі"],
    "vivo": ["vivo", "віво"],
    "honor": ["honor", "хонор"],
    "meizu": ["meizu", "мейзу"],
    "microsoft": ["microsoft", "мікрософт", "майкрософт"],
    "msi": ["msi", "мсі"],
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

    # Remove condition ratings (e.g., 9/10, 10/10) so the bot doesn't confuse them with digits
    clean_title = re.sub(r"\b(?:10|9|8|7|6|5)/10\b", "", title_lower)
    clean_full_text = re.sub(r"\b(?:10|9|8|7|6|5)/10\b", "", ad_full_text_lower)

    # 1. BRAND MATCHING
    if "Бренд" in filters and filters["Бренд"]:
        brands = [b.lower() for b in filters["Бренд"] if b]
        if brands:
            brand_matched = False

            explicit_brand_param = ""
            for k, v in ad.params.items():
                if "марка" in k.lower() or "бренд" in k.lower():
                    explicit_brand_param += str(v).lower() + " "

            for brand in brands:
                syns = brand_synonyms.get(brand, [brand])

                if explicit_brand_param:
                    if any(syn in explicit_brand_param for syn in syns):
                        brand_matched = True
                        break

                for syn in syns:
                    if re.search(
                        rf"(?<![a-zа-яієїґ]){re.escape(syn)}(?![a-zа-яієїґ])",
                        clean_full_text,
                    ):
                        brand_matched = True
                        break

                if brand_matched:
                    break

            if not brand_matched:
                return False

    # 2. MODEL MATCHING
    model_digits = []
    if "Модель" in filters and filters["Модель"]:
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
                synonyms.extend(["сяомі", "ксіомі", "ксиоми"])
            elif word == "macbook":
                synonyms.append("макбук")
            elif word == "ipad":
                synonyms.append("айпад")
            elif word == "air":
                synonyms.append("ейр")
            elif word == "galaxy":
                synonyms.extend(["галаксі", "гелаксі"])
            elif word == "ultra":
                synonyms.append("ультра")
            elif word == "plus":
                synonyms.extend(["плюс", "+"])

            matched = False
            for syn in synonyms:
                syn_esc = re.escape(syn)
                if syn.isdigit():
                    if re.search(rf"(?<!\d){syn_esc}(?!\d)", clean_title):
                        matched = True
                        break
                else:
                    if re.search(
                        rf"(?<![a-zа-яієїґ]){syn_esc}(?![a-zа-яієїґ])", clean_title
                    ):
                        matched = True
                        break

            if not matched:
                return False

    # 3. CPU MATCHING (Laptops)
    if "Процесор" in filters and filters["Процесор"]:
        cpu_mapping = {
            "intel core i3": ["i3", "core i3"],
            "intel core i5": ["i5", "core i5"],
            "intel core i7/i9": ["i7", "core i7", "i9", "core i9"],
            "amd ryzen 3": ["ryzen 3", "r3", "ryzen3"],
            "amd ryzen 5": ["ryzen 5", "r5", "ryzen5"],
            "amd ryzen 7/9": ["ryzen 7", "r7", "ryzen 9", "r9", "ryzen7", "ryzen9"],
            "apple m-серія": ["m1", "m2", "m3", "m4", "m-series", "m серія"],
        }
        cpu_matched = False
        for cpu in filters["Процесор"]:
            cpu_lower = cpu.lower()
            keywords = cpu_mapping.get(cpu_lower, [cpu_lower])
            if any(kw in clean_full_text for kw in keywords):
                cpu_matched = True
                break
        if not cpu_matched:
            return False

    # 4. OS MATCHING (Phones/Tablets)
    if "ОС" in filters and filters["ОС"]:
        os_matched = False
        for os_val in filters["ОС"]:
            os_lower = os_val.lower()
            if os_lower in clean_full_text:
                os_matched = True
                break
            if os_lower == "harmonyos" and "harmony" in clean_full_text:
                os_matched = True
                break
        if not os_matched:
            return False

    # 5. DIAGONAL MATCHING
    if "Діагональ" in filters and filters["Діагональ"]:
        ranges = []
        for opt in filters["Діагональ"]:
            opt_lower = opt.lower()
            nums = re.findall(r"\d+(?:\.\d+)?", opt_lower.replace(",", "."))
            if "до" in opt_lower and nums:
                ranges.append((0.0, float(nums[0])))
            elif "більше" in opt_lower and nums:
                ranges.append((float(nums[0]), 999.0))
            elif len(nums) == 2:
                ranges.append((float(nums[0]), float(nums[1])))
            elif len(nums) == 1:
                ranges.append((float(nums[0]), float(nums[0])))

        ad_diags = []
        for k, v in ad.params.items():
            if "діагональ" in k.lower():
                param_val = str(v).replace(",", ".")
                nums = re.findall(r"\d+(?:\.\d+)?", param_val)
                ad_diags.extend([float(n) for n in nums])

        text_diags = re.findall(
            r"\b(\d+(?:\.\d+)?)\s*(?:\"|''|дюйм)", clean_full_text.replace(",", ".")
        )
        ad_diags.extend([float(n) for n in text_diags])

        if ad_diags:
            diag_matched = False
            for ad_d in ad_diags:
                for r_min, r_max in ranges:
                    if r_min <= ad_d <= r_max:
                        diag_matched = True
                        break
                if diag_matched:
                    break
            if not diag_matched:
                return False

    # 6. INTERSECTION RULE AND "LAZY SELLER" RULE FOR MEMORY
    def check_memory_exact(filter_key, typical_values, is_ram=False):
        if filter_key not in filters or not filters[filter_key]:
            return True

        allowed_nums = []
        for opt in filters[filter_key]:
            allowed_nums.extend(re.findall(r"\d+", opt))

        if not allowed_nums:
            return True

        all_ad_nums = set(re.findall(r"\d+", clean_full_text))

        if any(num in all_ad_nums for num in allowed_nums):
            return True

        nums_to_check = set([n for n in all_ad_nums if n not in model_digits])

        if is_ram:
            explicit_ram = set()
            for m in re.finditer(
                r"\b(\d+)\s*(?:/|\\)\s*(?:64|128|256|512|1000|1024|2000|2048)\b",
                clean_full_text,
            ):
                explicit_ram.add(m.group(1))

            for m in re.finditer(r"\b(\d+)\s*(?:gb|гб|г|g)\b", clean_full_text):
                if m.group(1) in typical_values:
                    explicit_ram.add(m.group(1))

            for k, v in ad.params.items():
                if any(kw in k.lower() for kw in ["оперативна", "озп", "ram"]):
                    explicit_ram.update(re.findall(r"\d+", str(v).lower()))

            nums_to_check = nums_to_check.intersection(explicit_ram)
        else:
            explicit_storage = set()
            for m in re.finditer(
                r"\b(?:\d+)\s*(?:/|\\)\s*(\d+)\b",
                clean_full_text,
            ):
                explicit_storage.add(m.group(1))

            for m in re.finditer(r"\b(\d+)\s*(?:gb|гб|tb|тб)\b", clean_full_text):
                if m.group(1) in typical_values or int(m.group(1)) >= 32:
                    val = m.group(1)
                    explicit_storage.add(val)
                    if "tb" in m.group(0) or "тб" in m.group(0):
                        if val == "1":
                            explicit_storage.add("1000")
                        elif val == "2":
                            explicit_storage.add("2000")

            for k, v in ad.params.items():
                if any(
                    kw in k.lower()
                    for kw in ["вбудована", "пам'ять", "storage", "накопичувач"]
                ):
                    explicit_storage.update(re.findall(r"\d+", str(v).lower()))

            nums_to_check = set(n for n in nums_to_check if int(n) > 32)
            if explicit_storage:
                nums_to_check = nums_to_check.intersection(explicit_storage)

        if any(num in nums_to_check for num in typical_values):
            return False

        return True

    typical_ram = ["2", "3", "4", "6", "8", "12", "16", "24", "32", "64"]
    typical_storage = ["32", "64", "128", "256", "512", "1000", "1024", "2000", "2048"]

    if not check_memory_exact("Пам'ять (вбудована)", typical_storage, is_ram=False):
        return False
    if not check_memory_exact("ОЗП", typical_ram, is_ram=True):
        return False

    # 7. KEYWORDS
    if "Ключові слова" in filters and filters["Ключові слова"]:
        kw_lower = re.sub(r"\s+", "", filters["Ключові слова"].lower())
        ad_raw = re.sub(r"\s+", "", clean_full_text)
        if kw_lower not in ad_raw:
            return False

    # 8. Status
    if "Стан" in filters and filters["Стан"]:
        found_val = None
        for k, v in ad.params.items():
            if "стан" in k.lower():
                found_val = str(v).lower()
                break

        if found_val:
            matched = False
            for opt in filters["Стан"]:
                opt_lower = opt.lower()
                if "нов" in opt_lower:
                    if any(x in found_val for x in ["нов", "new"]):
                        matched = True
                elif "вживан" in opt_lower or "б/у" in opt_lower:
                    if any(x in found_val for x in ["вживан", "б/у", "б/в", "used"]):
                        matched = True
                elif "запчастини" in opt_lower:
                    if any(
                        x in found_val for x in ["запчасти", "damaged", "відновлення"]
                    ):
                        matched = True
            if not matched:
                return False

    # 9. Price
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
