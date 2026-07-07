"""
إزالة خلفية صورة المنتج تلقائيًا باستخدام مكتبة rembg (مجانية بالكامل،
تعمل محليًا بدون أي API مدفوع).
"""
from rembg import remove
from PIL import Image, ImageFilter, ImageEnhance
import io


def remove_background(input_path: str, output_path: str) -> str:
    with open(input_path, "rb") as f:
        input_bytes = f.read()

    output_bytes = remove(input_bytes)

    img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    img = _auto_enhance(img)
    img.save(output_path, "PNG")
    return output_path


def _auto_enhance(img: Image.Image) -> Image.Image:
    """تحسين تلقائي للحدة والألوان والسطوع والتباين بدون تشويه النسب."""
    rgb = img.convert("RGB")

    rgb = ImageEnhance.Sharpness(rgb).enhance(1.3)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.08)
    rgb = ImageEnhance.Color(rgb).enhance(1.12)
    rgb = ImageEnhance.Brightness(rgb).enhance(1.03)
    rgb = rgb.filter(ImageFilter.SMOOTH_MORE)

    # نرجع الشفافية الأصلية بعد التحسين
    r, g, b = rgb.split()
    _, _, _, a = img.split()
    return Image.merge("RGBA", (r, g, b, a))
