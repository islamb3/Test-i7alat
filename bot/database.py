import sqlite3
import json
import secrets
import string
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from .config import logger, DATABASE_PATH

CAPTCHA_QUESTIONS = [
    {"question": "ما هي العملة المشفرة التي تستخدم العقود الذكية؟", "options": ["Bitcoin", "Ethereum", "Litecoin", "Dogecoin"], "correct": 1},
    {"question": "ما هو الاسم الآخر لـ Bitcoin؟", "options": ["العملة الرقمية", "العملة المشفرة", "النقود الإلكترونية", "الذهب الرقمي"], "correct": 3},
    {"question": "كم عدد Bitcoins القصوى؟", "options": ["21 مليون", "100 مليون", "لا نهائي", "1 مليار"], "correct": 0},
    {"question": "ما هي تقنية سجل Bitcoin؟", "options": ["Cloud", "Blockchain", "Database", "Ledger"], "correct": 1},
]

def setup_database():
    """Initializes the database schema for the main bot and hosted bots."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER UNIQUE NOT NULL, username TEXT, full_name TEXT, referral_code TEXT UNIQUE, referred_by INTEGER, captcha_passed BOOLEAN DEFAULT 0, subscribed BOOLEAN DEFAULT 0, registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, is_banned BOOLEAN DEFAULT 0, points INTEGER DEFAULT 0, ton_balance REAL DEFAULT 0, stars_balance INTEGER DEFAULT 0, wallet_address TEXT, last_daily_bonus TIMESTAMP, daily_streak_count INTEGER DEFAULT 0, fingerprint_hash TEXT, fingerprint_components TEXT, fingerprint_verified BOOLEAN DEFAULT 0, fingerprint_verified_at TIMESTAMP, ip_address TEXT, is_admin BOOLEAN DEFAULT 0, total_referrals INTEGER DEFAULT 0, total_tasks_completed INTEGER DEFAULT 0, total_earned_points INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS referrals (id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER NOT NULL, referred_id INTEGER UNIQUE NOT NULL, is_valid BOOLEAN DEFAULT 0, points INTEGER DEFAULT 0, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS ip_attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, ip_address TEXT NOT NULL, user_id INTEGER, attempt_type TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ip_attempts ON ip_attempts(ip_address, timestamp)')
    cursor.execute('CREATE TABLE IF NOT EXISTS banned_ips (id INTEGER PRIMARY KEY AUTOINCREMENT, ip_address TEXT UNIQUE NOT NULL, banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, ban_reason TEXT, ban_duration INTEGER DEFAULT 72, banned_by INTEGER, expires_at TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS secret_links (id INTEGER PRIMARY KEY AUTOINCREMENT, secret TEXT UNIQUE NOT NULL, user_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP NOT NULL, used BOOLEAN DEFAULT 0, used_at TIMESTAMP)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_secret ON secret_links(secret)')
    cursor.execute('CREATE TABLE IF NOT EXISTS device_fingerprints (id INTEGER PRIMARY KEY AUTOINCREMENT, fingerprint_hash TEXT NOT NULL, user_id INTEGER NOT NULL, canvas_hash TEXT, webgl_hash TEXT, audio_hash TEXT, device_info TEXT, ip_address TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(telegram_id))')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fingerprint ON device_fingerprints(fingerprint_hash)')
    cursor.execute('CREATE TABLE IF NOT EXISTS hosted_bots (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_token TEXT UNIQUE NOT NULL, bot_username TEXT UNIQUE NOT NULL, bot_name TEXT, owner_id INTEGER NOT NULL, plan_type TEXT DEFAULT "free", is_active BOOLEAN DEFAULT 1, expires_at TIMESTAMP, max_users INTEGER DEFAULT 2000, current_users INTEGER DEFAULT 0, total_points_given INTEGER DEFAULT 0, config TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_activity TIMESTAMP, FOREIGN KEY (owner_id) REFERENCES users(telegram_id))')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bot_owner ON hosted_bots(owner_id)')
    cursor.execute('CREATE TABLE IF NOT EXISTS upgrade_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, bot_id INTEGER NOT NULL, requested_plan TEXT NOT NULL, payment_method TEXT, payment_amount REAL, status TEXT DEFAULT "pending", request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, processed_date TIMESTAMP, processed_by INTEGER, FOREIGN KEY (bot_id) REFERENCES hosted_bots(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT, link TEXT, points INTEGER NOT NULL, is_active BOOLEAN DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, max_completions INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS user_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, task_id INTEGER NOT NULL, completion_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, task_id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, asset_type TEXT NOT NULL, amount REAL NOT NULL, wallet_address TEXT, status TEXT DEFAULT "pending", request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, processed_date TIMESTAMP, processed_by INTEGER, notes TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS points_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, action_type TEXT NOT NULL, points INTEGER NOT NULL, description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS user_settings (user_id INTEGER PRIMARY KEY, notifications_enabled BOOLEAN DEFAULT 1, language TEXT DEFAULT "ar", theme TEXT DEFAULT "default")')
    cursor.execute('CREATE TABLE IF NOT EXISTS hosted_bot_users (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER NOT NULL, user_telegram_id INTEGER NOT NULL, username TEXT, full_name TEXT, referral_code TEXT, referred_by INTEGER, points INTEGER DEFAULT 0, ton_balance REAL DEFAULT 0, stars_balance INTEGER DEFAULT 0, wallet_address TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_activity TIMESTAMP, last_daily_bonus TIMESTAMP, daily_streak_count INTEGER DEFAULT 0, total_referrals INTEGER DEFAULT 0, total_tasks_completed INTEGER DEFAULT 0, total_earned_points INTEGER DEFAULT 0, fingerprint_hash TEXT, ip_address TEXT, is_banned BOOLEAN DEFAULT 0, fingerprint_verified BOOLEAN DEFAULT 0, UNIQUE(bot_id, user_telegram_id), FOREIGN KEY (bot_id) REFERENCES hosted_bots(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS hosted_bot_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER NOT NULL, name TEXT NOT NULL, description TEXT, link TEXT, points INTEGER NOT NULL, is_active BOOLEAN DEFAULT 1, max_completions INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (bot_id) REFERENCES hosted_bots(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS hosted_bot_user_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER NOT NULL, user_id INTEGER NOT NULL, task_id INTEGER NOT NULL, completion_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(bot_id, user_id, task_id), FOREIGN KEY (bot_id) REFERENCES hosted_bots(id), FOREIGN KEY (task_id) REFERENCES hosted_bot_tasks(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS hosted_bot_points_history (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER NOT NULL, user_id INTEGER NOT NULL, action_type TEXT NOT NULL, points INTEGER NOT NULL, description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (bot_id) REFERENCES hosted_bots(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS hosted_bot_withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER NOT NULL, user_id INTEGER NOT NULL, asset_type TEXT NOT NULL, amount REAL NOT NULL, wallet_address TEXT, status TEXT DEFAULT "pending", request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, processed_date TIMESTAMP, processed_by INTEGER, notes TEXT, FOREIGN KEY (bot_id) REFERENCES hosted_bots(id))')
    conn.commit()
    conn.close()
    print("✅ Database setup complete")

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

class SettingsManager:
    @staticmethod
    async def init_settings():
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, description TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_by INTEGER)')
        cursor.execute('CREATE TABLE IF NOT EXISTS plan_settings (plan_id TEXT NOT NULL, setting_key TEXT NOT NULL, setting_value TEXT NOT NULL, PRIMARY KEY (plan_id, setting_key))')
        defs = {
            'IP_BAN_ENABLED': ('1', 'تفعيل حظر IP'),
            'MAX_USERS_PER_IP': ('1', 'أقصى عدد مستخدمين لكل IP'),
            'BAN_DURATION_HOURS': ('72', 'مدة حظر IP (ساعة)'),
            'MAX_ATTEMPTS_PER_HOUR': ('5', 'أقصى محاولات لكل ساعة'),
            'SECRET_LINK_EXPIRY_MINUTES': ('5', 'صلاحية الرابط السري (دقيقة)'),
            'BLOCK_DUPLICATE_DEVICES': ('1', 'منع تكرار البصمة'),
            'VPN_DETECTION_ENABLED': ('1', 'كشف VPN/Proxy'),
            'REFERRAL_REWARD': ('10', 'نقاط الإحالة'),
            'DAILY_BONUS_BASE': ('10', 'نقاط المكافأة اليومية الأساسية'),
            'DAILY_BONUS_STREAK': ('5', 'نقاط إضافية لكل يوم متتالي'),
            'DAILY_BONUS_WEEKLY': ('100', 'مكافأة أسبوع كامل'),
            'DAILY_BONUS_MAX_STREAK': ('7', 'أقصى أيام متتالية للمكافأة'),
            'MIN_WITHDRAWAL_TON': ('0.5', 'أدنى سحب TON'),
            'MIN_WITHDRAWAL_STARS': ('100', 'أدنى سحب Stars'),
            'WITHDRAWAL_FEE_PERCENT': ('5', 'نسبة رسوم السحب (%)'),
            'WITHDRAWAL_ENABLED': ('1', 'تفعيل السحب'),
            'WITHDRAWAL_TON_ENABLED': ('1', 'تفعيل سحب TON'),
            'WITHDRAWAL_STARS_ENABLED': ('1', 'تفعيل سحب Stars'),
            'HOSTING_BUTTON_ENABLED': ('1', 'تفعيل زر استضافة بوت'),
            'MANDATORY_CHANNELS': ('[]', 'قنوات الاشتراك الإجباري'),
            'CONVERSION_POINTS_TON': ('1000', 'نقاط مقابل 1 TON'),
            'CONVERSION_POINTS_STARS': ('150', 'نقاط مقابل 10 Stars'),
            'CONVERSION_ENABLED': ('1', 'تفعيل التحويل'),
            'FREE_PLAN_MAX_USERS': ('2000', 'أقصى مستخدمين للباقة المجانية'),
            'PREMIUM_PLAN_MAX_USERS': ('10000', 'أقصى مستخدمين للباقة المميزة'),
            'ENTERPRISE_PLAN_MAX_USERS': ('100000', 'أقصى مستخدمين للباقة الاحترافية'),
            'PREMIUM_PLAN_PRICE_TON': ('50', 'سعر الباقة المميزة بـ TON'),
            'PREMIUM_PLAN_PRICE_STARS': ('15000', 'سعر الباقة المميزة بـ Stars'),
            'ENTERPRISE_PLAN_PRICE_TON': ('200', 'سعر الباقة الاحترافية بـ TON'),
            'ENTERPRISE_PLAN_PRICE_STARS': ('60000', 'سعر الباقة الاحترافية بـ Stars'),
            'PREMIUM_PLAN_DURATION': ('30', 'مدة الباقة المميزة (أيام)'),
            'ENTERPRISE_PLAN_DURATION': ('90', 'مدة الباقة الاحترافية (أيام)'),
            'TASKS_ENABLED': ('1', 'تفعيل نظام المهام'),
            'TASK_BONUS_POINTS': ('50', 'نقاط إضافية لإكمال جميع المهام'),
            'WELCOME_BONUS': ('5', 'نقاط ترحيبية للمستخدم الجديد'),
            'MAINTENANCE_MODE': ('0', 'وضع الصيانة'),
            'BROADCAST_ENABLED': ('1', 'تفعيل البث')
        }
        for k, (v, d) in defs.items(): cursor.execute('INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)', (k, v, d))
        feat = {('free', 'referral_system'): '1', ('free', 'daily_bonus'): '1', ('free', 'tasks_system'): '1', ('free', 'fingerprint_protection'): '1', ('free', 'ip_ban_protection'): '1', ('free', 'withdrawals'): '0', ('free', 'customization'): '0', ('free', 'store_access'): '1', ('free', 'conversion'): '1', ('premium', 'referral_system'): '1', ('premium', 'daily_bonus'): '1', ('premium', 'tasks_system'): '1', ('premium', 'fingerprint_protection'): '1', ('premium', 'ip_ban_protection'): '1', ('premium', 'withdrawals'): '0', ('premium', 'customization'): '1', ('premium', 'store_access'): '1', ('premium', 'conversion'): '1', ('enterprise', 'referral_system'): '1', ('enterprise', 'daily_bonus'): '1', ('enterprise', 'tasks_system'): '1', ('enterprise', 'fingerprint_protection'): '1', ('enterprise', 'ip_ban_protection'): '1', ('enterprise', 'withdrawals'): '1', ('enterprise', 'customization'): '1', ('enterprise', 'store_access'): '1', ('enterprise', 'conversion'): '1'}
        for (pid, f), v in feat.items(): cursor.execute('INSERT OR IGNORE INTO plan_settings (plan_id, setting_key, setting_value) VALUES (?, ?, ?)', (pid, f, v))
        conn.commit(); conn.close()
    @staticmethod
    async def get_setting(key, default=None):
        conn = get_db_connection(); res = conn.cursor().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone(); conn.close()
        return res['value'] if res else default
    @staticmethod
    async def get_int_setting(key, default=0):
        val = await SettingsManager.get_setting(key, str(default))
        try: return int(val)
        except: return default
    @staticmethod
    async def get_float_setting(key, default=0.0):
        val = await SettingsManager.get_setting(key, str(default))
        try: return float(val)
        except: return default
    @staticmethod
    async def get_bool_setting(key, default=False):
        return await SettingsManager.get_setting(key, "1" if default else "0") == "1"
    @staticmethod
    async def update_setting(key, value, user_id=None):
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ? WHERE key = ?", (value, user_id, key))
        conn.commit(); conn.close()
    @staticmethod
    async def get_all_settings():
        conn = get_db_connection(); rows = conn.cursor().execute("SELECT key, value FROM settings").fetchall(); conn.close()
        return {r['key']: r['value'] for r in rows}
    @staticmethod
    async def get_plan_config(plan_id):
        conn = get_db_connection()
        max_u = await SettingsManager.get_int_setting(f"{plan_id.upper()}_PLAN_MAX_USERS", 2000)
        p_ton = await SettingsManager.get_float_setting(f"{plan_id.upper()}_PLAN_PRICE_TON", 0)
        p_stars = await SettingsManager.get_int_setting(f"{plan_id.upper()}_PLAN_PRICE_STARS", 0)
        dur = await SettingsManager.get_int_setting(f"{plan_id.upper()}_PLAN_DURATION", 30) if plan_id != "free" else None
        feat = {r['setting_key']: r['setting_value'] == "1" for r in conn.cursor().execute("SELECT setting_key, setting_value FROM plan_settings WHERE plan_id = ?", (plan_id,)).fetchall()}
        conn.close()
        names = {'free': '🎁 مجاني', 'premium': '💎 بريميوم', 'enterprise': '👑 إنتربرايز'}
        return {'name': names.get(plan_id, plan_id), 'price_ton': p_ton, 'price_stars': p_stars, 'max_users': max_u, 'duration_days': dur, 'features': feat}
    @staticmethod
    async def get_protection_config():
        return {'IP_BAN_ENABLED': await SettingsManager.get_bool_setting('IP_BAN_ENABLED', True), 'MAX_USERS_PER_IP': await SettingsManager.get_int_setting('MAX_USERS_PER_IP', 1), 'BAN_DURATION_HOURS': await SettingsManager.get_int_setting('BAN_DURATION_HOURS', 72), 'MAX_ATTEMPTS_PER_HOUR': await SettingsManager.get_int_setting('MAX_ATTEMPTS_PER_HOUR', 5), 'SECRET_LINK_EXPIRY_MINUTES': await SettingsManager.get_int_setting('SECRET_LINK_EXPIRY_MINUTES', 5), 'BLOCK_DUPLICATE_DEVICES': await SettingsManager.get_bool_setting('BLOCK_DUPLICATE_DEVICES', True), 'VPN_DETECTION_ENABLED': await SettingsManager.get_bool_setting('VPN_DETECTION_ENABLED', True)}

def generate_referral_code(length=8):
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))

def is_valid_ton_address(addr):
    return addr and len(addr) == 48 and addr[0] in ['E', 'U', '0']

class SecretLinkSystem:
    @staticmethod
    async def generate_link(u_id):
        exp_m = await SettingsManager.get_int_setting('SECRET_LINK_EXPIRY_MINUTES', 5)
        sec = secrets.token_urlsafe(32); exp_at = (datetime.now() + timedelta(minutes=exp_m)).isoformat()
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("UPDATE secret_links SET used = 1, used_at = ? WHERE user_id = ? AND used = 0", (datetime.now().isoformat(), u_id))
        cursor.execute("INSERT INTO secret_links (secret, user_id, expires_at) VALUES (?, ?, ?)", (sec, u_id, exp_at))
        conn.commit(); conn.close(); return sec, exp_m
    @staticmethod
    async def verify_link(sec, u_id):
        conn = get_db_connection(); row = conn.cursor().execute("SELECT * FROM secret_links WHERE secret = ? AND user_id = ? AND used = 0", (sec, u_id)).fetchone()
        if not row: return False, 'رابط غير صالح'
        if datetime.now() > datetime.fromisoformat(row['expires_at']): return False, 'انتهت الصلاحية'
        conn.cursor().execute("UPDATE secret_links SET used = 1, used_at = ? WHERE id = ?", (datetime.now().isoformat(), row['id']))
        conn.commit(); conn.close(); return True, 'تم التحقق'

class SmartIPBan:
    @staticmethod
    async def check_ip(ip, u_id):
        conf = await SettingsManager.get_protection_config()
        if not conf['IP_BAN_ENABLED'] or ip == 'unknown': return {'banned': False}
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("DELETE FROM banned_ips WHERE expires_at IS NOT NULL AND expires_at < datetime('now')")
        banned = cursor.execute("SELECT * FROM banned_ips WHERE ip_address = ?", (ip,)).fetchone()
        if banned: return {'banned': True, 'reason': 'IP محظور'}
        u_count = cursor.execute("SELECT COUNT(DISTINCT telegram_id) as c FROM users WHERE ip_address = ? AND telegram_id != ?", (ip, u_id)).fetchone()['c']
        if u_count >= conf['MAX_USERS_PER_IP']:
            exp = (datetime.now() + timedelta(hours=conf['BAN_DURATION_HOURS'])).isoformat()
            cursor.execute("INSERT OR IGNORE INTO banned_ips (ip_address, ban_reason, ban_duration, expires_at) VALUES (?, ?, ?, ?)", (ip, f"Auto-ban: {u_count+1} users", conf['BAN_DURATION_HOURS'], exp))
            conn.commit(); conn.close(); return {'banned': True, 'reason': 'تجاوز الحد المسموح'}
        att = cursor.execute("SELECT COUNT(*) as c FROM ip_attempts WHERE ip_address = ? AND timestamp > datetime('now', '-1 hour')", (ip,)).fetchone()['c']
        if att >= conf['MAX_ATTEMPTS_PER_HOUR']:
            exp = (datetime.now() + timedelta(hours=conf['BAN_DURATION_HOURS'])).isoformat()
            cursor.execute("INSERT OR IGNORE INTO banned_ips (ip_address, ban_reason, ban_duration, expires_at) VALUES (?, ?, ?, ?)", (ip, "Too many attempts", conf['BAN_DURATION_HOURS'], exp))
            conn.commit(); conn.close(); return {'banned': True, 'reason': 'محاولات كثيرة'}
        cursor.execute("INSERT INTO ip_attempts (ip_address, user_id, attempt_type) VALUES (?, ?, ?)", (ip, u_id, 'verification'))
        conn.commit(); conn.close(); return {'banned': False, 'remaining': conf['MAX_USERS_PER_IP'] - u_count}
    @staticmethod
    async def check_vpn(ip):
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.get(f'http://ip-api.com/json/{ip}?fields=status,proxy,hosting') as r:
                    d = await r.json()
                    if d.get('status') == 'success': return {'is_vpn': d.get('proxy', False), 'is_hosting': d.get('hosting', False)}
        except: pass
        return {'is_vpn': False, 'is_hosting': False}
    @staticmethod
    async def ban_ip(ip, reason, hours, admin_id):
        exp = (datetime.now() + timedelta(hours=hours)).isoformat(); conn = get_db_connection()
        conn.cursor().execute("INSERT OR REPLACE INTO banned_ips (ip_address, ban_reason, ban_duration, banned_by, expires_at) VALUES (?, ?, ?, ?, ?)", (ip, reason, hours, admin_id, exp))
        conn.commit(); conn.close()
    @staticmethod
    async def unban_ip(ip):
        conn = get_db_connection(); conn.cursor().execute("DELETE FROM banned_ips WHERE ip_address = ?", (ip,)); conn.commit(); conn.close()
    @staticmethod
    async def get_banned_ips():
        conn = get_db_connection(); res = conn.cursor().execute("SELECT * FROM banned_ips WHERE expires_at IS NULL OR expires_at > datetime('now') ORDER BY banned_at DESC").fetchall(); conn.close(); return res

class FingerprintSystem:
    @staticmethod
    async def check_duplicate(fp, u_id):
        if not await SettingsManager.get_bool_setting('BLOCK_DUPLICATE_DEVICES', True): return {'duplicate': False}
        conn = get_db_connection(); res = conn.cursor().execute("SELECT user_id FROM device_fingerprints WHERE fingerprint_hash = ? AND user_id != ? LIMIT 1", (fp, u_id)).fetchone(); conn.close()
        return {'duplicate': True, 'existing_user': res['user_id']} if res else {'duplicate': False}
    @staticmethod
    async def save_fingerprint(u_id, fp, comp, ip):
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("INSERT INTO device_fingerprints (fingerprint_hash, user_id, canvas_hash, webgl_hash, audio_hash, device_info, ip_address) VALUES (?, ?, ?, ?, ?, ?, ?)", (fp, u_id, comp.get('canvas'), comp.get('webgl'), comp.get('audio'), json.dumps(comp), ip))
        cursor.execute("UPDATE users SET fingerprint_hash = ?, fingerprint_components = ?, fingerprint_verified = 1, fingerprint_verified_at = ?, ip_address = ? WHERE telegram_id = ?", (fp, json.dumps(comp), datetime.now().isoformat(), ip, u_id))
        conn.commit(); conn.close(); return True

class PointsSystem:
    @staticmethod
    async def add_points(u_id, p, act, desc=None):
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("UPDATE users SET points = points + ?, total_earned_points = total_earned_points + ? WHERE telegram_id = ?", (p, p, u_id))
        cursor.execute("INSERT INTO points_history (user_id, action_type, points, description) VALUES (?, ?, ?, ?)", (u_id, act, p, desc))
        conn.commit(); conn.close()
    @staticmethod
    async def subtract_points(u_id, p, act, desc=None):
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("UPDATE users SET points = points - ? WHERE telegram_id = ? AND points >= ?", (p, u_id, p))
        if cursor.rowcount > 0:
            cursor.execute("INSERT INTO points_history (user_id, action_type, points, description) VALUES (?, ?, ?, ?)", (u_id, act, -p, desc))
            conn.commit(); conn.close(); return True
        conn.close(); return False
    @staticmethod
    async def get_points_history(u_id, limit=20):
        conn = get_db_connection(); res = conn.cursor().execute("SELECT * FROM points_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (u_id, limit)).fetchall(); conn.close(); return res
