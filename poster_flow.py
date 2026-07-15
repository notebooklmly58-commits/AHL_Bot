"""
تدفق الأسئلة - شركة الحلول الجديدة.
نسخة مُصححة:
- بعد إنشاء أي بوستر، يعود البوت تلقائياً لطلب صورة المنتج التالي
  بدون الحاجة لإرسال /start مرة أخرى.
- زر إلغاء متاح في كل خطوة.
- معالجة الأخطاء ورسائل واضحة إذا أرسل المستخدم نوع رسالة غير متوقع.
- أمر /cancel لإلغاء العملية الحالية في أي وقت.
"""
import os
import uuid
import gc
import asyncio
import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from config import OUTPUT_SIZES, GENERATED_DIR
from database import get_company_settings
from background_removal import remove_background
from poster_generator import generate_poster, get_font_diagnostics, fonts_are_ready

logger = logging.getLogger(__name__)
router = Router()

# حد أقصى لعدد عمليات معالجة الصور الثقيلة (إزالة الخلفية + رسم البوستر)
# التي تعمل في نفس اللحظة بالضبط. تم تخفيضه إلى 1 (أي معالجة متسلسلة
# بالكامل) لأن خطة Railway الحالية (Trial) لا تملك ذاكرة كافية لتشغيل
# عمليتين بالتوازي بأمان - التزامن كان سيُضاعف الذروة القصوى لاستهلاك
# الذاكرة بالضبط وقت تصادم مستخدمين، مما يزيد فرصة الانهيار لا يقللها.
# ارفع الرقم إلى 2 لاحقاً فقط بعد ترقية الخطة والتأكد من وجود ذاكرة كافية
# (راجع تبويب Metrics في Railway).
_PROCESSING_SEMAPHORE = asyncio.Semaphore(1)


class PosterFlow(StatesGroup):
    waiting_photo = State()
    waiting_name = State()
    waiting_price = State()
    waiting_feat1 = State()
    waiting_feat2 = State()
    waiting_feat3 = State()
    waiting_promo = State()
    waiting_size = State()


class QuickFlow(StatesGroup):
    """الوضع السريع: يصمم بوستراً فورياً لكل صورة تُرسل، بمواصفات ثابتة
    (جودة عالية / أسعار منافسة) بدون سعر أو عرض ترويجي، مع خيار سؤال
    المستخدم عن اسم كل منتج أو تخطي الاسم بالكامل حسب اختياره."""

    active = State()
    waiting_name = State()


# ------------------------------------------------------------------
# لوحات الأزرار
# ------------------------------------------------------------------
def _skip_keyboard(step_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏩ تخطي هذا السؤال", callback_data=f"skip:{step_name}")],
            [InlineKeyboardButton(text="❌ إلغاء العملية", callback_data="cancel")],
        ]
    )


def _size_keyboard() -> InlineKeyboardMarkup:
    labels = {
        "instagram_post": "📺 مربع (Instagram/Facebook)",
        "instagram_portrait": "📱 طولي (Portrait)",
        "story": "📸 ستوري / حالة (Story)",
    }
    buttons = [[InlineKeyboardButton(text=label, callback_data=f"size:{key}")] for key, label in labels.items()]
    buttons.append([InlineKeyboardButton(text="❌ إلغاء العملية", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _multi_size_keyboard() -> InlineKeyboardMarkup:
    """لوحة تظهر بعد إنشاء أي بوستر، تتيح توليد نفس المنتج بمقاس آخر
    مباشرة دون إعادة كتابة الاسم والسعر والمواصفات من جديد."""
    labels = {
        "instagram_post": "📺 مربع",
        "instagram_portrait": "📱 طولي",
        "story": "📸 ستوري",
    }
    size_buttons = [InlineKeyboardButton(text=label, callback_data=f"size:{key}") for key, label in labels.items()]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📐 نفس المنتج بمقاس آخر:", callback_data="noop")],
            size_buttons,
            [InlineKeyboardButton(text="🆕 إنهاء وبدء منتج جديد", callback_data="finish_product")],
        ]
    )


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


async def _cleanup_state_files(state: FSMContext):
    """حذف أي ملفات صور مؤقتة متبقية في الحالة الحالية لتفادي تراكم الملفات على السيرفر."""
    data = await state.get_data()
    for key in ("product_image", "raw_image"):
        path = data.get(key)
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


# ------------------------------------------------------------------
# البداية
# ------------------------------------------------------------------
async def _ask_for_photo(message: Message, state: FSMContext, greeting: bool = True):
    if greeting:
        text = (
            "👋 أهلاً بك في نظام التصميم التلقائي لـ **شركة الحلول الجديدة**.\n\n"
            "📸 أرسل لي **صورة المنتج** لبدء العمل:"
        )
    else:
        text = "📸 أرسل صورة المنتج التالي متى ما أردت، وسأبدأ تصميمه مباشرة:"
    await message.answer(text)
    await state.set_state(PosterFlow.waiting_photo)


@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await _cleanup_state_files(state)
    await state.clear()
    await _ask_for_photo(message, state, greeting=True)


@router.message(F.text == "/cancel")
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("لا توجد عملية جارية حالياً. أرسل صورة منتج للبدء 📸")
        return
    await _cleanup_state_files(state)
    await state.clear()
    await message.answer("❌ تم إلغاء العملية الحالية.")
    await _ask_for_photo(message, state, greeting=False)


@router.message(F.text == "/fonts_status")
async def cmd_fonts_status(message: Message):
    diag = get_font_diagnostics()
    lines = ["🔎 **تشخيص حالة الخطوط**\n"]
    lines.append(f"📁 المسار المطلوب رفع الخطوط بداخله بالضبط:\n`{diag['fonts_dir']}`\n")

    all_ok = True
    for name, info in diag["files"].items():
        if info["valid"]:
            lines.append(f"✅ {name} — موجود وسليم ({info['size_kb']} KB)")
        elif info["exists"]:
            lines.append(
                f"⚠️ {name} — موجود لكن الحجم صغير جداً ({info['size_kb']} KB)، غالباً الملف تالف. ارفعه من جديد."
            )
            all_ok = False
        else:
            lines.append(f"❌ {name} — غير موجود إطلاقاً في هذا المسار.")
            all_ok = False

    lines.append("")
    if all_ok:
        lines.append("🎉 كل شيء سليم! الخطوط في مكانها الصحيح والنصوص العربية يجب أن تظهر بشكل صحيح.")
    else:
        lines.append(
            "🛠️ يجب رفع ملفي الخط (Tajawal-Bold.ttf و Tajawal-Regular.ttf) داخل المسار "
            "المذكور أعلاه بالضبط داخل مستودع GitHub، ثم انتظر إعادة نشر Railway تلقائياً."
        )

    await message.answer("\n".join(lines))


_QUICK_FEATURES = ["جودة عالية", "أسعار منافسة"]
_QUICK_DEFAULT_SIZE = "instagram_post"


def _quick_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 وضع سريع مع اسم (يسأل عن الاسم لكل صورة)", callback_data="quick:with_name")],
            [InlineKeyboardButton(text="🚀 وضع سريع فوري (بدون اسم إطلاقاً)", callback_data="quick:no_name")],
            [InlineKeyboardButton(text="⏹️ إيقاف الوضع السريع", callback_data="quick:off")],
        ]
    )


@router.message(F.text == "/quick")
async def cmd_quick(message: Message, state: FSMContext):
    await message.answer(
        "🚀 **الوضع السريع**\n\n"
        "يصمم بوستراً فورياً لكل صورة ترسلها، بمواصفات ثابتة دائماً:\n"
        f"⭐ {_QUICK_FEATURES[0]}\n⭐ {_QUICK_FEATURES[1]}\n"
        "(بدون سعر أو عرض ترويجي)\n\n"
        "💡 نصيحة: إن كتبت **وصفاً (Caption)** على الصورة عند إرسالها من "
        "المعرض، سيُستخدم تلقائياً كاسم المنتج مهما كان الخيار الذي تختاره "
        "أدناه.\n\n"
        "اختر طريقة عمل الوضع السريع:",
        reply_markup=_quick_mode_keyboard(),
    )


@router.callback_query(F.data.startswith("quick:"))
async def cb_quick_mode(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":", 1)[1]
    await _cleanup_state_files(state)

    if choice == "off":
        await state.clear()
        await callback.message.edit_text("⏹️ تم إيقاف الوضع السريع.")
        await _ask_for_photo(callback.message, state, greeting=False)
        await callback.answer()
        return

    with_name = choice == "with_name"
    await state.set_data({"quick_with_name": with_name, "quick_size": _QUICK_DEFAULT_SIZE})
    await state.set_state(QuickFlow.active)

    if with_name:
        msg = (
            "✅ تم تفعيل **الوضع السريع مع الاسم**.\n\n"
            "أرسل أي صورة منتج، وسأسألك فقط عن اسمه ثم أصمم البوستر فوراً "
            "(بدون سعر أو مواصفات إضافية). يمكنك إرسال عدة صور بالتتابع."
        )
    else:
        msg = (
            "✅ تم تفعيل **الوضع السريع الفوري**.\n\n"
            "أرسل أي عدد من صور المنتجات، وسأصمم بوستراً لكل واحدة فوراً "
            "بدون أي أسئلة إطلاقاً."
        )
    msg += (
        f"\n\n📐 المقاس الافتراضي حالياً: مربع (Instagram/Facebook). "
        "لتغييره أرسل /quick_size.\n"
        "لإيقاف الوضع السريع في أي وقت أرسل /quick مجدداً."
    )
    await callback.message.edit_text(msg)
    await callback.answer()


def _quick_size_keyboard() -> InlineKeyboardMarkup:
    labels = {
        "instagram_post": "📺 مربع",
        "instagram_portrait": "📱 طولي",
        "story": "📸 ستوري",
    }
    buttons = [[InlineKeyboardButton(text=label, callback_data=f"quicksize:{key}")] for key, label in labels.items()]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(F.text == "/quick_size")
async def cmd_quick_size(message: Message, state: FSMContext):
    current = await state.get_state()
    if current not in (QuickFlow.active.state, QuickFlow.waiting_name.state):
        await message.answer("⚠️ فعّل الوضع السريع أولاً عبر الأمر /quick قبل تغيير المقاس.")
        return
    await message.answer("📐 اختر المقاس الذي سيُستخدم لكل الصور القادمة في الوضع السريع:", reply_markup=_quick_size_keyboard())


@router.callback_query(F.data.startswith("quicksize:"))
async def cb_quick_size(callback: CallbackQuery, state: FSMContext):
    size_key = callback.data.split(":", 1)[1]
    await state.update_data(quick_size=size_key)
    await callback.message.edit_text("✅ تم تحديث المقاس الافتراضي للوضع السريع. أرسل الصور الآن.")
    await callback.answer()


async def _quick_generate(message: Message, state: FSMContext, product_name: str):
    """توليد بوستر فوري بمواصفات الوضع السريع الثابتة، ثم تنظيف الملفات
    المؤقتة الخاصة بهذه الصورة تحديداً (دون إنهاء الوضع السريع نفسه) حتى
    يبقى المستخدم جاهزاً لإرسال الصورة التالية مباشرة."""
    data = await state.get_data()
    if not data.get("product_image") or not os.path.exists(data["product_image"]):
        await message.answer("⚠️ لم تعد الصورة متاحة، أرسلها من جديد.")
        return

    status = await message.answer("🖌️ جاري تصميم البوستر...")
    size_key = data.get("quick_size", _QUICK_DEFAULT_SIZE)

    output_path = None
    try:
        company = get_company_settings()
        async with _PROCESSING_SEMAPHORE:
            output_path = await asyncio.to_thread(
                generate_poster,
                product_image_path=data["product_image"],
                product_name=product_name,
                price="",
                features=list(_QUICK_FEATURES),
                socket="",
                promo_text="",
                company=company,
                template_key="luxury_black",
                size_key=size_key,
            )
    except Exception:
        logger.exception("فشل توليد بوستر الوضع السريع")

    if output_path and os.path.exists(output_path):
        caption = "✨ **بوستر جاهز!**"
        if not fonts_are_ready():
            caption += "\n\n⚠️ تنبيه: الخطوط غير مضبوطة بالكامل. أرسل /fonts_status للتفاصيل."
        await status.delete()
        await message.answer_photo(photo=FSInputFile(output_path), caption=caption)
        os.remove(output_path)
    else:
        await status.edit_text("❌ حدث خطأ أثناء التصميم. جرّب هذه الصورة مرة أخرى.")

    for key in ("product_image", "raw_image"):
        p = data.get(key)
        if p and os.path.exists(p):
            os.remove(p)
    await state.update_data(product_image=None, raw_image=None)
    gc.collect()

    await message.answer(
        "📸 أرسل صورة المنتج التالي متى شئت، أو /quick لتغيير إعدادات الوضع السريع، أو /start للخروج منه."
    )


@router.message(QuickFlow.active, F.photo)
async def quick_got_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photo = message.photo[-1]
    msg = await message.answer("⏳ جاري تجهيز الصورة...")
    raw_path = f"raw_{uuid.uuid4()}.png"
    clean_path = f"clean_{uuid.uuid4()}.png"

    try:
        await message.bot.download(photo, destination=raw_path)
        async with _PROCESSING_SEMAPHORE:
            await asyncio.to_thread(remove_background, raw_path, clean_path)
    except Exception:
        logger.exception("فشل تجهيز صورة الوضع السريع")
        await msg.edit_text("❌ حدث خطأ في معالجة الصورة، حاول إرسالها مجدداً.")
        if os.path.exists(raw_path):
            os.remove(raw_path)
        return

    await state.update_data(product_image=clean_path, raw_image=raw_path)

    # وصف الصورة (Caption) عند الإرسال يُستخدم تلقائياً كاسم المنتج إن
    # وُجد، بغض النظر عن الخيار المفعّل - يوفر إرسالاً دفعياً سريعاً جداً.
    caption_name = (message.caption or "").strip()
    if caption_name:
        await msg.delete()
        await _quick_generate(message, state, product_name=caption_name)
        return

    if data.get("quick_with_name"):
        await msg.edit_text("✍️ اسم هذا المنتج؟")
        await state.set_state(QuickFlow.waiting_name)
    else:
        await msg.delete()
        await _quick_generate(message, state, product_name="")


@router.message(QuickFlow.waiting_name, F.text)
async def quick_got_name(message: Message, state: FSMContext):
    await state.set_state(QuickFlow.active)
    await _quick_generate(message, state, product_name=message.text.strip())



@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await _cleanup_state_files(state)
    await state.clear()
    await callback.message.edit_text("❌ تم إلغاء العملية الحالية.")
    await _ask_for_photo(callback.message, state, greeting=False)
    await callback.answer()


@router.callback_query(F.data == "finish_product")
async def cb_finish_product(callback: CallbackQuery, state: FSMContext):
    await _cleanup_state_files(state)
    await state.clear()
    await _ask_for_photo(callback.message, state, greeting=False)
    await callback.answer()


# ------------------------------------------------------------------
# استقبال الصورة
# ------------------------------------------------------------------
@router.message(PosterFlow.waiting_photo, F.photo)
async def got_photo(message: Message, state: FSMContext):
    photo = message.photo[-1]
    msg = await message.answer("⏳ جاري سحب الصورة وإزالة الخلفية وتحسين جودة المنتج برمجياً...")
    raw_path = f"raw_{uuid.uuid4()}.png"
    clean_path = f"clean_{uuid.uuid4()}.png"

    try:
        await message.bot.download(photo, destination=raw_path)
        # تشغيل إزالة الخلفية (عملية ثقيلة على المعالج) في خيط منفصل بدل
        # حجب حلقة الأحداث الرئيسية للبوت بالكامل. بدون هذا، أي مستخدم
        # آخر يرسل رسالة أثناء معالجة صورة شخص آخر سيبقى بلا رد حتى تنتهي
        # المعالجة الأولى تماماً. الـ Semaphore يحدد عدد الصور التي تُعالج
        # في نفس اللحظة لمنع استهلاك ذاكرة زائد عند تزاحم عدة مستخدمين.
        async with _PROCESSING_SEMAPHORE:
            await asyncio.to_thread(remove_background, raw_path, clean_path)
        await state.update_data(product_image=clean_path, raw_image=raw_path)
        await msg.edit_text(
            "✅ تم تجهيز صورة المنتج بنجاح!\n\n✍️ الآن أرسل **اسم المنتج** (مثال: شاشات أندرويد الذكية):"
        )
        await state.set_state(PosterFlow.waiting_name)
    except Exception as e:
        logger.exception("فشل في معالجة الصورة")
        await msg.edit_text(
            "❌ حدث خطأ أثناء معالجة الصورة. تأكد أنها صورة واضحة للمنتج وحاول إرسالها مجدداً."
        )
        if os.path.exists(raw_path):
            os.remove(raw_path)


@router.message(PosterFlow.waiting_photo)
async def waiting_photo_wrong_type(message: Message, state: FSMContext):
    await message.answer("📸 من فضلك أرسل **صورة** المنتج (وليس نصاً أو ملفاً آخر) لبدء التصميم.")


# ------------------------------------------------------------------
# الوضع السريع: بوستر فوري لكل صورة، بمواصفات ثابتة (جودة عالية / أسعار
# منافسة)، مع خيار وجود اسم منتج أو عدمه حسب اختيار المستخدم في أي وقت.
# ------------------------------------------------------------------
@router.message(F.photo)
async def photo_any_state_restart(message: Message, state: FSMContext):
    """يسمح بإرسال صورة منتج جديد في أي لحظة (حتى أثناء اختيار مقاسات
    إضافية لمنتج سابق) لبدء تصميم جديد فوراً دون الحاجة لأي أمر."""
    await _cleanup_state_files(state)
    await state.clear()
    await state.set_state(PosterFlow.waiting_photo)
    await got_photo(message, state)


# ------------------------------------------------------------------
# اسم المنتج
# ------------------------------------------------------------------
@router.message(PosterFlow.waiting_name, F.text)
async def got_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("⚠️ الرجاء إرسال اسم منتج غير فارغ.")
        return
    await state.update_data(product_name=name)
    await message.answer(
        "💰 الآن أرسل **سعر المنتج** بالأرقام فقط (مثال: 45) أو اضغط تخطي:",
        reply_markup=_skip_keyboard("price"),
    )
    await state.set_state(PosterFlow.waiting_price)


@router.message(PosterFlow.waiting_name)
async def waiting_name_wrong_type(message: Message, state: FSMContext):
    await message.answer("✍️ من فضلك أرسل اسم المنتج كنص.")


# ------------------------------------------------------------------
# التخطي التفاعلي
# ------------------------------------------------------------------
@router.callback_query(F.data.startswith("skip:"))
async def handle_skip(callback: CallbackQuery, state: FSMContext):
    step = callback.data.split(":")[1]

    if step == "price":
        await state.update_data(price="")
        await callback.message.edit_text(
            "⭐ أرسل **الميزة الأولى** للمنتج باختصار أو تخطى الحقل:", reply_markup=_skip_keyboard("feat1")
        )
        await state.set_state(PosterFlow.waiting_feat1)
    elif step == "feat1":
        await state.update_data(feat1="")
        await callback.message.edit_text(
            "⭐ أرسل **الميزة الثانية** باختصار أو تخطى الحقل:", reply_markup=_skip_keyboard("feat2")
        )
        await state.set_state(PosterFlow.waiting_feat2)
    elif step == "feat2":
        await state.update_data(feat2="")
        await callback.message.edit_text(
            "⭐ أرسل **الميزة الثالثة والأخيرة** أو تخطى الحقل:", reply_markup=_skip_keyboard("feat3")
        )
        await state.set_state(PosterFlow.waiting_feat3)
    elif step == "feat3":
        await state.update_data(feat3="")
        await callback.message.edit_text(
            "🚀 أرسل **العرض الترويجي النهائي** أسفل الاسم أو اضغط تخطي للإنهاء الفوري:",
            reply_markup=_skip_keyboard("promo"),
        )
        await state.set_state(PosterFlow.waiting_promo)
    elif step == "promo":
        await state.update_data(promo_text="")
        await callback.message.edit_text("📐 اختر مقاس الإخراج النهائي للنشر المطلوب:", reply_markup=_size_keyboard())
        await state.set_state(PosterFlow.waiting_size)
    await callback.answer()


# ------------------------------------------------------------------
# السعر والمواصفات والعرض الترويجي
# ------------------------------------------------------------------
@router.message(PosterFlow.waiting_price, F.text)
async def got_price(message: Message, state: FSMContext):
    await state.update_data(price=message.text.strip())
    await message.answer(
        "⭐ أرسل **الميزة الأولى** للمنتج باختصار أو اضغط تخطي:", reply_markup=_skip_keyboard("feat1")
    )
    await state.set_state(PosterFlow.waiting_feat1)


@router.message(PosterFlow.waiting_feat1, F.text)
async def got_feat1(message: Message, state: FSMContext):
    await state.update_data(feat1=message.text.strip())
    await message.answer(
        "⭐ أرسل **الميزة الثانية** باختصار أو اضغط تخطي:", reply_markup=_skip_keyboard("feat2")
    )
    await state.set_state(PosterFlow.waiting_feat2)


@router.message(PosterFlow.waiting_feat2, F.text)
async def got_feat2(message: Message, state: FSMContext):
    await state.update_data(feat2=message.text.strip())
    await message.answer(
        "⭐ أرسل **الميزة الثالثة والأخيرة** أو اضغط تخطي:", reply_markup=_skip_keyboard("feat3")
    )
    await state.set_state(PosterFlow.waiting_feat3)


@router.message(PosterFlow.waiting_feat3, F.text)
async def got_feat3(message: Message, state: FSMContext):
    await state.update_data(feat3=message.text.strip())
    await message.answer(
        "🚀 أرسل **العرض الترويجي النهائي** أسفل الاسم أو اضغط تخطي للإنهاء التام:",
        reply_markup=_skip_keyboard("promo"),
    )
    await state.set_state(PosterFlow.waiting_promo)


@router.message(PosterFlow.waiting_promo, F.text)
async def got_promo(message: Message, state: FSMContext):
    await state.update_data(promo_text=message.text.strip())
    await message.answer("📐 اختر مقاس التصميم الفاخر المطلوب للنشر فوراً:", reply_markup=_size_keyboard())
    await state.set_state(PosterFlow.waiting_size)


# ------------------------------------------------------------------
# اختيار المقاس وتوليد البوستر النهائي (يدعم توليد أكثر من مقاس لنفس المنتج)
# ------------------------------------------------------------------
@router.callback_query(PosterFlow.waiting_size, F.data.startswith("size:"))
async def got_size(callback: CallbackQuery, state: FSMContext):
    size_key = callback.data.split(":", 1)[1]
    data = await state.get_data()

    if not data.get("product_image") or not os.path.exists(data["product_image"]):
        await callback.answer("⚠️ انتهت صلاحية الصورة. أرسل صورة المنتج من جديد.", show_alert=True)
        await _ask_for_photo(callback.message, state, greeting=False)
        return

    await callback.message.answer("🖌️ جاري رسم وتثبيت البوستر بهذا المقاس، ثوانٍ...")

    features_list = []
    if data.get("feat1"):
        features_list.append(data["feat1"])
    if data.get("feat2"):
        features_list.append(data["feat2"])
    if data.get("feat3"):
        features_list.append(data["feat3"])

    output_path = None
    try:
        company = get_company_settings()
        # نفس مبدأ إزالة الخلفية: تشغيل الرسم (عملية ثقيلة أيضاً) في خيط
        # منفصل حتى لا تتجمد بقية المحادثات مع مستخدمين آخرين أثناء رسم
        # بوستر شخص آخر.
        async with _PROCESSING_SEMAPHORE:
            output_path = await asyncio.to_thread(
                generate_poster,
                product_image_path=data["product_image"],
                product_name=data["product_name"],
                price=data.get("price", ""),
                features=features_list,
                socket="",
                promo_text=data.get("promo_text", ""),
                company=company,
                template_key="luxury_black",
                size_key=size_key,
            )
    except Exception:
        logger.exception("فشل توليد البوستر")

    if output_path and os.path.exists(output_path):
        caption = "✨ **تم تصدير البوستر بنجاح لشركة الحلول الجديدة!**"
        if not fonts_are_ready():
            caption += (
                "\n\n⚠️ تنبيه: خط Tajawal غير مضبوط بشكل صحيح على السيرفر، لذلك "
                "قد تظهر بعض الحروف العربية ناقصة في الصورة أعلاه. أرسل الأمر "
                "/fonts_status لمعرفة السبب بالتحديد وحله."
            )
        await callback.message.answer_photo(photo=FSInputFile(output_path), caption=caption)
        os.remove(output_path)
        await callback.message.answer(
            "📐 يمكنك الآن توليد **نفس المنتج بمقاس آخر مباشرة** بدون إعادة كتابة أي بيانات، "
            "أو إنهاء والبدء بمنتج جديد:",
            reply_markup=_multi_size_keyboard(),
        )
    else:
        await callback.message.answer(
            "❌ حدث خطأ فني أثناء تصدير الصورة. جرّب مقاساً آخر أو ابدأ من جديد:",
            reply_markup=_multi_size_keyboard(),
        )

    gc.collect()
    # نبقى في نفس حالة اختيار المقاس عمداً للسماح بتوليد مقاسات إضافية
    # لنفس المنتج دون حذف الصورة أو إعادة كتابة البيانات.
    await callback.answer()
