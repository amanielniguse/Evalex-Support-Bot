import os
import html
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType, ChatAction, ParseMode
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
    first_name = html.escape(message.from_user.first_name or "there")
    welcome_text = (
        f"👋 Hi {first_name}!\n\n"
        "Welcome to our support desk. Send any message, question, or media right here, "
        "and our team will get back to you directly in this chat."
    )
    await message.answer(welcome_text)

# 2. Customer -> Admin Topic Thread
@dp.message(F.chat.type == ChatType.PRIVATE)
async def handle_user_message(message: Message):
    user_id = message.from_user.id
    raw_name = message.from_user.full_name or "Anonymous"
    raw_username = f"@{message.from_user.username}" if message.from_user.username else "No Username"

    safe_name = html.escape(raw_name)
    safe_username = html.escape(raw_username)

    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    thread_id = await db.get_thread_id(user_id)

    # Helper function to create a new forum topic
    async def create_new_topic():
        topic = await bot.create_forum_topic(
            chat_id=ADMIN_GROUP_ID,
            name=f"{raw_name} ({user_id})"[:128]
        )
        new_thread_id = topic.message_thread_id
        await db.save_mapping(user_id, new_thread_id)

        # Post info header using robust HTML formatting
        await bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            message_thread_id=new_thread_id,
            text=(
                f"💬 <b>New Support Session</b>\n"
                f"Name: {safe_name}\n"
                f"Handle: {safe_username}\n"
                f"ID: <code>{user_id}</code>"
            ),
            parse_mode=ParseMode.HTML
        )
        return new_thread_id

    # Create topic if not already tracked
    if not thread_id:
        try:
            thread_id = await create_new_topic()
        except TelegramBadRequest as e:
            print(f"[Error] Failed to create topic: {e}")
            await message.answer("⚠️ An error occurred while opening your session. Please try again shortly.")
            return

    # Relay user's message into their topic thread
    try:
        await bot.copy_message(
            chat_id=ADMIN_GROUP_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            message_thread_id=thread_id
        )
    except TelegramBadRequest as e:
        # If thread was deleted or invalid, recreate it on the fly and retry
        if "message thread not found" in str(e).lower() or "thread not found" in str(e).lower():
            try:
                thread_id = await create_new_topic()
                await bot.copy_message(
                    chat_id=ADMIN_GROUP_ID,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                    message_thread_id=thread_id
                )
            except Exception as inner_e:
                print(f"[Error] Recovery failed: {inner_e}")
                return
        else:
            print(f"[Error] Copy message failed: {e}")
            return

    # Receipt confirmation for the user
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
        await bot.send_message(
            chat_id=target_user_id,
            text="🔒 Your support session has ended. If you need anything else, simply send a new message!"
        )
        await bot.close_forum_topic(chat_id=ADMIN_GROUP_ID, message_thread_id=thread_id)
        await message.reply("Session marked resolved and closed.")
    except Exception as e:
        await message.reply(f"Could not close topic: {e}")

# 4. Admin Topic Thread -> Customer DM
@dp.message(F.chat.id == ADMIN_GROUP_ID)
async def handle_admin_reply(message: Message):
    thread_id = message.message_thread_id
    if not thread_id:
        return

    # Filter out bots to avoid loopbacks
    if message.from_user and message.from_user.is_bot:
        return

    # Filter out commands
    if message.text and message.text.startswith("/"):
        return

    # Filter out Telegram system/service messages
    if any([
        message.forum_topic_created,
        message.forum_topic_edited,
        message.forum_topic_closed,
        message.forum_topic_reopened,
        message.pinned_message,
        message.new_chat_members,
        message.left_chat_member
    ]):
        return

    target_user_id = await db.get_user_id(thread_id)
    if not target_user_id:
        return

    # Relay reply back to customer private chat
    try:
        await bot.copy_message(
            chat_id=target_user_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
    except TelegramForbiddenError:
        await message.reply("⚠️ Cannot deliver: The user blocked the bot or deleted their account.")
    except TelegramBadRequest as e:
        if message.text:
            try:
                await bot.send_message(chat_id=target_user_id, text=message.text)
                return
            except Exception as inner_e:
                await message.reply(f"⚠️ Delivery error: {inner_e}")
                return
        await message.reply(f"⚠️ Delivery error: {e}")
    except Exception as e:
        await message.reply(f"⚠️ Delivery error: {e}")

async def main():
    await db.init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("Support Bot started polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
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
