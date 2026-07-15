import asyncio
from aiogram import Bot

from app.database import (
    add_to_history,
    get_active_users,
    get_all_filters,
    is_in_history,
)
from app.parser import build_url, fetch_html, parse_html, passes_local_filter


async def check_new_ads(bot: Bot):
    print("\n⏳ [МОНІТОРИНГ] Запуск перевірки OLX...")
    users = await get_active_users()

    for user_id in users:
        filters = await get_all_filters(user_id)

        for category, filter_data in filters.items():
            # Get the list of brands. If no brands are set, use [None] to loop at least once.
            brands = filter_data.get("Бренд", [None])

            for brand in brands:
                url = build_url(category, filter_data, brand)
                print(f"🔗 URL для пошуку ({brand or 'Всі бренди'}): {url}")

                soup = await fetch_html(url)
                if not soup:
                    continue

                ads = parse_html(soup)
                passed_ads = [ad for ad in ads if passes_local_filter(ad, filter_data)]
                print(f"📦 Знайдено: {len(passed_ads)} оголошень.")

                sent_count = 0
                for ad in reversed(passed_ads):
                    if not await is_in_history(user_id, ad.ad_id):
                        text = (
                            f"🔥 <b>Нове оголошення!</b> ({category})\n\n"
                            f"📌 {ad.title}\n"
                            f"💰 <b>{ad.price}</b>\n\n"
                            f"🔗 <a href='{ad.url}'>Перейти на OLX</a>"
                        )
                        try:
                            if ad.image_url:
                                await bot.send_photo(
                                    chat_id=user_id,
                                    photo=ad.image_url,
                                    caption=text,
                                    parse_mode="HTML",
                                )
                            else:
                                await bot.send_message(
                                    chat_id=user_id, text=text, parse_mode="HTML"
                                )

                            await add_to_history(user_id, ad.ad_id)
                            sent_count += 1
                            await asyncio.sleep(1)
                        except Exception as e:
                            print(f"❌ Помилка: {e}")

                print(f"✅ Надіслано нових: {sent_count}")
    print("🏁 [МОНІТОРИНГ] Перевірку завершено.\n")
