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
    waiting_size = State()

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
    await message.answer("👋 أهلاً بك في بوت التصميم المطور لشركة الحلول الجديدة.\n📸 من فضلك أرسل لي **صورة المنتج** أولاً لبدء العمل:")
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
    except Exception:
        await msg.edit_text("❌ حدث خطأ أثناء معالجة الصورة. يرجى المحاولة مرة أخرى.")

@router.message(PosterFlow.waiting_details, F.text)
async def got_details(message: Message, state: FSMContext):
    msg = await message.answer("🧠 يقوم Gemini الآن بتحليل البيانات وصياغتها للتطابق مع جودة القالب الاحترافي...")
    
    if GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(
                model_name='gemini-1.5-flash',
                generation_config={"response_mime_type": "application/json"}
            )
            
            prompt = f"""
            أنت خبير تسويق كماليات سيارات محترف. خذ هذا النص واستخرج بيانات منتج دقيقة لبوستر إعلاني فخم جداً.
            أعد النتيجة فقط كـ JSON بهذه المفاتيح باللغة العربية:
            - "product_name": اسم المنتج بدقة وفخامة (مثال: "ماوس الألعاب الاحترافي").
            - "price": الرقم فقط (مثال: "45").
            - "features": قائمة تحتوي على 3 مميزات قصيرة جذابة (مثل: "سطوع فائق وقوي", "ألوان RGB متناسقة", "ضمان معتمد حقيقي").
            - "promo_text": سطر تسويقي فخم وجذاب (مثل: "التكنولوجيا الأحدث لسيارتك").
            
            النص: "{message.text}"
            """
            response = model.generate_content(prompt)
            parsed = json.loads(response.text.strip())
            
            await state.update_data(
                product_name=parsed.get("product_name", "منتج فاخر"),
                price=parsed.get("price", ""),
                features=parsed.get("features", ["جودة عالية", "أداء ممتاز"]),
                promo_text=parsed.get("promo_text", "إصدار خاص ومحدود")
            )
        except Exception:
            await state.update_data(product_name="منتج فاخر", price="", features=["أداء ممتاز", "جودة عالية"], promo_text="")
    else:
        await state.update_data(product_name="منتج متميز", price="", features=["مواصفات عالمية"], promo_text="")
        
    await msg.edit_text("📐 اختر مقاس النشر المطلوب للتصميم المرجعي الفاخر:", reply_markup=_size_keyboard())
    await state.set_state(PosterFlow.waiting_size)

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
        template_key="luxury_black",
        size_key=size_key
    )
    
    if output_path and os.path.exists(output_path):
        await callback.message.answer_photo(
            photo=FSInputFile(output_path),
            caption="✨ ها هي النتيجة النهائية الفاخرة لشركة الحلول الجديدة بجودة القالب المرجعي المرفق!"
        )
        os.remove(output_path)
    else:
        await callback.message.answer("❌ حدث خطأ أثناء تصدير الصورة النهائية.")
        
    if os.path.exists(data["product_image"]): os.remove(data["product_image"])
    if os.path.exists(data["raw_image"]): os.remove(data["raw_image"])
    
    gc.collect()
    await state.clear()
    await callback.answer()
