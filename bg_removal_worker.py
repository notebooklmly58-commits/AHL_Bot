
"""
هذا الملف يُنفَّذ بالكامل داخل عملية فرعية (subprocess) منعزلة عن عملية
البوت الرئيسية. أي ذاكرة يحجزها rembg/onnxruntime هنا تختفي تماماً مع
نظام التشغيل بمجرد انتهاء هذه العملية - بغض النظر عمّا كانت أي مكتبة
تحتفظ به داخلياً (arena، cache، أو أي شيء آخر).
"""
import io
import logging
import os

logger = logging.getLogger(__name__)

# مهم: يجب ضبط هذه المتغيرات قبل استيراد rembg/onnxruntime مباشرة. بشكل
# افتراضي، onnxruntime وبعض مكتباته الداخلية (OpenMP) تحاول استخدام كل
# أنوية المعالج المتاحة وتحجز ذاكرة مؤقتة إضافية لكل خيط - وهذا هو أحد
# الأسباب الشائعة لفشل المعالجة (نفاد الذاكرة) على خطة Railway المجانية
# المحدودة (ذاكرة ومعالج مشتركان صغيران). تحديدها بـ 1 يجعل الاستهلاك
# متوقعاً وثابتاً بدل ذروة عشوائية قد تتجاوز الحد المسموح.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("ORT_NUM_THREADS", "1")

from PIL import Image, ImageDraw, ImageFile, ImageFilter, ImageEnhance

# تليجرام أحياناً يرسل ملفات JPEG "شبه مكتملة" (خصوصاً الصور المضغوطة أو
# المرسلة بسرعة من الجوال)، وبدون هذا السطر يرفض Pillow فتحها بالكامل
# برسالة "image file is truncated" فتفشل المعالجة برسالة عامة غير مفهومة.
# هذا الإعداد يجعل Pillow يقبل فتح الجزء المتاح من الصورة بدل التوقف.
ImageFile.LOAD_TRUNCATED_IMAGES = True

# ------------------------------------------------------------------
# سبب المشكلة العامة (وليست خاصة بصورة معينة): كنا نستخدم "u2netp" وهو
# نسخة "مُصغّرة/مُقطّرة" من نموذج التجزئة، اختيرت أصلاً لصغر حجمها فقط
# (~4 ميجا) لتفادي مشاكل الذاكرة على خطة Railway المجانية. لكن دقتها
# منخفضة جداً مع المنتجات ذات الألوان الفاتحة/البيضاء على خلفية بيضاء
# أيضاً (حالة شائعة جداً في صور موردي الصين) - فهي أحياناً "تحذف" جسم
# المنتج بالكامل ظناً منها أنه جزء من الخلفية، ولا يبقى إلا العناصر
# الداكنة (نص، شعار...) عائمة بلا شكل المنتج الحقيقي. هذا يفسّر ما حدث
# مع صندوق C6 الأبيض بالضبط.
#
# الحل الجذري العام: نموذج "isnet-general-use" وهو النموذج العام الأدق
# والموصى به رسمياً في مكتبة rembg حالياً لأي منتج/جسم عام (وليس فقط
# الأشخاص)، ويتعامل بشكل صحيح مع تدرجات الأبيض على الأبيض. حجمه أكبر
# (~176 ميجا) فيستهلك ذاكرة أعلى وقت المعالجة من u2netp، لكن بما أن كل
# صورة تُعالج في عملية معزولة تُغلق فوراً (انظر background_removal.py)
# فذاكرته لا تتراكم عبر الطلبات - فقط الذروة اللحظية لكل صورة أعلى قليلاً.
#
# قابل للتغيير فوراً عبر متغير بيئة BG_REMOVAL_MODEL بدون لمس الكود، في
# حال ظهرت مشاكل ذاكرة على خطة Railway الحالية: أعده إلى "u2netp" مؤقتاً.
_BG_MODEL = os.getenv("BG_REMOVAL_MODEL", "isnet-general-use")

# "Alpha Matting": مرحلة تنقيح إضافية لحواف القص (خصوصاً الحواف الناعمة/
# اللامعة الشائعة في كماليات السيارات كالكروم والبلاستيك الشفاف) تُعطي
# نتيجة أنظف بكثير من القص الخام. تتطلب مكتبة `pymatting` مثبتة ضمن
# requirements.txt - لو لم تكن مثبتة، نكتشف ذلك تلقائياً ونكمل بدونها
# بدل توقف المعالجة بالكامل.
_USE_ALPHA_MATTING = os.getenv("BG_REMOVAL_ALPHA_MATTING", "1") == "1"

# ------------------------------------------------------------------
# حتى النموذج الأدق (isnet-general-use) قد يفشل في حالات "منتج فاتح على
# خلفية فاتحة جداً" لأن الفرق اللوني بينهما ضئيل حتى بالنسبة لنموذج ذكاء
# اصطناعي مدرَّب - هذا بالضبط ما حدث مع صندوق C6 الأبيض حتى بعد تبديل
# النموذج. لذلك نضيف طبقة "إنقاذ" لا تعتمد على أي نموذج ذكاء اصطناعي
# إطلاقاً، بل على حقيقة هندسية بسيطة وموثوقة: خلفية صورة المنتج دائماً
# متصلة بحواف الصورة الأربعة، بينما جسم المنتج محاط بحد/ظل يفصله عنها -
# حتى لو كان بنفس درجة اللون تقريباً. أي منطقة "محاصرة" لا تتصل بحواف
# الصورة تُعتبر جزءاً من المنتج، حتى لو صنّفها النموذج خطأً كخلفية شفافة.
_USE_EDGE_RESCUE = os.getenv("BG_REMOVAL_EDGE_RESCUE", "1") == "1"
_EDGE_RESCUE_TOLERANCE = int(os.getenv("BG_REMOVAL_EDGE_TOLERANCE", "26"))


def process_image_in_subprocess(input_path: str, output_path: str, max_dimension: int) -> None:
    from rembg import remove, new_session

    # تحديد صريح لعدد خيوط جلسة onnxruntime نفسها (وليس فقط عبر متغيرات
    # البيئة) لضمان تطبيق الحد الأدنى من الذاكرة حتى لو تجاهلت النسخة
    # المثبتة من onnxruntime متغيرات البيئة أعلاه.
    sess_options = None
    try:
        import onnxruntime as ort
        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = 1
        sess_options.inter_op_num_threads = 1
    except Exception:
        sess_options = None

    session = None
    if sess_options is not None:
        try:
            session = new_session(_BG_MODEL, sess_opts=sess_options)
        except TypeError:
            # نسخة rembg المثبتة لا تدعم تمرير sess_opts بهذا الاسم -
            # نكمل بالإعداد الافتراضي بدل توقف المعالجة بالكامل.
            session = None
        except Exception as e:
            logger.warning(f"تعذر تحميل نموذج {_BG_MODEL} بإعدادات مخصصة: {e}")
            session = None
    if session is None:
        try:
            session = new_session(_BG_MODEL)
        except Exception as e:
            # آخر خط دفاع: لو تعذر تحميل/تنزيل النموذج الأدق كلياً (مثلاً
            # مشكلة اتصال وقت أول تشغيل)، نرجع للنموذج الصغير القديم
            # بدل فشل معالجة الصورة بالكامل.
            logger.error(f"تعذر تحميل نموذج {_BG_MODEL}، الرجوع إلى u2netp: {e}")
            session = new_session("u2netp")

    with open(input_path, "rb") as f:
        input_bytes = f.read()

    img_in = Image.open(io.BytesIO(input_bytes)).convert("RGB")
    if max(img_in.size) > max_dimension:
        img_in.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img_in.save(buf, format="PNG")
    resized_rgb_for_rescue = img_in.copy() if _USE_EDGE_RESCUE else None
    img_in.close()
    resized_bytes = buf.getvalue()
    buf.close()
    del img_in

    matting_kwargs = {}
    if _USE_ALPHA_MATTING:
        matting_kwargs = dict(
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=8,
        )

    try:
        output_bytes = remove(resized_bytes, session=session, **matting_kwargs)
    except Exception as e:
        if matting_kwargs:
            # الفشل هنا غالباً بسبب غياب مكتبة pymatting (متطلب alpha
            # matting) - نكمل بدون هذه الميزة بدل فشل الصورة كاملة.
            logger.warning(f"فشل alpha matting ({e})، سيُعاد المحاولة بدونه.")
            output_bytes = remove(resized_bytes, session=session)
        else:
            raise
    del resized_bytes

    img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    del output_bytes

    if _USE_EDGE_RESCUE and resized_rgb_for_rescue is not None:
        try:
            img = _rescue_low_contrast_holes(img, resized_rgb_for_rescue, _EDGE_RESCUE_TOLERANCE)
        except Exception as e:
            logger.warning(f"تعذر تطبيق مرحلة إنقاذ الحواف منخفضة التباين: {e}")
    if resized_rgb_for_rescue is not None:
        resized_rgb_for_rescue.close()

    # تحقّق أن النموذج فعلاً "وجد" منتجاً في الصورة قبل المتابعة. لو كانت
    # الصورة معقدة جداً أو المنتج غير واضح، أحياناً ينتج rembg صورة شفافة
    # بالكامل تقريباً - وبدون هذا التحقق كان البوستر يُصمّم لاحقاً بمنتج
    # "فارغ" غير مرئي، وهو أسوأ من رسالة خطأ واضحة تطلب صورة أوضح.
    bbox = img.getbbox()
    if bbox is None:
        raise ValueError("لم يتم العثور على منتج واضح في الصورة (الناتج شفاف بالكامل)")
    visible_ratio = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / (img.width * img.height)
    if visible_ratio < 0.01:
        raise ValueError("المنتج المكتشف في الصورة صغير جداً أو غير واضح")

    img = _auto_enhance(img)
    img.save(output_path, "PNG")
    img.close()


def _rescue_low_contrast_holes(cut_img: Image.Image, original_rgb: Image.Image, tolerance: int) -> Image.Image:
    """
    يعيد أي جزء من المنتج حذفه النموذج بالخطأ لأن لونه قريب جداً من لون
    الخلفية (حالة "منتج أبيض على خلفية بيضاء"). الفكرة: نملأ (flood fill)
    من حواف الصورة فقط بالألوان القريبة من كل نقطة بداية - أي منطقة لم
    يصل إليها الملء (أي "محاصرة" ولا تتصل بحواف الصورة) تُعتبر جزءاً من
    المنتج وتُفرض شفافيتها كاملة (غير شفافة)، بصرف النظر عمّا قرره النموذج.
    """
    import numpy as np

    w, h = original_rgb.size
    work = original_rgb.copy()
    MARK = (255, 0, 255)  # لون علامة صارخ نادراً ما يظهر في صور المنتجات

    seeds = set()
    step_x = max(3, w // 80)
    for x in range(0, w, step_x):
        seeds.add((x, 0))
        seeds.add((x, h - 1))
    step_y = max(3, h // 80)
    for y in range(0, h, step_y):
        seeds.add((0, y))
        seeds.add((w - 1, y))

    for seed in seeds:
        try:
            if work.getpixel(seed) != MARK:
                ImageDraw.floodfill(work, seed, MARK, thresh=tolerance)
        except Exception:
            continue

    arr = np.array(work)
    bg_confirmed = np.all(arr == np.array(MARK), axis=-1)  # خلفية مؤكدة (متصلة بالحواف)
    foreground_candidate = (~bg_confirmed).astype("uint8") * 255

    fg_mask_img = Image.fromarray(foreground_candidate, mode="L")
    # تنعيم بسيط لحواف هذا القناع الإضافي فقط، لتجنّب أي حدود مسننة عند دمجه
    fg_mask_img = fg_mask_img.filter(ImageFilter.GaussianBlur(1.2))

    cut_alpha = np.array(cut_img.split()[3])
    fg_alpha = np.array(fg_mask_img)
    combined_alpha = np.maximum(cut_alpha, fg_alpha)

    rgb_arr = np.array(original_rgb)
    out = np.dstack([rgb_arr, combined_alpha])
    return Image.fromarray(out, mode="RGBA")


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
