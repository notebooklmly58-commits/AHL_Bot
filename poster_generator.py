"""
محرك التصميم الهندسي الاحترافي والمحكم - شركة الحلول الجديدة.
نسخة مُصححة: تعالج مشكلة الحروف/الأرقام المشوهة (مربعات فارغة) الناتجة عن
فشل تحميل خط Tajawal، وتُصلح ترتيب النص العربي المختلط بالأرقام عبر خوارزمية bidi
الرسمية بدلاً من العكس اليدوي، وتضيف تناسقاً بصرياً للوقو.
"""
import os
import uuid
import logging
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from config import OUTPUT_SIZES, FONTS_DIR, LOGO_DIR, GENERATED_DIR
import arabic_reshaper
from bidi.algorithm import get_display

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# إدارة الخطوط
# ------------------------------------------------------------------
# مهم جداً: أفضل حل هو رفع ملفي الخط هذين مباشرة داخل مستودع المشروع
# في نفس مسار FONTS_DIR بدلاً من الاعتماد على التنزيل وقت التشغيل،
# لأن سيرفرات الاستضافة (مثل Railway) قد تمنع الوصول لبعض الروابط
# الخارجية، وعندها كان الكود القديم "يصمت" عن الخطأ ويستخدم خط PIL
# الافتراضي الذي لا يدعم العربية إطلاقاً -> هذا هو سبب ظهور مربعات
# فارغة بدل الحروف في الصورة التي أرسلتها.
_FONT_URLS = {
    "Tajawal-Bold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/tajawal/Tajawal-Bold.ttf",
    "Tajawal-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/tajawal/Tajawal-Regular.ttf",
}

_SYSTEM_FALLBACKS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]

_font_cache = {}
_MIN_VALID_FONT_BYTES = 20_000  # أي ملف أصغر من هذا غالباً صفحة خطأ وليس خطاً حقيقياً


def _download_font_if_missing():
    os.makedirs(FONTS_DIR, exist_ok=True)
    for name, url in _FONT_URLS.items():
        path = os.path.join(FONTS_DIR, name)
        if os.path.exists(path) and os.path.getsize(path) > _MIN_VALID_FONT_BYTES:
            continue
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200 and len(r.content) > _MIN_VALID_FONT_BYTES:
                with open(path, "wb") as f:
                    f.write(r.content)
            else:
                logger.warning(f"تعذر تنزيل الخط {name}: استجابة غير صالحة ({r.status_code})")
        except Exception as e:
            logger.warning(f"تعذر تنزيل الخط {name}: {e}")


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """تحميل الخط مع ترتيب أولويات واضح وتسجيل أي فشل بدل تجاهله بصمت."""
    cache_key = (size, bold)
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    font_name = "Tajawal-Bold.ttf" if bold else "Tajawal-Regular.ttf"
    font_path = os.path.join(FONTS_DIR, font_name)

    # 1) الخط المرفوع يدوياً داخل المشروع (الأكثر ثباتاً وموصى به)
    if os.path.exists(font_path) and os.path.getsize(font_path) > _MIN_VALID_FONT_BYTES:
        try:
            font = ImageFont.truetype(font_path, size)
            _font_cache[cache_key] = font
            return font
        except Exception as e:
            logger.warning(f"ملف الخط تالف ({font_path}): {e}")

    # 2) محاولة تنزيل تلقائي كخطة بديلة فقط
    _download_font_if_missing()
    if os.path.exists(font_path) and os.path.getsize(font_path) > _MIN_VALID_FONT_BYTES:
        try:
            font = ImageFont.truetype(font_path, size)
            _font_cache[cache_key] = font
            return font
        except Exception:
            pass

    # 3) خط احتياطي من النظام (لا يدعم العربية بشكل مثالي لكنه أفضل من التوقف الكامل)
    for sys_font in _SYSTEM_FALLBACKS:
        if os.path.exists(sys_font):
            try:
                font = ImageFont.truetype(sys_font, size)
                logger.error(
                    "تنبيه: خط Tajawal غير موجود، تم استخدام خط بديل من النظام. "
                    "الرجاء رفع ملفات الخط داخل مجلد المشروع لحل المشكلة نهائياً."
                )
                _font_cache[cache_key] = font
                return font
            except Exception:
                continue

    logger.error("فشل تحميل أي خط يدعم العربية إطلاقاً - سيظهر النص بشكل غير سليم.")
    font = ImageFont.load_default()
    _font_cache[cache_key] = font
    return font


def fix_arabic_text(text: str) -> str:
    """إعادة تشكيل الحروف العربية وترتيبها بصرياً باستخدام خوارزمية bidi الرسمية.
    هذا يستبدل العكس اليدوي القديم reshaped[::-1] الذي كان يكسر ترتيب
    الأرقام والنصوص المختلطة (عربي + إنجليزي/أرقام) مثل الأسعار وأرقام الهاتف."""
    if not text:
        return ""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


# ------------------------------------------------------------------
# أدوات مساعدة للرسم
# ------------------------------------------------------------------
def _vertical_gradient(w: int, h: int, top_color, bottom_color) -> Image.Image:
    """توليد تدرج لوني عمودي بسرعة عالية (بدون المرور بيكسل بيكسل)."""
    column = Image.new("RGB", (1, h))
    for y in range(h):
        ratio = y / max(h - 1, 1)
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        column.putpixel((0, y), (r, g, b))
    return column.resize((w, h))


def _prepare_logo(logo_path: str, target_w: int) -> Image.Image:
    """قص الهوامش الشفافة الزائدة من اللوقو وتوحيد حجمه، لضمان ثبات شكله
    في كل بوستر بدل أن يظهر بحجم/تموضع مختلف حسب ملف اللوقو الأصلي."""
    logo_img = Image.open(logo_path).convert("RGBA")
    logo_img = ImageOps.exif_transpose(logo_img)
    bbox = logo_img.getbbox()
    if bbox:
        logo_img = logo_img.crop(bbox)
    target_h = max(1, int(logo_img.height * (target_w / logo_img.width)))
    return logo_img.resize((target_w, target_h), Image.Resampling.LANCZOS)


# ------------------------------------------------------------------
# التوليد الرئيسي
# ------------------------------------------------------------------
def generate_poster(
    product_image_path: str,
    product_name: str,
    price: str,
    features: list,
    socket: str,
    promo_text: str,
    company: dict,
    template_key: str,
    size_key: str,
) -> str:
    w, h = OUTPUT_SIZES.get(size_key, (1080, 1080))
    base = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(base)

    # 1. الخلفية الفاخرة المتدرجة (أسود ملكي داكن جداً) - نسخة سريعة
    top_color = (15, 15, 18)
    bottom_color = (35, 12, 15)
    gradient = _vertical_gradient(w, h, top_color, bottom_color).convert("RGBA")
    base.alpha_composite(gradient)

    # 2. هالة التوهج الخلفي (Neon Glow)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([w * 0.15, h * 0.22, w * 0.85, h * 0.58], fill=(220, 25, 35, 28))
    glow = glow.filter(ImageFilter.GaussianBlur(w * 0.08))
    base.alpha_composite(glow)

    # 3. شعار شركة الحلول الجديدة بالمنتصف الأعلى - داخل بطاقة موحدة
    #    (يحل مشكلة عدم تناسق شكل اللوقو مهما كانت خلفية الملف الأصلي)
    logo_path = os.path.join(LOGO_DIR, "logo.png")
    if os.path.exists(logo_path):
        try:
            logo_img = _prepare_logo(logo_path, int(w * 0.20))
            logo_x = int((w - logo_img.width) / 2)
            logo_y = int(h * 0.05)

            pad = int(w * 0.018)
            card = Image.new("RGBA", (logo_img.width + pad * 2, logo_img.height + pad * 2), (0, 0, 0, 0))
            card_draw = ImageDraw.Draw(card)
            card_draw.rounded_rectangle(
                [0, 0, card.width - 1, card.height - 1],
                radius=14,
                fill=(20, 20, 24, 235),
                outline=(215, 25, 32, 255),
                width=2,
            )
            card.paste(logo_img, (pad, pad), logo_img)
            base.alpha_composite(card, (logo_x - pad, logo_y - pad))
        except Exception as e:
            logger.warning(f"تعذر إضافة اللوقو: {e}")

    # 4. تثبيت صورة المنتج والظل
    if os.path.exists(product_image_path):
        p_img = Image.open(product_image_path).convert("RGBA")
        p_img = ImageOps.exif_transpose(p_img)
        max_p_w, max_p_h = int(w * 0.70), int(h * 0.40)
        p_img.thumbnail((max_p_w, max_p_h), Image.Resampling.LANCZOS)
        px = int((w - p_img.width) / 2)
        py = int(h * 0.21)

        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sh_draw = ImageDraw.Draw(shadow)
        sh_draw.ellipse(
            [px + 40, py + p_img.height - 12, px + p_img.width - 40, py + p_img.height + 12],
            fill=(0, 0, 0, 180),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(15))
        base.alpha_composite(shadow)
        base.paste(p_img, (px, py), p_img)

    # 5. تحميل الخطوط
    font_title = _load_font(int(w * 0.045), bold=True)
    font_promo = _load_font(int(w * 0.024), bold=False)
    font_price = _load_font(int(w * 0.032), bold=True)
    font_footer = _load_font(int(w * 0.022), bold=False)

    text_y = int(h * 0.65)

    # اسم المنتج (يمين)
    if product_name and product_name.strip():
        draw.text(
            (w - int(w * 0.08), text_y),
            fix_arabic_text(product_name.strip()),
            fill=(255, 255, 255),
            font=font_title,
            anchor="rm",
        )

    # السطر التسويقي
    if promo_text and promo_text.strip():
        draw.text(
            (w - int(w * 0.08), text_y + int(h * 0.055)),
            fix_arabic_text(promo_text.strip()),
            fill=(170, 170, 175),
            font=font_promo,
            anchor="rm",
        )

    # 6. بطاقة السعر (يسار)
    if price and price.strip():
        clean_price = price.replace("د.ل", "").strip()
        price_display = f"{clean_price} د.ل"
        draw.rounded_rectangle(
            [w * 0.08, text_y - 5, w * 0.28, text_y + int(h * 0.055)], radius=8, fill=(215, 25, 32)
        )
        draw.text(
            (w * 0.18, text_y + int(h * 0.025)),
            fix_arabic_text(price_display),
            fill=(255, 255, 255),
            font=font_price,
            anchor="mm",
        )

    # 7. كبسولات المواصفات
    feat_y_start = text_y + int(h * 0.11)
    col_w = int(w * 0.42)
    box_h = int(h * 0.05)

    clean_features = [f.strip() for f in features if f and f.strip()]
    for idx, feat in enumerate(clean_features[:4]):
        col = idx % 2
        row = idx // 2

        cx_center = int(w * 0.73) if col == 0 else int(w * 0.27)
        cy_center = feat_y_start + row * int(h * 0.07)

        draw.rounded_rectangle(
            [cx_center - col_w // 2, cy_center - box_h // 2, cx_center + col_w // 2, cy_center + box_h // 2],
            radius=6,
            fill=(26, 26, 30),
        )

        dot_x = cx_center + col_w // 2 - int(w * 0.03)
        draw.ellipse([dot_x - 4, cy_center - 4, dot_x + 4, cy_center + 4], fill=(215, 25, 32))

        current_feat_size = int(w * 0.024)
        feat_font = _load_font(current_feat_size, bold=False)
        feat_display = fix_arabic_text(feat)

        while draw.textlength(feat_display, font=feat_font) > (col_w - int(w * 0.07)) and current_feat_size > 14:
            current_feat_size -= 1
            feat_font = _load_font(current_feat_size, bold=False)

        draw.text(
            (dot_x - int(w * 0.02), cy_center),
            feat_display,
            fill=(240, 240, 240),
            font=feat_font,
            anchor="rm",
        )

    # 8. شريط التذييل
    footer_y = int(h * 0.91)
    draw.line([(w * 0.08, footer_y), (w * 0.92, footer_y)], fill=(50, 50, 55), width=1)

    p1 = company.get("phone1", "0924565333")
    p2 = company.get("phone2", "0914565333")
    slogan = "الحلول الجديدة لاستيراد وبيع كماليات السيارات"
    footer_text = f"📞 {p1}   |   📞 {p2}   |   ✨ {slogan}"

    draw.text((w / 2, h * 0.95), fix_arabic_text(footer_text), fill=(150, 150, 150), font=font_footer, anchor="mm")

    # التصدير
    out_name = f"AHL_Perfect_{uuid.uuid4()}.png"
    out_path = os.path.join(GENERATED_DIR, out_name)
    os.makedirs(GENERATED_DIR, exist_ok=True)

    final_image = Image.new("RGB", base.size, (15, 15, 18))
    final_image.paste(base, mask=base.split()[3])
    final_image.save(out_path, "PNG", quality=100)

    return out_path
