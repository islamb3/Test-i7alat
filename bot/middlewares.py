import json
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot, types
from aiogram.types import TelegramObject
from .database import SettingsManager, get_db_connection
from .config import ADMIN_ID, CHANNEL_USERNAME, logger
from aiogram.utils.keyboard import InlineKeyboardBuilder

class MandatorySubMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if not isinstance(event, (types.Message, types.CallbackQuery)):
            return await handler(event, data)

        user_id = event.from_user.id
        bot: Bot = data['bot']

        # Check if it's the main bot or a hosted bot
        is_hosted = 'bot_id' in data

        if not is_hosted:
            # Main Bot logic
            if user_id == ADMIN_ID:
                return await handler(event, data)

            # Allow /start and verification callbacks
            if isinstance(event, types.Message) and event.text and event.text.startswith('/start'):
                return await handler(event, data)
            if isinstance(event, types.CallbackQuery) and event.data in ['check_subscription', 'check_fingerprint_verified']:
                return await handler(event, data)
            # Add captcha and fingerprint check exemptions if needed
            if isinstance(event, types.CallbackQuery) and (event.data.startswith('captcha_') or event.data == 'check_fingerprint_verified'):
                return await handler(event, data)

            channels_json = await SettingsManager.get_setting('MANDATORY_CHANNELS', '[]')
            channels = json.loads(channels_json)
            if not channels and CHANNEL_USERNAME:
                channels = [CHANNEL_USERNAME]
        else:
            # Hosted Bot logic
            bot_id = data['bot_id']
            owner_id = data['owner_id']
            if user_id == owner_id:
                return await handler(event, data)

            if isinstance(event, types.Message) and event.text and event.text.startswith('/start'):
                return await handler(event, data)
            if isinstance(event, types.CallbackQuery) and event.data == 'h_check_sub':
                return await handler(event, data)

            conn = get_db_connection()
            r = conn.cursor().execute("SELECT config FROM hosted_bots WHERE id = ?", (bot_id,)).fetchone()
            conn.close()
            conf = json.loads(r["config"]) if r and r["config"] else {}
            channels = conf.get('mandatory_channels', [])
            if not channels and conf.get('channel_username'):
                channels = [conf['channel_username']]

        if not channels:
            return await handler(event, data)

        not_subscribed = []
        for channel in channels:
            try:
                member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
                if member.status in ['left', 'kicked']:
                    not_subscribed.append(channel)
            except Exception as e:
                logger.error(f"Error checking subscription for {channel}: {e}")
                not_subscribed.append(channel)

        if not not_subscribed:
            return await handler(event, data)

        # Generate subscription message
        text = "📢 <b>يجب الاشتراك في القنوات والمجموعات التالية للمتابعة:</b>\n\n"
        builder = InlineKeyboardBuilder()
        for channel in channels:
            clean_channel = str(channel).replace('@', '')
            if clean_channel.startswith('-100'):
                # For private groups/channels, we hope the owner provides a valid username or we can't easily link
                # But get_chat should work if bot is admin
                try:
                    chat = await bot.get_chat(channel)
                    link = chat.invite_link or f"https://t.me/{chat.username}" if chat.username else None
                    if link:
                        builder.button(text=f"📢 {chat.title}", url=link)
                        text += f"• {chat.title}\n"
                    else:
                        text += f"• {chat.title} (يرجى البحث عنها)\n"
                except:
                    text += f"• {channel}\n"
            else:
                builder.button(text=f"📢 {channel}", url=f"https://t.me/{clean_channel}")
                text += f"• {channel}\n"

        text += "\nبعد الاشتراك، اضغط على زر التحقق أدناه."
        builder.button(text="✅ تحقق من الاشتراك", callback_data="check_subscription" if not is_hosted else "h_check_sub")
        builder.adjust(1)

        if isinstance(event, types.Message):
            await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
            await event.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            await event.answer("⚠️ يجب الاشتراك أولاً!", show_alert=True)

        return None
