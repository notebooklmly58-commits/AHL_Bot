"""
محرك التصميم الهندسي المتطور - مطابقة جودة التصميم المرجعي الفاخر لشركة الحلول الجديدة.
"""
import os
import math
import uuid
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from config import TEMPLATES, OUTPUT_SIZES, FONTS_DIR, LOGO_DIR, GENERATED_DIR
from text_utils import shape_text

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """تحميل الخطوط الفاخرة المعتمدة في التصميم."""
    font_name = "Tajawal-Bold.ttf" if bold else "Tajawal-Regular.ttf"
    font_path = os.path.join(FONTS_DIR, font_name)
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
    # جلب مقاس النشر المختار
    w, h = OUTPUT_SIZES.get(size_key, (1080, 1080))
    
    # 1. إنشاء الخلفية المتدرجة (الفخامة الداكنة) بـ RGBA
    base = Image.new("RGBA", (w, h))
    top_color = (15, 15, 18, 255)     # أسود ملكي داكن جداً
    bottom_color = (35, 10, 12, 255)  # لمحة دائرية حمراء عميقة خافتة في الأسفل
    
    for y in range(h):
        ratio = y / h
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        for x in range(w):
            base.putpixel((x, y), (r, g, b, 255))

    draw = ImageDraw.Draw(base)

    # 2. تأثير التوهج الضوئي الخلفي (Neon Glow) لإبراز المنتج كأنه ثلاثي الأبعاد
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        [w * 0.15, h * 0.25, w * 0.85, h * 0.65],
        fill=(220, 30, 40, 28) # توهج أحمر رياضي خفيف ومحترف
    )
    glow = glow.filter(ImageFilter.GaussianBlur(w * 0.09))
    base.alpha_composite(glow)

    # 3. دمج شعار الشركة الفاخر (logo.png) من المجلد المحدد تلقائياً
    logo_path = os.path.join(LOGO_DIR, "logo.png")
    if os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            logo_w = int(w * 0.22)
            logo_h = int(logo_img.height * (logo_w / logo_img.width))
            logo_img = logo_img.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
            # وضع الشعار في أعلى اليمين أو الوسط بدقة هندسية
            base.paste(logo_img, (int(w * 0.06), int(h * 0.04)), logo_img)
        except Exception:
            pass

    # 4. معالجة وتثبيت صورة المنتج بالمنتصف مع رسم الظل الواقعي (Soft Shadow)
    if os.path.exists(product_image_path):
        p_img = Image.open(product_image_path).convert("RGBA")
        max_p_w, max_p_h = int(w * 0.70), int(h * 0.42)
        p_img.thumbnail((max_p_w, max_p_h), Image.Resampling.LANCZOS)
        
        px = int((w - p_img.width) / 2)
        py = int(h * 0.23)
        
        # الظل الواقعي أسفل المنتج
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sh_draw = ImageDraw.Draw(shadow)
        sh_draw.ellipse(
            [px + 30, py + p_img.height - 10, px + p_img.width - 30, py + p_img.height + 15],
            fill=(0, 0, 0, 160)
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(20))
        base.alpha_composite(shadow)
        
        # لصق المنتج
        base.paste(p_img, (px, py), p_img)

    # 5. كتابة البيانات الاحترافية وعناوين الخطوط العربية الفصحى الفخمة
    font_title = _load_font(int(w * 0.052), bold=True)
    font_promo = _load_font(int(w * 0.026), bold=False)
    font_price = _load_font(int(w * 0.034), bold=True)
    font_feat = _load_font(int(w * 0.028), bold=False)
    font_footer = _load_font(int(w * 0.024), bold=False)

    # اسم المنتج والسطر التسويقي في الثلث السفلي لتنظيم المساحة بصرياً
    text_y = int(h * 0.67)
    draw.text((w - int(w * 0.06), text_y), shape_text(product_name), fill=(255, 255, 255), font=font_title, anchor="rm")
    
    if promo_text:
        draw.text((w - int(w * 0.06), text_y + int(h * 0.055)), shape_text(promo_text), fill=(180, 180, 180), font=font_promo, anchor="rm")

    # 6. شارة السعر الذكية (Price Tag) المنفصلة بشكل جذاب
    if price:
        price_text = f"{price} د.ل" if "د.ل" not in price else price
        # رسم مستطيل انسيابي حاد الجوانب للسعر
        draw.rounded_rectangle([w * 0.06, text_y, w * 0.28, text_y + int(h * 0.055)], radius=8, fill=(210, 25, 35))
        draw.text((w * 0.17, text_y + int(h * 0.027)), shape_text(price_text), fill=(255, 255, 255), font=font_price, anchor="mm")

    # 7. شبكة كبسولات الميزات (Features Badges) - عمودين متناسقين تماماً
    feat_y_start = text_y + int(h * 0.09)
    col_w = int(w * 0.42)
    box_h = int(h * 0.045)

    for idx, feat in enumerate(features[:4]):
        col = idx % 2
        row = idx // 2
        
        # الحساب الدقيق للمواقع
        if col == 0:
            cx_center = int(w * 0.74)
        else:
            cx_center = int(w * 0.28)
            
        cy_center = feat_y_start + row * int(h * 0.06)
        
        # خلفية كبسولة الميزة الداكنة
        draw.rounded_rectangle(
            [cx_center - col_w//2, cy_center - box_h//2, cx_center + col_w//2, cy_center + box_h//2],
            radius=6, fill=(28, 28, 32)
        )
        # النقطة المضيئة الدائرية (أحمر الرياضي) كمؤشر جمالي للميزة
        dot_x = cx_center + col_w//2 - int(w * 0.03)
        draw.ellipse([dot_x - 5, cy_center - 5, dot_x + 5, cy_center + 5], fill=(210, 25, 35))
        
        # نص الميزة المصحح
        draw.text((dot_x - int(w * 0.02), cy_center), shape_text(feat), fill=(240, 240, 240), font=font_feat, anchor="rm")

    # 8. التذييل الفاخر (Footer) لبيانات التواصل والثقة بالشركة
    footer_y = int(h * 0.90)
    draw.line([(w * 0.06, footer_y), (w * 0.94, footer_y)], fill=(50, 50, 55), width=1)
    
    phone1 = company.get("phone1", "0924565333")
    phone2 = company.get("phone2", "0914565333")
    slogan = company.get("company_slogan", "لاستيراد وبيع كماليات السيارات")
    
    info_text = f"📞 {phone1}  |  📞 {phone2}  |  ✨ {slogan}"
    draw.text((w / 2, h * 0.945), shape_text(info_text), fill=(160, 160, 160), font=font_footer, anchor="mm")

    # حفظ الصورة بدقة فائقة كـ PNG لدعم الشفافية الكاملة والجودة
    out_name = f"AHL_Poster_{uuid.uuid4()}.png"
    out_path = os.path.join(GENERATED_DIR, out_name)
    
    final_image = Image.new("RGB", base.size, (15, 15, 18))
    final_image.paste(base, mask=base.split()[3])
    final_image.save(out_path, "PNG", quality=100)
    
    return out_path
