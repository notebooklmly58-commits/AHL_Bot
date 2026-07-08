"""
إزالة خلفية صورة المنتج تلقائيًا باستخدام مكتبة rembg (مجانية بالكامل،
تعمل محليًا بدون أي API مدفوع). نستخدم نموذج خفيف (u2netp) لتقليل
استهلاك الذاكرة والوقت على سيرفرات الاستضافة المجانية.

نسخة مُصححة لحل مشكلة "Ran Out of Memory" على Railway:
1. تصغير الصورة قبل معالجتها بالذكاء الاصطناعي (كانت تُعالج بدقتها
   الكاملة كما ترسلها كاميرا الهاتف، وقد تصل لـ 3000-4000 بكسل، رغم أن
   أقصى حجم يُستخدم في البوستر النهائي لا يتجاوز ~750 بكسل).
2. تحرير المتغيرات الكبيرة صراحة من الذاكرة فور الانتهاء منها.
3. إجبار نظام التشغيل (Linux) على استرجاع الذاكرة المُحررة فعلياً عبر
   malloc_trim، لأن Python وحده لا "يُعيد" الذاكرة لنظام التشغيل تلقائياً
   حتى بعد حذف المتغيرات - وهذا بالضبط سبب تراكم استهلاك الذاكرة مع كل
   صورة جديدة حتى ينهار البوت.
"""
import ctypes
import gc
import io
import logging

from PIL import Image, ImageFilter, ImageEnhance
from rembg import remove, new_session

logger = logging.getLogger(__name__)

_session = new_session("u2netp")

# أقصى بُعد للصورة قبل معالجتها بالذكاء الاصطناعي. هذا كافٍ جداً لجودة
# ممتازة في البوستر النهائي، ويقلل استهلاك الذاكرة والوقت بشكل كبير جداً
# مقارنة بمعالجة صور بدقة الكاميرا الكاملة.
_MAX_DIMENSION = 1600

try:
    _libc = ctypes.CDLL("libc.so.6")
except Exception:
    _libc = None


def _release_memory_to_os():
    """إجبار مكتبة C على إعادة الذاكرة المُحررة فعلياً لنظام التشغيل.
    بدون هذا، تبقى الذاكرة "محجوزة" لصالح Python حتى لو لم تعد مستخدمة،
    فيستمر استهلاك الذاكرة الظاهر بالتراكم مع كل صورة جديدة."""
    gc.collect()
    if _libc:
        try:
            _libc.malloc_trim(0)
        except Exception:
            pass


def remove_background(input_path: str, output_path: str) -> str:
    with open(input_path, "rb") as f:
        input_bytes = f.read()

    # الخطوة الحاسمة: تصغير الصورة الأصلية قبل تمريرها لنموذج الذكاء
    # الاصطناعي، بدل معالجتها بدقتها الكاملة كما ترسلها كاميرا الهاتف.
    img_in = Image.open(io.BytesIO(input_bytes)).convert("RGB")
    del input_bytes
    if max(img_in.size) > _MAX_DIMENSION:
        img_in.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION), Image.Resampling.LANCZOS)

    resized_buf = io.BytesIO()
    img_in.save(resized_buf, format="PNG")
    img_in.close()
    del img_in
    resized_bytes = resized_buf.getvalue()
    resized_buf.close()
    del resized_buf

    try:
        output_bytes = remove(resized_bytes, session=_session)
    finally:
        del resized_bytes

    img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    del output_bytes

    try:
        img = _auto_enhance(img)
        img.save(output_path, "PNG")
    finally:
        img.close()
        del img

    _release_memory_to_os()
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
    result = Image.merge("RGBA", (r, g, b, a))
    rgb.close()
    return result
