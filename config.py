"""
ملف الإعدادات العامة للبوت.
"""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__ ))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
LOGO_DIR = os.path.join(ASSETS_DIR, "logo")
GENERATED_DIR = os.path.join(BASE_DIR, "generated")

os.makedirs(FONTS_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)

DEFAULT_COMPANY = {
    "company_name": "شركة الحلول الجديدة",
    "company_slogan": "لاستيراد وبيع كماليات السيارات",
    "phone1": "0924565333",
    "phone2": "0914565333",
    "address": "طرابلس - ليبيا",
}

OUTPUT_SIZES = {
    "instagram_post": (1080, 1080),
    "instagram_portrait": (1080, 1350),
    "story": (1080, 1920),
    "facebook_post": (1200, 630),
}

TEMPLATES = {
    "luxury_dark": {
        "label": "القالب الفاخر الاحترافي",
        "bg_start": (15, 16, 22),
        "bg_end": (7, 8, 10),
        "accent": (218, 165, 32), # ذهبي رياضي أو استبدله بـ (230, 0, 0) للأحمر
        "text": (255, 255, 255),
        "secondary": (175, 180, 190),
        "badge_bg": (28, 30, 38)
    }
}
