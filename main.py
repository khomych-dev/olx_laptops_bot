import asyncio
import logging

from app.bot import main

if __name__ == "__main__":
    # Enable the output of system messages from aiogram to the terminal
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
