"""
إزالة خلفية صورة المنتج تلقائيًا باستخدام مكتبة rembg (مجانية بالكامل،
تعمل محليًا بدون أي API مدفوع). نستخدم نموذج خفيف (u2netp) لتقليل
استهلاك الذاكرة والوقت على سيرفرات الاستضافة المجانية.
"""
from rembg import remove, new_session
from PIL import Image, ImageFilter, ImageEnhance
import io

_session = new_session("u2netp")


def remove_background(input_path: str, output_path: str) -> str:
    with open(input_path, "rb") as f:
        input_bytes = f.read()

    output_bytes = remove(input_bytes, session=_session)

    img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    img = _auto_enhance(img)
    img.save(output_path, "PNG")
    return output_path


def _auto_enhance(img: Image.Image) -> Image.Image:
    rgb = img.convert("RGB")

    rgb = ImageEnhance.Sharpness(rgb).enhance(1.3)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.08)
    rgb = ImageEnhance.Color(rgb).enhance(1.12)
    rgb = ImageEnhance.Brightness(rgb).enhance(1.03)
    rgb = rgb.filter(ImageFilter.SMOOTH_MORE)

    r, g, b = rgb.split()
    _, _, _, a = img.split()
    return Image.merge("RGBA", (r, g, b, a))
