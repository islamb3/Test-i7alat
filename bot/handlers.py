import os, sys, asyncio, logging, json, sqlite3, secrets, string, hashlib, hmac, random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from .config import BOT_TOKEN, ADMIN_ID, CHANNEL_USERNAME, FINGERPRINT_WEB_URL, logger
from .database import get_db_connection, generate_referral_code, is_valid_ton_address, SettingsManager, PointsSystem, SmartIPBan, SecretLinkSystem, FingerprintSystem, CAPTCHA_QUESTIONS
from .states import RegistrationStates, AdminStates, BotHostingStates, PaymentStates, SettingsStates, WithdrawalStates, ConversionStates, StoreStates, TaskStates
from .hosting import HostedBotSystem


async def get_main_menu():
    """القائمة الرئيسية - جميع الأزرار مربوطة"""
    builder = InlineKeyboardBuilder()
    builder.button(text='📊 لوحة التحكم', callback_data='dashboard')
    builder.button(text='💸 سحب الأرباح', callback_data='request_withdrawal')
    builder.button(text='🔗 رابط الإحالة', callback_data='referral_link')
    builder.button(text='🎁 مكافأة يومية', callback_data='daily_bonus')
    builder.button(text='🎯 المهام', callback_data='tasks_list')
    builder.button(text='🔄 تحويل النقاط', callback_data='convert_points')

    hosting_enabled = await SettingsManager.get_bool_setting('HOSTING_BUTTON_ENABLED', True)
    if hosting_enabled:
        builder.button(text='🤖 استضافة بوت', callback_data='bot_hosting_menu')

    builder.button(text='📈 الإحصائيات', callback_data='statistics')
    builder.adjust(2)
    return builder.as_markup()


def get_dashboard_menu():
    """قائمة لوحة التحكم"""
    builder = InlineKeyboardBuilder()
    builder.button(text='🔄 تحويل النقاط', callback_data='convert_points')
    builder.button(text='⚙️ عنوان TON', callback_data='set_wallet_address')
    builder.button(text='📜 سجل النقاط', callback_data='points_history')
    builder.button(text='🔙 رئيسية', callback_data='main_menu')
    builder.adjust(2)
    return builder.as_markup()


def get_bot_hosting_menu():
    """قائمة استضافة البوتات"""
    builder = InlineKeyboardBuilder()
    builder.button(text='➕ إضافة بوت جديد', callback_data='add_new_bot')
    builder.button(text='📋 بوتاتي', callback_data='my_bots')
    builder.button(text='🔙 رئيسية', callback_data='main_menu')
    builder.adjust(1)
    return builder.as_markup()


def get_bot_dashboard_menu(bot_id: int, is_active: bool, plan_type: str,
    is_expired: bool=False):
    """قائمة لوحة تحكم البوت - مبسطة"""
    builder = InlineKeyboardBuilder()
    builder.button(text='🔑 تعديل التوكن', callback_data=
        f'bot_edit_token_{bot_id}')
    if is_active:
        builder.button(text='🔴 إيقاف', callback_data=f'bot_stop_{bot_id}')
    else:
        builder.button(text='🟢 تشغيل', callback_data=f'bot_start_{bot_id}')
    builder.button(text='🗑️ حذف البوت', callback_data=f'bot_delete_{bot_id}')
    builder.button(text='🔙 رجوع', callback_data='my_bots')
    builder.adjust(1)
    return builder.as_markup()


def get_admin_menu():
    """قائمة المشرف"""
    builder = InlineKeyboardBuilder()
    # الإحصائيات والمستخدمين
    builder.button(text='📊 إحصائيات', callback_data='admin_stats')
    builder.button(text='👥 المستخدمين', callback_data='admin_users_menu')

    # الإعدادات المالية
    builder.button(text='💰 إعدادات النقاط', callback_data='admin_points_settings')
    builder.button(text='💸 إعدادات السحب', callback_data='admin_withdrawal_types')
    builder.button(text='🔄 إعدادات التحويل', callback_data='admin_conversion_settings')

    # الإعدادات التشغيلية
    builder.button(text='🎯 إدارة المهام', callback_data='admin_tasks_menu')
    builder.button(text='📢 الاشتراك الإجباري', callback_data='admin_mandatory_sub_menu')
    builder.button(text='🤖 زر الاستضافة', callback_data='admin_hosting_button_toggle')

    # الأمان والتقني
    builder.button(text='🔧 إعدادات الحماية', callback_data='admin_security_settings')
    builder.button(text='💎 إعدادات الباقات', callback_data='admin_plan_settings')
    builder.button(text='📢 إشعار جماعي', callback_data='admin_broadcast')

    # الحظر
    builder.button(text='🚫 حظر IP', callback_data='admin_ban_ip')
    builder.button(text='✅ فك حظر IP', callback_data='admin_unban_ip')

    # أخرى
    builder.button(text='⚙️ جميع الإعدادات', callback_data='admin_all_settings')
    builder.button(text='🔙 رئيسية', callback_data='main_menu')

    builder.adjust(2)
    return builder.as_markup()


async def get_withdrawal_menu():
    """قائمة السحب"""
    builder = InlineKeyboardBuilder()
    ton_enabled = await SettingsManager.get_bool_setting('WITHDRAWAL_TON_ENABLED', True)
    stars_enabled = await SettingsManager.get_bool_setting('WITHDRAWAL_STARS_ENABLED', True)
    if ton_enabled:
        builder.button(text='🪙 سحب TON', callback_data='withdraw_ton')
    if stars_enabled:
        builder.button(text='⭐ سحب Stars', callback_data='withdraw_stars')
    builder.button(text='🔙 رجوع', callback_data='dashboard')
    builder.adjust(1)
    return builder.as_markup()


async def get_conversion_menu():
    """قائمة التحويل"""
    builder = InlineKeyboardBuilder()
    ton_enabled = await SettingsManager.get_bool_setting('WITHDRAWAL_TON_ENABLED', True)
    stars_enabled = await SettingsManager.get_bool_setting('WITHDRAWAL_STARS_ENABLED', True)
    if ton_enabled:
        builder.button(text='🪙 تحويل إلى TON', callback_data='convert_to_ton')
    if stars_enabled:
        builder.button(text='⭐ تحويل إلى Stars', callback_data='convert_to_stars')
    builder.button(text='🔙 رجوع', callback_data='dashboard')
    builder.adjust(1)
    return builder.as_markup()


def get_back_button(callback_data: str='main_menu'):
    """زر رجوع"""
    builder = InlineKeyboardBuilder()
    builder.button(text='🔙 عودة', callback_data=callback_data)
    return builder.as_markup()


def get_cancel_button(destination: str):
    """زر إلغاء"""
    builder = InlineKeyboardBuilder()
    builder.button(text='❌ إلغاء', callback_data=f'cancel_action_{destination}'
        )
    return builder.as_markup()


def get_captcha_keyboard(question_index: int):
    """لوحة مفاتيح الكابتشا"""
    builder = InlineKeyboardBuilder()
    question = CAPTCHA_QUESTIONS[question_index]
    for i, option in enumerate(question['options']):
        builder.button(text=option, callback_data=
            f'captcha_{question_index}_{i}')
    builder.adjust(2)
    return builder.as_markup()


async def cmd_start(message: types.Message, state: FSMContext, bot: Bot):
    """أمر /start - محسن"""
    user_id = message.from_user.id
    maintenance = await SettingsManager.get_bool_setting('MAINTENANCE_MODE',
        False)
    if maintenance and user_id != ADMIN_ID:
        await message.answer('🔧 البوت في وضع الصيانة. يرجى المحاولة لاحقاً.')
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    user = cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (
        user_id,)).fetchone()
    if user and user['is_banned']:
        await message.answer('⛔️ حسابك محظور.')
        conn.close()
        return
    if not user:
        referral_code = generate_referral_code()
        args = message.text.split()
        referred_by = None
        if len(args) > 1:
            referral_code_arg = args[1]
            referrer = cursor.execute(
                'SELECT telegram_id FROM users WHERE referral_code = ?', (
                referral_code_arg,)).fetchone()
            if referrer:
                referred_by = referrer['telegram_id']
        cursor.execute(
            """
            INSERT INTO users (telegram_id, username, full_name, referral_code, referred_by)
            VALUES (?, ?, ?, ?, ?)
        """
            , (user_id, message.from_user.username, message.from_user.
            full_name, referral_code, referred_by))
        conn.commit()
        if referred_by:
            referral_reward = await SettingsManager.get_int_setting(
                'REFERRAL_REWARD', 10)
            cursor.execute(
                """
                INSERT INTO referrals (referrer_id, referred_id, is_valid, points)
                VALUES (?, ?, 0, ?)
            """
                , (referred_by, user_id, referral_reward))
            conn.commit()
        user = cursor.execute('SELECT * FROM users WHERE telegram_id = ?',
            (user_id,)).fetchone()
    if user_id == ADMIN_ID and user and user['is_admin'] == 0:
        cursor.execute('UPDATE users SET is_admin = 1 WHERE telegram_id = ?',
            (user_id,))
        conn.commit()
        user = cursor.execute('SELECT * FROM users WHERE telegram_id = ?',
            (user_id,)).fetchone()
    if not user['fingerprint_verified']:
        conn.close()
        secret, expiry = await SecretLinkSystem.generate_link(user_id)
        bot_info = await bot.get_me()

        # التأكد من أن الرابط ليس رابط t.me لضمان عمل الـ WebApp
        base_url = FINGERPRINT_WEB_URL
        if "t.me/" in base_url:
            logger.warning(f"FINGERPRINT_WEB_URL contains t.me link: {base_url}. This might break Mini App functionality.")

        verification_url = (
            f'{base_url}?secret={secret}&user_id={user_id}&bot={bot_info.username}'
            )

        # التأكد من وجود بروتوكول HTTPS لتجنب أخطاء تيليجرام
        if not verification_url.startswith("http"):
            verification_url = "https://" + verification_url
        await message.answer(
            f"""🔐 <b>التحقق من الهوية مطلوب</b>

لمنع التسجيل المتعدد، نحتاج للتحقق من جهازك.
⏱️ صلاحية الرابط: {expiry} دقائق

👇 اضغط على الزر أدناه للتحقق:"""
            , reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
            types.InlineKeyboardButton(text='🛡️ فتح صفحة التحقق', web_app=types.WebAppInfo(url=verification_url) if "t.me/" not in verification_url else None, url=verification_url if "t.me/" in verification_url else None)], [types.InlineKeyboardButton(text=
            '✅ لقد قمت بالتحقق', callback_data='check_fingerprint_verified'
            )]]), parse_mode=ParseMode.HTML)
        return
    if not user['captcha_passed']:
        await state.set_state(RegistrationStates.captcha)
        question_idx = random.randint(0, len(CAPTCHA_QUESTIONS) - 1)
        question = CAPTCHA_QUESTIONS[question_idx]
        await message.answer(f"🔒 سؤال التحقق:\n\n{question['question']}",
            reply_markup=get_captcha_keyboard(question_idx))
        conn.close()
        return
    if not user['subscribed']:
        channels_json = await SettingsManager.get_setting('MANDATORY_CHANNELS', '[]')
        channels = json.loads(channels_json)
        if not channels and CHANNEL_USERNAME:
            channels = [CHANNEL_USERNAME]

        if channels:
            await state.set_state(RegistrationStates.subscription)
            text = "📢 يرجى الاشتراك في القنوات التالية أولاً:\n\n"
            builder = InlineKeyboardBuilder()
            for channel in channels:
                clean_channel = channel.replace('@', '')
                text += f"• @{clean_channel}\n"
                builder.button(text=f'📢 اشترك في {channel}', url=f'https://t.me/{clean_channel}')

            text += "\nثم اضغط تحقق."
            builder.button(text='✅ تحقق', callback_data='check_subscription')
            builder.adjust(1)
            await message.answer(text, reply_markup=builder.as_markup())
            conn.close()
            return
        else:
            cursor.execute('UPDATE users SET subscribed = 1 WHERE telegram_id = ?', (user_id,))
            conn.commit()
            user = cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (user_id,)).fetchone()
    conn.close()
    await show_main_menu(message, user)


async def check_fingerprint_verified(callback: types.CallbackQuery, bot:
    Bot, state: FSMContext):
    """التحقق من اكتمال التحقق من البصمة - محسن"""
    user_id = callback.from_user.id
    conn = get_db_connection()
    user = conn.cursor().execute('SELECT * FROM users WHERE telegram_id = ?',
        (user_id,)).fetchone()
    conn.close()
    if user and user['fingerprint_verified'] == 1:
        await callback.answer('✅ تم التحقق بنجاح!', show_alert=False)
        try:
            await callback.message.delete()
        except:
            pass
        await state.set_state(RegistrationStates.captcha)
        question_idx = random.randint(0, len(CAPTCHA_QUESTIONS) - 1)
        question = CAPTCHA_QUESTIONS[question_idx]
        await callback.message.answer(
            f"🔒 سؤال التحقق:\n\n{question['question']}", reply_markup=
            get_captcha_keyboard(question_idx))
    else:
        await callback.answer(
            """❌ لم يتم التحقق من جهازك بعد!

1. اضغط على زر 'فتح صفحة التحقق'
2. أكمل خطوات التحقق في الصفحة
3. ثم اضغط 'لقد قمت بالتحقق' مرة أخرى"""
            , show_alert=True, cache_time=10)


async def process_captcha(callback: types.CallbackQuery, state: FSMContext,
    bot: Bot):
    """معالجة إجابة الكابتشا - محسن"""
    data = callback.data.split('_')
    question_index, answer_index = int(data[1]), int(data[2])
    user_id = callback.from_user.id
    if answer_index == CAPTCHA_QUESTIONS[question_index]['correct']:
        conn = get_db_connection()
        conn.cursor().execute(
            'UPDATE users SET captcha_passed = 1 WHERE telegram_id = ?', (
            user_id,))
        conn.commit()
        conn.close()
        await callback.message.delete()
        await state.set_state(RegistrationStates.subscription)
        await callback.message.answer(
            f"""✅ إجابة صحيحة!

📢 يرجى الاشتراك في القناة:
{CHANNEL_USERNAME}"""
            , reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
            types.InlineKeyboardButton(text='📢 اشترك الآن', url=
            f'https://t.me/{CHANNEL_USERNAME[1:]}')], [types.
            InlineKeyboardButton(text='✅ تحقق', callback_data=
            'check_subscription')]]))
    else:
        await callback.answer('❌ إجابة خاطئة! حاول مرة أخرى.', show_alert=True)


async def check_subscription(callback: types.CallbackQuery, state:
    FSMContext, bot: Bot):
    """التحقق من الاشتراك في القنوات - محسن"""
    user_id = callback.from_user.id
    channels_json = await SettingsManager.get_setting('MANDATORY_CHANNELS', '[]')
    channels = json.loads(channels_json)
    if not channels and CHANNEL_USERNAME:
        channels = [CHANNEL_USERNAME]

    not_subscribed = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_subscribed.append(channel)
        except Exception as e:
            logger.error(f"Error checking sub for {channel}: {e}")
            not_subscribed.append(channel)

    if not not_subscribed:
        try:
            await callback.message.delete()
        except:
            pass
        await callback.answer('✅ تم التحقق من الاشتراك!', show_alert=False)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE users SET subscribed = 1 WHERE telegram_id = ?', (
            user_id,))
        user = cursor.execute(
            'SELECT referred_by FROM users WHERE telegram_id = ?', (
            user_id,)).fetchone()
        if user and user['referred_by']:
            referral = cursor.execute(
                'SELECT * FROM referrals WHERE referred_id = ? AND is_valid = 0'
                , (user_id,)).fetchone()
            if referral:
                referral_reward = await SettingsManager.get_int_setting(
                    'REFERRAL_REWARD', 10)
                cursor.execute(
                    'UPDATE referrals SET is_valid = 1, points = ? WHERE id = ?'
                    , (referral_reward, referral['id']))
                cursor.execute(
                    'UPDATE users SET points = points + ? WHERE telegram_id = ?'
                    , (referral_reward, referral['referrer_id']))
                cursor.execute(
                    'UPDATE users SET total_referrals = total_referrals + 1 WHERE telegram_id = ?'
                    , (referral['referrer_id'],))
                try:
                    await bot.send_message(referral['referrer_id'],
                        f'🎉 تم إحالة مستخدم جديد! +{referral_reward} نقطة')
                except:
                    pass
        conn.commit()
        user_data = cursor.execute(
            'SELECT * FROM users WHERE telegram_id = ?', (user_id,)
            ).fetchone()
        conn.close()
        try:
            await callback.message.delete()
        except:
            pass
        await state.clear()
        await show_main_menu(callback.message, user_data)
    else:
        await callback.answer('⚠️ أنت غير مشترك في جميع القنوات المطلوبة!', show_alert=True)


async def show_main_menu(message_or_callback, user_data):
    """عرض القائمة الرئيسية"""
    text = f"""👋 <b>أهلاً {user_data['full_name']}!</b>

💰 رصيد النقاط: <code>{user_data['points']}</code>
🪙 رصيد TON: <code>{user_data['ton_balance']:.4f}</code>
⭐ رصيد Stars: <code>{user_data['stars_balance']}</code>

اختر من القائمة:"""
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=await get_main_menu(),
            parse_mode=ParseMode.HTML)
    else:
        try:
            await message_or_callback.message.edit_text(text, reply_markup=
                await get_main_menu(), parse_mode=ParseMode.HTML)
        except:
            await message_or_callback.message.answer(text, reply_markup=
                await get_main_menu(), parse_mode=ParseMode.HTML)


async def back_to_main_menu_handler(callback: types.CallbackQuery):
    """العودة للقائمة الرئيسية"""
    conn = get_db_connection()
    user_data = conn.cursor().execute(
        'SELECT * FROM users WHERE telegram_id = ?', (callback.from_user.id,)
        ).fetchone()
    conn.close()
    if user_data:
        await show_main_menu(callback, user_data)
    await callback.answer()


async def cancel_action_handler(callback: types.CallbackQuery, state:
    FSMContext):
    """إلغاء الإجراء الحالي"""
    await state.clear()
    dest = callback.data.replace('cancel_action_', '')
    if dest == 'admin_panel':
        await admin_panel_handler(callback)
    elif dest == 'bot_hosting_menu':
        await bot_hosting_menu_handler(callback)
    elif dest == 'my_bots':
        await my_bots_handler(callback)
    elif dest == 'dashboard':
        await dashboard_handler(callback)
    elif dest == 'main_menu':
        await back_to_main_menu_handler(callback)
    elif dest == 'admin_tasks_menu':
        await admin_tasks_menu_handler(callback)
    elif dest == 'admin_users_menu':
        await admin_users_menu_handler(callback)
    elif dest.startswith('bot_tasks_'):
        callback.data = dest
        await admin_bot_tasks_handler(callback)
    elif dest.startswith('bot_dashboard_'):
        parts = dest.split('_')
        await show_bot_dashboard(callback, callback.from_user.id, int(parts[2])
            )
    else:
        await callback.message.edit_text('❌ تم إلغاء الإجراء')
        await callback.answer('تم الإلغاء')


async def dashboard_handler(callback: types.CallbackQuery):
    """عرض لوحة التحكم"""
    user_id = callback.from_user.id
    conn = get_db_connection()
    user = conn.cursor().execute('SELECT * FROM users WHERE telegram_id = ?',
        (user_id,)).fetchone()
    conn.close()
    if not user:
        await callback.answer('❌ خطأ في تحميل البيانات', show_alert=True)
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    referrals_count = cursor.execute(
        'SELECT COUNT(*) as count FROM referrals WHERE referrer_id = ? AND is_valid = 1'
        , (user_id,)).fetchone()['count']
    tasks_count = cursor.execute(
        'SELECT COUNT(*) as count FROM user_tasks WHERE user_id = ?', (
        user_id,)).fetchone()['count']
    conn.close()
    text = f"""📊 <b>لوحة التحكم</b>

👤 <b>معلوماتك:</b>
• الاسم: {user['full_name']}
• معرفك: <code>{user_id}</code>

💰 <b>أرصدتك:</b>
• النقاط: <code>{user['points']}</code>
• TON: <code>{user['ton_balance']:.4f}</code>
• Stars: <code>{user['stars_balance']}</code>

📈 <b>إحصائياتك:</b>
• الإحالات: <code>{referrals_count}</code>
• المهام المكتملة: <code>{tasks_count}</code>
• إجمالي النقاط المكتسبة: <code>{user['total_earned_points']}</code>
"""
    if user['wallet_address']:
        text += (
            f"\n💳 <b>عنوان المحفظة:</b>\n<code>{user['wallet_address']}</code>"
            )
    await callback.message.edit_text(text, reply_markup=get_dashboard_menu(
        ), parse_mode=ParseMode.HTML)
    await callback.answer()


async def referral_link_handler(callback: types.CallbackQuery, bot: Bot):
    """عرض رابط الإحالة"""
    user_id = callback.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    user = cursor.execute(
        'SELECT referral_code, total_referrals FROM users WHERE telegram_id = ?'
        , (user_id,)).fetchone()
    referral_reward = await SettingsManager.get_int_setting('REFERRAL_REWARD',
        10)
    bot_info = await bot.get_me()
    referral_link = (
        f"https://t.me/{bot_info.username}?start={user['referral_code']}")
    text = f"""🔗 <b>رابط الإحالة الخاص بك</b>

📎 الرابط:
<code>{referral_link}</code>

💰 مكافأة كل إحالة: <code>{referral_reward}</code> نقطة
👥 عدد إحالاتك: <code>{user['total_referrals']}</code>

📤 شارك الرابط مع أصدقائك واكسب النقاط!"""
    builder = InlineKeyboardBuilder()
    builder.button(text='📤 مشاركة', url=
        f'https://t.me/share/url?url={referral_link}&text=انضم إلي في هذا البوت الرائع!'
        )
    builder.button(text='🔙 رجوع', callback_data='main_menu')
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def daily_bonus_handler(callback: types.CallbackQuery):
    """المكافأة اليومية"""
    user_id = callback.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    user = cursor.execute(
        'SELECT last_daily_bonus, daily_streak_count, points FROM users WHERE telegram_id = ?'
        , (user_id,)).fetchone()
    base_bonus = await SettingsManager.get_int_setting('DAILY_BONUS_BASE', 10)
    streak_bonus = await SettingsManager.get_int_setting('DAILY_BONUS_STREAK',
        5)
    weekly_bonus = await SettingsManager.get_int_setting('DAILY_BONUS_WEEKLY',
        100)
    max_streak = await SettingsManager.get_int_setting('DAILY_BONUS_MAX_STREAK'
        , 7)
    can_claim = True
    streak = user['daily_streak_count'] if user['daily_streak_count'] else 0
    if user['last_daily_bonus']:
        last_bonus = datetime.fromisoformat(user['last_daily_bonus'])
        time_diff = datetime.now() - last_bonus
        if time_diff < timedelta(hours=20):
            can_claim = False
            remaining = timedelta(hours=24) - time_diff
            hours = int(remaining.total_seconds() // 3600)
            minutes = int(remaining.total_seconds() % 3600 // 60)
            wait_text = f'⏳ يمكنك المطالبة بعد: {hours} ساعة و {minutes} دقيقة'
        elif time_diff > timedelta(hours=48):
            streak = 0
    if can_claim:
        total_bonus = base_bonus + streak * streak_bonus
        if streak >= max_streak - 1:
            total_bonus += weekly_bonus
            streak = 0
            bonus_message = (
                f'🎉 مبروك! حصلت على مكافأة الأسبوع الكامل +{weekly_bonus}!')
        else:
            streak += 1
            bonus_message = f'🔥 تتابع يومي: {streak} أيام'
        cursor.execute(
            """
            UPDATE users SET
                points = points + ?,
                last_daily_bonus = ?,
                daily_streak_count = ?,
                total_earned_points = total_earned_points + ?
            WHERE telegram_id = ?
        """
            , (total_bonus, datetime.now().isoformat(), streak, total_bonus,
            user_id))
        cursor.execute(
            """
            INSERT INTO points_history (user_id, action_type, points, description)
            VALUES (?, 'daily_bonus', ?, ?)
        """
            , (user_id, total_bonus, f'مكافأة يومية - تتابع {streak} أيام'))
        conn.commit()
        text = f"""🎁 <b>المكافأة اليومية</b>

✅ حصلت على: <code>{total_bonus}</code> نقطة
{bonus_message}
💰 رصيدك الحالي: <code>{user['points'] + total_bonus}</code> نقطة

📅 عد غداً للحصول على المزيد!"""
    else:
        text = f"""🎁 <b>المكافأة اليومية</b>

{wait_text}

🔥 تتابعك الحالي: <code>{streak}</code> أيام
💡 عد غداً للحفاظ على تتابعك!"""
    conn.close()
    builder = InlineKeyboardBuilder()
    builder.button(text='🔙 رجوع', callback_data='main_menu')
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def tasks_list_handler(callback: types.CallbackQuery):
    """عرض قائمة المهام"""
    user_id = callback.from_user.id
    tasks_enabled = await SettingsManager.get_bool_setting('TASKS_ENABLED',
        True)
    if not tasks_enabled:
        await callback.answer('🚫 نظام المهام معطل حالياً', show_alert=True)
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    tasks = cursor.execute(
        """
        SELECT * FROM tasks WHERE is_active = 1 ORDER BY points DESC
    """
        ).fetchall()
    completed_tasks = cursor.execute(
        """
        SELECT task_id FROM user_tasks WHERE user_id = ?
    """,
        (user_id,)).fetchall()
    completed_ids = {t['task_id'] for t in completed_tasks}
    conn.close()
    if not tasks:
        await callback.message.edit_text(
            '🎯 <b>المهام</b>\n\nلا توجد مهام متاحة حالياً.', reply_markup=
            get_back_button(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    text = '🎯 <b>المهام المتاحة</b>\n\n'
    builder = InlineKeyboardBuilder()
    for task in tasks:
        status = '✅' if task['id'] in completed_ids else '⏳'
        text += f"{status} <b>{task['name']}</b>\n"
        text += f"💰 {task['points']} نقطة"
        if task['description']:
            text += f" - {task['description']}"
        text += '\n\n'
        if task['id'] not in completed_ids:
            if task['link']:
                builder.button(text=f"🔗 {task['name'][:15]}", url=task['link'])
            builder.button(text=f"✅ إكمال {task['name'][:10]}",
                callback_data=f"complete_task_{task['id']}")
    task_bonus = await SettingsManager.get_int_setting('TASK_BONUS_POINTS', 50)
    total_tasks = len(tasks)
    completed_count = len(completed_ids)
    text += f'\n📊 <b>تقدمك:</b> {completed_count}/{total_tasks} مهمة\n'
    if completed_count == total_tasks and total_tasks > 0:
        text += f'🎉 مبروك! أكملت جميع المهام!'
    else:
        text += f'💡 أكمل جميع المهام للحصول على +{task_bonus} نقطة إضافية!'
    builder.button(text='🔙 رجوع', callback_data='main_menu')
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def complete_task_handler(callback: types.CallbackQuery, bot: Bot):
    """إكمال مهمة"""
    user_id = callback.from_user.id
    task_id = int(callback.data.split('_')[2])
    conn = get_db_connection()
    cursor = conn.cursor()
    task = cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)
        ).fetchone()
    if not task:
        await callback.answer('❌ المهمة غير موجودة', show_alert=True)
        conn.close()
        return
    if task['link']:
        chat_id = task['link']
        if 't.me/' in chat_id or chat_id.startswith('@'):
            c_id = chat_id
            if 't.me/' in c_id:
                c_id = '@' + c_id.split('t.me/')[1].split('/')[0]
            try:
                member = await bot.get_chat_member(chat_id=c_id, user_id=
                    user_id)
                if member.status in ['left', 'kicked']:
                    await callback.answer(
                        '⚠️ يجب الانضمام أولاً للقناة لإتمام المهمة.',
                        show_alert=True)
                    conn.close()
                    return
            except:
                pass
    existing = cursor.execute(
        'SELECT * FROM user_tasks WHERE user_id = ? AND task_id = ?', (
        user_id, task_id)).fetchone()
    if existing:
        await callback.answer('✅ لقد أكملت هذه المهمة مسبقاً', show_alert=True)
        conn.close()
        return
    cursor.execute(
        """
        INSERT INTO user_tasks (user_id, task_id) VALUES (?, ?)
    """
        , (user_id, task_id))
    cursor.execute(
        """
        UPDATE users SET
            points = points + ?,
            total_tasks_completed = total_tasks_completed + 1,
            total_earned_points = total_earned_points + ?
        WHERE telegram_id = ?
    """
        , (task['points'], task['points'], user_id))
    cursor.execute(
        """
        INSERT INTO points_history (user_id, action_type, points, description)
        VALUES (?, 'task_completion', ?, ?)
    """
        , (user_id, task['points'], f"إكمال مهمة: {task['name']}"))
    all_tasks = cursor.execute(
        'SELECT COUNT(*) as count FROM tasks WHERE is_active = 1').fetchone()[
        'count']
    completed = cursor.execute(
        'SELECT COUNT(*) as count FROM user_tasks WHERE user_id = ?', (
        user_id,)).fetchone()['count']
    bonus_message = ''
    if completed == all_tasks:
        task_bonus = await SettingsManager.get_int_setting('TASK_BONUS_POINTS',
            50)
        cursor.execute(
            """
            UPDATE users SET points = points + ? WHERE telegram_id = ?
        """
            , (task_bonus, user_id))
        cursor.execute(
            """
            INSERT INTO points_history (user_id, action_type, points, description)
            VALUES (?, 'tasks_bonus', ?, 'مكافأة إكمال جميع المهام')
        """
            , (user_id, task_bonus))
        bonus_message = (
            f'\n🎉 مبروك! حصلت على مكافأة إكمال جميع المهام: +{task_bonus} نقطة!'
            )
    conn.commit()
    conn.close()
    await callback.answer(
        f"✅ تم إكمال المهمة! +{task['points']} نقطة{bonus_message}",
        show_alert=True)
    await tasks_list_handler(callback)


async def statistics_handler(callback: types.CallbackQuery):
    """عرض الإحصائيات"""
    user_id = callback.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    user = cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (
        user_id,)).fetchone()
    referrals_count = cursor.execute(
        """
        SELECT COUNT(*) as count FROM referrals WHERE referrer_id = ? AND is_valid = 1
    """
        , (user_id,)).fetchone()['count']
    tasks_count = cursor.execute(
        """
        SELECT COUNT(*) as count FROM user_tasks WHERE user_id = ?
    """
        , (user_id,)).fetchone()['count']
    total_users = cursor.execute('SELECT COUNT(*) as count FROM users'
        ).fetchone()['count']
    total_referrals = cursor.execute(
        'SELECT COUNT(*) as count FROM referrals WHERE is_valid = 1').fetchone(
        )['count']
    total_tasks = cursor.execute('SELECT COUNT(*) as count FROM user_tasks'
        ).fetchone()['count']
    conn.close()
    text = f"""📈 <b>إحصائياتك</b>

👤 <b>معلوماتك:</b>
• تاريخ التسجيل: {datetime.fromisoformat(user['registration_date']).strftime('%Y-%m-%d')}
• الإحالات الناجحة: {referrals_count}
• المهام المكتملة: {tasks_count}
• إجمالي النقاط المكتسبة: {user['total_earned_points']}

🌍 <b>إحصائيات عامة:</b>
• إجمالي المستخدمين: {total_users}
• إجمالي الإحالات: {total_referrals}
• إجمالي المهام المكتملة: {total_tasks}
"""
    builder = InlineKeyboardBuilder()
    builder.button(text='🔙 رجوع', callback_data='main_menu')
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def request_withdrawal_handler(callback: types.CallbackQuery):
    """طلب سحب"""
    withdrawal_enabled = await SettingsManager.get_bool_setting(
        'WITHDRAWAL_ENABLED', True)
    if not withdrawal_enabled:
        await callback.answer('🚫 السحب معطل حالياً', show_alert=True)
        return
    await callback.message.edit_text('💸 <b>طلب سحب</b>\n\nاختر نوع السحب:',
        reply_markup=await get_withdrawal_menu(), parse_mode=ParseMode.HTML)
    await callback.answer()


async def withdraw_ton_handler(callback: types.CallbackQuery, state: FSMContext
    ):
    """سحب TON"""
    if not await SettingsManager.get_bool_setting('WITHDRAWAL_TON_ENABLED', True):
        return await callback.answer('🚫 سحب TON معطل حالياً', show_alert=True)
    user_id = callback.from_user.id
    conn = get_db_connection()
    user = conn.cursor().execute(
        'SELECT ton_balance, wallet_address FROM users WHERE telegram_id = ?',
        (user_id,)).fetchone()
    conn.close()
    min_withdrawal = await SettingsManager.get_float_setting(
        'MIN_WITHDRAWAL_TON', 0.5)
    if user['ton_balance'] < min_withdrawal:
        await callback.answer(
            f'❌ رصيدك غير كافٍ. الحد الأدنى: {min_withdrawal} TON',
            show_alert=True)
        return
    if not user['wallet_address']:
        await callback.message.edit_text(
            """⚠️ <b>لم تقم بتحديد عنوان المحفظة</b>

يرجى تحديد عنوان TON أولاً:"""
            , reply_markup=InlineKeyboardBuilder().button(text=
            '⚙️ تحديد العنوان', callback_data='set_wallet_address').button(
            text='🔙 رجوع', callback_data='request_withdrawal').as_markup(),
            parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    await state.set_state(WithdrawalStates.request_ton_amount)
    await callback.message.edit_text(
        f"""🪙 <b>سحب TON</b>

رصيدك: <code>{user['ton_balance']:.4f}</code> TON
الحد الأدنى: <code>{min_withdrawal}</code> TON
عنوان المحفظة: <code>{user['wallet_address']}</code>

أدخل المبلغ الذي تريد سحبه:"""
        , reply_markup=get_cancel_button('request_withdrawal'), parse_mode=
        ParseMode.HTML)
    await callback.answer()


async def process_ton_withdrawal(message: types.Message, state: FSMContext):
    """معالجة سحب TON"""
    user_id = message.from_user.id
    try:
        amount = float(message.text.strip())
    except ValueError:
        await message.answer('❌ يرجى إدخال رقم صحيح')
        return
    min_withdrawal = await SettingsManager.get_float_setting(
        'MIN_WITHDRAWAL_TON', 0.5)
    if amount < min_withdrawal:
        await message.answer(f'❌ الحد الأدنى للسحب هو {min_withdrawal} TON')
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    user = cursor.execute(
        'SELECT ton_balance, wallet_address FROM users WHERE telegram_id = ?',
        (user_id,)).fetchone()
    if user['ton_balance'] < amount:
        await message.answer('❌ رصيدك غير كافٍ')
        conn.close()
        return
    cursor.execute(
        """
        UPDATE users SET ton_balance = ton_balance - ? WHERE telegram_id = ?
    """
        , (amount, user_id))
    cursor.execute(
        """
        INSERT INTO withdrawals (user_id, asset_type, amount, wallet_address, status)
        VALUES (?, 'TON', ?, ?, 'pending')
    """
        , (user_id, amount, user['wallet_address']))
    withdrawal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    await state.clear()
    try:
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ قبول", callback_data=f"admin_approve_wd_{withdrawal_id}")
        builder.button(text="❌ رفض", callback_data=f"admin_reject_wd_{withdrawal_id}")
        builder.adjust(2)

        await message.bot.send_message(ADMIN_ID,
            f"""🚨 <b>طلب سحب جديد</b>

🆔 طلب رقم: <code>#{withdrawal_id}</code>
👤 المستخدم: <code>{user_id}</code>
🪙 المبلغ: <code>{amount}</code> TON
💳 العنوان: <code>{user['wallet_address']}</code>"""
            , reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    except:
        pass
    await message.answer(
        f"""✅ <b>تم تقديم طلب السحب بنجاح!</b>

🪙 المبلغ: <code>{amount}</code> TON
💳 العنوان: <code>{user['wallet_address']}</code>

⏳ سيتم معالجة طلبك قريباً."""
        , reply_markup=get_back_button('dashboard'), parse_mode=ParseMode.HTML)


async def withdraw_stars_handler(callback: types.CallbackQuery, state:
    FSMContext):
    """سحب Stars"""
    if not await SettingsManager.get_bool_setting('WITHDRAWAL_STARS_ENABLED', True):
        return await callback.answer('🚫 سحب Stars معطل حالياً', show_alert=True)
    user_id = callback.from_user.id
    conn = get_db_connection()
    user = conn.cursor().execute(
        'SELECT stars_balance FROM users WHERE telegram_id = ?', (user_id,)
        ).fetchone()
    conn.close()
    min_withdrawal = await SettingsManager.get_int_setting(
        'MIN_WITHDRAWAL_STARS', 100)
    if user['stars_balance'] < min_withdrawal:
        await callback.answer(
            f'❌ رصيدك غير كافٍ. الحد الأدنى: {min_withdrawal} Stars',
            show_alert=True)
        return
    await state.set_state(WithdrawalStates.request_stars_amount)
    await callback.message.edit_text(
        f"""⭐ <b>سحب Stars</b>

رصيدك: <code>{user['stars_balance']}</code> Stars
الحد الأدنى: <code>{min_withdrawal}</code> Stars

أدخل عدد النجوم التي تريد سحبها:"""
        , reply_markup=get_cancel_button('request_withdrawal'), parse_mode=
        ParseMode.HTML)
    await callback.answer()


async def process_stars_withdrawal(message: types.Message, state: FSMContext):
    """معالجة سحب Stars"""
    user_id = message.from_user.id
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer('❌ يرجى إدخال رقم صحيح')
        return
    min_withdrawal = await SettingsManager.get_int_setting(
        'MIN_WITHDRAWAL_STARS', 100)
    if amount < min_withdrawal:
        await message.answer(f'❌ الحد الأدنى للسحب هو {min_withdrawal} Stars')
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    user = cursor.execute(
        'SELECT stars_balance FROM users WHERE telegram_id = ?', (user_id,)
        ).fetchone()
    if user['stars_balance'] < amount:
        await message.answer('❌ رصيدك غير كافٍ')
        conn.close()
        return
    cursor.execute(
        """
        UPDATE users SET stars_balance = stars_balance - ? WHERE telegram_id = ?
    """
        , (amount, user_id))
    cursor.execute(
        """
        INSERT INTO withdrawals (user_id, asset_type, amount, status)
        VALUES (?, 'STARS', ?, 'pending')
    """
        , (user_id, amount))
    withdrawal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    await state.clear()
    try:
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ قبول", callback_data=f"admin_approve_wd_{withdrawal_id}")
        builder.button(text="❌ رفض", callback_data=f"admin_reject_wd_{withdrawal_id}")
        builder.adjust(2)

        await message.bot.send_message(ADMIN_ID,
            f"""🚨 <b>طلب سحب جديد</b>

🆔 طلب رقم: <code>#{withdrawal_id}</code>
👤 المستخدم: <code>{user_id}</code>
⭐ المبلغ: <code>{amount}</code> Stars"""
            , reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    except:
        pass
    await message.answer(
        f"""✅ <b>تم تقديم طلب السحب بنجاح!</b>

⭐ المبلغ: <code>{amount}</code> Stars

⏳ سيتم معالجة طلبك قريباً."""
        , reply_markup=get_back_button('dashboard'), parse_mode=ParseMode.HTML)


async def set_wallet_address_handler(callback: types.CallbackQuery, state:
    FSMContext):
    """تحديد عنوان المحفظة"""
    await state.set_state(WithdrawalStates.set_wallet_address)
    await callback.message.edit_text(
        """⚙️ <b>تحديد عنوان TON</b>

أرسل عنوان محفظة TON الخاص بك:
(يجب أن يبدأ بـ E أو U أو 0 وطوله 48 حرف)"""
        , reply_markup=get_cancel_button('dashboard'), parse_mode=ParseMode
        .HTML)
    await callback.answer()


async def process_wallet_address(message: types.Message, state: FSMContext):
    """معالجة عنوان المحفظة"""
    address = message.text.strip()
    if not is_valid_ton_address(address):
        await message.answer(
            """❌ عنوان غير صالح!

يجب أن يكون العنوان:
• 48 حرفاً
• يبدأ بـ E أو U أو 0"""
            )
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET wallet_address = ? WHERE telegram_id = ?',
        (address, message.from_user.id))
    conn.commit()
    conn.close()
    await state.clear()
    await message.answer(
        f'✅ <b>تم تحديد العنوان بنجاح!</b>\n\n💳 العنوان: <code>{address}</code>'
        , reply_markup=get_back_button('dashboard'), parse_mode=ParseMode.HTML)


async def convert_points_handler(callback: types.CallbackQuery):
    """تحويل النقاط - المتجر الجديد"""
    conversion_enabled = await SettingsManager.get_bool_setting(
        'CONVERSION_ENABLED', True)
    if not conversion_enabled:
        await callback.answer('🚫 التحويل معطل حالياً', show_alert=True)
        return
    user_id = callback.from_user.id
    conn = get_db_connection()
    user = conn.cursor().execute(
        'SELECT points FROM users WHERE telegram_id = ?', (user_id,)).fetchone(
        )
    conn.close()
    points_ton = await SettingsManager.get_int_setting('CONVERSION_POINTS_TON',
        1000)
    points_stars = await SettingsManager.get_int_setting(
        'CONVERSION_POINTS_STARS', 150)
    text = f"""🔄 <b>تحويل النقاط</b>

💰 رصيدك: <code>{user['points']}</code> نقطة

📊 <b>أسعار التحويل:</b>
🪙 <code>{points_ton}</code> نقطة = 1 TON
⭐ <code>{points_stars}</code> نقطة = 10 Stars

اختر نوع التحويل:"""
    await callback.message.edit_text(text, reply_markup=await get_conversion_menu
        (), parse_mode=ParseMode.HTML)
    await callback.answer()


async def convert_to_ton_handler(callback: types.CallbackQuery, state:
    FSMContext):
    """تحويل إلى TON"""
    if not await SettingsManager.get_bool_setting('WITHDRAWAL_TON_ENABLED', True):
        return await callback.answer('🚫 تحويل TON معطل حالياً', show_alert=True)
    user_id = callback.from_user.id
    conn = get_db_connection()
    user = conn.cursor().execute(
        'SELECT points FROM users WHERE telegram_id = ?', (user_id,)).fetchone(
        )
    conn.close()
    conversion_rate = await SettingsManager.get_int_setting(
        'CONVERSION_POINTS_TON', 1000)
    await state.set_state(ConversionStates.enter_points_for_ton)
    await callback.message.edit_text(
        f"""🪙 <b>تحويل إلى TON</b>

رصيد النقاط: <code>{user['points']}</code>
سعر التحويل: <code>{conversion_rate}</code> نقطة = 1 TON

أدخل عدد النقاط التي تريد تحويلها:"""
        , reply_markup=get_cancel_button('convert_points'), parse_mode=
        ParseMode.HTML)
    await callback.answer()


async def process_convert_to_ton(message: types.Message, state: FSMContext):
    """معالجة التحويل إلى TON"""
    user_id = message.from_user.id
    try:
        points = int(message.text.strip())
    except ValueError:
        await message.answer('❌ يرجى إدخال رقم صحيح')
        return
    if points <= 0:
        await message.answer('❌ يجب أن يكون العدد أكبر من صفر')
        return
    conversion_rate = await SettingsManager.get_int_setting(
        'CONVERSION_POINTS_TON', 1000)
    ton_amount = points / conversion_rate
    conn = get_db_connection()
    cursor = conn.cursor()
    user = cursor.execute('SELECT points FROM users WHERE telegram_id = ?',
        (user_id,)).fetchone()
    if user['points'] < points:
        await message.answer('❌ رصيدك غير كافٍ')
        conn.close()
        return
    cursor.execute(
        """
        UPDATE users SET
            points = points - ?,
            ton_balance = ton_balance + ?
        WHERE telegram_id = ?
    """
        , (points, ton_amount, user_id))
    cursor.execute(
        """
        INSERT INTO points_history (user_id, action_type, points, description)
        VALUES (?, 'conversion', -?, ?)
    """
        , (user_id, points, f'تحويل إلى TON: {ton_amount:.4f}'))
    conn.commit()
    conn.close()
    await state.clear()
    await message.answer(
        f"""✅ <b>تم التحويل بنجاح!</b>

📤 النقاط المحولة: <code>{points}</code>
📥 TON المستلم: <code>{ton_amount:.4f}</code>"""
        , reply_markup=get_back_button('dashboard'), parse_mode=ParseMode.HTML)


async def convert_to_stars_handler(callback: types.CallbackQuery, state:
    FSMContext):
    """تحويل إلى Stars"""
    if not await SettingsManager.get_bool_setting('WITHDRAWAL_STARS_ENABLED', True):
        return await callback.answer('🚫 تحويل Stars معطل حالياً', show_alert=True)
    user_id = callback.from_user.id
    conn = get_db_connection()
    user = conn.cursor().execute(
        'SELECT points FROM users WHERE telegram_id = ?', (user_id,)).fetchone(
        )
    conn.close()
    conversion_rate = await SettingsManager.get_int_setting(
        'CONVERSION_POINTS_STARS', 150)
    await state.set_state(ConversionStates.enter_points_for_stars)
    await callback.message.edit_text(
        f"""⭐ <b>تحويل إلى Stars</b>

رصيد النقاط: <code>{user['points']}</code>
سعر التحويل: <code>{conversion_rate}</code> نقطة = 10 Stars

أدخل عدد النقاط التي تريد تحويلها:"""
        , reply_markup=get_cancel_button('convert_points'), parse_mode=
        ParseMode.HTML)
    await callback.answer()


async def process_convert_to_stars(message: types.Message, state: FSMContext):
    """معالجة التحويل إلى Stars"""
    user_id = message.from_user.id
    try:
        points = int(message.text.strip())
    except ValueError:
        await message.answer('❌ يرجى إدخال رقم صحيح')
        return
    if points <= 0:
        await message.answer('❌ يجب أن يكون العدد أكبر من صفر')
        return
    conversion_rate = await SettingsManager.get_int_setting(
        'CONVERSION_POINTS_STARS', 150)
    stars_amount = points // conversion_rate * 10
    actual_points = stars_amount // 10 * conversion_rate
    conn = get_db_connection()
    cursor = conn.cursor()
    user = cursor.execute('SELECT points FROM users WHERE telegram_id = ?',
        (user_id,)).fetchone()
    if user['points'] < actual_points:
        await message.answer('❌ رصيدك غير كافٍ')
        conn.close()
        return
    cursor.execute(
        """
        UPDATE users SET
            points = points - ?,
            stars_balance = stars_balance + ?
        WHERE telegram_id = ?
    """
        , (actual_points, stars_amount, user_id))
    cursor.execute(
        """
        INSERT INTO points_history (user_id, action_type, points, description)
        VALUES (?, 'conversion', -?, ?)
    """
        , (user_id, actual_points, f'تحويل إلى Stars: {stars_amount}'))
    conn.commit()
    conn.close()
    await state.clear()
    await message.answer(
        f"""✅ <b>تم التحويل بنجاح!</b>

📤 النقاط المحولة: <code>{actual_points}</code>
📥 Stars المستلمة: <code>{stars_amount}</code>"""
        , reply_markup=get_back_button('dashboard'), parse_mode=ParseMode.HTML)


async def points_history_handler(callback: types.CallbackQuery):
    """عرض سجل النقاط"""
    user_id = callback.from_user.id
    history = await PointsSystem.get_points_history(user_id, 15)
    if not history:
        text = '📜 <b>سجل النقاط</b>\n\nلا توجد سجلات.'
    else:
        text = '📜 <b>سجل النقاط</b>\n\n'
        for record in history:
            date = datetime.fromisoformat(record['created_at']).strftime(
                '%Y-%m-%d %H:%M')
            points = record['points']
            sign = '+' if points > 0 else ''
            text += f"{sign}{points} - {record['description']} ({date})\n"
    builder = InlineKeyboardBuilder()
    builder.button(text='🔙 رجوع', callback_data='dashboard')
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def bot_hosting_menu_handler(callback: types.CallbackQuery):
    """عرض قائمة استضافة البوتات"""
    free_max = await SettingsManager.get_int_setting('FREE_PLAN_MAX_USERS',
        2000)
    premium_price_ton = await SettingsManager.get_float_setting(
        'PREMIUM_PLAN_PRICE_TON', 50)
    enterprise_price_ton = await SettingsManager.get_float_setting(
        'ENTERPRISE_PLAN_PRICE_TON', 200)
    premium_duration = await SettingsManager.get_int_setting(
        'PREMIUM_PLAN_DURATION', 30)
    enterprise_duration = await SettingsManager.get_int_setting(
        'ENTERPRISE_PLAN_DURATION', 90)
    await callback.message.edit_text(
        f"""🤖 <b>نظام استضافة البوتات</b>

يمكنك استضافة بوتات تليجرام بسهولة!

🎁 <b>الباقة المجانية:</b>
• {free_max} مستخدم
• بصمة جهاز
• حماية IP
• نظام إحالة
• مهام يومية

💎 <b>بريميوم - {premium_price_ton} TON/{premium_duration} يوم</b>
• 10,000 مستخدم
• تخصيص البوت
• دعم فني VIP

👑 <b>إنتربرايز - {enterprise_price_ton} TON/{enterprise_duration} يوم</b>
• 100,000+ مستخدم
• نظام سحب كامل
• تخصيص كامل"""
        , reply_markup=get_bot_hosting_menu(), parse_mode=ParseMode.HTML)
    await callback.answer()


async def add_new_bot_handler(callback: types.CallbackQuery, state: FSMContext
    ):
    """بدء إضافة بوت جديد"""
    await state.set_state(BotHostingStates.enter_token)
    await callback.message.edit_text(
        """🤖 <b>استضافة بوت جديد</b>

أرسل لي <b>توكن البوت</b> الذي تريد استضافته.

⚠️ <b>تنبيه مهم</b>:
• توكن البوت هو مفتاح التحكم الكامل
• نضمن عدم استخدامه لأغراض ضارة
• يمكنك تغيير التوكن في أي وقت

📌 <b>كيف تحصل على التوكن:</b>
1. تواصل مع @BotFather
2. أرسل /newbot وأنشئ بوتاً
3. انسخ التوكن وأرسله هنا"""
        , reply_markup=get_cancel_button('bot_hosting_menu'), parse_mode=
        ParseMode.HTML)
    await callback.answer()


async def process_bot_token(message: types.Message, state: FSMContext, bot: Bot
    ):
    """معالجة توكن البوت - مُحسَّن"""
    token = message.text.strip()
    user_id = message.from_user.id
    data = await state.get_data()
    is_update = data.get('is_update', False)
    bot_id = data.get('bot_id')
    status_msg = await message.answer('🔄 جاري التحقق من التوكن...')
    try:
        temp_bot = Bot(token=token)
        me = await temp_bot.get_me()
        bot_username = me.username
        bot_name = me.full_name
        await temp_bot.session.close()
    except Exception as e:
        await status_msg.delete()
        await message.answer(
            """❌ <b>توكن غير صالح!</b>

تأكد من:
• نسخ التوكن كاملاً
• البوت غير مفعل من قبل
• عدم وجود مسافات في التوكن"""
            , parse_mode=ParseMode.HTML)
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    if is_update and bot_id:
        existing = cursor.execute(
            'SELECT * FROM hosted_bots WHERE id = ? AND owner_id = ?', (
            bot_id, user_id)).fetchone()
        if not existing:
            await status_msg.delete()
            await message.answer('❌ البوت غير موجود أو ليس لديك صلاحية!')
            conn.close()
            return
        await HostedBotSystem.stop_bot(bot_id)
        cursor.execute(
            """
            UPDATE hosted_bots
            SET bot_token = ?, bot_username = ?, bot_name = ?, is_active = 1
            WHERE id = ?
        """
            , (token, bot_username, bot_name, bot_id))
        conn.commit()
        conn.close()
        await status_msg.delete()
        await state.clear()
        success = await HostedBotSystem.start_bot(bot_id, token,
            bot_username, user_id)
        if success:
            await message.answer(
                f"""✅ <b>تم تحديث التوكن بنجاح!</b>

🤖 {bot_name}
👤 @{bot_username}

تم تشغيل البوت تلقائياً."""
                , parse_mode=ParseMode.HTML)
        else:
            await message.answer(
                f"""⚠️ <b>تم تحديث التوكن لكن فشل تشغيل البوت</b>

يمكنك محاولة التشغيل يدوياً من لوحة التحكم."""
                , parse_mode=ParseMode.HTML)
        await show_bot_dashboard(message, user_id, bot_id)
        return
    existing = cursor.execute(
        'SELECT * FROM hosted_bots WHERE bot_token = ? OR bot_username = ?',
        (token, bot_username)).fetchone()
    if existing:
        await status_msg.delete()
        await message.answer('❌ هذا البوت مستضاف مسبقاً!')
        conn.close()
        return
    free_max_users = await SettingsManager.get_int_setting(
        'FREE_PLAN_MAX_USERS', 2000)
    cursor.execute(
        """
        INSERT INTO hosted_bots
        (bot_token, bot_username, bot_name, owner_id, plan_type, max_users, config)
        VALUES (?, ?, ?, ?, 'free', ?, ?)
    """
        , (token, bot_username, bot_name, user_id, free_max_users, json.
        dumps({
            'referral_reward': 10,
            'channel_username': None,
            'min_withdrawal_ton': 0.5,
            'min_withdrawal_stars': 100,
            'withdrawal_ton_enabled': True,
            'withdrawal_stars_enabled': True,
            'mandatory_channels': [],
            'custom_welcome': None,
            'created_at': datetime.now().isoformat()
        })))
    bot_id = cursor.lastrowid
    conn.commit()
    conn.close()
    await status_msg.delete()
    await state.clear()
    await message.answer(
        f"""✅ <b>تم إضافة البوت بنجاح!</b>

🤖 {bot_name}
👤 @{bot_username}
📊 الخطة: مجاني - {free_max_users} مستخدم

يمكنك الآن التحكم بالبوت من لوحة البوتات."""
        , parse_mode=ParseMode.HTML)
    await HostedBotSystem.start_bot(bot_id, token, bot_username, user_id)
    await show_bot_dashboard(message, user_id, bot_id)


async def my_bots_handler(callback: types.CallbackQuery):
    """عرض قائمة بوتات المستخدم - مُحسَّن"""
    user_id = callback.from_user.id
    conn = get_db_connection()
    bots = conn.cursor().execute(
        """
        SELECT * FROM hosted_bots WHERE owner_id = ? ORDER BY created_at DESC
    """
        , (user_id,)).fetchall()
    conn.close()
    if not bots:
        await callback.message.edit_text(
            """📋 <b>ليس لديك أي بوتات مستضافة</b>

ابدأ بإضافة أول بوت لك الآن!"""
            , reply_markup=InlineKeyboardBuilder().button(text=
            '➕ إضافة بوت جديد', callback_data='add_new_bot').button(text=
            '🔙 رجوع', callback_data='bot_hosting_menu').adjust(1).as_markup
            (), parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    text = '📋 <b>بوتاتك المستضافة:</b>\n\n'
    builder = InlineKeyboardBuilder()
    for bot in bots[:5]:
        status = '🟢' if bot['is_active'] else '🔴'
        text += f"{status} {bot['bot_name']} - @{bot['bot_username']}\n"
        text += f"📊 {bot['current_users']}/{bot['max_users']} مستخدم\n"
        text += f"💎 {bot['plan_type'].capitalize()}\n"
        if bot['expires_at']:
            expires = datetime.fromisoformat(bot['expires_at'])
            if expires > datetime.now():
                text += f"⏳ ينتهي: {expires.strftime('%Y-%m-%d')}\n"
            else:
                text += f'⚠️ <b>منتهية الصلاحية</b>\n'
        text += '\n'
        builder.button(text=f"🤖 {bot['bot_name'][:15]}", callback_data=
            f"bot_dashboard_{bot['id']}")
    builder.button(text='🔙 رجوع', callback_data='bot_hosting_menu')
    builder.adjust(2)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def show_bot_dashboard(message_or_callback, user_id: int, bot_id: int):
    """عرض لوحة تحكم البوت - مُحسَّنة مع جميع الأزرار"""
    conn = get_db_connection()
    try:
        bot_data = conn.cursor().execute(
            'SELECT * FROM hosted_bots WHERE id = ? AND owner_id = ?', (
            bot_id, user_id)).fetchone()
    finally:
        conn.close()
    if not bot_data:
        if isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.answer('❌ البوت غير موجود',
                show_alert=True)
        return
    plan_config = await SettingsManager.get_plan_config(bot_data['plan_type'])
    expires = datetime.fromisoformat(bot_data['expires_at']) if bot_data[
        'expires_at'] else None
    is_expired = expires and expires <= datetime.now()
    text = f"""🤖 <b>{bot_data['bot_name']}</b>
👤 @{bot_data['bot_username']}

📊 <b>الإحصائيات</b>:
• المستخدمون: {bot_data['current_users']}/{bot_data['max_users']}
• النقاط الممنوحة: {bot_data['total_points_given']}

💎 <b>الباقة</b>: {plan_config['name']}
"""
    if expires:
        if not is_expired:
            text += f"⏳ تنتهي: {expires.strftime('%Y-%m-%d')}\n"
        else:
            text += f'⚠️ <b>منتهية الصلاحية</b>\n'
    text += f'\n✅ <b>الميزات المتاحة</b>:\n'
    features_text = ''
    for feature_key, feature_name in [('referral_system', '🔗 نظام الإحالة'),
        ('daily_bonus', '🎁 مكافأة يومية'), ('tasks_system', '🎯 نظام المهام'
        ), ('fingerprint_protection', '🛡️ بصمة الجهاز'), (
        'ip_ban_protection', '🚫 حظر IP'), ('withdrawals', '💸 نظام السحب'),
        ('customization', '⚙️ تخصيص'), ('conversion', '🔄 تحويل النقاط')]:
        if plan_config['features'].get(feature_key, False):
            features_text += f'✅ {feature_name}\n'
    if features_text:
        text += features_text
    else:
        text += 'لا توجد ميزات متاحة\n'
    reply_markup = get_bot_dashboard_menu(bot_id, bot_data['is_active'],
        bot_data['plan_type'], is_expired)
    try:
        if isinstance(message_or_callback, types.CallbackQuery):
            try:
                await message_or_callback.message.edit_text(text,
                    reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            except TelegramBadRequest as e:
                if 'message is not modified' in str(e).lower():
                    await message_or_callback.answer('✅ محدث بالفعل',
                        show_alert=False)
                else:
                    raise
        else:
            await message_or_callback.answer(text, reply_markup=
                reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f'خطأ في عرض لوحة التحكم: {e}')
        if isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.answer('❌ حدث خطأ في العرض',
                show_alert=True)


async def bot_edit_token_start(callback: types.CallbackQuery, state: FSMContext
    ):
    """بدء تحديث توكن البوت"""
    bot_id = int(callback.data.split('_')[3])
    user_id = callback.from_user.id
    await state.set_state(BotHostingStates.enter_token)
    await state.update_data(bot_id=bot_id, is_update=True)
    await callback.message.edit_text(
        """🔑 <b>تحديث توكن البوت</b>

⚠️ <b>تحذير:</b>
• سيتم إيقاف البوت الحالي
• يجب الحصول على توكن جديد من @BotFather

أرسل التوكن الجديد:"""
        , reply_markup=get_cancel_button(f'bot_dashboard_{bot_id}'),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def bot_delete_handler(callback: types.CallbackQuery):
    """حذف بوت - مُحسَّن"""
    bot_id = int(callback.data.split('_')[2])
    user_id = callback.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    bot_data = cursor.execute(
        'SELECT * FROM hosted_bots WHERE id = ? AND owner_id = ?', (bot_id,
        user_id)).fetchone()
    if not bot_data:
        await callback.answer('❌ البوت غير موجود', show_alert=True)
        conn.close()
        return
    await HostedBotSystem.stop_bot(bot_id)
    cursor.execute('DELETE FROM hosted_bots WHERE id = ?', (bot_id,))
    conn.commit()
    conn.close()
    await callback.answer('✅ تم حذف البوت بنجاح', show_alert=True)
    await my_bots_handler(callback)


async def bot_toggle_handler(callback: types.CallbackQuery):
    """تشغيل/إيقاف بوت - مُحسَّن"""
    data = callback.data.split('_')
    action = data[1]
    bot_id = int(data[2])
    user_id = callback.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    bot_data = cursor.execute(
        'SELECT * FROM hosted_bots WHERE id = ? AND owner_id = ?', (bot_id,
        user_id)).fetchone()
    if not bot_data:
        await callback.answer('❌ البوت غير موجود', show_alert=True)
        conn.close()
        return
    if action == 'start':
        success = await HostedBotSystem.start_bot(bot_id, bot_data[
            'bot_token'], bot_data['bot_username'], user_id)
        if success:
            await callback.answer('✅ تم تشغيل البوت', show_alert=True)
        else:
            await callback.answer('❌ فشل تشغيل البوت', show_alert=True)
    else:
        success = await HostedBotSystem.stop_bot(bot_id)
        if success:
            cursor.execute('UPDATE hosted_bots SET is_active = 0 WHERE id = ?',
                (bot_id,))
            conn.commit()
            await callback.answer('✅ تم إيقاف البوت', show_alert=True)
        else:
            await callback.answer('❌ فشل إيقاف البوت', show_alert=True)
    conn.close()
    await show_bot_dashboard(callback.message, user_id, bot_id)


async def upgrade_bot_handler(callback: types.CallbackQuery):
    """عرض خطط الترقية - معطل مؤقتاً"""
    await callback.answer('⛔️ نظام الترقية معطل حالياً', show_alert=True)
    return


async def admin_add_task_process(message: types.Message, state: FSMContext, bot: Bot):
    """معالجة إضافة مهمة - بنظام تفاعلي (Step-by-Step)"""
    data = await state.get_data()
    step = data.get("step", "name")
    bot_type = data.get("bot_type", "main")
    bot_id = data.get("bot_id")
    back_dest = "admin_tasks_menu" if bot_type == "main" else f"bot_tasks_{bot_id}"

    if step == "name":
        await state.update_data(name=message.text.strip())
        builder = InlineKeyboardBuilder()
        builder.button(text="التالي ⬇️", callback_data="task_next_step")
        await message.answer(f"✅ تم حفظ الاسم: <b>{message.text}</b>\n\nاضغط على التالي للمتابعة.", reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    elif step == "max_users":
        try:
            max_users = int(message.text.strip())
            await state.update_data(max_users=max_users)
            builder = InlineKeyboardBuilder()
            builder.button(text="التالي ⬇️", callback_data="task_next_step")
            await message.answer(f"✅ تم حفظ العدد: <b>{max_users}</b>\n\nاضغط على التالي للمتابعة.", reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        except:
            await message.answer("❌ يرجى إدخال رقم صحيح لعدد المستفيدين")
    elif step == "points":
        try:
            points = int(message.text.strip())
            await state.update_data(points=points)
            builder = InlineKeyboardBuilder()
            builder.button(text="التالي ⬇️", callback_data="task_next_step")
            await message.answer(f"✅ تم حفظ النقاط: <b>{points}</b>\n\nاضغط على التالي للمتابعة.", reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        except:
            await message.answer("❌ يرجى إدخال رقم صحيح لعدد النقاط")
    elif step == "link":
        link = message.text.strip()
        chat_id = link
        if 't.me/' in chat_id:
            chat_id = '@' + chat_id.split('t.me/')[1].split('/')[0]
        try:
            target_bot = bot
            if bot_type == 'hosted':
                conn = get_db_connection()
                b_info = conn.cursor().execute(
                    'SELECT bot_token FROM hosted_bots WHERE id = ?', (bot_id,)
                    ).fetchone()
                conn.close()
                if b_info:
                    target_bot = Bot(token=b_info['bot_token'])
            me = await target_bot.get_me()
            try:
                member = await target_bot.get_chat_member(chat_id=chat_id,
                    user_id=me.id)
                if member.status not in ['administrator', 'creator']:
                    await message.answer(
                        '❌ البوت ليس مشرفاً في القناة أو المجموعة. يرجى رفعه لمشرف أولاً ثم المحاولة مرة أخرى.'
                        )
                    if bot_type == 'hosted' and target_bot != bot:
                        await target_bot.session.close()
                    return
            except Exception as e:
                await message.answer(
                    f"""❌ تعذر التحقق من صلاحيات البوت. تأكد من أن البوت موجود في القناة/المجموعة ومن صحة الرابط.
{str(e)}"""
                    )
                if bot_type == 'hosted' and target_bot != bot:
                    await target_bot.session.close()
                return
            if bot_type == 'hosted' and target_bot != bot:
                await target_bot.session.close()
            conn = get_db_connection()
            cursor = conn.cursor()
            if bot_type == 'main':
                cursor.execute(
                    'INSERT INTO tasks (name, points, link, max_completions, is_active) VALUES (?, ?, ?, ?, 1)'
                    , (data['name'], data['points'], link, data['max_users']))
            else:
                cursor.execute(
                    'INSERT INTO hosted_bot_tasks (bot_id, name, points, link, max_completions, is_active) VALUES (?, ?, ?, ?, ?, 1)'
                    , (bot_id, data['name'], data['points'], link, data[
                    'max_users']))
            conn.commit()
            conn.close()
            await state.clear()
            await message.answer('✅ تم تأكيد نشر المهمة بنجاح!',
                reply_markup=get_back_button(back_dest))
        except Exception as e:
            await message.answer(f'❌ حدث خطأ: {str(e)}')


async def task_next_step_handler(callback: types.CallbackQuery, state: FSMContext):
    """التحكم في الانتقال للخطوة التالية في إنشاء المهام"""
    data = await state.get_data()
    step = data.get("step", "name")

    if step == "name":
        await state.update_data(step="max_users")
        await callback.message.edit_text("🟢 الخطوة 2:\nطلب إدخال عدد الأشخاص المستفيدين من المهمة", reply_markup=get_cancel_button("admin_tasks_menu"))
    elif step == "max_users":
        await state.update_data(step="points")
        await callback.message.edit_text("🟢 الخطوة 3:\nطلب إدخال عدد النقاط التي يحصل عليها كل شخص", reply_markup=get_cancel_button("admin_tasks_menu"))
    elif step == "points":
        await state.update_data(step="link")
        await callback.message.edit_text("🟢 الخطوة 4:\nطلب إدخال: رابط قناة أو يوزر قناة أو رابط مجموعة", reply_markup=get_cancel_button("admin_tasks_menu"))
    else:
        await callback.answer("يرجى إكمال البيانات المطلوبة.")


async def cmd_admin(message: types.Message):
    """أمر /admin"""
    if not is_admin(message.from_user.id):
        return await message.answer('⛔️ هذا الأمر للمشرفين فقط')
    await message.answer('👑 <b>لوحة تحكم المشرف</b>', reply_markup=
        get_admin_menu(), parse_mode=ParseMode.HTML)


def is_admin(user_id: int) ->bool:
    """التحقق من صلاحية المشرف"""
    if user_id == ADMIN_ID:
        return True
    conn = get_db_connection()
    user = conn.cursor().execute(
        'SELECT is_admin FROM users WHERE telegram_id = ?', (user_id,)
        ).fetchone()
    conn.close()
    return user and user['is_admin'] == 1


async def admin_panel_handler(callback: types.CallbackQuery):
    """عرض لوحة المشرف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    await callback.message.edit_text('👑 <b>لوحة تحكم المشرف</b>',
        reply_markup=get_admin_menu(), parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_stats_handler(callback: types.CallbackQuery):
    """إحصائيات المشرف"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    total_users = cursor.execute('SELECT COUNT(*) as count FROM users'
        ).fetchone()['count']
    total_bots = cursor.execute('SELECT COUNT(*) as count FROM hosted_bots'
        ).fetchone()['count']
    active_bots = cursor.execute(
        'SELECT COUNT(*) as count FROM hosted_bots WHERE is_active = 1'
        ).fetchone()['count']
    total_referrals = cursor.execute(
        'SELECT COUNT(*) as count FROM referrals WHERE is_valid = 1').fetchone(
        )['count']
    total_points = cursor.execute('SELECT SUM(points) as sum FROM users'
        ).fetchone()['sum'] or 0
    total_ton = cursor.execute('SELECT SUM(ton_balance) as sum FROM users'
        ).fetchone()['sum'] or 0
    total_stars = cursor.execute('SELECT SUM(stars_balance) as sum FROM users'
        ).fetchone()['sum'] or 0
    pending_withdrawals = cursor.execute(
        "SELECT COUNT(*) as count FROM withdrawals WHERE status = 'pending'"
        ).fetchone()['count']
    today = datetime.now().strftime('%Y-%m-%d')
    new_today = cursor.execute(
        'SELECT COUNT(*) as count FROM users WHERE date(registration_date) = ?'
        , (today,)).fetchone()['count']
    conn.close()
    text = f"""📊 <b>إحصائيات النظام</b>

👥 <b>المستخدمين:</b>
• إجمالي المستخدمين: {total_users}
• مستخدمين جدد اليوم: {new_today}

🤖 <b>البوتات:</b>
• البوتات المستضافة: {total_bots}
• البوتات النشطة: {active_bots}

🔗 <b>الإحالات:</b>
• الإحالات الناجحة: {total_referrals}

💰 <b>الأرصدة:</b>
• إجمالي النقاط: {total_points}
• إجمالي TON: {total_ton:.4f}
• إجمالي Stars: {total_stars}

💸 <b>طلبات السحب المعلقة:</b> {pending_withdrawals}"""
    builder = InlineKeyboardBuilder()
    builder.button(text='🔄 تحديث', callback_data='admin_stats')
    builder.button(text='🔙 رجوع', callback_data='admin_panel')
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_users_menu_handler(callback: types.CallbackQuery):
    """قائمة إدارة المستخدمين"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    text = f'👥 <b>إدارة المستخدمين</b>\n\nاختر الإجراء:'
    builder = InlineKeyboardBuilder()
    builder.button(text='🔍 البحث عن مستخدم', callback_data='admin_find_user')
    builder.button(text='➕ إضافة نقاط', callback_data='admin_add_points')
    builder.button(text='➖ خصم نقاط', callback_data='admin_subtract_points')
    builder.button(text='📋 قائمة المحظورين', callback_data='admin_banned_users'
        )
    builder.button(text='🔙 رجوع', callback_data='admin_panel')
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_find_user_start(callback: types.CallbackQuery, state:
    FSMContext):
    """بدء البحث عن مستخدم"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    await state.set_state(AdminStates.find_user)
    await callback.message.edit_text(
        """🔍 <b>البحث عن مستخدم</b>

أرسل معرف المستخدم (ID) أو اسم المستخدم:"""
        , reply_markup=get_cancel_button('admin_users_menu'), parse_mode=
        ParseMode.HTML)
    await callback.answer()


async def admin_find_user_process(message: types.Message, state: FSMContext):
    """معالجة البحث عن مستخدم - ✅ تم إضافة التحقق"""
    search = message.text.strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        user_id = int(search)
        user = cursor.execute('SELECT * FROM users WHERE telegram_id = ?',
            (user_id,)).fetchone()
    except ValueError:
        user = cursor.execute(
            'SELECT * FROM users WHERE username LIKE ? OR full_name LIKE ?',
            (f'%{search}%', f'%{search}%')).fetchone()
    conn.close()
    if not user:
        await message.answer('❌ لم يتم العثور على المستخدم', reply_markup=
            get_back_button('admin_users_menu'))
        await state.clear()
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    referrals = cursor.execute(
        'SELECT COUNT(*) as count FROM referrals WHERE referrer_id = ? AND is_valid = 1'
        , (user['telegram_id'],)).fetchone()['count']
    tasks = cursor.execute(
        'SELECT COUNT(*) as count FROM user_tasks WHERE user_id = ?', (user
        ['telegram_id'],)).fetchone()['count']
    conn.close()
    text = f"""👤 <b>معلومات المستخدم</b>

🆔 المعرف: <code>{user['telegram_id']}</code>
👤 الاسم: {user['full_name']}
📱 اليوزر: @{user['username'] or 'لا يوجد'}
📅 تاريخ التسجيل: {datetime.fromisoformat(user['registration_date']).strftime('%Y-%m-%d')}
🚫 محظور: {'نعم' if user['is_banned'] else 'لا'}
✅ موثق: {'نعم' if user['fingerprint_verified'] else 'لا'}

💰 <b>الأرصدة:</b>
• النقاط: {user['points']}
• TON: {user['ton_balance']:.4f}
• Stars: {user['stars_balance']}

📊 <b>الإحصائيات:</b>
• الإحالات: {referrals}
• المهام: {tasks}
• إجمالي النقاط المكتسبة: {user['total_earned_points']}
"""
    if user['wallet_address']:
        text += f"\n💳 <b>العنوان:</b> <code>{user['wallet_address']}</code>"
    builder = InlineKeyboardBuilder()
    builder.button(text='➕ إضافة نقاط', callback_data=
        f"admin_add_points_to_{user['telegram_id']}")
    builder.button(text='➖ خصم نقاط', callback_data=
        f"admin_sub_points_from_{user['telegram_id']}")
    if user['is_banned']:
        builder.button(text='✅ فك الحظر', callback_data=
            f"admin_unban_user_{user['telegram_id']}")
    else:
        builder.button(text='🚫 حظر', callback_data=
            f"admin_ban_user_{user['telegram_id']}")
    builder.button(text='🔙 رجوع', callback_data='admin_users_menu')
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode
        =ParseMode.HTML)
    await state.clear()


async def admin_broadcast_start(callback: types.CallbackQuery, state:
    FSMContext):
    """بدء البث"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    broadcast_enabled = await SettingsManager.get_bool_setting(
        'BROADCAST_ENABLED', True)
    if not broadcast_enabled:
        await callback.answer('🚫 البث معطل حالياً', show_alert=True)
        return
    await state.set_state(AdminStates.broadcast)
    await callback.message.edit_text(
        """📢 <b>إرسال إشعار للجميع</b>

أرسل الرسالة التي تريد إرسالها:
(يمكنك استخدام HTML formatting)"""
        , reply_markup=get_cancel_button('admin_panel'), parse_mode=
        ParseMode.HTML)
    await callback.answer()


async def admin_broadcast_process(message: types.Message, state: FSMContext,
    bot: Bot):
    """معالجة البث"""
    broadcast_text = message.text
    conn = get_db_connection()
    users = conn.cursor().execute(
        'SELECT telegram_id FROM users WHERE is_banned = 0').fetchall()
    conn.close()
    status_msg = await message.answer('🔄 جاري الإرسال...')
    sent = 0
    failed = 0
    for user in users:
        try:
            await bot.send_message(user['telegram_id'],
                f"""📢 <b>إشعار من الإدارة</b>

{broadcast_text}""",
                parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
    await status_msg.edit_text(
        f'✅ <b>تم الإرسال!</b>\n\n📤 نجح: {sent}\n❌ فشل: {failed}')
    await state.clear()


async def admin_security_settings_handler(callback: types.CallbackQuery):
    """عرض إعدادات الحماية"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    ip_ban = await SettingsManager.get_bool_setting('IP_BAN_ENABLED', True)
    max_users_ip = await SettingsManager.get_int_setting('MAX_USERS_PER_IP', 1)
    ban_duration = await SettingsManager.get_int_setting('BAN_DURATION_HOURS',
        72)
    max_attempts = await SettingsManager.get_int_setting(
        'MAX_ATTEMPTS_PER_HOUR', 5)
    secret_expiry = await SettingsManager.get_int_setting(
        'SECRET_LINK_EXPIRY_MINUTES', 5)
    block_duplicate = await SettingsManager.get_bool_setting(
        'BLOCK_DUPLICATE_DEVICES', True)
    vpn_detection = await SettingsManager.get_bool_setting(
        'VPN_DETECTION_ENABLED', True)
    text = f"""🔧 <b>إعدادات الحماية</b>

🚫 <b>حظر IP</b>: {'✅ مفعل' if ip_ban else '❌ معطل'}
👥 <b>أقصى مستخدمين لكل IP</b>: <code>{max_users_ip}</code>
⏱️ <b>مدة حظر IP</b>: <code>{ban_duration}</code> ساعة
🔄 <b>أقصى محاولات/ساعة</b>: <code>{max_attempts}</code>
🔗 <b>صلاحية الرابط السري</b>: <code>{secret_expiry}</code> دقيقة
🛡️ <b>منع تكرار البصمة</b>: {'✅ مفعل' if block_duplicate else '❌ معطل'}
🔒 <b>كشف VPN</b>: {'✅ مفعل' if vpn_detection else '❌ معطل'}

📌 لتغيير أي إعداد، اختر من القائمة:"""
    builder = InlineKeyboardBuilder()
    builder.button(text='🚫 تفعيل/تعطيل حظر IP', callback_data=
        'admin_toggle_ip_ban')
    builder.button(text='👥 تغيير أقصى مستخدمين/IP', callback_data=
        'admin_set_max_users_ip')
    builder.button(text='⏱️ تغيير مدة الحظر', callback_data=
        'admin_set_ban_duration')
    builder.button(text='🔄 تغيير أقصى محاولات', callback_data=
        'admin_set_max_attempts')
    builder.button(text='🔗 تغيير صلاحية الرابط', callback_data=
        'admin_set_secret_expiry')
    builder.button(text='🛡️ تفعيل/تعطيل منع التكرار', callback_data=
        'admin_toggle_duplicate')
    builder.button(text='🔒 تفعيل/تعطيل كشف VPN', callback_data=
        'admin_toggle_vpn')
    builder.button(text='🔙 رجوع', callback_data='admin_panel')
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_toggle_setting_handler(callback: types.CallbackQuery):
    """تبديل إعداد منطقي"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    setting_map = {'admin_toggle_ip_ban': 'IP_BAN_ENABLED',
        'admin_toggle_duplicate': 'BLOCK_DUPLICATE_DEVICES',
        'admin_toggle_vpn': 'VPN_DETECTION_ENABLED'}
    setting_key = setting_map.get(callback.data)
    if not setting_key:
        return await callback.answer('❌ إعداد غير معروف', show_alert=True)
    current = await SettingsManager.get_bool_setting(setting_key, True)
    new_value = not current
    await SettingsManager.update_setting(setting_key, '1' if new_value else
        '0', callback.from_user.id)
    await callback.answer(f"✅ تم {'تفعيل' if new_value else 'تعطيل'} الإعداد",
        show_alert=True)
    await admin_security_settings_handler(callback)


async def admin_set_value_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء تغيير قيمة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    setting_map = {
        'admin_set_max_users_ip': ('MAX_USERS_PER_IP', 'أقصى مستخدمين لكل IP', SettingsStates.set_max_users_per_ip, 'admin_security_settings'),
        'admin_set_ban_duration': ('BAN_DURATION_HOURS', 'مدة حظر IP (ساعات)', SettingsStates.set_ban_duration, 'admin_security_settings'),
        'admin_set_max_attempts': ('MAX_ATTEMPTS_PER_HOUR', 'أقصى محاولات في الساعة', SettingsStates.set_max_attempts, 'admin_security_settings'),
        'admin_set_secret_expiry': ('SECRET_LINK_EXPIRY_MINUTES', 'صلاحية الرابط السري (دقائق)', SettingsStates.set_secret_expiry, 'admin_security_settings'),
        'admin_set_referral_reward': ('REFERRAL_REWARD', 'نقاط الإحالة', SettingsStates.set_referral_reward, 'admin_points_settings'),
        'admin_set_daily_bonus_base': ('DAILY_BONUS_BASE', 'المكافأة اليومية الأساسية', SettingsStates.set_daily_bonus_base, 'admin_points_settings'),
        'admin_set_daily_bonus_streak': ('DAILY_BONUS_STREAK', 'نقاط التتابع اليومي', SettingsStates.set_daily_bonus_streak, 'admin_points_settings'),
        'admin_set_daily_bonus_weekly': ('DAILY_BONUS_WEEKLY', 'مكافأة الأسبوع الكامل', SettingsStates.set_daily_bonus_weekly, 'admin_points_settings'),
        'admin_set_welcome_bonus': ('WELCOME_BONUS', 'نقاط الترحيب', SettingsStates.set_welcome_bonus, 'admin_points_settings'),
        'admin_set_min_withdrawal_ton': ('MIN_WITHDRAWAL_TON', 'الحد الأدنى لسحب TON', SettingsStates.set_min_withdrawal_ton, 'admin_withdrawal_types'),
        'admin_set_min_withdrawal_stars': ('MIN_WITHDRAWAL_STARS', 'الحد الأدنى لسحب Stars', SettingsStates.set_min_withdrawal_stars, 'admin_withdrawal_types'),
    }
    setting_info = setting_map.get(callback.data)
    if not setting_info:
        return await callback.answer('❌ إعداد غير معروف', show_alert=True)

    setting_key, setting_name, state_to_set, return_menu = setting_info
    current_value = await SettingsManager.get_setting(setting_key, '0')
    await state.set_state(state_to_set)
    await state.update_data(setting_key=setting_key, setting_name=setting_name, return_menu=return_menu)

    await callback.message.edit_text(
        f"""🔧 <b>تغيير {setting_name}</b>

القيمة الحالية: <code>{current_value}</code>

أدخل القيمة الجديدة:"""
        , reply_markup=get_cancel_button(return_menu),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_set_value_process(message: types.Message, state: FSMContext):
    """معالجة تغيير القيمة - ✅ تم إضافة التحقق من البيانات"""
    data = await state.get_data()
    setting_key = data.get('setting_key')
    setting_name = data.get('setting_name')
    return_menu = data.get('return_menu', 'admin_panel')

    if not setting_key or not setting_name:
        await message.answer(
            '❌ خطأ: لم يتم العثور على بيانات الإعداد. يرجى المحاولة مرة أخرى.',
            reply_markup=get_back_button(return_menu))
        await state.clear()
        return

    try:
        if 'TON' in setting_key or 'PRICE' in setting_key:
            new_value = float(message.text.strip())
        else:
            new_value = int(message.text.strip())

        if new_value < 0:
            await message.answer('❌ يجب أن تكون القيمة موجبة')
            return
    except ValueError:
        await message.answer('❌ يرجى إدخال رقم صحيح')
        return

    await SettingsManager.update_setting(setting_key, str(new_value), message.from_user.id)
    await message.answer(
        f'✅ <b>تم التحديث بنجاح!</b>\n\n{setting_name}: <code>{new_value}</code>',
        reply_markup=get_back_button(return_menu), parse_mode=ParseMode.HTML)
    await state.clear()


async def admin_plan_settings_handler(callback: types.CallbackQuery):
    """عرض إعدادات الباقات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    free_max = await SettingsManager.get_int_setting('FREE_PLAN_MAX_USERS',
        2000)
    premium_max = await SettingsManager.get_int_setting(
        'PREMIUM_PLAN_MAX_USERS', 10000)
    enterprise_max = await SettingsManager.get_int_setting(
        'ENTERPRISE_PLAN_MAX_USERS', 100000)
    premium_price_ton = await SettingsManager.get_float_setting(
        'PREMIUM_PLAN_PRICE_TON', 50)
    premium_price_stars = await SettingsManager.get_int_setting(
        'PREMIUM_PLAN_PRICE_STARS', 15000)
    enterprise_price_ton = await SettingsManager.get_float_setting(
        'ENTERPRISE_PLAN_PRICE_TON', 200)
    enterprise_price_stars = await SettingsManager.get_int_setting(
        'ENTERPRISE_PLAN_PRICE_STARS', 60000)
    premium_duration = await SettingsManager.get_int_setting(
        'PREMIUM_PLAN_DURATION', 30)
    enterprise_duration = await SettingsManager.get_int_setting(
        'ENTERPRISE_PLAN_DURATION', 90)
    text = f"""💎 <b>إعدادات الباقات</b>

🎁 <b>الباقة المجانية</b>:
• أقصى مستخدمين: <code>{free_max}</code>

💎 <b>الباقة المميزة</b>:
• أقصى مستخدمين: <code>{premium_max}</code>
• السعر: <code>{premium_price_ton}</code> TON / <code>{premium_price_stars}</code> Stars
• المدة: <code>{premium_duration}</code> يوم

👑 <b>الباقة الاحترافية</b>:
• أقصى مستخدمين: <code>{enterprise_max}</code>
• السعر: <code>{enterprise_price_ton}</code> TON / <code>{enterprise_price_stars}</code> Stars
• المدة: <code>{enterprise_duration}</code> يوم

📌 لتغيير أي إعداد، اختر من القائمة:"""
    builder = InlineKeyboardBuilder()
    builder.button(text='🎁 تغيير حد المجانية', callback_data=
        'admin_set_free_max')
    builder.button(text='💎 تغيير حد بريميوم', callback_data=
        'admin_set_premium_max')
    builder.button(text='👑 تغيير حد إنتربرايز', callback_data=
        'admin_set_enterprise_max')
    builder.button(text='💰 تغيير سعر بريميوم TON', callback_data=
        'admin_set_premium_price_ton')
    builder.button(text='⭐ تغيير سعر بريميوم Stars', callback_data=
        'admin_set_premium_price_stars')
    builder.button(text='💰 تغيير سعر إنتربرايز TON', callback_data=
        'admin_set_enterprise_price_ton')
    builder.button(text='⭐ تغيير سعر إنتربرايز Stars', callback_data=
        'admin_set_enterprise_price_stars')
    builder.button(text='⏱️ تغيير مدة بريميوم', callback_data=
        'admin_set_premium_duration')
    builder.button(text='⏱️ تغيير مدة إنتربرايز', callback_data=
        'admin_set_enterprise_duration')
    builder.button(text='🔙 رجوع', callback_data='admin_panel')
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_points_settings_handler(callback: types.CallbackQuery):
    """إعدادات النقاط"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    referral_reward = await SettingsManager.get_int_setting('REFERRAL_REWARD',
        10)
    daily_bonus_base = await SettingsManager.get_int_setting('DAILY_BONUS_BASE'
        , 10)
    daily_bonus_streak = await SettingsManager.get_int_setting(
        'DAILY_BONUS_STREAK', 5)
    daily_bonus_weekly = await SettingsManager.get_int_setting(
        'DAILY_BONUS_WEEKLY', 100)
    welcome_bonus = await SettingsManager.get_int_setting('WELCOME_BONUS', 5)
    text = f"""💰 <b>إعدادات النقاط</b>

🔗 <b>نقاط الإحالة</b>: <code>{referral_reward}</code>
🎁 <b>المكافأة اليومية الأساسية</b>: <code>{daily_bonus_base}</code>
🔥 <b>نقاط التتابع اليومي</b>: <code>{daily_bonus_streak}</code>
🎉 <b>مكافأة الأسبوع الكامل</b>: <code>{daily_bonus_weekly}</code>
👋 <b>نقاط الترحيب</b>: <code>{welcome_bonus}</code>

📌 لتغيير أي إعداد، اختر من القائمة:"""
    builder = InlineKeyboardBuilder()
    builder.button(text='🔗 تغيير نقاط الإحالة', callback_data=
        'admin_set_referral_reward')
    builder.button(text='🎁 تغيير المكافأة اليومية', callback_data=
        'admin_set_daily_bonus_base')
    builder.button(text='🔥 تغيير نقاط التتابع', callback_data=
        'admin_set_daily_bonus_streak')
    builder.button(text='🎉 تغيير مكافأة الأسبوع', callback_data=
        'admin_set_daily_bonus_weekly')
    builder.button(text='👋 تغيير نقاط الترحيب', callback_data=
        'admin_set_welcome_bonus')
    builder.button(text='🔙 رجوع', callback_data='admin_panel')
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_conversion_settings_handler(callback: types.CallbackQuery):
    """إعدادات التحويل - يمكن تعديل الأسعار من هنا"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    conversion_enabled = await SettingsManager.get_bool_setting(
        'CONVERSION_ENABLED', True)
    points_ton = await SettingsManager.get_int_setting('CONVERSION_POINTS_TON',
        1000)
    points_stars = await SettingsManager.get_int_setting(
        'CONVERSION_POINTS_STARS', 150)
    text = f"""🔄 <b>إعدادات تحويل النقاط (متجر النقاط)</b>

📊 <b>الحالة</b>: {'✅ مفعل' if conversion_enabled else '❌ معطل'}

🪙 <b>سعر TON</b>: <code>{points_ton}</code> نقطة = 1 TON
⭐ <b>سعر Stars</b>: <code>{points_stars}</code> نقطة = 10 Stars

💡 <b>ملاحظة:</b>
يمكن للمستخدمين تحويل نقاطهم إلى TON أو Stars من قسم 'تحويل النقاط'

📌 لتغيير أي إعداد، اختر من القائمة:"""
    builder = InlineKeyboardBuilder()
    builder.button(text='📊 تفعيل/تعطيل التحويل', callback_data=
        'admin_toggle_conversion')
    builder.button(text='🪙 تغيير سعر TON', callback_data=
        'admin_set_conversion_ton')
    builder.button(text='⭐ تغيير سعر Stars', callback_data=
        'admin_set_conversion_stars')
    builder.button(text='🔙 رجوع', callback_data='admin_panel')
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_withdrawals_pending_handler(callback: types.CallbackQuery):
    """عرض طلبات السحب المعلقة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    withdrawals = cursor.execute(
        """
        SELECT w.*, u.username, u.full_name
        FROM withdrawals w
        JOIN users u ON w.user_id = u.telegram_id
        WHERE w.status = 'pending'
        ORDER BY w.request_date DESC
        LIMIT 10
    """
        ).fetchall()
    conn.close()
    if not withdrawals:
        await callback.message.edit_text(
            '💸 <b>طلبات السحب</b>\n\nلا توجد طلبات معلقة.', reply_markup=
            get_back_button('admin_panel'), parse_mode=ParseMode.HTML)
        await callback.answer()
        return
    text = '💸 <b>طلبات السحب المعلقة</b>\n\n'
    builder = InlineKeyboardBuilder()
    for w in withdrawals:
        date = datetime.fromisoformat(w['request_date']).strftime(
            '%Y-%m-%d %H:%M')
        text += f"""🆔 <b>#{w['id']}</b>
👤 {w['full_name']} (@{w['username'] or 'N/A'})
💰 {w['amount']} {w['asset_type']}
📅 {date}

"""
        builder.button(text=f"✅ قبول #{w['id']}", callback_data=
            f"admin_approve_wd_{w['id']}")
        builder.button(text=f"❌ رفض #{w['id']}", callback_data=
            f"admin_reject_wd_{w['id']}")
    builder.button(text='🔙 رجوع', callback_data='admin_panel')
    builder.adjust(2)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_process_withdrawal_handler(callback: types.CallbackQuery,
    bot: Bot, state: FSMContext):
    """معالجة طلب السحب"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    data = callback.data.split('_')
    action = data[1]
    withdrawal_id = int(data[3])
    if action == 'reject':
        await state.set_state(AdminStates.reject_withdrawal_reason)
        await state.update_data(wd_id=withdrawal_id, bot_type='main')
        await callback.message.answer('📝 يرجى إدخال سبب الرفض:')
        await callback.answer()
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    withdrawal = cursor.execute('SELECT * FROM withdrawals WHERE id = ?', (
        withdrawal_id,)).fetchone()
    if not withdrawal:
        await callback.answer('❌ الطلب غير موجود', show_alert=True)
        conn.close()
        return
    cursor.execute(
        """
        UPDATE withdrawals
        SET status = 'approved', processed_date = ?, processed_by = ?
        WHERE id = ?
    """
        , (datetime.now().isoformat(), callback.from_user.id, withdrawal_id))
    conn.commit()
    conn.close()
    try:
        await bot.send_message(withdrawal['user_id'],
            f"""✅ تم قبول طلب السحب الخاص بك.
💰 المبلغ: {withdrawal['amount']} {withdrawal['asset_type']}
يرجى التأكد من محفظتك."""
            , parse_mode=ParseMode.HTML)
    except:
        pass
    await callback.answer('✅ تم القبول', show_alert=True)
    await admin_withdrawals_pending_handler(callback)


async def admin_reject_withdrawal_reason_process(message: types.Message,
    state: FSMContext, bot: Bot):
    """معالجة سبب رفض طلب السحب"""
    data = await state.get_data()
    wd_id = data.get('wd_id')
    bot_type = data.get('bot_type')
    reason = message.text.strip()
    conn = get_db_connection()
    cursor = conn.cursor()
    if bot_type == 'main':
        withdrawal = cursor.execute('SELECT * FROM withdrawals WHERE id = ?',
            (wd_id,)).fetchone()
        if not withdrawal:
            await message.answer('❌ الطلب غير موجود')
            conn.close()
            await state.clear()
            return
        cursor.execute(
            """
            UPDATE withdrawals SET status = 'rejected', notes = ?, processed_date = ?, processed_by = ?
            WHERE id = ?
        """
            , (reason, datetime.now().isoformat(), message.from_user.id, wd_id)
            )
        if withdrawal['asset_type'] == 'TON':
            cursor.execute(
                'UPDATE users SET ton_balance = ton_balance + ? WHERE telegram_id = ?'
                , (withdrawal['amount'], withdrawal['user_id']))
        else:
            cursor.execute(
                'UPDATE users SET stars_balance = stars_balance + ? WHERE telegram_id = ?'
                , (int(withdrawal['amount']), withdrawal['user_id']))
        target_user_id = withdrawal['user_id']
        amount_text = f"{withdrawal['amount']} {withdrawal['asset_type']}"
    else:
        withdrawal = cursor.execute(
            'SELECT * FROM hosted_bot_withdrawals WHERE id = ?', (wd_id,)
            ).fetchone()
        if not withdrawal:
            await message.answer('❌ الطلب غير موجود')
            conn.close()
            await state.clear()
            return
        cursor.execute(
            """
            UPDATE hosted_bot_withdrawals SET status = 'rejected', notes = ?, processed_date = ?, processed_by = ?
            WHERE id = ?
        """
            , (reason, datetime.now().isoformat(), message.from_user.id, wd_id)
            )
        if withdrawal['asset_type'] == 'TON':
            cursor.execute(
                'UPDATE hosted_bot_users SET ton_balance = ton_balance + ? WHERE bot_id = ? AND user_telegram_id = ?'
                , (withdrawal['amount'], withdrawal['bot_id'], withdrawal[
                'user_id']))
        else:
            cursor.execute(
                'UPDATE hosted_bot_users SET stars_balance = stars_balance + ? WHERE bot_id = ? AND user_telegram_id = ?'
                , (int(withdrawal['amount']), withdrawal['bot_id'],
                withdrawal['user_id']))
        target_user_id = withdrawal['user_id']
        amount_text = f"{withdrawal['amount']} {withdrawal['asset_type']}"
    conn.commit()
    conn.close()
    try:
        await bot.send_message(target_user_id,
            f"""❌ تم رفض طلب السحب الخاص بك.
💰 المبلغ: {amount_text}
📝 السبب: {reason}"""
            , parse_mode=ParseMode.HTML)
    except:
        pass
    await message.answer(f'✅ تم رفض الطلب #{wd_id} وإرسال السبب للمستخدم.')
    await state.clear()


async def admin_tasks_menu_handler(callback: types.CallbackQuery):
    """قائمة إدارة المهام"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    tasks_enabled = await SettingsManager.get_bool_setting('TASKS_ENABLED',
        True)
    conn = get_db_connection()
    tasks = conn.cursor().execute('SELECT * FROM tasks WHERE is_active = 1'
        ).fetchall()
    conn.close()
    text = f"""🎯 <b>إدارة المهام</b>

📊 <b>الحالة</b>: {'✅ مفعل' if tasks_enabled else '❌ معطل'}
📋 <b>المهام النشطة</b>: {len(tasks)}

اختر الإجراء:"""
    builder = InlineKeyboardBuilder()
    builder.button(text='➕ إضافة مهمة', callback_data='admin_add_task')
    builder.button(text='📋 عرض المهام', callback_data='admin_list_tasks')
    builder.button(text='📊 تفعيل/تعطيل', callback_data='admin_toggle_tasks')
    builder.button(text='🔙 رجوع', callback_data='admin_panel')
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_add_task_start(callback: types.CallbackQuery, state: FSMContext
    ):
    """بدء إضافة مهمة - البوت الرئيسي"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    await state.set_state(AdminStates.add_task)
    await state.update_data(step='name', bot_type='main')
    await callback.message.edit_text('🟢 الخطوة 1:\nطلب إدخال اسم المهمة',
        reply_markup=get_cancel_button('admin_tasks_menu'), parse_mode=
        ParseMode.HTML)
    await callback.answer()


async def admin_list_tasks_handler(callback: types.CallbackQuery):
    """عرض قائمة المهام"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    tasks = cursor.execute(
        'SELECT * FROM tasks ORDER BY is_active DESC, points DESC').fetchall()
    conn.close()
    if not tasks:
        await callback.message.edit_text('🎯 <b>لا توجد مهام</b>',
            reply_markup=get_back_button('admin_tasks_menu'), parse_mode=
            ParseMode.HTML)
        await callback.answer()
        return
    text = '🎯 <b>قائمة المهام</b>:\n\n'
    builder = InlineKeyboardBuilder()
    for task in tasks:
        status = '🟢' if task['is_active'] else '🔴'
        text += f"""{status} <b>{task['name']}</b>
💰 {task['points']} نقطة
📊 {'نشط' if task['is_active'] else 'معطل'}

"""
        if task['is_active']:
            builder.button(text=f"🔴 تعطيل {task['id']}", callback_data=
                f"admin_toggle_task_{task['id']}")
        else:
            builder.button(text=f"🟢 تفعيل {task['id']}", callback_data=
                f"admin_toggle_task_{task['id']}")
        builder.button(text=f"🗑️ حذف {task['id']}", callback_data=
            f"admin_delete_task_{task['id']}")
    builder.button(text='🔙 رجوع', callback_data='admin_tasks_menu')
    builder.adjust(2)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_toggle_task_handler(callback: types.CallbackQuery):
    """تفعيل/تعطيل مهمة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    task_id = int(callback.data.split('_')[3])
    conn = get_db_connection()
    cursor = conn.cursor()
    task = cursor.execute('SELECT is_active FROM tasks WHERE id = ?', (
        task_id,)).fetchone()
    if task:
        new_status = 0 if task['is_active'] else 1
        cursor.execute('UPDATE tasks SET is_active = ? WHERE id = ?', (
            new_status, task_id))
        conn.commit()
    conn.close()
    await callback.answer('✅ تم التحديث', show_alert=True)
    await admin_list_tasks_handler(callback)


async def admin_delete_task_handler(callback: types.CallbackQuery):
    """حذف مهمة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    task_id = int(callback.data.split('_')[3])
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    await callback.answer('✅ تم الحذف', show_alert=True)
    await admin_list_tasks_handler(callback)


async def admin_toggle_tasks_handler(callback: types.CallbackQuery):
    """تفعيل/تعطيل نظام المهام"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    current = await SettingsManager.get_bool_setting('TASKS_ENABLED', True)
    new_value = not current
    await SettingsManager.update_setting('TASKS_ENABLED', '1' if new_value else
        '0', callback.from_user.id)
    await callback.answer(
        f"✅ تم {'تفعيل' if new_value else 'تعطيل'} نظام المهام", show_alert
        =True)
    await admin_tasks_menu_handler(callback)


async def admin_ban_ip_start(callback: types.CallbackQuery, state: FSMContext):
    """بدء حظر IP"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    await state.set_state(AdminStates.ban_ip)
    await callback.message.edit_text('🚫 <b>حظر IP</b>\n\nأدخل عنوان IP للحظر:',
        reply_markup=get_cancel_button('admin_panel'), parse_mode=ParseMode
        .HTML)
    await callback.answer()


async def admin_ban_ip_process(message: types.Message, state: FSMContext):
    """معالجة حظر IP"""
    ip_address = message.text.strip()
    await state.update_data(ip_address=ip_address, step='duration')
    await state.set_state(AdminStates.ban_ip_duration)
    await message.answer(
        '🚫 <b>حظر IP</b>\n\nأدخل مدة الحظر بالساعات (0 للحظر الدائم):',
        reply_markup=get_cancel_button('admin_panel'), parse_mode=ParseMode
        .HTML)


async def admin_ban_ip_duration(message: types.Message, state: FSMContext):
    """مدة حظر IP"""
    try:
        duration = int(message.text.strip())
    except ValueError:
        await message.answer('❌ يرجى إدخال رقم صحيح')
        return
    data = await state.get_data()
    ip_address = data['ip_address']
    await SmartIPBan.ban_ip(ip_address, 'حظر يدوي من المشرف', duration if
        duration > 0 else 8760, message.from_user.id)
    await state.clear()
    duration_text = f'{duration} ساعة' if duration > 0 else 'دائم'
    await message.answer(
        f"""✅ <b>تم حظر IP بنجاح!</b>

🌐 IP: <code>{ip_address}</code>
⏱️ المدة: {duration_text}"""
        , reply_markup=get_back_button('admin_panel'), parse_mode=ParseMode
        .HTML)


async def admin_unban_ip_start(callback: types.CallbackQuery, state: FSMContext
    ):
    """بدء فك حظر IP"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    banned_ips = await SmartIPBan.get_banned_ips()
    if not banned_ips:
        await callback.message.edit_text('✅ <b>لا توجد IPs محظورة حالياً</b>',
            reply_markup=get_back_button('admin_panel'), parse_mode=
            ParseMode.HTML)
        await callback.answer()
        return
    text = '📋 <b>الـ IPs المحظورة</b>:\n\n'
    for ip in banned_ips:
        text += f"🌐 <code>{ip['ip_address']}</code>\n"
        text += f"📅 {ip['banned_at']}\n"
        text += f"📝 {ip['ban_reason']}\n\n"
    await state.set_state(AdminStates.unban_ip)
    await callback.message.edit_text(text + '\nأدخل IP لفك الحظر:',
        reply_markup=get_cancel_button('admin_panel'), parse_mode=ParseMode
        .HTML)
    await callback.answer()


async def admin_unban_ip_process(message: types.Message, state: FSMContext):
    """معالجة فك حظر IP"""
    ip_address = message.text.strip()
    await SmartIPBan.unban_ip(ip_address)
    await state.clear()
    await message.answer(
        f'✅ <b>تم فك حظر IP بنجاح!</b>\n\n🌐 IP: <code>{ip_address}</code>',
        reply_markup=get_back_button('admin_panel'), parse_mode=ParseMode.HTML)


async def admin_all_bots_handler(callback: types.CallbackQuery):
    """عرض جميع البوتات المستضافة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    bots = cursor.execute(
        """
        SELECT hb.*, u.username as owner_username, u.full_name as owner_name
        FROM hosted_bots hb
        JOIN users u ON hb.owner_id = u.telegram_id
        ORDER BY hb.created_at DESC
        LIMIT 10
    """
        ).fetchall()
    conn.close()
    if not bots:
        await callback.message.edit_text('🤖 <b>لا توجد بوتات مستضافة</b>',
            reply_markup=get_back_button('admin_panel'), parse_mode=
            ParseMode.HTML)
        await callback.answer()
        return
    text = '📋 <b>البوتات المستضافة</b>:\n\n'
    for bot in bots:
        status = '🟢' if bot['is_active'] else '🔴'
        text += f"""{status} <b>{bot['bot_name']}</b>
👤 المالك: {bot['owner_name']}
📊 {bot['current_users']}/{bot['max_users']} مستخدم
💎 {bot['plan_type'].capitalize()}

"""
    builder = InlineKeyboardBuilder()
    builder.button(text='🔄 تحديث', callback_data='admin_all_bots')
    builder.button(text='🔙 رجوع', callback_data='admin_panel')
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_all_settings_handler(callback: types.CallbackQuery):
    """عرض جميع الإعدادات"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    settings = await SettingsManager.get_all_settings()
    text = '⚙️ <b>جميع الإعدادات</b>:\n\n'
    categories = {'🔧 الحماية': ['IP_BAN_ENABLED', 'MAX_USERS_PER_IP',
        'BAN_DURATION_HOURS', 'MAX_ATTEMPTS_PER_HOUR',
        'SECRET_LINK_EXPIRY_MINUTES', 'BLOCK_DUPLICATE_DEVICES',
        'VPN_DETECTION_ENABLED'], '💰 النقاط': ['REFERRAL_REWARD',
        'DAILY_BONUS_BASE', 'DAILY_BONUS_STREAK', 'DAILY_BONUS_WEEKLY',
        'WELCOME_BONUS'], '💸 السحب': ['MIN_WITHDRAWAL_TON',
        'MIN_WITHDRAWAL_STARS', 'WITHDRAWAL_FEE_PERCENT',
        'WITHDRAWAL_ENABLED', 'WITHDRAWAL_TON_ENABLED', 'WITHDRAWAL_STARS_ENABLED'],
        '🔄 التحويل': ['CONVERSION_POINTS_TON',
        'CONVERSION_POINTS_STARS', 'CONVERSION_ENABLED'], '💎 الباقات': [
        'FREE_PLAN_MAX_USERS', 'PREMIUM_PLAN_MAX_USERS',
        'ENTERPRISE_PLAN_MAX_USERS', 'PREMIUM_PLAN_PRICE_TON',
        'ENTERPRISE_PLAN_PRICE_TON'], '🎯 المهام': ['TASKS_ENABLED',
        'TASK_BONUS_POINTS'], '🔧 عام': ['MAINTENANCE_MODE',
        'BROADCAST_ENABLED', 'HOSTING_BUTTON_ENABLED', 'MANDATORY_CHANNELS']}
    for category, keys in categories.items():
        text += f'\n<b>{category}</b>:\n'
        for key in keys:
            value = settings.get(key, 'غير محدد')
            text += f'• {key}: <code>{value}</code>\n'
    builder = InlineKeyboardBuilder()
    builder.button(text='🔙 رجوع', callback_data='admin_panel')
    if len(text) > 4000:
        text = text[:4000] + '\n\n... (تم اقتصاص الباقي)'
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_add_points_start(callback: types.CallbackQuery, state:
    FSMContext):
    """بدء إضافة نقاط"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    await state.set_state(AdminStates.add_points)
    await state.update_data(step='user_id')
    await callback.message.edit_text(
        '➕ <b>إضافة نقاط</b>\n\nأدخل معرف المستخدم (ID):', reply_markup=
        get_cancel_button('admin_users_menu'), parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_add_points_process(message: types.Message, state:
    FSMContext, bot: Bot):
    """معالجة إضافة نقاط - ✅ تم إضافة معامل bot"""
    data = await state.get_data()
    step = data.get('step', 'user_id')
    if step == 'user_id':
        try:
            user_id = int(message.text.strip())
            conn = get_db_connection()
            user = conn.cursor().execute(
                'SELECT * FROM users WHERE telegram_id = ?', (user_id,)
                ).fetchone()
            conn.close()
            if not user:
                await message.answer('❌ المستخدم غير موجود')
                return
            await state.update_data(target_user_id=user_id,
                target_user_name=user['full_name'], step='points')
            await message.answer(
                f"➕ <b>إضافة نقاط لـ {user['full_name']}</b>\n\nأدخل عدد النقاط:"
                , reply_markup=get_cancel_button('admin_users_menu'),
                parse_mode=ParseMode.HTML)
        except ValueError:
            await message.answer('❌ يرجى إدخال معرف صحيح')
    elif step == 'points':
        try:
            points = int(message.text.strip())
            if points <= 0:
                await message.answer('❌ يجب أن تكون النقاط أكبر من صفر')
                return
        except ValueError:
            await message.answer('❌ يرجى إدخال رقم صحيح')
            return
        await state.update_data(points=points, step='reason')
        await message.answer(
            "➕ <b>إضافة نقاط</b>\n\nأدخل سبب الإضافة (أو أرسل 'تخطي'):",
            reply_markup=get_cancel_button('admin_users_menu'), parse_mode=
            ParseMode.HTML)
    elif step == 'reason':
        data = await state.get_data()
        reason = message.text.strip()
        if reason == 'تخطي':
            reason = None
        target_user_id = data['target_user_id']
        points = data['points']
        await PointsSystem.add_points(target_user_id, points, 'admin_add',
            reason)
        await state.clear()
        try:
            await bot.send_message(target_user_id,
                f"""🎉 <b>تم إضافة نقاط!</b>

➕ النقاط المضافة: <code>{points}</code>
📝 السبب: {reason or 'لا يوجد'}"""
                , parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning(f'فشل إرسال إشعار للمستخدم {target_user_id}: {e}')
        await message.answer(
            f"""✅ <b>تم إضافة النقاط بنجاح!</b>

👤 المستخدم: {data['target_user_name']}
➕ النقاط: {points}"""
            , reply_markup=get_back_button('admin_users_menu'), parse_mode=
            ParseMode.HTML)


async def admin_subtract_points_start(callback: types.CallbackQuery, state:
    FSMContext):
    """بدء خصم نقاط"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    await state.set_state(AdminStates.subtract_points)
    await state.update_data(step='user_id')
    await callback.message.edit_text(
        '➖ <b>خصم نقاط</b>\n\nأدخل معرف المستخدم (ID):', reply_markup=
        get_cancel_button('admin_users_menu'), parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_subtract_points_process(message: types.Message, state:
    FSMContext, bot: Bot):
    """معالجة خصم نقاط - ✅ تم إضافة معامل bot"""
    data = await state.get_data()
    step = data.get('step', 'user_id')
    if step == 'user_id':
        try:
            user_id = int(message.text.strip())
            conn = get_db_connection()
            user = conn.cursor().execute(
                'SELECT * FROM users WHERE telegram_id = ?', (user_id,)
                ).fetchone()
            conn.close()
            if not user:
                await message.answer('❌ المستخدم غير موجود')
                return
            await state.update_data(target_user_id=user_id,
                target_user_name=user['full_name'], step='points')
            await message.answer(
                f"""➖ <b>خصم نقاط من {user['full_name']}</b>

رصيده الحالي: {user['points']}

أدخل عدد النقاط:"""
                , reply_markup=get_cancel_button('admin_users_menu'),
                parse_mode=ParseMode.HTML)
        except ValueError:
            await message.answer('❌ يرجى إدخال معرف صحيح')
    elif step == 'points':
        try:
            points = int(message.text.strip())
            if points <= 0:
                await message.answer('❌ يجب أن تكون النقاط أكبر من صفر')
                return
        except ValueError:
            await message.answer('❌ يرجى إدخال رقم صحيح')
            return
        await state.update_data(points=points, step='reason')
        await message.answer(
            "➖ <b>خصم نقاط</b>\n\nأدخل سبب الخصم (أو أرسل 'تخطي'):",
            reply_markup=get_cancel_button('admin_users_menu'), parse_mode=
            ParseMode.HTML)
    elif step == 'reason':
        data = await state.get_data()
        reason = message.text.strip()
        if reason == 'تخطي':
            reason = None
        target_user_id = data['target_user_id']
        points = data['points']
        success = await PointsSystem.subtract_points(target_user_id, points,
            'admin_subtract', reason)
        await state.clear()
        if success:
            try:
                await bot.send_message(target_user_id,
                    f"""⚠️ <b>تم خصم نقاط</b>

➖ النقاط المخصومة: <code>{points}</code>
📝 السبب: {reason or 'لا يوجد'}"""
                    , parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.warning(
                    f'فشل إرسال إشعار للمستخدم {target_user_id}: {e}')
            await message.answer(
                f"""✅ <b>تم خصم النقاط بنجاح!</b>

👤 المستخدم: {data['target_user_name']}
➖ النقاط: {points}"""
                , reply_markup=get_back_button('admin_users_menu'),
                parse_mode=ParseMode.HTML)
        else:
            await message.answer('❌ رصيد المستخدم غير كافٍ', reply_markup=
                get_back_button('admin_users_menu'))


async def admin_ban_user_handler(callback: types.CallbackQuery):
    """حظر مستخدم"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    user_id = int(callback.data.split('_')[3])
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 1 WHERE telegram_id = ?',
        (user_id,))
    conn.commit()
    conn.close()
    await callback.answer('✅ تم حظر المستخدم', show_alert=True)


async def admin_unban_user_handler(callback: types.CallbackQuery):
    """فك حظر مستخدم"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    user_id = int(callback.data.split('_')[3])
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_banned = 0 WHERE telegram_id = ?',
        (user_id,))
    conn.commit()
    conn.close()
    await callback.answer('✅ تم فك حظر المستخدم', show_alert=True)


async def admin_banned_users_handler(callback: types.CallbackQuery):
    """عرض المستخدمين المحظورين"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    banned_users = cursor.execute(
        'SELECT * FROM users WHERE is_banned = 1 ORDER BY registration_date DESC LIMIT 20'
        ).fetchall()
    conn.close()
    if not banned_users:
        await callback.message.edit_text('✅ <b>لا يوجد مستخدمين محظورين</b>',
            reply_markup=get_back_button('admin_users_menu'), parse_mode=
            ParseMode.HTML)
        await callback.answer()
        return
    text = '🚫 <b>المستخدمين المحظورين</b>:\n\n'
    for user in banned_users:
        text += f"""🆔 <code>{user['telegram_id']}</code>
👤 {user['full_name']}
📅 {datetime.fromisoformat(user['registration_date']).strftime('%Y-%m-%d')}

"""
    builder = InlineKeyboardBuilder()
    builder.button(text='🔙 رجوع', callback_data='admin_users_menu')
    await callback.message.edit_text(text, reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_toggle_conversion_handler(callback: types.CallbackQuery):
    """تفعيل/تعطيل التحويل"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    current = await SettingsManager.get_bool_setting('CONVERSION_ENABLED', True
        )
    new_value = not current
    await SettingsManager.update_setting('CONVERSION_ENABLED', '1' if
        new_value else '0', callback.from_user.id)
    await callback.answer(f"✅ تم {'تفعيل' if new_value else 'تعطيل'} التحويل",
        show_alert=True)
    await admin_conversion_settings_handler(callback)


async def admin_set_conversion_ton_start(callback: types.CallbackQuery,
    state: FSMContext):
    """تغيير سعر تحويل TON"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    current = await SettingsManager.get_int_setting('CONVERSION_POINTS_TON',
        1000)
    await state.set_state(SettingsStates.set_conversion_points_ton)
    await callback.message.edit_text(
        f"""🪙 <b>تغيير سعر تحويل TON</b>

القيمة الحالية: <code>{current}</code> نقطة = 1 TON

أدخل القيمة الجديدة:"""
        , reply_markup=get_cancel_button('admin_conversion_settings'),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_set_conversion_ton_process(message: types.Message, state:
    FSMContext):
    """معالجة تغيير سعر TON"""
    try:
        value = int(message.text.strip())
        if value <= 0:
            await message.answer('❌ يجب أن تكون القيمة أكبر من صفر')
            return
    except ValueError:
        await message.answer('❌ يرجى إدخال رقم صحيح')
        return
    await SettingsManager.update_setting('CONVERSION_POINTS_TON', str(value
        ), message.from_user.id)
    await state.clear()
    await message.answer(
        f"""✅ <b>تم التحديث!</b>

🪙 السعر الجديد: <code>{value}</code> نقطة = 1 TON"""
        , reply_markup=get_back_button('admin_conversion_settings'),
        parse_mode=ParseMode.HTML)


async def admin_set_conversion_stars_start(callback: types.CallbackQuery,
    state: FSMContext):
    """تغيير سعر تحويل Stars"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    current = await SettingsManager.get_int_setting('CONVERSION_POINTS_STARS',
        150)
    await state.set_state(SettingsStates.set_conversion_points_stars)
    await callback.message.edit_text(
        f"""⭐ <b>تغيير سعر تحويل Stars</b>

القيمة الحالية: <code>{current}</code> نقطة = 10 Stars

أدخل القيمة الجديدة:"""
        , reply_markup=get_cancel_button('admin_conversion_settings'),
        parse_mode=ParseMode.HTML)
    await callback.answer()


async def admin_set_conversion_stars_process(message: types.Message, state:
    FSMContext):
    """معالجة تغيير سعر Stars"""
    try:
        value = int(message.text.strip())
        if value <= 0:
            await message.answer('❌ يجب أن تكون القيمة أكبر من صفر')
            return
    except ValueError:
        await message.answer('❌ يرجى إدخال رقم صحيح')
        return
    await SettingsManager.update_setting('CONVERSION_POINTS_STARS', str(
        value), message.from_user.id)
    await state.clear()
    await message.answer(
        f"""✅ <b>تم التحديث!</b>

⭐ السعر الجديد: <code>{value}</code> نقطة = 10 Stars"""
        , reply_markup=get_back_button('admin_conversion_settings'),
        parse_mode=ParseMode.HTML)




async def admin_set_plan_value_start(callback: types.CallbackQuery, state:
    FSMContext):
    """بدء تغيير قيمة باقة"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)
    setting_map = {'admin_set_free_max': ('FREE_PLAN_MAX_USERS',
        'حد المستخدمين للباقة المجانية', SettingsStates.set_free_max_users),
        'admin_set_premium_max': ('PREMIUM_PLAN_MAX_USERS',
        'حد المستخدمين للباقة المميزة', SettingsStates.
        set_premium_max_users), 'admin_set_enterprise_max': (
        'ENTERPRISE_PLAN_MAX_USERS', 'حد المستخدمين للباقة الاحترافية',
        SettingsStates.set_enterprise_max_users),
        'admin_set_premium_price_ton': ('PREMIUM_PLAN_PRICE_TON',
        'سعر الباقة المميزة (TON)', SettingsStates.set_premium_price_ton),
        'admin_set_premium_price_stars': ('PREMIUM_PLAN_PRICE_STARS',
        'سعر الباقة المميزة (Stars)', SettingsStates.
        set_premium_price_stars), 'admin_set_enterprise_price_ton': (
        'ENTERPRISE_PLAN_PRICE_TON', 'سعر الباقة الاحترافية (TON)',
        SettingsStates.set_enterprise_price_ton),
        'admin_set_enterprise_price_stars': ('ENTERPRISE_PLAN_PRICE_STARS',
        'سعر الباقة الاحترافية (Stars)', SettingsStates.
        set_enterprise_price_stars), 'admin_set_premium_duration': (
        'PREMIUM_PLAN_DURATION', 'مدة الباقة المميزة (أيام)',
        SettingsStates.set_premium_duration),
        'admin_set_enterprise_duration': ('ENTERPRISE_PLAN_DURATION',
        'مدة الباقة الاحترافية (أيام)', SettingsStates.set_enterprise_duration)
        }
    setting_info = setting_map.get(callback.data)
    if not setting_info:
        return await callback.answer('❌ إعداد غير معروف', show_alert=True)
    setting_key, setting_name, state_to_set = setting_info
    current_value = await SettingsManager.get_setting(setting_key, '0')
    await state.set_state(state_to_set)
    await state.update_data(setting_key=setting_key, setting_name=setting_name)
    await callback.message.edit_text(
        f"""💎 <b>تغيير {setting_name}</b>

القيمة الحالية: <code>{current_value}</code>

أدخل القيمة الجديدة:"""
        , reply_markup=get_cancel_button('admin_plan_settings'), parse_mode
        =ParseMode.HTML)
    await callback.answer()


async def admin_set_plan_value_process(message: types.Message, state:
    FSMContext):
    """معالجة تغيير قيمة باقة"""
    data = await state.get_data()
    setting_key = data['setting_key']
    setting_name = data['setting_name']
    try:
        if 'PRICE_TON' in setting_key:
            new_value = float(message.text.strip())
        else:
            new_value = int(message.text.strip())
        if new_value < 0:
            await message.answer('❌ يجب أن تكون القيمة موجبة')
            return
    except ValueError:
        await message.answer('❌ يرجى إدخال رقم صحيح')
        return
    await SettingsManager.update_setting(setting_key, str(new_value),
        message.from_user.id)
    await state.clear()
    await message.answer(
        f'✅ <b>تم التحديث!</b>\n\n{setting_name}: <code>{new_value}</code>',
        reply_markup=get_back_button('admin_plan_settings'), parse_mode=
        ParseMode.HTML)


async def bot_dashboard_handler(callback: types.CallbackQuery):
    try:
        parts = callback.data.split('_')
        if len(parts) < 3:
            return
        bot_id = int(parts[2])
        await show_bot_dashboard(callback, callback.from_user.id, bot_id)
    except:
        pass

async def admin_withdrawal_types_handler(callback: types.CallbackQuery):
    """إعدادات السحب - البوت الرئيسي"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)

    ton_enabled = await SettingsManager.get_bool_setting('WITHDRAWAL_TON_ENABLED', True)
    stars_enabled = await SettingsManager.get_bool_setting('WITHDRAWAL_STARS_ENABLED', True)
    min_ton = await SettingsManager.get_float_setting('MIN_WITHDRAWAL_TON', 0.5)
    min_stars = await SettingsManager.get_int_setting('MIN_WITHDRAWAL_STARS', 100)

    text = f"💰 <b>إعدادات السحب</b>\n\n"
    text += f"🪙 سحب TON: {'✅ مفعل' if ton_enabled else '❌ معطل'}\n"
    text += f"📉 الحد الأدنى لـ TON: <code>{min_ton}</code>\n\n"
    text += f"⭐ سحب Stars: {'✅ مفعل' if stars_enabled else '❌ معطل'}\n"
    text += f"📉 الحد الأدنى لـ Stars: <code>{min_stars}</code>\n"

    builder = InlineKeyboardBuilder()
    builder.button(text=f"{'🔴 تعطيل' if ton_enabled else '🟢 تفعيل'} TON", callback_data='admin_toggle_wd_TON')
    builder.button(text="⚙️ تعديل أدنى TON", callback_data='admin_set_min_withdrawal_ton')
    builder.button(text=f"{'🔴 تعطيل' if stars_enabled else '🟢 تفعيل'} Stars", callback_data='admin_toggle_wd_STARS')
    builder.button(text="⚙️ تعديل أدنى Stars", callback_data='admin_set_min_withdrawal_stars')
    builder.button(text='🔙 رجوع', callback_data='admin_panel')
    builder.adjust(2)

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    await callback.answer()

async def admin_toggle_wd_type_handler(callback: types.CallbackQuery):
    """تبديل حالة نوع السحب"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)

    wd_type = callback.data.split('_')[3] # TON or STARS
    setting_key = f'WITHDRAWAL_{wd_type}_ENABLED'

    current = await SettingsManager.get_bool_setting(setting_key, True)
    await SettingsManager.update_setting(setting_key, '0' if current else '1', callback.from_user.id)

    await callback.answer(f"✅ تم التحديث", show_alert=True)
    await admin_withdrawal_types_handler(callback)

async def admin_hosting_button_toggle_handler(callback: types.CallbackQuery):
    """تبديل حالة زر استضافة البوت"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)

    current = await SettingsManager.get_bool_setting('HOSTING_BUTTON_ENABLED', True)
    new_status = not current
    await SettingsManager.update_setting('HOSTING_BUTTON_ENABLED', '1' if new_status else '0', callback.from_user.id)

    await callback.answer(f"✅ تم {'تفعيل' if new_status else 'إخفاء'} زر استضافة البوت", show_alert=True)
    await admin_panel_handler(callback)

async def admin_mandatory_sub_menu_handler(callback: types.CallbackQuery):
    """إدارة الاشتراك الإجباري - البوت الرئيسي"""
    if not is_admin(callback.from_user.id):
        return await callback.answer('⛔️ غير مصرح', show_alert=True)

    channels_json = await SettingsManager.get_setting('MANDATORY_CHANNELS', '[]')
    channels = json.loads(channels_json)

    text = "📢 <b>إدارة الاشتراك الإجباري</b>\n\n"
    if not channels:
        text += "لا توجد قنوات مضافة حالياً."
    else:
        text += "القنوات الحالية:\n"
        for i, ch in enumerate(channels, 1):
            text += f"{i}. {ch}\n"

    builder = InlineKeyboardBuilder()
    builder.button(text='➕ إضافة قناة', callback_data='admin_add_mandatory_ch')
    if channels:
        builder.button(text='🗑 حذف قناة', callback_data='admin_remove_mandatory_ch_menu')
    builder.button(text='🔙 رجوع', callback_data='admin_panel')
    builder.adjust(1)

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    await callback.answer()

async def admin_add_mandatory_channel_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.add_mandatory_channel)
    await callback.message.edit_text("أرسل يوزر القناة مع @ (مثال: @channel):", reply_markup=get_cancel_button('admin_mandatory_sub_menu'))
    await callback.answer()

async def admin_add_mandatory_channel_process(message: types.Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id): return
    channel = message.text.strip()
    if not (channel.startswith('@') or channel.startswith('-100')):
        return await message.answer("❌ يجب أن يبدأ اليوزر بـ @ أو معرف المجموعة بـ -100")

    status_msg = await message.answer("🔄 جاري التحقق من صلاحيات البوت...")
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id=channel, user_id=me.id)
        if member.status not in ['administrator', 'creator']:
            await status_msg.edit_text("❌ يجب إضافة البوت كمشرف في القناة أو المجموعة أولاً قبل حفظها.")
            return
    except Exception as e:
        logger.error(f"Error validating mandatory channel {channel}: {e}")
        await status_msg.edit_text(f"❌ فشل التحقق من القناة/المجموعة. تأكد من صحة اليوزر/المعرف وأن البوت موجود هناك.\nخطأ: {str(e)}")
        return

    channels_json = await SettingsManager.get_setting('MANDATORY_CHANNELS', '[]')
    channels = json.loads(channels_json)

    if channel not in channels:
        channels.append(channel)
        await SettingsManager.update_setting('MANDATORY_CHANNELS', json.dumps(channels), message.from_user.id)
        await status_msg.edit_text(f"✅ تم التحقق وإضافة القناة/المجموعة {channel} بنجاح.", reply_markup=get_back_button('admin_mandatory_sub_menu'))
    else:
        await status_msg.edit_text("❌ هذه القناة/المجموعة مضافة بالفعل.")
    await state.clear()

async def admin_remove_mandatory_channel_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    channels_json = await SettingsManager.get_setting('MANDATORY_CHANNELS', '[]')
    channels = json.loads(channels_json)

    builder = InlineKeyboardBuilder()
    for ch in channels:
        builder.button(text=f"🗑 {ch}", callback_data=f"admin_rm_ch_{ch}")
    builder.button(text='🔙 رجوع', callback_data='admin_mandatory_sub_menu')
    builder.adjust(1)

    await callback.message.edit_text("اختر القناة لحذفها:", reply_markup=builder.as_markup())

async def admin_remove_mandatory_channel_process(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id): return
    channel_to_rm = callback.data.replace('admin_rm_ch_', '')

    channels_json = await SettingsManager.get_setting('MANDATORY_CHANNELS', '[]')
    channels = json.loads(channels_json)

    if channel_to_rm in channels:
        channels.remove(channel_to_rm)
        await SettingsManager.update_setting('MANDATORY_CHANNELS', json.dumps(channels), callback.from_user.id)
        await callback.answer(f"✅ تم حذف القناة {channel_to_rm}")

    await admin_mandatory_sub_menu_handler(callback)
