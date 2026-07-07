"""
ملف الإعدادات العامة للبوت.
كل القيم الحساسة (التوكن، آيدي الأدمن) تُقرأ من ملف .env
باقي بيانات الشركة (الاسم، الأرقام، العنوان) تُخزَّن في قاعدة البيانات
ويمكن للأدمن تعديلها من داخل البوت بأمر /admin بدون لمس الكود.
"""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
LOGO_DIR = os.path.join(ASSETS_DIR, "logo")
GENERATED_DIR = os.path.join(BASE_DIR, "generated")

os.makedirs(GENERATED_DIR, exist_ok=True)

# القيم الافتراضية الأولى لبيانات الشركة (الأدمن يقدر يغيّرها لاحقًا من البوت)
DEFAULT_COMPANY = {
    "company_name": "شركة الحلول الجديدة",
    "company_slogan": "لاستيراد وبيع كماليات السيارات",
    "phone1": "0924565333",
    "phone2": "0914565333",
    "address": "",
}

# مقاسات النشر المدعومة (بالبكسل) - 300 DPI تقريبًا لكل الشبكات الاجتماعية
OUTPUT_SIZES = {
    "instagram_post": (1080, 1080),      # مربع
    "instagram_portrait": (1080, 1350),  # بورتريه
    "story": (1080, 1920),               # ستوري / حالة
    "facebook_post": (1200, 630),        # لاندسكيب
}

# القوالب المتاحة - كل قالب له لوحة ألوان مختلفة
TEMPLATES = {
    "luxury_black": {
        "label": "Template 1 - Luxury Black",
        "bg": (10, 10, 12),
        "bg2": (22, 6, 8),
        "accent": (208, 32, 43),
        "text": (255, 255, 255),
        "secondary": (185, 185, 185),
    },
    "red_racing": {
        "label": "Template 2 - Red Racing",
        "bg": (18, 3, 5),
        "bg2": (40, 6, 9),
        "accent": (255, 40, 40),
        "text": (255, 255, 255),
        "secondary": (230, 200, 200),
    },
    "minimal_white": {
        "label": "Template 3 - Minimal White",
        "bg": (245, 245, 245),
        "bg2": (230, 230, 230),
        "accent": (208, 32, 43),
        "text": (20, 20, 20),
        "secondary": (90, 90, 90),
    },
    "premium_carbon": {
        "label": "Template 4 - Premium Carbon Fiber",
        "bg": (16, 16, 18),
        "bg2": (28, 28, 30),
        "accent": (170, 170, 170),
        "text": (255, 255, 255),
        "secondary": (170, 170, 170),
    },
}
