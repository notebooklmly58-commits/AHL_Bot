"""
محرك التصميم المتطور لشركة الحلول الجديدة - مع ميزة التحميل التلقائي للخطوط الاحترافية
"""
import os
import math
import uuid
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from config import OUTPUT_SIZES, FONTS_DIR, LOGO_DIR, GENERATED_DIR
from text_utils import shape_text

def _download_font_if_missing(font_name: str, url: str):
    """تنزيل الخط تلقائياً إذا كان مجلدك فارغاً لمنع تشوه التصميم."""
    os.makedirs(FONTS_DIR, exist_ok=True)
    font_path = os.path.join(FONTS_DIR, font_name)
    if not os.path.exists(font_path):
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                with open(font_path, "wb") as f:
                    f.write(r.content)
        except Exception:
            pass

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """تحميل الخطوط الاحترافية وضمان وجودها تلقائياً."""
    if bold:
        _download_font_if_missing("Tajawal-Bold.ttf", "https://github.com/google/fonts/raw/main/ofl/tajawal/Tajawal-Bold.ttf")
        font_path = os.path.join(FONTS_DIR, "Tajawal-Bold.ttf")
    else:
        _download_font_if_missing("Tajawal-Regular.ttf", "https://github.com/google/fonts/raw/main/ofl/tajawal/Tajawal-Regular.ttf")
        font_path = os.path.join(FONTS_DIR, "Tajawal-Regular.ttf")

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
    # تحديد أبعاد اللوحة الإعلانية بدقة فائقة
    w, h = OUTPUT_SIZES.get(size_key, (1080, 1080))
    
    # 创建画布 (RGBA لدعم عمليات الدمج والتوهج البصري الناعم)
    base = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(base)

    # 1. رسم الخلفية المتدرجة الفاخرة ( Luxury Dark / طابع الوكالات )
    top_color = (13, 13, 15, 255)     # أسود فخم مخملي
    bottom_color = (26, 12, 14, 255)  # لمحة توهج رياضي أحمر داكن بالأسفل
    
    for y in range(h):
        ratio = y / h
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        for x in range(w):
            base.putpixel((x, y), (r, g, b, 255))

    # 2. تأثير هالة الضوء النيون خلف المنتج (Backlight Glow)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        [w * 0.18, h * 0.22, w * 0.82, h * 0.62],
        fill=(220, 25, 35, 30) # توهج رياضي أحمر مائل للشفافية
    )
    glow = glow.filter(ImageFilter.GaussianBlur(w * 0.08))
    base.alpha_composite(glow)

    # 3. وضع شعار شركة الحلول الجديدة الفاخر في الأعلى بالمنتصف بدقة هندسية
    logo_path = os.path.join(LOGO_DIR, "logo.png")
    if os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            logo_w = int(w * 0.20) # حجم متناسق غير ضخم
            logo_h = int(logo_img.height * (logo_w / logo_img.width))
            logo_img = logo_img.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            base.paste(logo_img, (int((w - logo_w) / 2), int(h * 0.05)), logo_img)
        except Exception:
            pass

    # 4. معالجة موضع وحجم صورة المنتج مع الظل السفلي ثلاثي الأبعاد
    if os.path.exists(product_image_path):
        p_img = Image.open(product_image_path).convert("RGBA")
        max_p_w, max_p_h = int(w * 0.68), int(h * 0.40)
        p_img.thumbnail((max_p_w, max_p_h), Image.Resampling.LANCZOS)
        
        px = int((w - p_img.width) / 2)
        py = int(h * 0.22)
        
        # الظل الناعم أسفل المنتج مباشرة ليعطي انطباعاً بالعمق والواقعية
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sh_draw = ImageDraw.Draw(shadow)
        sh_draw.ellipse(
            [px + 30, py + p_img.height - 12, px + p_img.width - 30, py + p_img.height + 12],
            fill=(0, 0, 0, 170)
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(18))
        base.alpha_composite(shadow)
        
        # دمج المنتج فوق الخلفية والظل
        base.paste(p_img, (px, py), p_img)

    # 5. تحميل مصفوفة الخطوط الاحترافية بدقة بكسل حادة ومحسوبة هندسياً
    font_title = _load_font(int(w * 0.046), bold=True)
    font_promo = _load_font(int(w * 0.024), bold=False)
    font_price = _load_font(int(w * 0.035), bold=True)
    font_feat = _load_font(int(w * 0.025), bold=False)
    font_footer = _load_font(int(w * 0.023), bold=False)

    text_y = int(h * 0.65)

    # اسم المنتج في الجهة اليمنى الفاخرة
    draw.text((w - int(w * 0.06), text_y), shape_text(product_name), fill=(255, 255, 255), font=font_title, anchor="rm")
    
    # السطر التسويقي الصغير الجذاب أسفله
    if promo_text:
        draw.text((w - int(w * 0.06), text_y + int(h * 0.052)), shape_text(promo_text), fill=(160, 160, 165), font=font_promo, anchor="rm")

    # 6. شارة السعر (Price Badge) المنفصلة في جهة اليسار المقابلة للاسم
    if price:
        price_text = f"{price} د.ل" if "د.ل" not in price else price
        # رسم الحاوية الانسيابية للسعر
        draw.rounded_rectangle([w * 0.06, text_y - 5, w * 0.26, text_y + int(h * 0.052)], radius=6, fill=(215, 25, 32))
        draw.text((w * 0.16, text_y + int(h * 0.023)), shape_text(price_text), fill=(255, 255, 255), font=font_price, anchor="mm")

    # 7. توزيع كبسولات المواصفات (Features Grid) - عمودين متوازيين بدقة رياضية متناهية
    feat_y_start = text_y + int(h * 0.10)
    col_w = int(w * 0.42)
    box_h = int(h * 0.046)

    for idx, feat in enumerate(features[:4]):
        if not feat: continue
        col = idx % 2
        row = idx // 2
        
        # الحساب الدقيق لمركز كل عمود (الأيمن والأيسر) لضمان عدم التداخل
        cx_center = int(w * 0.74) if col == 0 else int(w * 0.26)
        cy_center = feat_y_start + row * int(h * 0.062)
        
        # خلفية الكبسولة الداكنة الأنيقة
        draw.rounded_rectangle(
            [cx_center - col_w//2, cy_center - box_h//2, cx_center + col_w//2, cy_center + box_h//2],
            radius=6, fill=(24, 24, 27)
        )
        
        # النقطة الحمراء المضيئة ( Bullet Indicator )
        dot_x = cx_center + col_w//2 - int(w * 0.03)
        draw.ellipse([dot_x - 4, cy_center - 4, dot_x + 4, cy_center + 4], fill=(215, 25, 32))
        
        # نص المواصفات بعد إعادة التشكيل والاتجاه
        draw.text((dot_x - int(w * 0.02), cy_center), shape_text(feat), fill=(235, 235, 235), font=font_feat, anchor="rm")

    # 8. تذييل اللوحة الإعلانية (Footer) الذي يحمل الثقة وعلامة الشركة التجارية
    footer_y = int(h * 0.91)
    draw.line([(w * 0.06, footer_y), (w * 0.94, footer_y)], fill=(45, 45, 48), width=1)
    
    p1 = company.get("phone1", "0924565333")
    p2 = company.get("phone2", "0914565333")
    slogan = "الحلول الجديدة لاستيراد وبيع كماليات السيارات"
    
    footer_text = f"📞 {p1}   |   📞 {p2}   |   ✨ {slogan}"
    draw.text((w / 2, h * 0.95), shape_text(footer_text), fill=(150, 150, 150), font=font_footer, anchor="mm")

    # تصدير الملف النهائي بجودة رقمية صافية غير مضغوطة
    out_name = f"Perfect_AHL_{uuid.uuid4()}.png"
    out_path = os.path.join(GENERATED_DIR, out_name)
    
    final_image = Image.new("RGB", base.size, (13, 13, 15))
    final_image.paste(base, mask=base.split()[3])
    final_image.save(out_path, "PNG", quality=100)
    
    return out_path
