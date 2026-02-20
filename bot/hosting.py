import json
import asyncio
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from .config import logger
from .database import get_db_connection, generate_referral_code
from .states import BotHostingStates
from .middlewares import MandatorySubMiddleware


class HostedBotSystem:
    running_bots = {}

    @staticmethod
    async def start_bot(bot_id, bot_token, bot_username, owner_id):
        try:
            if bot_id in HostedBotSystem.running_bots:
                await HostedBotSystem.stop_bot(bot_id)
            bot, dp = Bot(token=bot_token), Dispatcher(
                storage=MemoryStorage(),
                bot_id=bot_id,
                owner_id=owner_id
            )

            # Register Middleware
            dp.message.middleware(MandatorySubMiddleware())
            dp.callback_query.middleware(MandatorySubMiddleware())

            await HostedBotSystem._register_hosted_bot_handlers(
                bot, dp, bot_id, owner_id
            )
            HostedBotSystem.running_bots[bot_id] = {
                "bot": bot,
                "dp": dp,
                "token": bot_token,
                "username": bot_username,
                "owner_id": owner_id,
                "started_at": datetime.now(),
            }
            HostedBotSystem.running_bots[bot_id]["task"] = asyncio.create_task(
                dp.start_polling(bot)
            )
            conn = get_db_connection()
            conn.cursor().execute(
                "UPDATE hosted_bots SET is_active = 1, last_activity = ? WHERE id = ?",
                (datetime.now().isoformat(), bot_id),
            )
            conn.commit()
            conn.close()
            return True
        except:
            return False

    @staticmethod
    async def stop_bot(bot_id):
        if bot_id not in HostedBotSystem.running_bots:
            return False
        try:
            bot_data = HostedBotSystem.running_bots[bot_id]
            if bot_data.get("task"):
                bot_data["task"].cancel()
                try:
                    await bot_data["task"]
                except:
                    pass
            if bot_data.get("bot"):
                await bot_data["bot"].session.close()
            del HostedBotSystem.running_bots[bot_id]
            conn = get_db_connection()
            conn.cursor().execute(
                "UPDATE hosted_bots SET is_active = 0 WHERE id = ?", (bot_id,)
            )
            conn.commit()
            conn.close()
            return True
        except:
            return False

    @staticmethod
    async def _register_hosted_bot_handlers(bot, dp, bot_id, owner_id):
        async def check_active():
            conn = get_db_connection()
            r = (
                conn.cursor()
                .execute("SELECT is_active FROM hosted_bots WHERE id = ?", (bot_id,))
                .fetchone()
            )
            conn.close()
            return r and r["is_active"] == 1

        async def get_config():
            conn = get_db_connection()
            r = (
                conn.cursor()
                .execute("SELECT config FROM hosted_bots WHERE id = ?", (bot_id,))
                .fetchone()
            )
            conn.close()
            c = json.loads(r["config"]) if r and r["config"] else {}
            d = {
                "referral_reward": 10,
                "daily_bonus_base": 10,
                "daily_bonus_streak": 5,
                "daily_bonus_weekly": 100,
                "welcome_bonus": 5,
                "min_withdrawal_ton": 0.5,
                "min_withdrawal_stars": 100,
                "conversion_points_ton": 1000,
                "conversion_points_stars": 150,
                "custom_welcome": None,
                "withdrawal_enabled": True,
                "withdrawal_ton_enabled": True,
                "withdrawal_stars_enabled": True,
                "mandatory_channels": [],
                "conversion_enabled": True,
            }
            d.update(c)
            return d

        async def get_user(u_id):
            conn = get_db_connection()
            r = (
                conn.cursor()
                .execute(
                    "SELECT * FROM hosted_bot_users WHERE bot_id = ? AND user_telegram_id = ?",
                    (bot_id, u_id),
                )
                .fetchone()
            )
            conn.close()
            return r

        async def create_user(u, ref_by=None):
            conn = get_db_connection()
            cur = conn.cursor()
            ref = generate_referral_code()
            now = datetime.now().isoformat()
            cur.execute(
                "INSERT INTO hosted_bot_users (bot_id, user_telegram_id, username, full_name, referral_code, referred_by, joined_at, last_activity, points) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (bot_id, u.id, u.username, u.full_name, ref, ref_by, now, now),
            )
            cur.execute(
                "UPDATE hosted_bots SET current_users = current_users + 1, last_activity = ? WHERE id = ?",
                (now, bot_id),
            )
            conn.commit()
            r = cur.execute(
                "SELECT * FROM hosted_bot_users WHERE bot_id = ? AND user_telegram_id = ?",
                (bot_id, u.id),
            ).fetchone()
            conn.close()
            return r

        async def add_p(u_id, p, act, desc=None):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE hosted_bot_users SET points = points + ?, total_earned_points = total_earned_points + ? WHERE bot_id = ? AND user_telegram_id = ?",
                (p, p, bot_id, u_id),
            )
            cur.execute(
                "INSERT INTO hosted_bot_points_history (bot_id, user_id, action_type, points, description) VALUES (?, ?, ?, ?, ?)",
                (bot_id, u_id, act, p, desc),
            )
            conn.commit()
            conn.close()

        async def get_hosted_main_menu(u_id):
            builder = InlineKeyboardBuilder()
            conf = await get_config()
            ton_enabled = conf.get('withdrawal_ton_enabled', True)
            stars_enabled = conf.get('withdrawal_stars_enabled', True)

            builder.button(text="📊 لوحة التحكم", callback_data="hosted_dashboard")

            if ton_enabled or stars_enabled:
                builder.button(text="💸 سحب الأرباح", callback_data="hosted_withdrawal")

            builder.button(text="🔗 رابط الإحالة", callback_data="hosted_referral")
            builder.button(text="🎁 المكافأة اليومية", callback_data="hosted_daily")
            builder.button(text="🎯 المهام", callback_data="hosted_tasks")

            if ton_enabled or stars_enabled:
                builder.button(text="🔄 تحويل النقاط", callback_data="hosted_convert")

            builder.button(text="📈 الإحصائيات", callback_data="hosted_stats")

            if u_id == owner_id:
                builder.button(
                    text="⚙️ لوحة التحكم", callback_data="hosted_owner_panel"
                )
            builder.adjust(2)
            return builder.as_markup()

        def get_hosted_dashboard_menu():
            builder = InlineKeyboardBuilder()
            builder.button(text="🔄 تحويل النقاط", callback_data="hosted_convert")
            builder.button(text="⚙️ عنوان TON", callback_data="hwd_wallet")
            builder.button(text="📈 الإحصائيات", callback_data="hosted_stats")
            builder.button(text="🔙 رئيسية", callback_data="hosted_main")
            builder.adjust(2)
            return builder.as_markup()

        @dp.message(CommandStart())
        async def cmd_start(msg: types.Message):
            if msg.from_user.is_bot:
                return
            if not await check_active():
                await msg.answer("⛔️ هذا البوت غير نشط حالياً.")
                return
            u_id = msg.from_user.id
            user = await get_user(u_id)
            if not user:
                conn = get_db_connection()
                bot_i = (
                    conn.cursor()
                    .execute(
                        "SELECT max_users, current_users FROM hosted_bots WHERE id = ?",
                        (bot_id,),
                    )
                    .fetchone()
                )
                conn.close()
                if bot_i["current_users"] >= bot_i["max_users"]:
                    await msg.answer("⚠️ وصل البوت للحد الأقصى.")
                    return
                args = msg.text.split()
                ref_by = None
                if len(args) > 1:
                    conn = get_db_connection()
                    referrer = (
                        conn.cursor()
                        .execute(
                            "SELECT user_telegram_id FROM hosted_bot_users WHERE bot_id = ? AND referral_code = ?",
                            (bot_id, args[1]),
                        )
                        .fetchone()
                    )
                    conn.close()
                    if referrer:
                        ref_by = referrer["user_telegram_id"]
                user = await create_user(msg.from_user, ref_by)

            conf = await get_config()
            channels = conf.get('mandatory_channels', [])
            if not channels and conf.get('channel_username'):
                channels = [conf['channel_username']]

            if channels:
                not_subbed = []
                for ch in channels:
                    try:
                        m = await bot.get_chat_member(chat_id=ch, user_id=u_id)
                        if m.status in ['left', 'kicked']:
                            not_subbed.append(ch)
                    except:
                        not_subbed.append(ch)

                if not_subbed:
                    text = "📢 يرجى الاشتراك في القنوات التالية أولاً:\n\n"
                    builder = InlineKeyboardBuilder()
                    for ch in channels:
                        clean_ch = ch.replace('@', '')
                        text += f"• @{clean_ch}\n"
                        builder.button(text=f'📢 اشترك في {ch}', url=f'https://t.me/{clean_ch}')

                    text += "\nثم اضغط تحقق."
                    builder.button(text='✅ تحقق', callback_data='h_check_sub')
                    builder.adjust(1)
                    await msg.answer(text, reply_markup=builder.as_markup())
                    return

            if not user: # Re-fetch if it was just created
                user = await get_user(u_id)

            if user:
                # Welcome bonus if first time
                # The creation logic already handles this above but let's make sure it doesn't get skipped by sub check
                # Actually, creation logic is only called once.
                if ref_by:
                    conn = get_db_connection()
                    conn.cursor().execute(
                        "UPDATE hosted_bot_users SET total_referrals = total_referrals + 1 WHERE bot_id = ? AND user_telegram_id = ?",
                        (bot_id, ref_by),
                    )
                    conn.commit()
                    conn.close()

                    await add_p(
                        ref_by,
                        conf["referral_reward"],
                        "referral",
                        f"إحالة مستخدم جديد: {msg.from_user.full_name}",
                    )
                    try:
                        await bot.send_message(
                            ref_by,
                            f"🎉 تم إحالة مستخدم جديد! +{conf['referral_reward']} نقطة",
                        )
                    except:
                        pass
                if conf.get("welcome_bonus", 5) > 0:
                    await add_p(
                        u_id, conf["welcome_bonus"], "welcome_bonus", "نقاط ترحيبية"
                    )
                user = await get_user(u_id)

            text = f"""👋 <b>أهلاً {user['full_name']}!</b>

💰 رصيد النقاط: <code>{user['points']}</code>
🪙 رصيد TON: <code>{user['ton_balance']:.4f}</code>
⭐ رصيد Stars: <code>{user['stars_balance']}</code>

اختر من القائمة:"""
            await msg.answer(
                text,
                reply_markup=await get_hosted_main_menu(u_id),
                parse_mode=ParseMode.HTML,
            )

        @dp.callback_query(F.data == "hosted_tasks")
        async def hosted_tasks_list(callback: types.CallbackQuery):
            conn = get_db_connection()
            tasks = (
                conn.cursor()
                .execute(
                    "SELECT * FROM hosted_bot_tasks WHERE bot_id = ? AND is_active = 1",
                    (bot_id,),
                )
                .fetchall()
            )
            completed = [
                r["task_id"]
                for r in conn.cursor()
                .execute(
                    "SELECT task_id FROM hosted_bot_user_tasks WHERE bot_id = ? AND user_id = ?",
                    (bot_id, callback.from_user.id),
                )
                .fetchall()
            ]
            conn.close()
            if not tasks:
                await callback.message.edit_text(
                    "🎯 لا توجد مهام حالياً.",
                    reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 رجوع", callback_data="hosted_main")
                    .as_markup(),
                )
                return
            text = "🎯 <b>المهام المتاحة:</b>\n\n"
            builder = InlineKeyboardBuilder()
            for t in tasks:
                status = "✅" if t["id"] in completed else "⏳"
                text += f"{status} {t['name']} - {t['points']} نقطة\n"
                if t["id"] not in completed:
                    if t["link"]:
                        builder.button(text=f"🔗 {t['name'][:10]}", url=t["link"])
                    builder.button(
                        text=f"✅ إكمال {t['name'][:10]}",
                        callback_data=f"hcomp_{t['id']}",
                    )
            builder.button(text="🔙 رجوع", callback_data="hosted_main")
            builder.adjust(1)
            await callback.message.edit_text(
                text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
            )

        @dp.callback_query(F.data.startswith("hcomp_"))
        async def hosted_complete_task(callback: types.CallbackQuery):
            t_id = int(callback.data.split("_")[1])
            u_id = callback.from_user.id
            conn = get_db_connection()
            task = (
                conn.cursor()
                .execute("SELECT * FROM hosted_bot_tasks WHERE id = ?", (t_id,))
                .fetchone()
            )
            if not task:
                conn.close()
                return
            if task["link"]:
                c_id = task["link"]
                if "t.me/" in c_id:
                    c_id = "@" + c_id.split("t.me/")[1].split("/")[0]
                if c_id.startswith("@"):
                    try:
                        m = await callback.bot.get_chat_member(
                            chat_id=c_id, user_id=u_id
                        )
                        if m.status in ["left", "kicked"]:
                            await callback.answer(
                                "⚠️ يجب الانضمام أولاً للقناة لإتمام المهمة.",
                                show_alert=True,
                            )
                            conn.close()
                            return
                    except:
                        pass
            exist = (
                conn.cursor()
                .execute(
                    "SELECT id FROM hosted_bot_user_tasks WHERE bot_id = ? AND user_id = ? AND task_id = ?",
                    (bot_id, u_id, t_id),
                )
                .fetchone()
            )
            if exist:
                await callback.answer("✅ مكملة مسبقاً")
                conn.close()
                return
            conn.cursor().execute(
                "INSERT INTO hosted_bot_user_tasks (bot_id, user_id, task_id) VALUES (?, ?, ?)",
                (bot_id, u_id, t_id),
            )
            conn.commit()
            conn.close()
            await add_p(u_id, task["points"], "task", f"إكمال مهمة: {task['name']}")
            await callback.answer(f"✅ تم الإكمال! +{task['points']}")
            await hosted_tasks_list(callback)

        @dp.callback_query(F.data == "hosted_main")
        async def hosted_main_menu_callback(callback: types.CallbackQuery):
            u_id = callback.from_user.id
            u = await get_user(u_id)
            text = f"""👋 <b>أهلاً {u['full_name']}!</b>

💰 رصيد النقاط: <code>{u['points']}</code>
🪙 رصيد TON: <code>{u['ton_balance']:.4f}</code>
⭐ رصيد Stars: <code>{u['stars_balance']}</code>

اختر من القائمة:"""
            await callback.message.edit_text(
                text, reply_markup=await get_hosted_main_menu(u_id), parse_mode=ParseMode.HTML
            )

        @dp.callback_query(F.data == "hosted_dashboard")
        async def hosted_dashboard_handler(callback: types.CallbackQuery):
            u_id = callback.from_user.id
            u = await get_user(u_id)
            if not u:
                await callback.answer("❌ خطأ في تحميل البيانات", show_alert=True)
                return

            conn = get_db_connection()
            cursor = conn.cursor()
            referrals_count = cursor.execute(
                "SELECT COUNT(*) as count FROM hosted_bot_users WHERE bot_id = ? AND referred_by = ?",
                (bot_id, u_id),
            ).fetchone()["count"]
            tasks_count = cursor.execute(
                "SELECT COUNT(*) as count FROM hosted_bot_user_tasks WHERE bot_id = ? AND user_id = ?",
                (bot_id, u_id),
            ).fetchone()["count"]
            conn.close()

            text = f"""📊 <b>لوحة التحكم</b>

👤 <b>معلوماتك:</b>
• الاسم: {u['full_name']}
• معرفك: <code>{u_id}</code>

💰 <b>أرصدتك:</b>
• النقاط: <code>{u['points']}</code>
• TON: <code>{u['ton_balance']:.4f}</code>
• Stars: <code>{u['stars_balance']}</code>

📈 <b>إحصائياتك:</b>
• الإحالات: <code>{referrals_count}</code>
• المهام المكتملة: <code>{tasks_count}</code>
• إجمالي النقاط المكتسبة: <code>{u['total_earned_points']}</code>
"""
            if u["wallet_address"]:
                text += (
                    f"\n💳 <b>عنوان المحفظة:</b>\n<code>{u['wallet_address']}</code>"
                )

            await callback.message.edit_text(
                text,
                reply_markup=get_hosted_dashboard_menu(),
                parse_mode=ParseMode.HTML,
            )

        @dp.callback_query(F.data == "hosted_referral")
        async def hosted_referral_handler(callback: types.CallbackQuery):
            u_id = callback.from_user.id
            u = await get_user(u_id)
            conf = await get_config()
            me = await callback.bot.get_me()
            referral_link = f"https://t.me/{me.username}?start={u['referral_code']}"

            text = f"""🔗 <b>رابط الإحالة الخاص بك</b>

📎 الرابط:
<code>{referral_link}</code>

💰 مكافأة كل إحالة: <code>{conf['referral_reward']}</code> نقطة
👥 عدد إحالاتك: <code>{u['total_referrals']}</code>

📤 شارك الرابط مع أصدقائك واكسب النقاط!"""

            builder = InlineKeyboardBuilder()
            builder.button(
                text="📤 مشاركة",
                url=f"https://t.me/share/url?url={referral_link}&text=انضم إلي في هذا البوت الرائع!",
            )
            builder.button(text="🔙 رجوع", callback_data="hosted_main")
            builder.adjust(1)
            await callback.message.edit_text(
                text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
            )

        @dp.callback_query(F.data == "hosted_stats")
        async def hosted_stats_handler(callback: types.CallbackQuery):
            u_id = callback.from_user.id
            u = await get_user(u_id)

            conn = get_db_connection()
            cursor = conn.cursor()
            referrals_count = cursor.execute(
                "SELECT COUNT(*) as count FROM hosted_bot_users WHERE bot_id = ? AND referred_by = ?",
                (bot_id, u_id),
            ).fetchone()["count"]
            tasks_count = cursor.execute(
                "SELECT COUNT(*) as count FROM hosted_bot_user_tasks WHERE bot_id = ? AND user_id = ?",
                (bot_id, u_id),
            ).fetchone()["count"]

            total_users = cursor.execute(
                "SELECT COUNT(*) as count FROM hosted_bot_users WHERE bot_id = ?",
                (bot_id,),
            ).fetchone()["count"]
            total_referrals = cursor.execute(
                "SELECT COUNT(*) as count FROM hosted_bot_users WHERE bot_id = ? AND referred_by IS NOT NULL",
                (bot_id,),
            ).fetchone()["count"]
            total_tasks = cursor.execute(
                "SELECT COUNT(*) as count FROM hosted_bot_user_tasks WHERE bot_id = ?",
                (bot_id,),
            ).fetchone()["count"]
            conn.close()

            text = f"""📈 <b>إحصائياتك</b>

👤 <b>معلوماتك:</b>
• تاريخ التسجيل: {datetime.fromisoformat(u['joined_at']).strftime('%Y-%m-%d')}
• الإحالات الناجحة: {referrals_count}
• المهام المكتملة: {tasks_count}
• إجمالي النقاط المكتسبة: {u['total_earned_points']}

🌍 <b>إحصائيات عامة:</b>
• إجمالي المستخدمين: {total_users}
• إجمالي الإحالات: {total_referrals}
• إجمالي المهام المكتملة: {total_tasks}
"""
            builder = InlineKeyboardBuilder()
            builder.button(text="🔙 رجوع", callback_data="hosted_main")
            await callback.message.edit_text(
                text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data == "hosted_daily")
        async def hosted_daily_bonus(callback: types.CallbackQuery):
            u_id = callback.from_user.id
            user = await get_user(u_id)
            conf = await get_config()

            base_bonus = conf.get("daily_bonus_base", 10)
            streak_bonus = conf.get("daily_bonus_streak", 5)
            weekly_bonus = conf.get("daily_bonus_weekly", 100)
            max_streak = 7

            can_claim = True
            streak = user["daily_streak_count"] if user["daily_streak_count"] else 0
            wait_text = ""

            if user["last_daily_bonus"]:
                last_bonus = datetime.fromisoformat(user["last_daily_bonus"])
                time_diff = datetime.now() - last_bonus
                if time_diff < timedelta(hours=20):
                    can_claim = False
                    remaining = timedelta(hours=24) - time_diff
                    hours = int(remaining.total_seconds() // 3600)
                    minutes = int(remaining.total_seconds() % 3600 // 60)
                    wait_text = f"⏳ يمكنك المطالبة بعد: {hours} ساعة و {minutes} دقيقة"
                elif time_diff > timedelta(hours=48):
                    streak = 0

            if can_claim:
                total_bonus = base_bonus + streak * streak_bonus
                if streak >= max_streak - 1:
                    total_bonus += weekly_bonus
                    streak = 0
                    bonus_message = (
                        f"🎉 مبروك! حصلت على مكافأة الأسبوع الكامل +{weekly_bonus}!"
                    )
                else:
                    streak += 1
                    bonus_message = f"🔥 تتابع يومي: {streak} أيام"

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE hosted_bot_users SET
                        points = points + ?,
                        last_daily_bonus = ?,
                        daily_streak_count = ?,
                        total_earned_points = total_earned_points + ?
                    WHERE bot_id = ? AND user_telegram_id = ?
                """,
                    (
                        total_bonus,
                        datetime.now().isoformat(),
                        streak,
                        total_bonus,
                        bot_id,
                        u_id,
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO hosted_bot_points_history (bot_id, user_id, action_type, points, description)
                    VALUES (?, ?, 'daily_bonus', ?, ?)
                """,
                    (
                        bot_id,
                        u_id,
                        total_bonus,
                        f"مكافأة يومية - تتابع {streak} أيام",
                    ),
                )
                conn.commit()
                conn.close()

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

            builder = InlineKeyboardBuilder()
            builder.button(text="🔙 رجوع", callback_data="hosted_main")
            await callback.message.edit_text(
                text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
            )
            await callback.answer()

        @dp.callback_query(F.data == "hosted_convert")
        async def hosted_convert_handler(callback: types.CallbackQuery):
            u = await get_user(callback.from_user.id)
            conf = await get_config()
            ton_enabled = conf.get('withdrawal_ton_enabled', True)
            stars_enabled = conf.get('withdrawal_stars_enabled', True)

            text = f"🔄 <b>تحويل النقاط</b>\n\n💰 نقاطك: {u['points']}\n\n📊 أسعار التحويل:\n"
            if ton_enabled: text += f"🪙 {conf['conversion_points_ton']} نقطة = 1 TON\n"
            if stars_enabled: text += f"⭐ {conf['conversion_points_stars']} نقطة = 10 Stars\n"

            builder = InlineKeyboardBuilder()
            if ton_enabled: builder.button(text="🪙 تحويل إلى TON", callback_data="hconv_TON")
            if stars_enabled: builder.button(text="⭐ تحويل إلى Stars", callback_data="hconv_STARS")
            builder.button(text="🔙 رجوع", callback_data="hosted_main")
            builder.adjust(1)
            await callback.message.edit_text(
                text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
            )

        @dp.callback_query(F.data.startswith("hconv_"))
        async def hosted_process_convert(
            callback: types.CallbackQuery, state: FSMContext
        ):
            asset = callback.data.split("_")[1]
            conf = await get_config()
            if asset == "TON" and not conf.get('withdrawal_ton_enabled', True):
                return await callback.answer("🚫 تحويل TON معطل", show_alert=True)
            if asset == "STARS" and not conf.get('withdrawal_stars_enabled', True):
                return await callback.answer("🚫 تحويل Stars معطل", show_alert=True)

            await state.set_state(BotHostingStates.convert_points)
            await state.update_data(asset=asset, bot_id=bot_id)
            await callback.message.edit_text(
                f"🔄 <b>تحويل إلى {asset}</b>\n\nأدخل عدد النقاط التي تريد تحويلها:",
                reply_markup=InlineKeyboardBuilder()
                .button(text="❌ إلغاء", callback_data="hosted_convert")
                .as_markup(),
            )

        @dp.message(BotHostingStates.convert_points)
        async def process_hosted_convert_req(message: types.Message, state: FSMContext):
            try:
                pts = int(message.text)
            except:
                await message.answer("❌ أدخل رقم صحيح")
                return
            if pts <= 0:
                await message.answer("❌ أدخل رقم أكبر من 0")
                return
            data = await state.get_data()
            asset = data.get("asset")
            u_id = message.from_user.id
            user = await get_user(u_id)
            conf = await get_config()
            if user["points"] < pts:
                await message.answer("❌ نقاطك غير كافية")
                return
            conn = get_db_connection()
            cur = conn.cursor()
            if asset == "TON":
                amt = pts / conf["conversion_points_ton"]
                cur.execute(
                    "UPDATE hosted_bot_users SET points = points - ?, ton_balance = ton_balance + ? WHERE bot_id = ? AND user_telegram_id = ?",
                    (pts, amt, bot_id, u_id),
                )
            else:
                amt = (pts // conf["conversion_points_stars"]) * 10
                pts_used = (amt // 10) * conf["conversion_points_stars"]
                if pts_used == 0:
                    await message.answer(
                        "❌ النقاط غير كافية لتحويل Stars (أقل كمية 10 Stars)"
                    )
                    conn.close()
                    return
                cur.execute(
                    "UPDATE hosted_bot_users SET points = points - ?, stars_balance = stars_balance + ? WHERE bot_id = ? AND user_telegram_id = ?",
                    (pts_used, amt, bot_id, u_id),
                )
            conn.commit()
            conn.close()
            await state.clear()
            await message.answer(
                f"✅ تم التحويل بنجاح! حصلت على {amt} {asset}",
                reply_markup=await get_hosted_main_menu(u_id),
            )

        @dp.callback_query(F.data == "hosted_withdrawal")
        async def hosted_withdrawal_menu(callback: types.CallbackQuery):
            u = await get_user(callback.from_user.id)
            conf = await get_config()
            ton_enabled = conf.get('withdrawal_ton_enabled', True)
            stars_enabled = conf.get('withdrawal_stars_enabled', True)

            text = f"💸 <b>طلب سحب الأرباح</b>\n\n"
            if ton_enabled: text += f"🪙 TON: {u['ton_balance']:.4f}\n"
            if stars_enabled: text += f"⭐ Stars: {u['stars_balance']}\n"
            text += "\nاختر نوع العملة:"

            builder = InlineKeyboardBuilder()
            if ton_enabled: builder.button(text="🪙 TON", callback_data="hwd_TON")
            if stars_enabled: builder.button(text="⭐ Stars", callback_data="hwd_STARS")
            builder.button(text="⚙️ تعيين محفظة TON", callback_data="hwd_wallet")
            builder.button(text="🔙 رجوع", callback_data="hosted_main")
            builder.adjust(1)
            await callback.message.edit_text(
                text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
            )

        @dp.callback_query(F.data == "hwd_wallet")
        async def hosted_set_wallet(callback: types.CallbackQuery, state: FSMContext):
            await state.set_state(BotHostingStates.set_wallet_address)
            await state.update_data(bot_id=bot_id)
            await callback.message.edit_text(
                "⚙️ <b>تحديد عنوان TON</b>\n\nأرسل عنوان محفظة TON الخاص بك:\n(يجب أن يبدأ بـ E أو U أو 0 وطوله 48 حرف)",
                reply_markup=InlineKeyboardBuilder()
                .button(text="❌ إلغاء", callback_data="hosted_withdrawal")
                .as_markup(),
                parse_mode=ParseMode.HTML,
            )

        @dp.message(BotHostingStates.set_wallet_address)
        async def process_hosted_wallet(message: types.Message, state: FSMContext):
            wallet = message.text.strip()
            from .database import is_valid_ton_address

            if not is_valid_ton_address(wallet):
                await message.answer(
                    "❌ عنوان غير صالح!\n\nيجب أن يكون العنوان:\n• 48 حرفاً\n• يبدأ بـ E أو U أو 0"
                )
                return

            u_id = message.from_user.id
            conn = get_db_connection()
            conn.cursor().execute(
                "UPDATE hosted_bot_users SET wallet_address = ? WHERE bot_id = ? AND user_telegram_id = ?",
                (wallet, bot_id, u_id),
            )
            conn.commit()
            conn.close()
            await state.clear()
            await message.answer(
                f"✅ <b>تم تحديد العنوان بنجاح!</b>\n\n💳 العنوان: <code>{wallet}</code>",
                reply_markup=await get_hosted_main_menu(u_id),
                parse_mode=ParseMode.HTML,
            )

        @dp.callback_query(F.data.startswith("hwd_"))
        async def hosted_request_wd(callback: types.CallbackQuery, state: FSMContext):
            asset = callback.data.split("_")[1]
            if asset == "wallet": return # Handled by hwd_wallet

            conf = await get_config()
            if asset == "TON" and not conf.get('withdrawal_ton_enabled', True):
                return await callback.answer("🚫 سحب TON معطل", show_alert=True)
            if asset == "STARS" and not conf.get('withdrawal_stars_enabled', True):
                return await callback.answer("🚫 سحب Stars معطل", show_alert=True)

            u = await get_user(callback.from_user.id)
            if not u["wallet_address"]:
                await callback.message.edit_text(
                    "⚠️ <b>لم تقم بتحديد عنوان المحفظة</b>\n\nيرجى تحديد عنوان TON أولاً:",
                    reply_markup=InlineKeyboardBuilder()
                    .button(text="⚙️ تحديد العنوان", callback_data="hwd_wallet")
                    .button(text="🔙 رجوع", callback_data="hosted_withdrawal")
                    .as_markup(),
                    parse_mode=ParseMode.HTML,
                )
                await callback.answer()
                return

            await state.set_state(BotHostingStates.request_withdrawal)
            await state.update_data(asset=asset, bot_id=bot_id)
            await callback.message.edit_text(
                f"💰 <b>سحب {asset}</b>\n\nأدخل المبلغ الذي تريد سحبه:",
                reply_markup=InlineKeyboardBuilder()
                .button(text="❌ إلغاء", callback_data="hosted_withdrawal")
                .as_markup(),
            )

        @dp.message(BotHostingStates.request_withdrawal)
        async def process_hosted_wd_req(message: types.Message, state: FSMContext):
            data = await state.get_data()
            asset = data.get("asset")
            try:
                amount = float(message.text)
            except:
                await message.answer("❌ أدخل رقم صحيح")
                return
            u_id = message.from_user.id
            user = await get_user(u_id)
            conf = await get_config()
            if asset == "TON" and user["ton_balance"] < amount:
                await message.answer("❌ رصيد TON غير كافٍ")
                return
            if asset == "STARS" and user["stars_balance"] < amount:
                await message.answer("❌ رصيد Stars غير كافٍ")
                return
            conn = get_db_connection()
            cur = conn.cursor()
            if asset == "TON":
                cur.execute(
                    "UPDATE hosted_bot_users SET ton_balance = ton_balance - ? WHERE bot_id = ? AND user_telegram_id = ?",
                    (amount, bot_id, u_id),
                )
            else:
                cur.execute(
                    "UPDATE hosted_bot_users SET stars_balance = stars_balance - ? WHERE bot_id = ? AND user_telegram_id = ?",
                    (amount, bot_id, u_id),
                )
            cur.execute(
                "INSERT INTO hosted_bot_withdrawals (bot_id, user_id, asset_type, amount, wallet_address, status) VALUES (?, ?, ?, ?, ?, 'pending')",
                (bot_id, u_id, asset, amount, user["wallet_address"]),
            )
            h_withdrawal_id = cur.lastrowid
            conn.commit()
            conn.close()
            await state.clear()
            await message.answer(
                f"✅ <b>تم تقديم طلب السحب بنجاح!</b>\n\n💰 المبلغ: <code>{amount}</code> {asset}\n💳 العنوان: <code>{user['wallet_address']}</code>\n\n⏳ سيتم معالجة طلبك قريباً.",
                reply_markup=await get_hosted_main_menu(u_id),
                parse_mode=ParseMode.HTML,
            )
            try:
                builder = InlineKeyboardBuilder()
                builder.button(text="✅ قبول", callback_data=f"ho_app_w_{h_withdrawal_id}")
                builder.button(text="❌ رفض", callback_data=f"ho_rej_w_{h_withdrawal_id}")
                builder.adjust(2)

                await message.bot.send_message(
                    owner_id,
                    f"🚨 <b>طلب سحب جديد في بوتك!</b>\n\n🆔 طلب رقم: <code>#{h_withdrawal_id}</code>\n👤 المستخدم: <code>{u_id}</code>\n💰 المبلغ: <code>{amount}</code> {asset}\n💳 العنوان: <code>{user['wallet_address']}</code>",
                    reply_markup=builder.as_markup(),
                    parse_mode=ParseMode.HTML,
                )
            except:
                pass

        # ==================== ⚙️ لوحة تحكم المالك ====================
        @dp.callback_query(F.data == "hosted_owner_panel")
        async def hosted_owner_panel(callback: types.CallbackQuery):
            if callback.from_user.id != owner_id:
                return await callback.answer("⛔️ غير مصرح")
            text = "⚙️ <b>لوحة تحكم بوتك</b>\n\nمن هنا يمكنك التحكم في جميع إعدادات بوتك المستضاف."
            builder = InlineKeyboardBuilder()
            builder.button(text="📊 إحصائيات", callback_data="ho_stats")
            builder.button(text="👥 المستخدمين", callback_data="ho_users")
            builder.button(text="💸 طلبات السحب", callback_data="ho_withdrawals")
            builder.button(text="🎯 المهام", callback_data="ho_tasks")
            builder.button(text="🛠 الإعدادات", callback_data="ho_settings")
            builder.button(text="🔙 رجوع", callback_data="hosted_main")
            builder.adjust(2)
            await callback.message.edit_text(
                text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
            )

        @dp.callback_query(F.data == "ho_stats")
        async def ho_stats(callback: types.CallbackQuery):
            if callback.from_user.id != owner_id:
                return
            conn = get_db_connection()
            cur = conn.cursor()
            u_stats = cur.execute(
                "SELECT COUNT(*) as total, SUM(points) as pts FROM hosted_bot_users WHERE bot_id = ?",
                (bot_id,),
            ).fetchone()
            w_stats = cur.execute(
                "SELECT COUNT(*) as total FROM hosted_bot_withdrawals WHERE bot_id = ? AND status = 'pending'",
                (bot_id,),
            ).fetchone()
            conn.close()
            text = f"📊 <b>إحصائيات البوت:</b>\n\n👤 عدد المستخدمين: {u_stats['total']}\n💰 إجمالي النقاط الموزعة: {u_stats['pts'] or 0}\n💸 سحوبات معلقة: {w_stats['total']}"
            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 رجوع", callback_data="hosted_owner_panel")
                .as_markup(),
                parse_mode=ParseMode.HTML,
            )

        @dp.callback_query(F.data == "ho_settings")
        async def ho_settings(callback: types.CallbackQuery):
            if callback.from_user.id != owner_id:
                return
            conf = await get_config()
            ton_enabled = conf.get('withdrawal_ton_enabled', True)
            stars_enabled = conf.get('withdrawal_stars_enabled', True)

            text = f"🛠 <b>إعدادات البوت:</b>\n\n💰 نقاط الإحالة: {conf['referral_reward']}\n"
            text += f"🪙 سحب TON: {'✅ مفعل' if ton_enabled else '❌ معطل'} (الحد الأدنى: {conf['min_withdrawal_ton']})\n"
            text += f"⭐ سحب Stars: {'✅ مفعل' if stars_enabled else '❌ معطل'} (الحد الأدنى: {conf['min_withdrawal_stars']})\n\n"
            text += "اختر ما تريد تعديله:"

            builder = InlineKeyboardBuilder()
            builder.button(text="💰 تعديل نقاط الإحالة", callback_data="ho_edit_ref")
            builder.button(text=f"{'🔴 تعطيل' if ton_enabled else '🟢 تفعيل'} سحب TON", callback_data="ho_toggle_ton")
            builder.button(text="💸 تعديل حد سحب TON", callback_data="ho_edit_ton")
            builder.button(text=f"{'🔴 تعطيل' if stars_enabled else '🟢 تفعيل'} سحب Stars", callback_data="ho_toggle_stars")
            builder.button(text="⭐ تعديل حد سحب Stars", callback_data="ho_edit_stars")
            builder.button(text="📢 إدارة الاشتراك الإجباري", callback_data="ho_mandatory_sub")
            builder.button(text="🔙 رجوع", callback_data="hosted_owner_panel")
            builder.adjust(1)
            await callback.message.edit_text(
                text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
            )

        @dp.callback_query(F.data.startswith("ho_edit_"))
        async def ho_edit_start(callback: types.CallbackQuery, state: FSMContext):
            if callback.from_user.id != owner_id:
                return
            field = callback.data.split("_")[2]
            await state.set_state(BotHostingStates.edit_bot_config)
            await state.update_data(field=field)
            msgs = {
                "ref": "أدخل عدد نقاط الإحالة الجديد:",
                "ton": "أدخل الحد الأدنى لسحب TON الجديد:",
                "stars": "أدخل الحد الأدنى لسحب Stars الجديد:",
            }
            await callback.message.edit_text(
                msgs[field],
                reply_markup=InlineKeyboardBuilder()
                .button(text="❌ إلغاء", callback_data="ho_settings")
                .as_markup(),
            )

        @dp.message(BotHostingStates.edit_bot_config)
        async def process_ho_edit(message: types.Message, state: FSMContext):
            if message.from_user.id != owner_id:
                return
            data = await state.get_data()
            field = data.get("field")
            try:
                val = float(message.text) if field != "ref" else int(message.text)
            except:
                return await message.answer("❌ أدخل قيمة صحيحة")
            conn = get_db_connection()
            cur = conn.cursor()
            cfg_raw = cur.execute(
                "SELECT config FROM hosted_bots WHERE id = ?", (bot_id,)
            ).fetchone()["config"]
            cfg = json.loads(cfg_raw) if cfg_raw else {}
            map_f = {
                "ref": "referral_reward",
                "ton": "min_withdrawal_ton",
                "stars": "min_withdrawal_stars",
            }
            cfg[map_f[field]] = val
            cur.execute(
                "UPDATE hosted_bots SET config = ? WHERE id = ?",
                (json.dumps(cfg), bot_id),
            )
            conn.commit()
            conn.close()
            await state.clear()
            await message.answer(
                "✅ تم التحديث بنجاح!",
                reply_markup=InlineKeyboardBuilder()
                .button(text="🔙 للوحة التحكم", callback_data="hosted_owner_panel")
                .as_markup(),
            )

        @dp.callback_query(F.data == "ho_users")
        async def ho_users(callback: types.CallbackQuery):
            if callback.from_user.id != owner_id:
                return
            conn = get_db_connection()
            count = (
                conn.cursor()
                .execute(
                    "SELECT COUNT(*) as count FROM hosted_bot_users WHERE bot_id = ?",
                    (bot_id,),
                )
                .fetchone()["count"]
            )
            conn.close()
            text = f"👥 <b>إدارة المستخدمين</b>\n\nعدد المستخدمين: <code>{count}</code>\n\nيمكنك إرسال رسالة لجميع مستخدمي بوتك."
            builder = InlineKeyboardBuilder()
            builder.button(text="📢 إذاعة للكل", callback_data="ho_broadcast")
            builder.button(text="🔙 رجوع", callback_data="hosted_owner_panel")
            builder.adjust(1)
            await callback.message.edit_text(
                text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
            )

        @dp.callback_query(F.data == "ho_broadcast")
        async def ho_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
            if callback.from_user.id != owner_id:
                return
            await state.set_state(BotHostingStates.broadcast)
            await callback.message.edit_text(
                "📢 أرسل الرسالة التي تريد بثها لمستخدميك:",
                reply_markup=InlineKeyboardBuilder()
                .button(text="❌ إلغاء", callback_data="ho_users")
                .as_markup(),
            )

        @dp.message(BotHostingStates.broadcast)
        async def process_ho_broadcast(message: types.Message, state: FSMContext):
            if message.from_user.id != owner_id:
                return
            text = message.text
            await state.clear()
            conn = get_db_connection()
            users = (
                conn.cursor()
                .execute(
                    "SELECT user_telegram_id FROM hosted_bot_users WHERE bot_id = ?",
                    (bot_id,),
                )
                .fetchall()
            )
            conn.close()
            status_msg = await message.answer("🔄 جاري الإرسال...")
            sent, failed = 0, 0
            for u in users:
                try:
                    await message.bot.send_message(u["user_telegram_id"], text)
                    sent += 1
                    await asyncio.sleep(0.05)
                except:
                    failed += 1
            await status_msg.edit_text(f"✅ تم البث!\n📤 نجح: {sent}\n❌ فشل: {failed}")

        @dp.callback_query(F.data == "ho_withdrawals")
        async def ho_withdrawals(callback: types.CallbackQuery):
            if callback.from_user.id != owner_id:
                return
            conn = get_db_connection()
            ws = (
                conn.cursor()
                .execute(
                    "SELECT w.*, u.full_name FROM hosted_bot_withdrawals w JOIN hosted_bot_users u ON w.user_id = u.user_telegram_id AND w.bot_id = u.bot_id WHERE w.bot_id = ? AND w.status = 'pending'",
                    (bot_id,),
                )
                .fetchall()
            )
            conn.close()
            if not ws:
                return await callback.message.edit_text(
                    "💸 لا توجد طلبات سحب معلقة.",
                    reply_markup=InlineKeyboardBuilder()
                    .button(text="🔙 رجوع", callback_data="hosted_owner_panel")
                    .as_markup(),
                )
            text = "💸 <b>طلبات السحب المعلقة:</b>\n\n"
            builder = InlineKeyboardBuilder()
            for w in ws:
                text += f"👤 {w['full_name']}\n💰 {w['amount']} {w['asset_type']}\n💳 {w['wallet_address'] or 'N/A'}\n\n"
                builder.button(
                    text=f"✅ قبول #{w['id']}", callback_data=f"ho_app_w_{w['id']}"
                )
                builder.button(
                    text=f"❌ رفض #{w['id']}", callback_data=f"ho_rej_w_{w['id']}"
                )
            builder.button(text="🔙 رجوع", callback_data="hosted_owner_panel")
            builder.adjust(2)
            await callback.message.edit_text(
                text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
            )

        @dp.callback_query(F.data.startswith("ho_app_w_"))
        async def ho_approve_w(callback: types.CallbackQuery):
            if callback.from_user.id != owner_id:
                return
            w_id = int(callback.data.split("_")[3])
            conn = get_db_connection()
            cur = conn.cursor()
            w = cur.execute(
                "SELECT * FROM hosted_bot_withdrawals WHERE id = ?", (w_id,)
            ).fetchone()
            if not w:
                conn.close()
                return
            cur.execute(
                "UPDATE hosted_bot_withdrawals SET status = 'approved', processed_date = ? WHERE id = ?",
                (datetime.now().isoformat(), w_id),
            )
            conn.commit()
            conn.close()
            await callback.answer("✅ تم القبول")
            await ho_withdrawals(callback)
            try:
                await callback.bot.send_message(
                    w["user_id"],
                    "✅ تم قبول طلب السحب الخاص بك! يرجى التأكد من محفظتك.",
                )
            except:
                pass

        @dp.callback_query(F.data.startswith("ho_rej_w_"))
        async def ho_reject_w_start(callback: types.CallbackQuery, state: FSMContext):
            if callback.from_user.id != owner_id:
                return
            w_id = int(callback.data.split("_")[3])
            await state.set_state(BotHostingStates.reject_withdrawal_reason)
            await state.update_data(w_id=w_id)
            await callback.message.edit_text(
                "❌ يرجى إدخال سبب الرفض:",
                reply_markup=InlineKeyboardBuilder()
                .button(text="❌ إلغاء", callback_data="ho_withdrawals")
                .as_markup(),
            )

        @dp.message(BotHostingStates.reject_withdrawal_reason)
        async def process_ho_reject_w(message: types.Message, state: FSMContext):
            if message.from_user.id != owner_id:
                return
            data = await state.get_data()
            w_id = data.get("w_id")
            reason = message.text
            await state.clear()
            conn = get_db_connection()
            cur = conn.cursor()
            w = cur.execute(
                "SELECT * FROM hosted_bot_withdrawals WHERE id = ?", (w_id,)
            ).fetchone()
            if not w:
                conn.close()
                return
            cur.execute(
                "UPDATE hosted_bot_withdrawals SET status = 'rejected', notes = ?, processed_date = ? WHERE id = ?",
                (reason, datetime.now().isoformat(), w_id),
            )
            if w["asset_type"] == "TON":
                cur.execute(
                    "UPDATE hosted_bot_users SET ton_balance = ton_balance + ? WHERE bot_id = ? AND user_telegram_id = ?",
                    (w["amount"], bot_id, w["user_id"]),
                )
            else:
                cur.execute(
                    "UPDATE hosted_bot_users SET stars_balance = stars_balance + ? WHERE bot_id = ? AND user_telegram_id = ?",
                    (int(w["amount"]), bot_id, w["user_id"]),
                )
            conn.commit()
            conn.close()
            await message.answer(f"✅ تم رفض الطلب #{w_id} وإعادة الرصيد.")
            try:
                await message.bot.send_message(
                    w["user_id"], f"❌ تم رفض طلب السحب الخاص بك.\nالسبب: {reason}"
                )
            except:
                pass

        @dp.callback_query(F.data == "ho_tasks")
        async def ho_tasks(callback: types.CallbackQuery):
            if callback.from_user.id != owner_id:
                return
            conn = get_db_connection()
            ts = (
                conn.cursor()
                .execute("SELECT * FROM hosted_bot_tasks WHERE bot_id = ?", (bot_id,))
                .fetchall()
            )
            conn.close()
            text = "🎯 <b>إدارة المهام:</b>\n\n"
            builder = InlineKeyboardBuilder()
            for t in ts:
                st = "🟢" if t["is_active"] else "🔴"
                text += f"{st} {t['name']} - {t['points']} نقطة\n"
                builder.button(
                    text=f"🗑 {t['name'][:10]}", callback_data=f"ho_del_t_{t['id']}"
                )
            builder.button(text="➕ إضافة مهمة", callback_data="ho_add_t")
            builder.button(text="🔙 رجوع", callback_data="hosted_owner_panel")
            builder.adjust(1)
            await callback.message.edit_text(
                text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML
            )

        @dp.callback_query(F.data == "ho_add_t")
        async def ho_add_task_start(callback: types.CallbackQuery, state: FSMContext):
            if callback.from_user.id != owner_id:
                return
            await state.set_state(BotHostingStates.add_task)
            await state.update_data(step="name")
            await callback.message.edit_text(
                "🟢 الخطوة 1:\nطلب إدخال اسم المهمة",
                reply_markup=InlineKeyboardBuilder()
                .button(text="❌ إلغاء", callback_data="ho_tasks")
                .as_markup(),
            )

        @dp.message(BotHostingStates.add_task)
        async def process_ho_add_task(message: types.Message, state: FSMContext):
            if message.from_user.id != owner_id:
                return
            data = await state.get_data()
            step = data.get("step")
            if step == "name":
                await state.update_data(name=message.text)
                await message.answer(
                    f"✅ تم حفظ الاسم: <b>{message.text}</b>\n\nاضغط على التالي للمتابعة.",
                    reply_markup=InlineKeyboardBuilder().button(text="التالي ⬇️", callback_data="task_next_step").as_markup(),
                    parse_mode=ParseMode.HTML,
                )
            elif step == "max_users":
                try:
                    m_u = int(message.text)
                    await state.update_data(max_users=m_u)
                except:
                    return await message.answer("❌ أدخل رقم صحيح لعدد المستفيدين")
                await message.answer(
                    f"✅ تم حفظ العدد: <b>{m_u}</b>\n\nاضغط على التالي للمتابعة.",
                    reply_markup=InlineKeyboardBuilder().button(text="التالي ⬇️", callback_data="task_next_step").as_markup(),
                    parse_mode=ParseMode.HTML,
                )
            elif step == "points":
                try:
                    pts = int(message.text)
                    await state.update_data(points=pts)
                except:
                    return await message.answer("❌ أدخل رقم صحيح لعدد النقاط")
                await message.answer(
                    f"✅ تم حفظ النقاط: <b>{pts}</b>\n\nاضغط على التالي للمتابعة.",
                    reply_markup=InlineKeyboardBuilder().button(text="التالي ⬇️", callback_data="task_next_step").as_markup(),
                    parse_mode=ParseMode.HTML,
                )
            elif step == "link":
                link = message.text.strip()
                chat_id = link
                if "t.me/" in chat_id:
                    chat_id = "@" + chat_id.split("t.me/")[1].split("/")[0]
                try:
                    me = await message.bot.get_me()
                    mem = await message.bot.get_chat_member(
                        chat_id=chat_id, user_id=me.id
                    )
                    if mem.status not in ["administrator", "creator"]:
                        return await message.answer("❌ البوت ليس مشرفاً!")
                except:
                    return await message.answer("❌ تعذر التحقق من البوت في القناة.")
                conn = get_db_connection()
                conn.cursor().execute(
                    "INSERT INTO hosted_bot_tasks (bot_id, name, points, link, max_completions, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                    (bot_id, data["name"], data["points"], link, data["max_users"]),
                )
                conn.commit()
                conn.close()
                await state.clear()
                await message.answer(
                    "✅ تم إضافة المهمة بنجاح!",
                    reply_markup=InlineKeyboardBuilder().button(text="🔙 للمهام", callback_data="ho_tasks").as_markup(),
                )

        @dp.callback_query(F.data == "task_next_step")
        async def ho_task_next_step(callback: types.CallbackQuery, state: FSMContext):
            data = await state.get_data()
            step = data.get("step", "name")
            if step == "name":
                await state.update_data(step="max_users")
                await callback.message.edit_text("🟢 الخطوة 2:\nطلب إدخال عدد الأشخاص المستفيدين من المهمة", reply_markup=InlineKeyboardBuilder().button(text="❌ إلغاء", callback_data="ho_tasks").as_markup())
            elif step == "max_users":
                await state.update_data(step="points")
                await callback.message.edit_text("🟢 الخطوة 3:\nطلب إدخال عدد النقاط التي يحصل عليها كل شخص", reply_markup=InlineKeyboardBuilder().button(text="❌ إلغاء", callback_data="ho_tasks").as_markup())
            elif step == "points":
                await state.update_data(step="link")
                await callback.message.edit_text("🟢 الخطوة 4:\nطلب إدخال: رابط قناة أو يوزر قناة أو رابط مجموعة", reply_markup=InlineKeyboardBuilder().button(text="❌ إلغاء", callback_data="ho_tasks").as_markup())
            else:
                await callback.answer("يرجى إكمال البيانات المطلوبة.")

        @dp.callback_query(F.data.startswith("ho_del_t_"))
        async def ho_del_task(callback: types.CallbackQuery):
            if callback.from_user.id != owner_id:
                return
            t_id = int(callback.data.split("_")[3])
            conn = get_db_connection()
            conn.cursor().execute("DELETE FROM hosted_bot_tasks WHERE id = ?", (t_id,))
            conn.commit()
            conn.close()
            await callback.answer("✅ تم الحذف")
            await ho_tasks(callback)

        @dp.callback_query(F.data.in_(['ho_toggle_ton', 'ho_toggle_stars']))
        async def ho_toggle_wd_type(callback: types.CallbackQuery):
            if callback.from_user.id != owner_id: return
            try:
                field = 'withdrawal_ton_enabled' if callback.data == 'ho_toggle_ton' else 'withdrawal_stars_enabled'
                conf = await get_config()
                conf[field] = not conf.get(field, True)

                conn = get_db_connection()
                conn.cursor().execute("UPDATE hosted_bots SET config = ? WHERE id = ?", (json.dumps(conf), bot_id))
                conn.commit()
                conn.close()
                await callback.answer("✅ تم التحديث")
                await ho_settings(callback)
            except Exception as e:
                logger.error(f"Error toggling withdrawal type for bot {bot_id}: {e}")
                await callback.answer("❌ حدث خطأ أثناء التحديث", show_alert=True)

        @dp.callback_query(F.data == "ho_mandatory_sub")
        async def ho_mandatory_sub_menu(callback: types.CallbackQuery):
            if callback.from_user.id != owner_id: return
            conf = await get_config()
            channels = conf.get('mandatory_channels', [])

            text = "📢 <b>إدارة الاشتراك الإجباري</b>\n\n"
            if not channels:
                text += "لا توجد قنوات مضافة حالياً."
            else:
                text += "القنوات الحالية:\n"
                for i, ch in enumerate(channels, 1):
                    text += f"{i}. {ch}\n"

            builder = InlineKeyboardBuilder()
            builder.button(text='➕ إضافة قناة', callback_data='ho_add_ch')
            if channels:
                builder.button(text='🗑 حذف قناة', callback_data='ho_rm_ch_menu')
            builder.button(text='🔙 رجوع', callback_data='ho_settings')
            builder.adjust(1)
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

        @dp.callback_query(F.data == "ho_add_ch")
        async def ho_add_ch_start(callback: types.CallbackQuery, state: FSMContext):
            if callback.from_user.id != owner_id: return
            await state.set_state(BotHostingStates.add_mandatory_channel)
            await state.update_data(bot_id=bot_id)
            await callback.message.edit_text("أرسل يوزر القناة مع @ (مثال: @channel):",
                reply_markup=InlineKeyboardBuilder().button(text="❌ إلغاء", callback_data="ho_mandatory_sub").as_markup())

        @dp.message(BotHostingStates.add_mandatory_channel)
        async def process_ho_add_ch(message: types.Message, state: FSMContext):
            if message.from_user.id != owner_id: return
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
                await status_msg.edit_text(f"❌ فشل التحقق من القناة/المجموعة. تأكد من صحة اليوزر/المعرف وأن البوت موجود هناك.\nخطأ: {str(e)}")
                return

            conf = await get_config()
            channels = conf.get('mandatory_channels', [])
            if channel not in channels:
                channels.append(channel)
                conf['mandatory_channels'] = channels
                conn = get_db_connection()
                conn.cursor().execute("UPDATE hosted_bots SET config = ? WHERE id = ?", (json.dumps(conf), bot_id))
                conn.commit()
                conn.close()
                await status_msg.edit_text(f"✅ تم التحقق وإضافة القناة/المجموعة {channel} بنجاح.",
                    reply_markup=InlineKeyboardBuilder().button(text="🔙 للوحة التحكم", callback_data="ho_mandatory_sub").as_markup())
            else:
                await status_msg.edit_text("❌ هذه القناة/المجموعة مضافة بالفعل.")
            await state.clear()

        @dp.callback_query(F.data == "ho_rm_ch_menu")
        async def ho_rm_ch_menu(callback: types.CallbackQuery):
            if callback.from_user.id != owner_id: return
            conf = await get_config()
            channels = conf.get('mandatory_channels', [])

            builder = InlineKeyboardBuilder()
            for ch in channels:
                builder.button(text=f"🗑 {ch}", callback_data=f"ho_rmc_{ch}")
            builder.button(text='🔙 رجوع', callback_data='ho_mandatory_sub')
            builder.adjust(1)
            await callback.message.edit_text("اختر القناة لحذفها:", reply_markup=builder.as_markup())

        @dp.callback_query(F.data.startswith("ho_rmc_"))
        async def ho_rm_ch_process(callback: types.CallbackQuery):
            if callback.from_user.id != owner_id: return
            ch_to_rm = callback.data.replace('ho_rmc_', '')
            conf = await get_config()
            channels = conf.get('mandatory_channels', [])
            if ch_to_rm in channels:
                channels.remove(ch_to_rm)
                conf['mandatory_channels'] = channels
                conn = get_db_connection()
                conn.cursor().execute("UPDATE hosted_bots SET config = ? WHERE id = ?", (json.dumps(conf), bot_id))
                conn.commit()
                conn.close()
                await callback.answer(f"✅ تم حذف القناة {ch_to_rm}")
            await ho_mandatory_sub_menu(callback)

        @dp.callback_query(F.data == "h_check_sub")
        async def h_check_sub(callback: types.CallbackQuery):
            u_id = callback.from_user.id
            conf = await get_config()
            channels = conf.get('mandatory_channels', [])
            if not channels and conf.get('channel_username'):
                channels = [conf['channel_username']]

            not_subbed = []
            for ch in channels:
                try:
                    m = await callback.bot.get_chat_member(chat_id=ch, user_id=u_id)
                    if m.status in ['left', 'kicked']:
                        not_subbed.append(ch)
                except:
                    not_subbed.append(ch)

            if not not_subbed:
                await callback.answer("✅ تم التحقق بنجاح!")
                await callback.message.delete()
                u = await get_user(u_id)
                text = f"""👋 <b>أهلاً {u['full_name']}!</b>

💰 رصيد النقاط: <code>{u['points']}</code>
🪙 رصيد TON: <code>{u['ton_balance']:.4f}</code>
⭐ رصيد Stars: <code>{u['stars_balance']}</code>

اختر من القائمة:"""
                await callback.message.answer(text, reply_markup=await get_hosted_main_menu(u_id), parse_mode=ParseMode.HTML)
            else:
                await callback.answer("⚠️ أنت غير مشترك في جميع القنوات!", show_alert=True)

    @staticmethod
    async def update_bot_token(bot_id, new_token, user_id):
        conn = get_db_connection()
        cur = conn.cursor()
        bot_d = cur.execute(
            "SELECT * FROM hosted_bots WHERE id = ? AND owner_id = ?", (bot_id, user_id)
        ).fetchone()
        if not bot_d:
            return False, "البوت غير موجود"
        await HostedBotSystem.stop_bot(bot_id)
        try:
            temp_bot = Bot(token=new_token)
            me = await temp_bot.get_me()
            await temp_bot.session.close()
            cur.execute(
                "UPDATE hosted_bots SET bot_token = ?, bot_username = ?, bot_name = ?, is_active = 1 WHERE id = ?",
                (new_token, me.username, me.full_name, bot_id),
            )
            conn.commit()
            conn.close()
            await HostedBotSystem.start_bot(bot_id, new_token, me.username, user_id)
            return True, f"تم التحديث: @{me.username}"
        except Exception as e:
            return False, str(e)

    @staticmethod
    async def delete_bot(bot_id, user_id):
        conn = get_db_connection()
        cur = conn.cursor()
        bot_d = cur.execute(
            "SELECT * FROM hosted_bots WHERE id = ? AND owner_id = ?", (bot_id, user_id)
        ).fetchone()
        if not bot_d:
            return False, "البوت غير موجود"
        await HostedBotSystem.stop_bot(bot_id)
        cur.execute("DELETE FROM hosted_bot_users WHERE bot_id = ?", (bot_id,))
        cur.execute("DELETE FROM hosted_bots WHERE id = ?", (bot_id,))
        conn.commit()
        conn.close()
        return True, "تم الحذف"
