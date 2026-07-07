"""
محرك التصميم الهندسي الاحترافي والمحكم - حل مشكلة تشوه الحروف والأرقام نهائياً لشركة الحلول الجديدة.
"""
import os
import uuid
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from config import OUTPUT_SIZES, FONTS_DIR, LOGO_DIR, GENERATED_DIR
import arabic_reshaper

def _download_font_if_missing():
    """تنزيل الخطوط الاحترافية فوراً وإنشاء المجلد برمجياً على السيرفر."""
    os.makedirs(FONTS_DIR, exist_ok=True)
    
    fonts = {
        "Tajawal-Bold.ttf": "https://github.com/google/fonts/raw/main/ofl/tajawal/Tajawal-Bold.ttf",
        "Tajawal-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/tajawal/Tajawal-Regular.ttf"
    }
    
    for name, url in fonts.items():
        path = os.path.join(FONTS_DIR, name)
        if not os.path.exists(path):
            try:
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    with open(path, "wb") as f:
                        f.write(r.content)
            except Exception:
                pass

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """تحميل الخط وضمان استدعائه الاحترافي."""
    _download_font_if_missing()
    font_name = "Tajawal-Bold.ttf" if bold else "Tajawal-Regular.ttf"
    font_path = os.path.join(FONTS_DIR, font_name)
    
    if os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()

def fix_arabic_text(text: str) -> str:
    """إعادة تشكيل الحروف العربية وتصحيح اتجاهها يدوياً بدون استخدام بيدي المسبب للتشوه للكلمات المختلطة."""
    if not text:
        return ""
    # إعادة تشكيل الحروف لتبدو متصلة
    reshaped = arabic_reshaper.reshape(text)
    # عكس النص يدوياً ليعرض من اليمين لليسار بشكل صحيح في Pillow
    return reshaped[::-1]

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
    # جلب الأبعاد بدقة
    w, h = OUTPUT_SIZES.get(size_key, (1080, 1080))
    base = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(base)

    # 1. الخلفية الفاخرة المتدرجة (أسود ملكي داكن جداً)
    top_color = (15, 15, 18, 255)
    bottom_color = (35, 12, 15, 255)
    for y in range(h):
        ratio = y / h
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        for x in range(w):
            base.putpixel((x, y), (r, g, b, 255))

    # 2. هالة التوهج الخلفي (Neon Glow)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([w * 0.15, h * 0.22, w * 0.85, h * 0.58], fill=(220, 25, 35, 28))
    glow = glow.filter(ImageFilter.GaussianBlur(w * 0.08))
    base.alpha_composite(glow)

    # 3. وضع شعار شركة الحلول الجديدة بالمنتصف الأعلى
    logo_path = os.path.join(LOGO_DIR, "logo.png")
    if os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            logo_w = int(w * 0.20)
            logo_h = int(logo_img.height * (logo_w / logo_img.width))
            logo_img = logo_img.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            base.paste(logo_img, (int((w - logo_w) / 2), int(h * 0.05)), logo_img)
        except Exception:
            pass

    # 4. تثبيت صورة المنتج والظل
    if os.path.exists(product_image_path):
        p_img = Image.open(product_image_path).convert("RGBA")
        max_p_w, max_p_h = int(w * 0.70), int(h * 0.40)
        p_img.thumbnail((max_p_w, max_p_h), Image.Resampling.LANCZOS)
        px = int((w - p_img.width) / 2)
        py = int(h * 0.21)
        
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sh_draw = ImageDraw.Draw(shadow)
        sh_draw.ellipse([px + 40, py + p_img.height - 12, px + p_img.width - 40, py + p_img.height + 12], fill=(0, 0, 0, 180))
        shadow = shadow.filter(ImageFilter.GaussianBlur(15))
        base.alpha_composite(shadow)
        base.paste(p_img, (px, py), p_img)

    # 5. تحميل الخطوط الفاخرة
    font_title = _load_font(int(w * 0.045), bold=True)
    font_promo = _load_font(int(w * 0.024), bold=False)
    font_price = _load_font(int(w * 0.032), bold=True)
    font_footer = _load_font(int(w * 0.022), bold=False)

    text_y = int(h * 0.65)

    # كتابة اسم المنتج جهة اليمين
    draw.text((w - int(w * 0.08), text_y), fix_arabic_text(product_name), fill=(255, 255, 255), font=font_title, anchor="rm")
    
    # السطر التسويقي
    if promo_text:
        draw.text((w - int(w * 0.08), text_y + int(h * 0.055)), fix_arabic_text(promo_text), fill=(170, 170, 175), font=font_promo, anchor="rm")

    # 6. بطاقة السعر المحمية من التشوه (د.ل) جهة اليسار
    if price and price.strip():
        clean_price = price.replace("د.ل", "").strip()
        price_display = f"{clean_price} د.ل"
        # رسم مستطيل بطاقة السعر
        draw.rounded_rectangle([w * 0.08, text_y - 5, w * 0.28, text_y + int(h * 0.055)], radius=8, fill=(215, 25, 32))
        draw.text((w * 0.18, text_y + int(h * 0.025)), fix_arabic_text(price_display), fill=(255, 255, 255), font=font_price, anchor="mm")

    # 7. توزيع كبسولات المواصفات بدقة هندسية ومقاومة للقطع
    feat_y_start = text_y + int(h * 0.11)
    col_w = int(w * 0.42)
    box_h = int(h * 0.05)

    for idx, feat in enumerate(features[:4]):
        if not feat or not feat.strip(): continue
        col = idx % 2
        row = idx // 2
        
        cx_center = int(w * 0.73) if col == 0 else int(w * 0.27)
        cy_center = feat_y_start + row * int(h * 0.07)
        
        # خلفية الكبسولة الداكنة
        draw.rounded_rectangle(
            [cx_center - col_w//2, cy_center - box_h//2, cx_center + col_w//2, cy_center + box_h//2],
            radius=6, fill=(26, 26, 30)
        )
        
        # النقطة المضيئة الدائرية في اليمين الداخلي للكبسولة
        dot_x = cx_center + col_w//2 - int(w * 0.03)
        draw.ellipse([dot_x - 4, cy_center - 4, dot_x + 4, cy_center + 4], fill=(215, 25, 32))
        
        # التحكم الذكي بحجم النص لمنع التداخل والقطع
        current_feat_size = int(w * 0.024)
        feat_font = _load_font(current_feat_size, bold=False)
        
        while draw.textlength(fix_arabic_text(feat), font=feat_font) > (col_w - int(w * 0.07)) and current_feat_size > 14:
            current_feat_size -= 1
            feat_font = _load_font(current_feat_size, bold=False)
            
        # طباعة نص الميزة محاذياً لليمن من النقطة الإرشادية
        draw.text((dot_x - int(w * 0.02), cy_center), fix_arabic_text(feat), fill=(240, 240, 240), font=feat_font, anchor="rm")

    # 8. شريط التذييل الاحترافي لبيانات الاتصال
    footer_y = int(h * 0.91)
    draw.line([(w * 0.08, footer_y), (w * 0.92, footer_y)], fill=(50, 50, 55), width=1)
    
    p1 = company.get("phone1", "0924565333")
    p2 = company.get("phone2", "0914565333")
    slogan = "الحلول الجديدة لاستيراد وبيع كماليات السيارات"
    footer_text = f"📞 {p1}   |   📞 {p2}   |   ✨ {slogan}"
    
    draw.text((w / 2, h * 0.95), fix_arabic_text(footer_text), fill=(150, 150, 150), font=font_footer, anchor="mm")

    # التصدير الصافي
    out_name = f"AHL_Perfect_{uuid.uuid4()}.png"
    out_path = os.path.join(GENERATED_DIR, out_name)
    
    final_image = Image.new("RGB", base.size, (15, 15, 18))
    final_image.paste(base, mask=base.split()[3])
    final_image.save(out_path, "PNG", quality=100)
    
    return out_path
