import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

import database as db

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# 1. Customer -> Admin Topic Thread
@dp.message(F.chat.type == ChatType.PRIVATE)
async def handle_user_message(message: Message):
    user_id = message.from_user.id
    name = message.from_user.full_name
    username = f"@{message.from_user.username}" if message.from_user.username else "No Username"

    thread_id = await db.get_thread_id(user_id)

    # First time user: create dedicated topic
    if not thread_id:
        try:
            topic = await bot.create_forum_topic(
                chat_id=ADMIN_GROUP_ID,
                name=f"{name} ({user_id})"[:128]
            )
            thread_id = topic.message_thread_id
            await db.save_mapping(user_id, thread_id)

            # Ticket header inside the new topic
            await bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                message_thread_id=thread_id,
                text=f"🎫 **New Support Ticket**\nName: {name}\nHandle: {username}\nID: `{user_id}`",
                parse_mode="Markdown"
            )
        except TelegramBadRequest as e:
            print(f"[Error] Failed to create topic: {e}")
            return

    # Mirror user content directly to their topic thread
    await bot.copy_message(
        chat_id=ADMIN_GROUP_ID,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        message_thread_id=thread_id
    )

# 2. Admin Topic Thread -> Customer DM
@dp.message(F.chat.id == ADMIN_GROUP_ID)
async def handle_admin_reply(message: Message):
    thread_id = message.message_thread_id
    if not thread_id:
        return

    # Check if this thread belongs to a customer
    target_user_id = await db.get_user_id(thread_id)
    if not target_user_id:
        return

    # Deliver reply to customer private chat
    try:
        await bot.copy_message(
            chat_id=target_user_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
    except TelegramForbiddenError:
        await message.reply("⚠️ Cannot deliver: The user blocked the bot or deleted their account.")
    except Exception as e:
        await message.reply(f"⚠️ Delivery error: {e}")

async def main():
    await db.init_db()
    # Clear backlog so restarts don't trigger old messages
    await bot.delete_webhook(drop_pending_updates=True)
    print("Support Bot started polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
