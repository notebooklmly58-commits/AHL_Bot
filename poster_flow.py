"""
تدفق الأسئلة - إضافة أزرار التخطي (Skip) التفاعلية لجميع المراحل الفرعية.
"""
import os
import uuid
import gc
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from config import OUTPUT_SIZES, GENERATED_DIR
from database import get_company_settings
from background_removal import remove_background
from poster_generator import generate_poster

router = Router()

class PosterFlow(StatesGroup):
    waiting_photo = State()
    waiting_name = State()
    waiting_price = State()
    waiting_feat1 = State()
    waiting_feat2 = State()
    waiting_feat3 = State()
    waiting_promo = State()
    waiting_size = State()

# أزرار التخطي السريعة
def _skip_keyboard(step_name: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏩ تخطي هذا السؤال", callback_data=f"skip:{step_name}")]
    ])

def _size_keyboard():
    labels = {
        "instagram_post": "📺 مربع (Instagram/Facebook)",
        "instagram_portrait": "📱 طولي (Portrait)",
        "story": "📸 ستوري / حالة (Story)",
    }
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"size:{key}")]
        for key, label in labels.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("👋 أهلاً بك في نظام التصميم التلقائي لـ **شركة الحلول الجديدة**.\n\n📸 أولاً: من فضلك أرسل لي **صورة المنتج** لبدء العمل:")
    await state.set_state(PosterFlow.waiting_photo)

@router.message(PosterFlow.waiting_photo, F.photo)
async def got_photo(message: Message, state: FSMContext):
    photo = message.photo[-1]
    msg = await message.answer("⏳ جاري سحب الصورة وإزالة الخلفية وتحسين جودة المنتج برمجياً...")
    raw_path = f"raw_{uuid.uuid4()}.png"
    clean_path = f"clean_{uuid.uuid4()}.png"
    
    try:
        await message.bot.download(photo, destination=raw_path)
        remove_background(raw_path, clean_path)
        await state.update_data(product_image=clean_path, raw_image=raw_path)
        await msg.edit_text("✅ تم تجهيز صورة المنتج بنجاح!\n\n✍️ الآن أرسل **اسم المنتج** (مثال: شاشات أندرويد الذكية):")
        await state.set_state(PosterFlow.waiting_name)
    except Exception:
        await msg.edit_text("❌ حدث خطأ في معالجة وعزل الصورة. يرجى المحاولة مجدداً.")

@router.message(PosterFlow.waiting_name, F.text)
async def got_name(message: Message, state: FSMContext):
    await state.update_data(product_name=message.text.strip())
    await message.answer("💰 الآن أرسل **سعر المنتج** بالأرقام فقط (مثال: 45) أو اضغط تخطي:", reply_markup=_skip_keyboard("price"))
    await state.set_state(PosterFlow.waiting_price)

# معالجة عمليات التخطي عبر الأزرار التفاعلية
@router.callback_query(F.data.startswith("skip:"))
async def handle_skip(callback: CallbackQuery, state: FSMContext):
    step = callback.data.split(":")[1]
    
    if step == "price":
        await state.update_data(price="")
        await callback.message.edit_text("⭐ أرسل **الميزة الأولى** للمنتج باختصار أو تخطى الحقل:", reply_markup=_skip_keyboard("feat1"))
        await state.set_state(PosterFlow.waiting_feat1)
    elif step == "feat1":
        await state.update_data(feat1="")
        await callback.message.edit_text("⭐ أرسل **الميزة الثانية** باختصار أو تخطى الحقل:", reply_markup=_skip_keyboard("feat2"))
        await state.set_state(PosterFlow.waiting_feat2)
    elif step == "feat2":
        await state.update_data(feat2="")
        await callback.message.edit_text("⭐ أرسل **الميزة الثالثة والأخيرة** أو تخطى الحقل:", reply_markup=_skip_keyboard("feat3"))
        await state.set_state(PosterFlow.waiting_feat3)
    elif step == "feat3":
        await state.update_data(feat3="")
        await callback.message.edit_text("🚀 أرسل **العرض الترويجي النهائي** أسفل الاسم أو اضغط تخطي وللإنهاء الفوري:", reply_markup=_skip_keyboard("promo"))
        await state.set_state(PosterFlow.waiting_promo)
    elif step == "promo":
        await state.update_data(promo_text="")
        await callback.message.edit_text("📐 اختر مقاس الإخراج النهائي للنشر المطلوب:")
        await callback.message.answer("المقاسات المتاحة المرجعية:", reply_markup=_size_keyboard())
        await state.set_state(PosterFlow.waiting_size)
    await callback.answer()

@router.message(PosterFlow.waiting_price, F.text)
async def got_price(message: Message, state: FSMContext):
    await state.update_data(price=message.text.strip())
    await message.answer("⭐ أرسل **الميزة الأولى** للمنتج باختصار أو اضغط تخطي:", reply_markup=_skip_keyboard("feat1"))
    await state.set_state(PosterFlow.waiting_feat1)

@router.message(PosterFlow.waiting_feat1, F.text)
async def got_feat1(message: Message, state: FSMContext):
    await state.update_data(feat1=message.text.strip())
    await message.answer("⭐ أرسل **الميزة الثانية** باختصار أو اضغط تخطي:", reply_markup=_skip_keyboard("feat2"))
    await state.set_state(PosterFlow.waiting_feat2)

@router.message(PosterFlow.waiting_feat2, F.text)
async def got_feat2(message: Message, state: FSMContext):
    await state.update_data(feat2=message.text.strip())
    await message.answer("⭐ أرسل **الميزة الثالثة والأخيرة** أو اضغط تخطي:", reply_markup=_skip_keyboard("feat3"))
    await state.set_state(PosterFlow.waiting_feat3)

@router.message(PosterFlow.waiting_feat3, F.text)
async def got_feat3(message: Message, state: FSMContext):
    await state.update_data(feat3=message.text.strip())
    await message.answer("🚀 أرسل **العرض الترويجي النهائي** أسفل الاسم أو اضغط تخطي للإنهاء التام:", reply_markup=_skip_keyboard("promo"))
    await state.set_state(PosterFlow.waiting_promo)

@router.message(PosterFlow.waiting_promo, F.text)
async def got_promo(message: Message, state: FSMContext):
    await state.update_data(promo_text=message.text.strip())
    await message.answer("📐 اختر مقاس التصميم الفاخر المطلوب للنشر فوراً:", reply_markup=_size_keyboard())
    await state.set_state(PosterFlow.waiting_size)

@router.callback_query(PosterFlow.waiting_size, F.data.startswith("size:"))
async def got_size(callback: CallbackQuery, state: FSMContext):
    size_key = callback.data.split(":", 1)[1]
    data = await state.get_data()
    await callback.message.edit_text("🖌️ جاري رسم وتثبيت البوستر بهندسة التصميم المرجعي الفاخر، ثوانٍ...")
    
    # تجميع الكبسولات المدخلة فقط
    features_list = []
    if data.get("feat1"): features_list.append(data["feat1"])
    if data.get("feat2"): features_list.append(data["feat2"])
    if data.get("feat3"): features_list.append(data["feat3"])
    
    company = get_company_settings()
    output_path = generate_poster(
        product_image_path=data["product_image"],
        product_name=data["product_name"],
        price=data.get("price", ""),
        features=features_list,
        socket="",
        promo_text=data.get("promo_text", ""),
        company=company,
        template_key="luxury_black",
        size_key=size_key
    )
    
    if output_path and os.path.exists(output_path):
        await callback.message.answer_photo(
            photo=FSInputFile(output_path),
            caption=f"✨ **تم تصدير البوستر المثالي لشركة الحلول الجديدة بنجاح كامل!**"
        )
        os.remove(output_path)
    else:
        await callback.message.answer("❌ حدث خطأ فني أثناء تصدير الصورة النهائية.")
        
    if os.path.exists(data["product_image"]): os.remove(data["product_image"])
    if os.path.exists(data["raw_image"]): os.remove(data["raw_image"])
    
    gc.collect()
    await state.clear()
    await callback.answer()
