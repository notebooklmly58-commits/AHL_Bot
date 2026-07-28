"""
إزالة خلفية صورة المنتج - نسخة معزولة بالكامل في عملية فرعية (subprocess).

بعد تجربة تعطيل cpu_mem_arena وتدوير الجلسة واستمرار الانهيار، هذا يعني
أن مصدر التسريب أعمق من طبقة ONNX وحدها. الحل المضمون الوحيد: كل صورة
تُعالج في عملية (Process) منفصلة تماماً عن عملية البوت الرئيسية، تُغلق
فور الانتهاء. عند إغلاق عملية في Linux، نظام التشغيل يسترجع 100% من
ذاكرتها فوراً - ضمان من نظام التشغيل نفسه، لا حيلة على مستوى بايثون.

⚠️ متطلب أساسي قبل النشر: يجب أن يحتوي bot.py على:

    if __name__ == "__main__":
        # كل كود بدء تشغيل البوت (asyncio.run(...) إلخ) هنا بالداخل

نستخدم multiprocessing بوضع "spawn"، وهذا الوضع يقوم بإعادة استيراد
الملف الرئيسي (bot.py) في كل عملية فرعية جديدة. بدون هذا الحارس (guard)،
كل صورة سترسل ستُشغّل نسخة كاملة إضافية من البوت نفسه في الخلفية -
مشكلة أخطر بكثير من التي نحاول حلها الآن.
"""
import gc
import logging
import multiprocessing
import os

logger = logging.getLogger(__name__)

_MAX_DIMENSION = int(os.getenv("MAX_IMAGE_DIMENSION", "900"))
_SUBPROCESS_TIMEOUT = int(os.getenv("BG_REMOVAL_TIMEOUT_SECONDS", "120"))

# "spawn" عمداً: تبدأ عملية بايثون جديدة تماماً من الصفر بدل استنساخ ذاكرة
# عملية البوت الحالية، فتضمن عزلاً كاملاً 100% (fork قد يرث حالة خيوط
# غير آمنة من داخل asyncio.to_thread).
_mp_context = multiprocessing.get_context("spawn")


def remove_background(input_path: str, output_path: str) -> str:
    # قناة (Queue) لتمرير سبب الفشل الحقيقي (نص الاستثناء الكامل) من داخل
    # العملية الفرعية إلى العملية الرئيسية. بدونها، كل فشل - مهما كان سببه
    # الفعلي (صورة تالفة، منتج غير واضح، نفاد ذاكرة، ...) - كان يظهر بنفس
    # الرسالة العامة، مما جعل تشخيص المشكلة الحقيقية شبه مستحيل من السجلات.
    error_queue = _mp_context.Queue()
    process = _mp_context.Process(
        target=_run_in_subprocess,
        args=(input_path, output_path, _MAX_DIMENSION, error_queue),
    )
    process.start()
    process.join(timeout=_SUBPROCESS_TIMEOUT)

    if process.is_alive():
        logger.error("⏱️ تجاوزت معالجة الصورة الوقت المسموح، سيتم إيقافها قسرياً.")
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            # terminate() أحياناً لا يكفي لإيقاف عملية عالقة داخل مكتبة C
            # خارجية (onnxruntime)؛ kill() يرسل SIGKILL مباشرة كحل أخير.
            process.kill()
            process.join(timeout=5)
        raise TimeoutError("انتهى وقت معالجة الصورة (bg removal subprocess timeout)")

    if process.exitcode != 0 or not os.path.exists(output_path):
        detail = None
        try:
            if not error_queue.empty():
                detail = error_queue.get_nowait()
        except Exception:
            pass
        # exitcode سالب يعني أن نظام التشغيل أنهى العملية بإشارة (غالباً
        # SIGKILL بسبب نفاد الذاكرة على خطة Railway المجانية) لا بسبب خطأ
        # برمجي داخل بايثون نفسه - نوضح هذا صراحة في رسالة السجل.
        if detail is None and process.exitcode is not None and process.exitcode < 0:
            detail = f"العملية أُنهيت قسرياً بإشارة نظام التشغيل (على الأغلب نفاد الذاكرة)، رمز: {process.exitcode}"
        raise RuntimeError(
            f"فشلت عملية إزالة الخلفية الفرعية (exit code: {process.exitcode}): {detail or 'سبب غير معروف'}"
        )

    gc.collect()
    return output_path


def _run_in_subprocess(input_path: str, output_path: str, max_dimension: int, error_queue=None) -> None:
    """نقطة الدخول التي تُنفَّذ بالكامل داخل العملية الفرعية الجديدة."""
    from bg_removal_worker import process_image_in_subprocess

    try:
        process_image_in_subprocess(input_path, output_path, max_dimension)
    except Exception:
        import traceback

        if error_queue is not None:
            try:
                error_queue.put(traceback.format_exc(limit=6))
            except Exception:
                pass
        raise
