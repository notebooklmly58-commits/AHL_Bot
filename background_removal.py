"""
إزالة خلفية صورة المنتج تلقائيًا باستخدام مكتبة rembg (مجانية بالكامل،
تعمل محليًا بدون أي API مدفوع). نستخدم نموذج خفيف (u2netp) لتقليل
استهلاك الذاكرة والوقت على سيرفرات الاستضافة المجانية.

نسخة مُصححة لحل مشكلة "Ran Out of Memory" على Railway (السبب الجذري):
1. تصغير الصورة قبل معالجتها بالذكاء الاصطناعي (كما في السابق).
2. تحرير المتغيرات الكبيرة صراحة من الذاكرة فور الانتهاء منها.
3. malloc_trim لإجبار Linux على استرجاع ما حرره Python فعلياً.
4. [جديد] تعطيل cpu_mem_arena في ONNX Runtime: الجلسة (InferenceSession)
   تحتفظ داخلياً بـ"arena" للذاكرة يكبر مع كل صورة جديدة ولا يتقلص أبداً
   طالما الجلسة حية - هذا تسريب "شرعي" داخل مكتبة ONNX نفسها، خارج نطاق
   malloc_trim تماماً لأنه ليس تحت تصرف Python. تعطيل الـ arena يجعل
   ONNX يخصص ويحرر الذاكرة مباشرة مع كل عملية بدل تجميعها.
5. [جديد] تدوير الجلسة (session recycling): كشبكة أمان إضافية، نُعيد بناء
   الجلسة بالكامل كل عدد محدد من الصور، مما يجبر ONNX على تحرير كل ما
   يملكه فعلياً عند تدمير الجلسة القديمة، ثم malloc_trim يُعيده للنظام.
   آمن تماماً لأن _PROCESSING_SEMAPHORE في poster_flow.py يضمن معالجة
   صورة واحدة فقط في نفس اللحظة (لا تزامن أثناء إعادة البناء).
"""
import ctypes
import gc
import io
import logging
import os
import threading

from PIL import Image, ImageFilter, ImageEnhance
from rembg import remove, new_session

logger = logging.getLogger(__name__)

_MODEL_NAME = "u2netp"

# عدد الصور التي تُعالج بنفس الجلسة قبل إعادة بنائها من الصفر لتفريغ أي
# ذاكرة داخلية تراكمت في ONNX رغم تعطيل الـ arena. قابل للتعديل من
# متغيرات البيئة في Railway باسم SESSION_RECYCLE_EVERY بدون تعديل الكود.
_SESSION_RECYCLE_EVERY = int(os.getenv("SESSION_RECYCLE_EVERY", "15"))

# أقصى بُعد للصورة قبل معالجتها بالذكاء الاصطناعي.
_MAX_DIMENSION = int(os.getenv("MAX_IMAGE_DIMENSION", "1100"))

try:
    _libc = ctypes.CDLL("libc.so.6")
except Exception:
    _libc = None

_session = None
_session_lock = threading.Lock()
_images_since_recycle = 0


def _build_session():
    """ينشئ جلسة ONNX جديدة مع تعطيل cpu_mem_arena صراحة.

    هذا هو الإصلاح الجذري لتسرب الذاكرة: بدون هذا، ONNX يحجز "arena"
    للذاكرة يكبر تلقائياً مع كل صورة ولا يتقلص أبداً طالما الجلسة حية،
    بغض النظر عن أي gc.collect() أو malloc_trim نستدعيه من بايثون.
    """
    try:
        import onnxruntime as ort

        sess_opts = ort.SessionOptions()
        sess_opts.intra_op_num_threads = 1
        sess_opts.inter_op_num_threads = 1

        # تعطيل الـ arena: كل تخصيص ذاكرة يُحرر فور انتهاء استخدامه بدل
        # تجميعه في مجمع متضخم يكبر باستمرار.
        providers = [
            ("CPUExecutionProvider", {"arena_extend_strategy": "kSameAsRequested"}),
        ]
        sess_opts.enable_cpu_mem_arena = False

        session = new_session(_MODEL_NAME, sess_options=sess_opts, providers=providers)
        logger.info("✅ تم إنشاء جلسة ONNX جديدة مع تعطيل cpu_mem_arena بنجاح.")
        return session
    except TypeError:
        # بعض إصدارات rembg القديمة لا تقبل sess_options/providers كوسائط.
        # في هذه الحالة نعتمد فقط على تدوير الجلسة كشبكة أمان.
        logger.warning(
            "⚠️ إصدار rembg الحالي لا يدعم تمرير sess_options مباشرة - "
            "سيتم الاعتماد فقط على تدوير الجلسة كل %s صورة لتفريغ الذاكرة.",
            _SESSION_RECYCLE_EVERY,
        )
        return new_session(_MODEL_NAME)
    except Exception:
        logger.exception("فشل إنشاء جلسة مخصصة، سيتم استخدام الإعدادات الافتراضية.")
        return new_session(_MODEL_NAME)


def _get_session():
    """يُعيد الجلسة الحالية، ويُعيد بناءها من الصفر كل SESSION_RECYCLE_EVERY
    صورة لضمان تحرير أي ذاكرة داخلية تراكمت في ONNX."""
    global _session, _images_since_recycle

    with _session_lock:
        if _session is None:
            _session = _build_session()
            _images_since_recycle = 0
            return _session

        if _images_since_recycle >= _SESSION_RECYCLE_EVERY:
            logger.info(
                "🔄 تدوير جلسة ONNX بعد %s صورة لتفريغ الذاكرة الداخلية المتراكمة...",
                _images_since_recycle,
            )
            old_session = _session
            _session = None
            del old_session
            gc.collect()
            _release_memory_to_os()

            _session = _build_session()
            _images_since_recycle = 0

        return _session


def _release_memory_to_os():
    """إجبار مكتبة C على إعادة الذاكرة المُحررة فعلياً لنظام التشغيل."""
    gc.collect()
    if _libc:
        try:
            _libc.malloc_trim(0)
        except Exception:
            pass


def remove_background(input_path: str, output_path: str) -> str:
    global _images_since_recycle

    with open(input_path, "rb") as f:
        input_bytes = f.read()

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

    session = _get_session()
    try:
        output_bytes = remove(resized_bytes, session=session)
    finally:
        del resized_bytes
        with _session_lock:
            _images_since_recycle += 1

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
