"""
محرك التصميم - يركّب البوستر النهائي تلقائيًا:
خلفية فاخرة + شعار + صورة المنتج بظل وانعكاس + نصوص + مواصفات + سعر + تذييل.
كل شي ديناميكي (المواقع والأحجام تتحسب تلقائيًا حسب مقاس الإخراج).
"""
import os
import math
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from config import TEMPLATES, OUTPUT_SIZES, FONTS_DIR, LOGO_DIR, GENERATED_DIR
from text_utils import shape_text, is_arabic


# ---------- أدوات الخطوط ----------

def _load_font(size: int, bold: bool = False, arabic: bool = False) -> ImageFont.FreeTypeFont:
    """
    يحاول تحميل خط عربي (Tajawal/Cairo) إن وُجد في assets/fonts,
    وإلا يرجع لخط لاتيني، وإلا يرجع لخط Pillow الافتراضي حتى لا يتوقف البرنامج.
    ضع ملفات الخطوط بنفسك في مجلد assets/fonts (اسمها بالضبط كما بالأسفل)
    لأنها لا يمكن تحميلها تلقائيًا بدون إنترنت وقت كتابة الكود.
    """
    candidates = []
    if arabic:
        candidates += ["Tajawal-Bold.ttf" if bold else "Tajawal-Regular.ttf"]
        candidates += ["Cairo-Bold.ttf" if bold else "Cairo-Regular.ttf"]
    candidates += ["Montserrat-Bold.ttf" if bold else "Montserrat-Regular.ttf"]
    candidates += ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]

    for name in candidates:
        path = os.path.join(FONTS_DIR, name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _font_for(text: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return _load_font(size, bold=bold, arabic=is_arabic(text))


def _draw_text_auto(draw, xy, text, max_width, size, fill, bold=False, align="center", font_obj=None):
    """
    يرسم نص مع تصغير تلقائي للخط إذا كان أطول من العرض المتاح (Adaptive font size),
    ويدعم العربي (تشكيل + اتجاه) والإنجليزي بنفس الدالة.
    """
    text = shape_text(text)
    font = font_obj or _font_for(text, size, bold=bold)
    while font.getlength(text) > max_width and size > 12:
        size -= 2
        font = _load_font(size, bold=bold, arabic=is_arabic(text))

    x, y = xy
    w = font.getlength(text)
    if align == "center":
        x = x - w / 2
    elif align == "right":
        x = x - w
    draw.text((x, y), text, font=font, fill=fill)
    return font


def _wrap_text(text, font, max_width):
    words = text.split(" ")
    lines, current = [], ""
    for word in words:
        trial = (current + " " + word).strip()
        if font.getlength(trial) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ---------- الخلفية ----------

def _make_background(size, palette):
    w, h = size
    bg = Image.new("RGB", size, palette["bg"])
    draw = ImageDraw.Draw(bg)

    # تدرج قطري خفيف من الزاوية العلوية
    top = Image.new("RGB", size, palette["bg"])
    bottom = Image.new("RGB", size, palette["bg2"])
    mask = Image.new("L", size)
    mask_draw = ImageDraw.Draw(mask)
    for y in range(h):
        val = int(255 * (y / h))
        mask_draw.line([(0, y), (w, y)], fill=val)
    bg = Image.composite(bottom, top, mask)
    draw = ImageDraw.Draw(bg, "RGBA")

    # أشرطة حمراء قطرية في الزوايا (نفس ستايل الهوية البصرية)
    accent = palette["accent"]
    stripe_w = int(w * 0.12)
    draw.polygon(
        [(w, 0), (w - stripe_w, 0), (w, h * 0.28), (w, 0)],
        fill=accent + (255,),
    )
    draw.polygon(
        [(0, h), (stripe_w, h), (0, h * 0.72)],
        fill=accent + (60,),
    )

    # خطوط سرعة خفيفة (Speed Lines) في الخلفية
    for i in range(6):
        y = int(h * (0.15 + i * 0.03))
        alpha = 25 - i * 3
        if alpha > 0:
            draw.line([(0, y), (w * 0.35, y)], fill=(255, 255, 255, alpha), width=2)

    # توهج خفيف خلف منطقة المنتج
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    cx, cy = w // 2, int(h * 0.42)
    radius = int(w * 0.42)
    glow_draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=accent + (55,),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius // 2))
    bg = Image.alpha_composite(bg.convert("RGBA"), glow)

    return bg.convert("RGB")


# ---------- المنتج (ظل + انعكاس) ----------

def _prepare_product(product_rgba: Image.Image, target_w: int) -> Image.Image:
    ratio = target_w / product_rgba.width
    target_h = int(product_rgba.height * ratio)
    product = product_rgba.resize((target_w, target_h), Image.LANCZOS)

    pad = int(target_h * 0.35)
    canvas = Image.new("RGBA", (target_w + 40, target_h + pad), (0, 0, 0, 0))
    canvas.paste(product, (20, 0), product)

    # الظل: نسخة سوداء من قناة الشفافية موضوعة أسفل المنتج ومموّهة
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    alpha = product.split()[3]
    shadow_shape = Image.new("RGBA", product.size, (0, 0, 0, 160))
    shadow_shape.putalpha(alpha.point(lambda p: int(p * 0.55)))
    shadow.paste(shadow_shape, (20, int(target_h * 0.06)), shadow_shape)
    shadow = shadow.filter(ImageFilter.GaussianBlur(target_h * 0.02 + 6))

    # الانعكاس: قلب المنتج رأسيًا وتخفيف شفافيته تدريجيًا
    reflection = ImageOps.flip(product)
    refl_alpha = reflection.split()[3].point(lambda p: int(p * 0.25))
    reflection.putalpha(refl_alpha)
    fade = Image.new("L", reflection.size, 0)
    fade_draw = ImageDraw.Draw(fade)
    for y in range(reflection.height):
        val = int(255 * (1 - y / reflection.height))
        fade_draw.line([(0, y), (reflection.width, y)], fill=val)
    combined_alpha = Image.composite(refl_alpha, Image.new("L", refl_alpha.size, 0), fade)
    reflection.putalpha(combined_alpha)

    final = Image.new("RGBA", (canvas.width, canvas.height + int(target_h * 0.4)), (0, 0, 0, 0))
    final.paste(shadow, (0, target_h), shadow)
    final.paste(reflection, (20, target_h + 5), reflection)
    final.paste(canvas, (0, 0), canvas)
    return final


# ---------- التذييل والشعار ----------

def _paste_logo(bg, template_size):
    w, h = template_size
    logo_path = None
    for name in os.listdir(LOGO_DIR) if os.path.exists(LOGO_DIR) else []:
        if name.lower().endswith((".png", ".jpg", ".jpeg")):
            logo_path = os.path.join(LOGO_DIR, name)
            break
    if not logo_path:
        return bg  # لا يوجد شعار مرفوع بعد - يتخطى بدون خطأ

    logo = Image.open(logo_path).convert("RGBA")
    logo_w = int(w * 0.32)
    ratio = logo_w / logo.width
    logo = logo.resize((logo_w, int(logo.height * ratio)), Image.LANCZOS)
    bg.paste(logo, (int((w - logo_w) / 2), int(h * 0.03)), logo)
    return bg


# ---------- الدالة الرئيسية ----------

def generate_poster(
    product_image_path: str,
    product_name: str,
    price: str,
    features: list,
    socket: str,
    promo_text: str,
    company: dict,
    template_key: str = "luxury_black",
    size_key: str = "instagram_portrait",
) -> str:
    palette = TEMPLATES.get(template_key, TEMPLATES["luxury_black"])
    size = OUTPUT_SIZES.get(size_key, OUTPUT_SIZES["instagram_portrait"])
    w, h = size

    bg = _make_background(size, palette).convert("RGBA")
    bg = _paste_logo(bg, size)

    draw = ImageDraw.Draw(bg, "RGBA")

    # اسم الشركة أسفل الشعار
    _draw_text_auto(
        draw, (w / 2, h * 0.17), company["company_name"], w * 0.85,
        size=int(w * 0.045), fill=palette["text"], bold=True,
    )
    if company.get("company_slogan"):
        _draw_text_auto(
            draw, (w / 2, h * 0.205), company["company_slogan"], w * 0.8,
            size=int(w * 0.022), fill=palette["secondary"],
        )

    # صورة المنتج مع الظل والانعكاس
    product_img = Image.open(product_image_path).convert("RGBA")
    product_target_w = int(w * 0.62)
    product_layer = _prepare_product(product_img, product_target_w)
    px = int((w - product_layer.width) / 2)
    py = int(h * 0.24)
    bg.paste(product_layer, (px, py), product_layer)
    draw = ImageDraw.Draw(bg, "RGBA")

    # شريط العرض الترويجي (ركن علوي)
    if promo_text:
        ribbon_font = _font_for(promo_text, int(w * 0.03), bold=True)
        ribbon_text = shape_text(promo_text)
        text_w = ribbon_font.getlength(ribbon_text)
        pad_x = 24
        rx1, ry1 = w * 0.03, h * 0.03
        rx2, ry2 = rx1 + text_w + pad_x * 2, ry1 + int(w * 0.05)
        draw.rounded_rectangle([rx1, ry1, rx2, ry2], radius=8, fill=palette["accent"] + (255,))
        draw.text((rx1 + pad_x, ry1 + 6), ribbon_text, font=ribbon_font, fill=(255, 255, 255))

    content_top = py + product_layer.height - int(h * 0.05)
    content_top = max(content_top, int(h * 0.58))

    # اسم المنتج
    _draw_text_auto(
        draw, (w / 2, content_top), product_name, w * 0.9,
        size=int(w * 0.055), fill=palette["text"], bold=True,
    )

    # السعر (كبسولة حمراء)
    if price:
        price_text = shape_text(f"{price}")
        price_font = _font_for(price_text, int(w * 0.05), bold=True)
        text_w = price_font.getlength(price_text)
        cx = w / 2
        cy = content_top + int(h * 0.065)
        pad_x, pad_y = 30, 14
        draw.rounded_rectangle(
            [cx - text_w / 2 - pad_x, cy - pad_y, cx + text_w / 2 + pad_x, cy + int(w * 0.05) + pad_y],
            radius=14, fill=palette["accent"] + (255,),
        )
        draw.text((cx - text_w / 2, cy), price_text, font=price_font, fill=(255, 255, 255))
        content_top = cy + int(w * 0.05) + pad_y + int(h * 0.02)
    else:
        content_top += int(h * 0.02)

    # المواصفات (Features) - أعمدة تلقائية
    feat_font = _font_for(" ".join(features) if features else "A", int(w * 0.026))
    line_h = int(w * 0.045)
    start_y = content_top + int(h * 0.015)
    max_line_w = w * 0.42
    col1_x = w * 0.28
    col2_x = w * 0.72
    for idx, feat in enumerate(features[:8]):
        col_x = col1_x if idx % 2 == 0 else col2_x
        row = idx // 2
        bullet_y = start_y + row * line_h
        draw.ellipse(
            [col_x - max_line_w / 2 - 22, bullet_y + 6, col_x - max_line_w / 2 - 10, bullet_y + 18],
            fill=palette["accent"] + (255,),
        )
        _draw_text_auto(
            draw, (col_x, bullet_y), feat, max_line_w, size=int(w * 0.026),
            fill=palette["text"], align="center", font_obj=feat_font,
        )

    feature_rows = math.ceil(min(len(features), 8) / 2)
    after_features_y = start_y + feature_rows * line_h + int(h * 0.02)

    # التوافق (Compatibility)
    if socket:
        _draw_text_auto(
            draw, (w / 2, after_features_y), f"Compatible: {socket}", w * 0.85,
            size=int(w * 0.026), fill=palette["secondary"],
        )
        after_features_y += int(h * 0.035)

    # التذييل: أرقام التواصل + العنوان
    footer_y = h * 0.92
    draw.line([(w * 0.1, footer_y - 20), (w * 0.9, footer_y - 20)], fill=palette["accent"] + (180,), width=2)

    contacts = " | ".join(filter(None, [company.get("phone1"), company.get("phone2")]))
    if contacts:
        _draw_text_auto(
            draw, (w / 2, footer_y), contacts, w * 0.9,
            size=int(w * 0.028), fill=palette["text"], bold=True,
        )
    if company.get("address"):
        _draw_text_auto(
            draw, (w / 2, footer_y + int(h * 0.03)), company["address"], w * 0.9,
            size=int(w * 0.02), fill=palette["secondary"],
        )

    out_path = os.path.join(GENERATED_DIR, f"poster_{template_key}_{size_key}.png")
    bg.convert("RGB").save(out_path, "PNG", dpi=(300, 300))
    return out_path
