import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import F
from aiogram.filters import CommandStart, Command, StateFilter
from .config import BOT_TOKEN, ADMIN_ID, logger
from .database import setup_database, SettingsManager, get_db_connection
from .hosting import HostedBotSystem
from .web_server import start_verification_server
from .states import *
from .handlers import *
from .middlewares import MandatorySubMiddleware


async def main():
    setup_database()
    await SettingsManager.init_settings()
    bot, dp = Bot(token=BOT_TOKEN), Dispatcher(storage=MemoryStorage())

    # Register Middleware
    dp.message.middleware(MandatorySubMiddleware())
    dp.callback_query.middleware(MandatorySubMiddleware())

    dp.message.register(admin_add_points_process, AdminStates.add_points)
    dp.message.register(admin_subtract_points_process, AdminStates.
        subtract_points)
    dp.message.register(admin_reject_withdrawal_reason_process, AdminStates
        .reject_withdrawal_reason)
    dp.message.register(admin_reject_withdrawal_reason_process,
        BotHostingStates.reject_withdrawal_reason)
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_admin, Command('admin'))
    dp.callback_query.register(check_fingerprint_verified, F.data ==
        'check_fingerprint_verified')
    dp.callback_query.register(process_captcha, F.data.startswith('captcha_'))
    dp.callback_query.register(check_subscription, F.data ==
        'check_subscription')
    dp.callback_query.register(back_to_main_menu_handler, F.data == 'main_menu'
        )
    dp.callback_query.register(bot_hosting_menu_handler, F.data ==
        'bot_hosting_menu')
    dp.callback_query.register(my_bots_handler, F.data == 'my_bots')
    dp.callback_query.register(add_new_bot_handler, F.data == 'add_new_bot')
    dp.message.register(process_bot_token, BotHostingStates.enter_token)
    dp.callback_query.register(dashboard_handler, F.data == 'dashboard')
    dp.callback_query.register(referral_link_handler, F.data == 'referral_link'
        )
    dp.callback_query.register(daily_bonus_handler, F.data == 'daily_bonus')
    dp.callback_query.register(tasks_list_handler, F.data == 'tasks_list')
    dp.callback_query.register(complete_task_handler, F.data.startswith(
        'complete_task_'))
    dp.callback_query.register(convert_points_handler, F.data ==
        'convert_points')
    dp.callback_query.register(convert_to_ton_handler, F.data ==
        'convert_to_ton')
    dp.callback_query.register(convert_to_stars_handler, F.data ==
        'convert_to_stars')
    dp.message.register(process_convert_to_ton, ConversionStates.
        enter_points_for_ton)
    dp.message.register(process_convert_to_stars, ConversionStates.
        enter_points_for_stars)
    dp.callback_query.register(statistics_handler, F.data == 'statistics')
    dp.callback_query.register(request_withdrawal_handler, F.data ==
        'request_withdrawal')
    dp.callback_query.register(withdraw_ton_handler, F.data == 'withdraw_ton')
    dp.callback_query.register(withdraw_stars_handler, F.data ==
        'withdraw_stars')
    dp.callback_query.register(set_wallet_address_handler, F.data ==
        'set_wallet_address')
    dp.message.register(process_wallet_address, WithdrawalStates.
        set_wallet_address)
    dp.message.register(process_ton_withdrawal, WithdrawalStates.
        request_ton_amount)
    dp.message.register(process_stars_withdrawal, WithdrawalStates.
        request_stars_amount)
    dp.callback_query.register(points_history_handler, F.data ==
        'points_history')
    dp.callback_query.register(bot_dashboard_handler, F.data.startswith(
        'bot_dashboard_'))
    dp.callback_query.register(bot_delete_handler, F.data.startswith(
        'bot_delete_'))
    dp.callback_query.register(bot_toggle_handler, F.data.startswith(
        'bot_start_'))
    dp.callback_query.register(bot_toggle_handler, F.data.startswith(
        'bot_stop_'))
    dp.callback_query.register(bot_edit_token_start, F.data.startswith(
        'bot_edit_token_'))
    dp.callback_query.register(admin_panel_handler, F.data == 'admin_panel')
    dp.callback_query.register(admin_stats_handler, F.data == 'admin_stats')
    dp.callback_query.register(admin_users_menu_handler, F.data ==
        'admin_users_menu')
    dp.callback_query.register(admin_find_user_start, F.data ==
        'admin_find_user')
    dp.message.register(admin_find_user_process, AdminStates.find_user)
    dp.callback_query.register(admin_add_points_start, F.data ==
        'admin_add_points')
    dp.callback_query.register(admin_subtract_points_start, F.data ==
        'admin_subtract_points')
    dp.callback_query.register(admin_ban_user_handler, F.data.startswith(
        'admin_ban_user_'))
    dp.callback_query.register(admin_unban_user_handler, F.data.startswith(
        'admin_unban_user_'))
    dp.callback_query.register(admin_banned_users_handler, F.data ==
        'admin_banned_users')
    dp.callback_query.register(admin_broadcast_start, F.data ==
        'admin_broadcast')
    dp.message.register(admin_broadcast_process, AdminStates.broadcast)
    dp.callback_query.register(admin_security_settings_handler, F.data ==
        'admin_security_settings')
    dp.callback_query.register(admin_toggle_setting_handler, F.data.in_([
        'admin_toggle_ip_ban', 'admin_toggle_duplicate', 'admin_toggle_vpn']))
    dp.callback_query.register(admin_set_value_start, F.data.in_([
        'admin_set_max_users_ip', 'admin_set_ban_duration',
        'admin_set_max_attempts', 'admin_set_secret_expiry',
        'admin_set_referral_reward', 'admin_set_daily_bonus_base',
        'admin_set_daily_bonus_streak', 'admin_set_daily_bonus_weekly',
        'admin_set_welcome_bonus',
        'admin_set_min_withdrawal_ton', 'admin_set_min_withdrawal_stars']))
    dp.message.register(admin_set_value_process, StateFilter(
        SettingsStates.set_max_users_per_ip, SettingsStates.set_ban_duration,
        SettingsStates.set_max_attempts, SettingsStates.set_secret_expiry,
        SettingsStates.set_referral_reward, SettingsStates.set_daily_bonus_base,
        SettingsStates.set_daily_bonus_streak, SettingsStates.set_daily_bonus_weekly,
        SettingsStates.set_welcome_bonus,
        SettingsStates.set_min_withdrawal_ton, SettingsStates.set_min_withdrawal_stars))
    dp.callback_query.register(admin_plan_settings_handler, F.data ==
        'admin_plan_settings')
    dp.callback_query.register(admin_set_plan_value_start, F.data.in_([
        'admin_set_free_max', 'admin_set_premium_max',
        'admin_set_enterprise_max', 'admin_set_premium_price_ton',
        'admin_set_premium_price_stars', 'admin_set_enterprise_price_ton',
        'admin_set_enterprise_price_stars', 'admin_set_premium_duration',
        'admin_set_enterprise_duration']))
    dp.message.register(admin_set_plan_value_process, StateFilter(SettingsStates.
        set_free_max_users, SettingsStates.set_premium_max_users,
        SettingsStates.set_enterprise_max_users, SettingsStates.
        set_premium_price_ton, SettingsStates.set_premium_price_stars,
        SettingsStates.set_enterprise_price_ton, SettingsStates.
        set_enterprise_price_stars, SettingsStates.set_premium_duration,
        SettingsStates.set_enterprise_duration))
    dp.callback_query.register(admin_points_settings_handler, F.data ==
        'admin_points_settings')
    dp.callback_query.register(admin_conversion_settings_handler, F.data ==
        'admin_conversion_settings')
    dp.callback_query.register(admin_toggle_conversion_handler, F.data ==
        'admin_toggle_conversion')
    dp.callback_query.register(admin_set_conversion_ton_start, F.data ==
        'admin_set_conversion_ton')
    dp.callback_query.register(admin_set_conversion_stars_start, F.data ==
        'admin_set_conversion_stars')
    dp.message.register(admin_set_conversion_ton_process, SettingsStates.
        set_conversion_points_ton)
    dp.message.register(admin_set_conversion_stars_process, SettingsStates.
        set_conversion_points_stars)
    dp.callback_query.register(admin_withdrawals_pending_handler, F.data ==
        'admin_withdrawals_pending')
    dp.callback_query.register(admin_process_withdrawal_handler, F.data.
        startswith('admin_approve_wd_'))
    dp.callback_query.register(admin_process_withdrawal_handler, F.data.
        startswith('admin_reject_wd_'))
    dp.callback_query.register(admin_tasks_menu_handler, F.data ==
        'admin_tasks_menu')
    dp.callback_query.register(admin_withdrawal_types_handler, F.data ==
        'admin_withdrawal_types')
    dp.callback_query.register(admin_toggle_wd_type_handler, F.data.startswith(
        'admin_toggle_wd_'))
    dp.callback_query.register(admin_hosting_button_toggle_handler, F.data ==
        'admin_hosting_button_toggle')
    dp.callback_query.register(admin_mandatory_sub_menu_handler, F.data ==
        'admin_mandatory_sub_menu')
    dp.callback_query.register(admin_add_mandatory_channel_start, F.data ==
        'admin_add_mandatory_ch')
    dp.message.register(admin_add_mandatory_channel_process, AdminStates.
        add_mandatory_channel)
    dp.callback_query.register(admin_remove_mandatory_channel_menu, F.data ==
        'admin_remove_mandatory_ch_menu')
    dp.callback_query.register(admin_remove_mandatory_channel_process, F.data.
        startswith('admin_rm_ch_'))
    dp.callback_query.register(admin_add_task_start, F.data == 'admin_add_task'
        )
    dp.callback_query.register(admin_list_tasks_handler, F.data ==
        'admin_list_tasks')
    dp.callback_query.register(admin_toggle_tasks_handler, F.data ==
        'admin_toggle_tasks')
    dp.callback_query.register(admin_toggle_task_handler, F.data.startswith
        ('admin_toggle_task_'))
    dp.callback_query.register(admin_delete_task_handler, F.data.startswith
        ('admin_delete_task_'))
    dp.message.register(admin_add_task_process, AdminStates.add_task)
    dp.message.register(admin_add_task_process, BotHostingStates.add_task)
    dp.callback_query.register(task_next_step_handler, F.data ==
        'task_next_step')
    dp.callback_query.register(admin_ban_ip_start, F.data == 'admin_ban_ip')
    dp.callback_query.register(admin_unban_ip_start, F.data == 'admin_unban_ip'
        )
    dp.message.register(admin_ban_ip_process, AdminStates.ban_ip)
    dp.message.register(admin_ban_ip_duration, AdminStates.ban_ip_duration)
    dp.message.register(admin_unban_ip_process, AdminStates.unban_ip)
    dp.callback_query.register(admin_all_bots_handler, F.data ==
        'admin_all_bots')
    dp.callback_query.register(admin_all_settings_handler, F.data ==
        'admin_all_settings')
    dp.callback_query.register(cancel_action_handler, F.data.startswith(
        'cancel_action_'))
    asyncio.create_task(start_verification_server())
    conn = get_db_connection()
    active_bots = conn.cursor().execute(
        'SELECT * FROM hosted_bots WHERE is_active = 1').fetchall()
    conn.close()
    for bot_data in active_bots:
        await HostedBotSystem.start_bot(bot_data['id'], bot_data[
            'bot_token'], bot_data['bot_username'], bot_data['owner_id'])
        await asyncio.sleep(1)
    me = await bot.get_me()
    print(f'🤖 Bot @{me.username} is running...')
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\n🛑 Stopped')
    except Exception as e:
        logging.critical(f'❌ Fatal: {e}', exc_info=True)
