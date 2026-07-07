"""
نقطة تشغيل البوت. هذا هو الملف اللي نشغّله عشان يشتغل البوت.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
import poster_flow
import admin_flow

logging.basicConfig(level=logging.INFO)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "لم يتم العثور على BOT_TOKEN. تأكد أنك أنشأت ملف .env وحطيت فيه التوكن."
        )

    init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(admin_flow.router)
    dp.include_router(poster_flow.router)

    logging.info("✅ البوت شغّال الآن...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
