import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType, ChatAction
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

import database as db

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# 1. /start command in DM
@dp.message(F.chat.type == ChatType.PRIVATE, CommandStart())
async def handle_start(message: Message):
    welcome_text = (
        f"👋 Hi {message.from_user.first_name}!\n\n"
        "Welcome to our support desk. Send any message, question, or media right here, "
        "and our team will get back to you directly in this chat."
    )
    await message.answer(welcome_text)

# 2. Customer -> Admin Topic Thread
@dp.message(F.chat.type == ChatType.PRIVATE)
async def handle_user_message(message: Message):
    user_id = message.from_user.id
    name = message.from_user.full_name
    username = f"@{message.from_user.username}" if message.from_user.username else "No Username"

    # Show a brief upload/typing indicator
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    thread_id = await db.get_thread_id(user_id)

    # First-time user: create a dedicated topic thread
    if not thread_id:
        try:
            topic = await bot.create_forum_topic(
                chat_id=ADMIN_GROUP_ID,
                name=f"{name} ({user_id})"[:128]
            )
            thread_id = topic.message_thread_id
            await db.save_mapping(user_id, thread_id)

            await bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                message_thread_id=thread_id,
                text=f"🎫 **User**\nName: {name}\nHandle: {username}\nID: `{user_id}`",
                parse_mode="Markdown"
            )
        except TelegramBadRequest as e:
            print(f"[Error] Failed to create topic: {e}")
            await message.answer("⚠️ An error occurred while contacting the team. Please try again in a moment.")
            return

    # Relay user's content to the topic thread
    await bot.copy_message(
        chat_id=ADMIN_GROUP_ID,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        message_thread_id=thread_id
    )

    # Immediate confirmation receipt for the customer
    await message.reply("✅ Delivered. An agent will reply shortly.")

# 3. /close command inside an Admin topic
@dp.message(F.chat.id == ADMIN_GROUP_ID, Command("close"))
async def handle_close_topic(message: Message):
    thread_id = message.message_thread_id
    if not thread_id:
        return

    target_user_id = await db.get_user_id(thread_id)
    if not target_user_id:
        return

    try:
        # Notify the customer
        await bot.send_message(
            chat_id=target_user_id,
            text="🔒 Your support session has been closed. If you need anything else, simply send a new message!"
        )
        # Close topic in Telegram
        await bot.close_forum_topic(chat_id=ADMIN_GROUP_ID, message_thread_id=thread_id)
        await message.reply("Ticket marked resolved and closed.")
    except Exception as e:
        await message.reply(f"Could not close topic: {e}")

# 4. Admin Topic Thread -> Customer DM
@dp.message(F.chat.id == ADMIN_GROUP_ID)
async def handle_admin_reply(message: Message):
    thread_id = message.message_thread_id
    if not thread_id:
        return

    # Ignore slash commands so internal team commands aren't sent to the user
    if message.text and message.text.startswith("/"):
        return

    target_user_id = await db.get_user_id(thread_id)
    if not target_user_id:
        return

    # Deliver reply to the customer's private chat
    try:
        await bot.copy_message(
            chat_id=target_user_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
    except TelegramForbiddenError:
        await message.reply("⚠️ Cannot deliver: The user has blocked the bot or deleted their account.")
    except Exception as e:
        await message.reply(f"⚠️ Delivery error: {e}")

async def main():
    await db.init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("Support Bot started polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
