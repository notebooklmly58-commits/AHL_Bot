"""
محرك التصميم الهندسي الاحترافي والمحكم - شركة الحلول الجديدة.
نسخة مُصححة: تعالج مشكلة الحروف/الأرقام المشوهة (مربعات فارغة) الناتجة عن
فشل تحميل خط Tajawal، وتُصلح ترتيب النص العربي المختلط بالأرقام عبر خوارزمية bidi
الرسمية بدلاً من العكس اليدوي، وتضيف تناسقاً بصرياً للوقو.
"""
import os
import uuid
import gc
import ctypes
import logging
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, features
from config import OUTPUT_SIZES, FONTS_DIR, LOGO_DIR, GENERATED_DIR
import arabic_reshaper
from bidi.algorithm import get_display

try:
    _libc = ctypes.CDLL("libc.so.6")
except Exception:
    _libc = None


def _release_memory_to_os():
    """إجبار نظام التشغيل على استرجاع الذاكرة المُحررة فعلياً (Linux فقط).
    نفس الآلية المستخدمة في background_removal.py لحل مشكلة تراكم استهلاك
    الذاكرة على Railway مع كل صورة/بوستر جديد."""
    gc.collect()
    if _libc:
        try:
            _libc.malloc_trim(0)
        except Exception:
            pass

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# محرك تنسيق النص العربي (الحل الجذري)
# ------------------------------------------------------------------
# المشكلة الحقيقية: مكتبة arabic_reshaper تحوّل كل حرف إلى رمز يونيكود
# من نطاق "Presentation Forms" الخاص بالشكل المتصل للحرف. لكن ليست كل
# الخطوط (ومنها Tajawal) تحتوي فعلياً على رسمة (Glyph) لكل رمز من هذه
# الرموز داخل ملف الخط - فتظهر مربعات فارغة لبعض الحروف تحديداً (خصوصاً
# حروف الربط مثل "لا") بينما تظهر حروف أخرى بشكل سليم. هذا يفسّر ظهور
# مربعات متفرقة وسط كلام يبدو صحيحاً جزئياً.
#
# الحل الصحيح والمعتمد عالمياً: استخدام محرك التنضيد RAQM المدمج داخل
# مكتبة Pillow نفسها، والذي يقوم بعملية "التشكيل" (Shaping) الحقيقية
# عبر جداول OpenType الموجودة داخل ملف الخط مباشرة (تماماً كما تعرض
# المتصفحات وبرامج التصميم النص العربي)، بدل تخمين الشكل يدوياً. هذا
# يلغي الحاجة لأي "حيلة" برمجية، ويعمل بشكل صحيح 100% مع أي خط عربي
# سليم مثل Tajawal.
RAQM_AVAILABLE = features.check("raqm")
if not RAQM_AVAILABLE:
    logger.error(
        "مكتبة Pillow المثبتة لا تدعم RAQM. سيتم استخدام المسار البديل "
        "المُصحح (إعداد use_unshaped_instead_of_isolated) الذي يعمل بشكل "
        "سليم مع خط Tajawal دون الحاجة لـ RAQM إطلاقاً."
    )

# إعداد موثّق رسمياً من مكتبة arabic_reshaper نفسها لحل مشكلة الحروف
# الناقصة تحديداً: بعض الخطوط (ومنها Tajawal) لا تحتوي على "الشكل المعزول"
# (Isolated Form) لبعض الحروف الذي يستخدمه الإعداد الافتراضي للمكتبة،
# فتظهر مربعات فارغة مكان تلك الحروف تحديداً (كما في الصور التي أرسلتها).
# تفعيل use_unshaped_instead_of_isolated يجعل المكتبة تستخدم الشكل الأساسي
# للحرف بدل الشكل المعزول المفقود، وهذا يحل المشكلة نهائياً بغض النظر عن
# توفر RAQM من عدمه.
_reshaper = arabic_reshaper.ArabicReshaper(
    configuration={"use_unshaped_instead_of_isolated": True, "delete_harakat": True}
)

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
    layout_engine = ImageFont.Layout.RAQM if RAQM_AVAILABLE else ImageFont.Layout.BASIC

    # 1) الخط المرفوع يدوياً داخل المشروع (الأكثر ثباتاً وموصى به)
    if os.path.exists(font_path) and os.path.getsize(font_path) > _MIN_VALID_FONT_BYTES:
        try:
            font = ImageFont.truetype(font_path, size, layout_engine=layout_engine)
            _font_cache[cache_key] = font
            return font
        except Exception as e:
            logger.warning(f"ملف الخط تالف ({font_path}): {e}")

    # 2) محاولة تنزيل تلقائي كخطة بديلة فقط
    _download_font_if_missing()
    if os.path.exists(font_path) and os.path.getsize(font_path) > _MIN_VALID_FONT_BYTES:
        try:
            font = ImageFont.truetype(font_path, size, layout_engine=layout_engine)
            _font_cache[cache_key] = font
            return font
        except Exception:
            pass

    # 3) خط احتياطي من النظام (لا يدعم العربية بشكل مثالي لكنه أفضل من التوقف الكامل)
    for sys_font in _SYSTEM_FALLBACKS:
        if os.path.exists(sys_font):
            try:
                font = ImageFont.truetype(sys_font, size, layout_engine=layout_engine)
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


def get_font_diagnostics() -> dict:
    """تشخيص فوري وواضح لحالة ملفات الخط - ليُستخدم في أمر تشخيصي داخل
    البوت نفسه، فلا يحتاج المستخدم لفتح Railway أو مراجعة الأكواد."""
    os.makedirs(FONTS_DIR, exist_ok=True)
    results = {"fonts_dir": FONTS_DIR, "raqm_available": RAQM_AVAILABLE, "files": {}}
    for name in ("Tajawal-Bold.ttf", "Tajawal-Regular.ttf"):
        path = os.path.join(FONTS_DIR, name)
        exists = os.path.exists(path)
        size = os.path.getsize(path) if exists else 0
        results["files"][name] = {
            "path": path,
            "exists": exists,
            "size_kb": round(size / 1024, 1),
            "valid": exists and size > _MIN_VALID_FONT_BYTES,
        }
    return results


def fonts_are_ready() -> bool:
    diag = get_font_diagnostics()
    return all(f["valid"] for f in diag["files"].values())



def fix_arabic_text(text: str) -> str:
    """تجهيز النص العربي للرسم.
    - إذا كان RAQM متوفراً: لا حاجة لأي معالجة يدوية، RAQM يتولى كل شيء.
    - إذا لم يتوفر RAQM (حالة سيرفرك حالياً): نستخدم إعادة التشكيل مع
      إعداد use_unshaped_instead_of_isolated المُصحح خصيصاً ليعمل بشكل
      سليم مع خطوط مثل Tajawal، مع ترتيب bidi الرسمي للنص المختلط."""
    if not text:
        return ""
    if RAQM_AVAILABLE:
        return text
    reshaped = _reshaper.reshape(text)
    return get_display(reshaped)


def draw_rtl_text(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, anchor: str):
    """رسم نص عربي بالاتجاه الصحيح من اليمين لليسار.
    يعتمد على RAQM (direction/language) عند توفره وهو الحل الجذري والدقيق،
    ويرجع تلقائياً للطريقة اليدوية القديمة فقط إذا كانت بيئة السيرفر لا
    تحتوي على دعم RAQM ضمن مكتبة Pillow المثبتة."""
    prepared_text = fix_arabic_text(text)
    if RAQM_AVAILABLE:
        try:
            draw.text(xy, prepared_text, font=font, fill=fill, anchor=anchor, direction="rtl", language="ar")
            return
        except Exception as e:
            logger.warning(f"فشل الرسم عبر RAQM، سيتم استخدام الطريقة الاحتياطية: {e}")
    draw.text(xy, prepared_text, font=font, fill=fill, anchor=anchor)


def measure_rtl_text(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    """قياس عرض النص العربي بنفس طريقة الرسم بالضبط لضمان توافق القياس مع
    الشكل الفعلي المرسوم (مهم لحسابات تصغير حجم الخط لمنع القطع)."""
    prepared_text = fix_arabic_text(text)
    if RAQM_AVAILABLE:
        try:
            bbox = draw.textbbox((0, 0), prepared_text, font=font, direction="rtl", language="ar")
            return bbox[2] - bbox[0]
        except Exception:
            pass
    return draw.textlength(prepared_text, font=font)


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

    text_y = int(h * 0.65)

    # اسم المنتج (يمين)
    if product_name and product_name.strip():
        draw_rtl_text(
            draw,
            (w - int(w * 0.08), text_y),
            product_name.strip(),
            font=font_title,
            fill=(255, 255, 255),
            anchor="rm",
        )

    # السطر التسويقي
    if promo_text and promo_text.strip():
        draw_rtl_text(
            draw,
            (w - int(w * 0.08), text_y + int(h * 0.055)),
            promo_text.strip(),
            font=font_promo,
            fill=(170, 170, 175),
            anchor="rm",
        )

    # 6. بطاقة السعر (يسار)
    if price and price.strip():
        clean_price = price.replace("د.ل", "").strip()
        price_display = f"{clean_price} د.ل"
        draw.rounded_rectangle(
            [w * 0.08, text_y - 5, w * 0.28, text_y + int(h * 0.055)], radius=8, fill=(215, 25, 32)
        )
        draw_rtl_text(
            draw,
            (w * 0.18, text_y + int(h * 0.025)),
            price_display,
            font=font_price,
            fill=(255, 255, 255),
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

        while measure_rtl_text(draw, feat, feat_font) > (col_w - int(w * 0.07)) and current_feat_size > 14:
            current_feat_size -= 1
            feat_font = _load_font(current_feat_size, bold=False)

        draw_rtl_text(
            draw,
            (dot_x - int(w * 0.02), cy_center),
            feat,
            font=feat_font,
            fill=(240, 240, 240),
            anchor="rm",
        )

    # 8. شريط التذييل - أوضح وأكبر، بسطرين منفصلين لسهولة القراءة
    footer_line_y = int(h * 0.875)
    draw.line([(w * 0.08, footer_line_y), (w * 0.92, footer_line_y)], fill=(60, 60, 66), width=1)

    font_footer_name = _load_font(int(w * 0.026), bold=True)
    font_footer_phone = _load_font(int(w * 0.023), bold=False)

    company_name = company.get("company_name") or company.get("name") or "شركة الحلول الجديدة"
    slogan = company.get("company_slogan") or company.get("slogan") or "لاستيراد وبيع كماليات السيارات"

    # السطر الأول: اسم الشركة بارز وواضح
    draw_rtl_text(
        draw,
        (w / 2, h * 0.915),
        f"{company_name} {slogan}",
        font=font_footer_name,
        fill=(235, 235, 238),
        anchor="mm",
    )

    # السطر الثاني: أرقام الهواتف بحجم أكبر ووضوح أعلى
    p1 = company.get("phone1", "0924565333")
    p2 = company.get("phone2", "0914565333")
    phone_text = f"📞 {p1}   |   📞 {p2}"
    draw_rtl_text(
        draw,
        (w / 2, h * 0.955),
        phone_text,
        font=font_footer_phone,
        fill=(215, 25, 32),
        anchor="mm",
    )

    # التصدير
    out_name = f"AHL_Perfect_{uuid.uuid4()}.png"
    out_path = os.path.join(GENERATED_DIR, out_name)
    os.makedirs(GENERATED_DIR, exist_ok=True)

    final_image = Image.new("RGB", base.size, (15, 15, 18))
    final_image.paste(base, mask=base.split()[3])
    final_image.save(out_path, "PNG", quality=100)

    # إغلاق الصور الوسيطة الكبيرة (القماشة الأساسية بحجم البوستر الكامل)
    # صراحة، ثم إجبار نظام التشغيل على استرجاع الذاكرة فعلياً - هذا يمنع
    # تراكم استهلاك الذاكرة عبر توليد بوسترات متعددة في نفس الجلسة.
    final_image.close()
    base.close()
    del final_image, base
    _release_memory_to_os()

    return out_path
