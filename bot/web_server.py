import os
import json
import traceback
from aiohttp import web
from datetime import datetime
from .config import VERIFICATION_SERVER_PORT, FINGERPRINT_WEB_URL, logger
from .database import SecretLinkSystem, SmartIPBan, FingerprintSystem, PointsSystem, SettingsManager

async def handle_fingerprint_verification(request):
    # ✅ إضافة دعم CORS للمواقع الخارجية مثل GitHub Pages
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

    if request.method == "OPTIONS":
        return web.Response(headers=headers)

    try:
        data = await request.json()
        user_id, fp, sec = data.get("user_id"), data.get("fingerprint"), data.get("secret")
        comp, ip = data.get("fingerprint_components", {}), data.get("ip") or request.remote or "unknown"

        if not all([user_id, fp, sec]):
            return web.json_response({"success": False, "message": "بيانات ناقصة"}, status=400, headers=headers)

        v_l, l_m = await SecretLinkSystem.verify_link(sec, user_id)
        if not v_l:
            return web.json_response({"success": False, "message": f"⚠️ {l_m}"}, headers=headers)

        ip_c = await SmartIPBan.check_ip(ip, user_id)
        if ip_c["banned"]:
            return web.json_response({"success": False, "message": "⛔️ محظور", "details": ip_c["reason"]}, headers=headers)

        try:
            vpn = await SmartIPBan.check_vpn(ip)
            if vpn.get("is_vpn") or vpn.get("is_hosting"):
                return web.json_response({"success": False, "message": "⚠️ عطل VPN"}, headers=headers)
        except:
            pass

        dup = await FingerprintSystem.check_duplicate(fp, user_id)
        if dup["duplicate"]:
            return web.json_response({"success": False, "message": "⚠️ جهاز مسجل مسبقاً"}, headers=headers)

        await FingerprintSystem.save_fingerprint(user_id, fp, comp, ip)
        bonus = await SettingsManager.get_int_setting("WELCOME_BONUS", 5)
        if bonus > 0:
            await PointsSystem.add_points(user_id, bonus, "welcome_bonus", "ترحيب")

        return web.json_response({"success": True, "message": "✅ تم التحقق!", "welcome_bonus": bonus}, headers=headers)
    except:
        return web.json_response({"success": False, "message": "خطأ"}, status=500, headers=headers)

async def serve_fingerprint_html(request):
    if os.path.exists('index.html'): return web.FileResponse('index.html')
    return web.Response(text="not found", status=404)

async def start_verification_server():
    app = web.Application()
    # ✅ السماح بجميع الطرق (بما في ذلك OPTIONS و POST) للتعامل مع CORS
    app.router.add_route('*', '/verify-fingerprint', handle_fingerprint_verification)
    app.router.add_get('/index.html', serve_fingerprint_html)
    app.router.add_get('/', serve_fingerprint_html)
    if not os.path.exists('stickers'): os.makedirs('stickers')
    app.router.add_static('/stickers/', path='stickers', name='stickers')
    runner = web.AppRunner(app); await runner.setup(); await web.TCPSite(runner, '0.0.0.0', VERIFICATION_SERVER_PORT).start()
    print(f"🌐 Server: {VERIFICATION_SERVER_PORT}")
