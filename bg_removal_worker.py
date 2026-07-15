"""
هذا الملف يُنفَّذ بالكامل داخل عملية فرعية (subprocess) منعزلة عن عملية
البوت الرئيسية. أي ذاكرة يحجزها rembg/onnxruntime هنا تختفي تماماً مع
نظام التشغيل بمجرد انتهاء هذه العملية - بغض النظر عمّا كانت أي مكتبة
تحتفظ به داخلياً (arena، cache، أو أي شيء آخر).
"""
import io

from PIL import Image, ImageFilter, ImageEnhance


def process_image_in_subprocess(input_path: str, output_path: str, max_dimension: int) -> None:
    from rembg import remove, new_session

    session = new_session("u2netp")

    with open(input_path, "rb") as f:
        input_bytes = f.read()

    img_in = Image.open(io.BytesIO(input_bytes)).convert("RGB")
    if max(img_in.size) > max_dimension:
        img_in.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img_in.save(buf, format="PNG")
    img_in.close()
    resized_bytes = buf.getvalue()
    buf.close()

    output_bytes = remove(resized_bytes, session=session)

    img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    img = _auto_enhance(img)
    img.save(output_path, "PNG")
    img.close()


def _auto_enhance(img: Image.Image) -> Image.Image:
    rgb = img.convert("RGB")
    rgb = ImageEnhance.Sharpness(rgb).enhance(1.3)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.08)
    rgb = ImageEnhance.Color(rgb).enhance(1.12)
    rgb = ImageEnhance.Brightness(rgb).enhance(1.03)
    rgb = rgb.filter(ImageFilter.SMOOTH_MORE)
    r, g, b = rgb.split()
    _, _, _, a = img.split()
    result = Image.merge("RGBA", (r, g, b, a))
    rgb.close()
    return result
