"""
محرك التصميم الهندسي المتطور لمطابقة جودة التصميم المرجعي الفاخر وتفادي أخطاء الخطوط.
"""
import os
import math
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from config import TEMPLATES, OUTPUT_SIZES, FONTS_DIR, GENERATED_DIR
from text_utils import shape_text

def _download_font_if_missing():
    """إذا كان مجلد الخطوط فارغاً، يجلب الخط تلقائياً من الإنترنت لتفادي المربعات المشوهة."""
    font_path = os.path.join(FONTS_DIR, "Tajawal-Bold.ttf")
    if not os.path.exists(font_path):
        try:
            url = "https://github.com/google/fonts/raw/main/ofl/tajawal/Tajawal-Bold.ttf"
            r = requests.get(url, timeout=10)
            with open(font_path, "wb") as f:
                f.write(r.content)
        except:
            pass

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    _download_font_if_missing()
    font_path = os.path.join(FONTS_DIR, "Tajawal-Bold.ttf")
    if os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()

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
    palette = TEMPLATES.get(template_key, TEMPLATES["luxury_dark"])
    w, h = OUTPUT_SIZES.get(size_key, (1080, 1080))

    # 1. إنشاء الخلفية المتدرجة الفاخرة (Gradient)
    base = Image.new("RGBA", (w, h))
    top_color = palette["bg_start"]
    bottom_color = palette["bg_end"]
    
    # رسم التدرج التلقائي
    for y in range(h):
        ratio = y / h
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        for x in range(w):
            base.putpixel((x, y), (r, g, b, 255))

    draw = ImageDraw.Draw(base)

    # 2. إضافة توهج خلفية النيون (Glow Efect) خلف المنتج لإبراز جودته وفخامته
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        [w * 0.2, h * 0.25, w * 0.8, h * 0.65],
        fill=palette["accent"] + (35,)
    )
    glow = glow.filter(ImageFilter.GaussianBlur(w * 0.08))
    base.alpha_composite(glow)

    # 3. معالجة ورسم صورة المنتج مدمجاً بالكامل بالوسط
    if os.path.exists(product_image_path):
        p_img = Image.open(product_image_path).convert("RGBA")
        max_p_w, max_p_h = int(w * 0.65), int(h * 0.4)
        p_img.thumbnail((max_p_w, max_p_h), Image.Resampling.LANCZOS)
        
        # موقع وضع المنتج بالمنتصف العلوي المهيأ
        px = int((w - p_img.width) / 2)
        py = int(h * 0.25)
        
        # رسم ظل سفلي ناعم للمنتج ليعطي طابع الواقعية الفاخرة
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sh_draw = ImageDraw.Draw(shadow)
        sh_draw.ellipse(
            [px + 20, py + p_img.height - 15, px + p_img.width - 20, py + p_img.height + 15],
            fill=(0, 0, 0, 140)
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(15))
        base.alpha_composite(shadow)
        base.paste(p_img, (px, py), p_img)

    # 4. كتابة النصوص العلوية (اسم المنتج الفخم والعلامة التجارية)
    title_font = _load_font(int(w * 0.048))
    promo_font = _load_font(int(w * 0.028))
    
    # اسم الشركة كـ Badge صغير في الأعلى
    comp_font = _load_font(int(w * 0.024))
    c_text = shape_text(company.get("company_name", ""))
    draw.rounded_rectangle([w*0.35, h*0.03, w*0.65, h*0.07], radius=10, fill=palette["badge_bg"])
    draw.text((w/2, h*0.05), c_text, fill=palette["accent"], font=comp_font, anchor="mm")

    # اسم المنتج والسطر الترويجي
    draw.text((w/2, h*0.13), shape_text(product_name), fill=palette["text"], font=title_font, anchor="mm")
    if promo_text:
        draw.text((w/2, h*0.19), shape_text(promo_text), fill=palette["secondary"], font=promo_font, anchor="mm")

    # 5. السعر بشكل بطاقة دائرية لافتة للنظر (أحمر أو ذهبي)
    if price:
        price_font = _load_font(int(w * 0.032))
        p_text = shape_text(price)
        draw.rounded_rectangle([w*0.05, h*0.11, w*0.22, h*0.16], radius=15, fill=palette["accent"])
        draw.text((w*0.135, h*0.135), p_text, fill=(255, 255, 255), font=price_font, anchor="mm")

    # 6. رسم جدول المميزات السفلي (تخطيط عمودين احترافي مطابق للمرجع)
    feat_font = _load_font(int(w * 0.028))
    start_y = int(h * 0.68)
    col_width = w * 0.42
    
    for idx, feat in enumerate(features[:4]):
        col = idx % 2
        row = idx // 2
        
        # حساب المواقع الهندسية للعمودين
        cx = w * 0.28 if col == 0 else w * 0.72
        cy = start_y + row * int(h * 0.08)
        
        # رسم بادج خلفية الميزة
        draw.rounded_rectangle([cx - col_width/2, cy - h*0.03, cx + col_width/2, cy + h*0.03], radius=12, fill=palette["badge_bg"])
        
        # رسم أيقونة برمجية دائرية ملونة ومضيئة تحاكي مميزات (السطوع والتركيب والضمان)
        icon_x = cx + col_width/2 - w*0.04
        draw.ellipse([icon_x - 8, cy - 8, icon_x + 8, cy + 8], fill=palette["accent"])
        
        # نص الميزة مصحح وموجه لليمين
        draw.text((icon_x - w*0.03, cy), shape_text(feat), fill=palette["text"], font=feat_font, anchor="rm")

    # 7. الشريط السفلي النهائي (Footer) للتواصل والثقة
    footer_y = int(h * 0.91)
    draw.line([(w * 0.08, footer_y), (w * 0.92, footer_y)], fill=palette["secondary"] + (50,), width=1)
    
    footer_font = _load_font(int(w * 0.026))
    contacts = f"📞 {company.get('phone1','')}   |   📞 {company.get('phone2','')}"
    draw.text((w/2, h * 0.95), shape_text(contacts), fill=palette["secondary"], font=footer_font, anchor="mm")

    out_name = f"final_poster_{uuid.uuid4()}.png"
    out_path = os.path.join(GENERATED_DIR, out_name)
    base.convert("RGB").save(out_path, "JPEG", quality=95)
    return out_path
