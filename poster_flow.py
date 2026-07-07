"""
تدفق العمل الذكي باستخدام Gemini API لتصحيح النصوص وصياغتها دفعة واحدة.
"""
import os
import uuid
import json
import gc
import google.generativeai as genai
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from config import TEMPLATES, OUTPUT_SIZES, GENERATED_DIR, GEMINI_API_KEY
from database import get_company_settings
from background_removal import remove_background
from poster_generator import generate_poster

router = Router()

class PosterFlow(StatesGroup):
    waiting_photo = State()
    waiting_details = State()
    waiting_template = State()
    waiting_size = State()

def _template_keyboard():
    buttons = [
        [InlineKeyboardButton(text=meta["label"], callback_data=f"tpl:{key}")]
        for key, meta in TEMPLATES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def _size_keyboard():
    labels = {
        "instagram_post": "مربع (Instagram Post)",
        "instagram_portrait": "طولي (Portrait)",
        "story": "ستوري / حالة (Story)",
        "facebook_post": "منشور فيسبوك (Facebook)",
    }
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"size:{key}")]
        for key, label in labels.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("👋 أهلاً بك في بوت التصميم الذكي المطور.\n📸 من فضلك أرسل لي **صورة المنتج** أولاً لبدء العمل:")
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
        await msg.edit_text("✅ تم تجهيز المنتج بنجاح!\n✍️ الآن أرسل لي **بيانات المنتج** في رسالة واحدة (مثال: اسم المنتج، السعر، المميزات مثل ضمان أو سطوع عالي، إلخ). سيتولى الذكاء الاصطناعي تنظيمها بدون أخطاء إملائية:")
        await state.set_state(PosterFlow.waiting_details)
    except Exception as e:
        await msg.edit_text(f"❌ حدث خطأ أثناء معالجة الصورة. يرجى المحاولة مرة أخرى.")
        if os.path.exists(raw_path): os.remove(raw_path)
        if os.path.exists(clean_path): os.remove(clean_path)

@router.message(PosterFlow.waiting_details, F.text)
async def got_details(message: Message, state: FSMContext):
    if not GEMINI_API_KEY:
        await message.answer("❌ خطأ: مفتاح Gemini API غير معرف في إعدادات السيرفر.")
        return
        
    msg = await message.answer("🧠 يقوم Gemini الآن بتحليل النص، صياغته إعلانياً وتصحيحه إملائياً...")
    
    # تشغيل العقل المفكر Gemini
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    أنت مصحح لغوي ومسوق محترف ل كماليات السيارات. خذ النص التالي واستخرج منه بيانات المنتج بدقة تامة وباللغة العربية الفصحى بدون أخطاء إملائية.
    يجب أن تعيد النتيجة كـ JSON صلب فقط بدون أي علامات ماركداون أو نصوص إضافية خارج أقواس الـ JSON.
    النص: "{message.text}"
    
    عليك صياغة الحقول التالية في الـ JSON:
    1. "product_name": اسم المنتج بشكل فخم وجذاب وقصير.
    2. "price": السعر متبوعاً بكلمة د.ل (إذا لم يذكر السعر اترك الحقل فارغاً "").
    3. "features": مصفوفة تحتوي على 3 إلى 4 مميزات باختصار شديد جداً (من 2 إلى 4 كلمات للميزة الواحدة) لتناسب التصميم مثل ("سطوع فائق", "تركيب سهل وسريع", "ضمان لمدة سنة", "مقاوم للحرارة").
    4. "promo_text": جملة ترويجية للمنتج أسفل الاسم (مثل: "الجيل الجديد من الإضاءة الذكية").
    """
    
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.strip().replace("```json", "").replace("```", "")
        parsed_data = json.loads(clean_text)
        
        await state.update_data(
            product_name=parsed_data.get("product_name", "منتج متمير"),
            price=parsed_data.get("price", ""),
            features=parsed_data.get("features", []),
            promo_text=parsed_data.get("promo_text", "")
        )
        
        await msg.edit_text("🎨 اختر مظهر البوستر الإعلاني:", reply_markup=_template_keyboard())
        await state.set_state(PosterFlow.waiting_template)
    except Exception as e:
        await msg.edit_text("⚠️ لم يتمكن الذكاء الاصطناعي من هيكلة النص تلقائياً، سيتم استخدام النص الافتراضي لتجنب التوقف.")
        await state.update_data(product_name="منتج ممتاز", price="", features=["جودة عالية", "أداء مثالي"], promo_text="")
        await message.answer("🎨 اختر مظهر البوستر الإعلاني:", reply_markup=_template_keyboard())
        await state.set_state(PosterFlow.waiting_template)

@router.callback_query(PosterFlow.waiting_template, F.data.startswith("tpl:"))
async def got_template(callback: CallbackQuery, state: FSMContext):
    template_key = callback.data.split(":", 1)[1]
    await state.update_data(template_key=template_key)
    await callback.message.edit_text("📐 اختر مقاس النشر المطلوب للتصميم المرجعي:")
    await callback.message.answer("المقاسات المتوفرة:", reply_markup=_size_keyboard())
    await state.set_state(PosterFlow.waiting_size)
    await callback.answer()

@router.callback_query(PosterFlow.waiting_size, F.data.startswith("size:"))
async def got_size(callback: CallbackQuery, state: FSMContext):
    size_key = callback.data.split(":", 1)[1]
    data = await state.get_data()
    
    await callback.message.edit_text("🖌️ جاري رسم البوستر بهندسة التصميم المرجعي الفاخر، ثوانٍ...")
    
    company = get_company_settings()
    output_path = generate_poster(
        product_image_path=data["product_image"],
        product_name=data.get("product_name", ""),
        price=data.get("price", ""),
        features=data.get("features", []),
        socket="",
        promo_text=data.get("promo_text", ""),
        company=company,
        template_key=data.get("template_key", "luxury_dark"),
        size_key=size_key
    )
    
    if output_path and os.path.exists(output_path):
        await callback.message.answer_photo(
            photo=FSInputFile(output_path),
            caption="✨ ها هي النتيجة النهائية الفاخرة المرجعية بدون أي خطأ إملائي وبثبات تام!"
        )
        os.remove(output_path)
    else:
        await callback.message.answer("❌ حدث خطأ غير متوقع أثناء رسم الصورة النهائية.")
        
    # تنظيف فوري وشامل لملفات النظام المؤقتة وتحرير الذاكرة
    if os.path.exists(data["product_image"]): os.remove(data["product_image"])
    if os.path.exists(data["raw_image"]): os.remove(data["raw_image"])
    
    gc.collect() # تحرير الرام فوراً منعاً لأخطاء Railway
    await state.clear()
    await callback.answer()
