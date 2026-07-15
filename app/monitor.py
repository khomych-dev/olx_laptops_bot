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
    """
    Main monitoring function.
    It scans all active users, searches for new listings, and sends them.
    """
    users = await get_active_users()

    for user_id in users:
        filters = await get_all_filters(user_id)

        for category, filter_data in filters.items():
            url = build_url(category, filter_data)
            soup = await fetch_html(url)

            if not soup:
                continue

            ads = parse_html(soup)

            # We reverse the list so that the oldest of the new listings appear first,
            # and the newest (which are at the top of the page) are sent last.
            for ad in reversed(ads):
                # 1. Check if it matches our local filter (Brand, Keywords)
                if passes_local_filter(ad, filter_data):
                    # 2. Check if we have already sent this ad
                    if not await is_in_history(user_id, ad.ad_id):
                        # 3. Let's create a nice message
                        text = (
                            f"🔥 <b>Нове оголошення!</b> ({category})\n\n"
                            f"📌 {ad.title}\n"
                            f"💰 <b>{ad.price}</b>\n\n"
                            f"🔗 <a href='{ad.url}'>Перейти на OLX</a>"
                        )

                        try:
                            # If there is a photo - send with the photo, if not - just text
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

                            # 4. Save to history to avoid sending again
                            await add_to_history(user_id, ad.ad_id)

                            # Pause 1 second so Telegram doesn't block the bot for spam
                            await asyncio.sleep(1)

                        except Exception as e:
                            print(f"Помилка відправки користувачу {user_id}: {e}")
