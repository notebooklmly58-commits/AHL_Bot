"""
هذا الملف هو "منطق البوت" - يدير الأسئلة بالترتيب:
صورة -> اسم -> سعر -> مواصفات -> توافق -> عرض ترويجي -> اختيار قالب -> اختيار مقاس -> توليد البوستر
"""
import os
import uuid

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from config import TEMPLATES, OUTPUT_SIZES, GENERATED_DIR
from database import get_company_settings
from background_removal import remove_background
from poster_generator import generate_poster

router = Router()


class PosterFlow(StatesGroup):
    waiting_photo = State()
    waiting_name = State()
    waiting_price = State()
    waiting_features = State()
    waiting_socket = State()
    waiting_promo = State()
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
        "instagram_post": "Instagram Post (مربع)",
        "instagram_portrait": "Instagram Portrait",
        "story": "Story / ستوري",
        "facebook_post": "Facebook Post",
    }
    buttons = [
        [InlineKeyboardButton(text=labels[key], callback_data=f"size:{key}")]
        for key in OUTPUT_SIZES
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "أهلاً بك في بوت تصميم البوسترات الإعلانية 🚗🔴\n\n"
        "أرسل الآن *صورة المنتج* (بدون خلفية، الصورة بس، وبإضاءة واضحة) لأبدأ التصميم.",
        parse_mode="Markdown",
    )
    await state.set_state(PosterFlow.waiting_photo)


@router.message(PosterFlow.waiting_photo, F.photo)
async def got_photo(message: Message, state: FSMContext):
    processing = await message.answer("⏳ جاري إزالة الخلفية وتحسين الصورة، لحظات...")

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    raw_path = os.path.join(GENERATED_DIR, f"raw_{uuid.uuid4().hex}.jpg")
    clean_path = os.path.join(GENERATED_DIR, f"clean_{uuid.uuid4().hex}.png")
    await message.bot.download_file(file.file_path, destination=raw_path)

    remove_background(raw_path, clean_path)

    await state.update_data(product_image=clean_path)
    await processing.edit_text("✅ تم! الآن أرسل *اسم المنتج*", parse_mode="Markdown")
    await state.set_state(PosterFlow.waiting_name)


@router.message(PosterFlow.waiting_photo)
async def wrong_photo(message: Message):
    await message.answer("الرجاء إرسال صورة للمنتج (كصورة وليس كملف).")


@router.message(PosterFlow.waiting_name, F.text)
async def got_name(message: Message, state: FSMContext):
    await state.update_data(product_name=message.text.strip())
    await message.answer("💰 الآن أرسل *السعر* (أو اكتب `تخطي` إذا ما تريد إظهار السعر)", parse_mode="Markdown")
    await state.set_state(PosterFlow.waiting_price)


@router.message(PosterFlow.waiting_price, F.text)
async def got_price(message: Message, state: FSMContext):
    price = "" if message.text.strip() in ("تخطي", "skip") else message.text.strip()
    await state.update_data(price=price)
    await message.answer(
        "🔧 أرسل *المواصفات* الآن - كل ميزة بسطر منفصل، مثال:\n\n"
        "12000LM\n2 Years Warranty\nWhite LED\nCopper Cooling",
        parse_mode="Markdown",
    )
    await state.set_state(PosterFlow.waiting_features)


@router.message(PosterFlow.waiting_features, F.text)
async def got_features(message: Message, state: FSMContext):
    features = [line.strip() for line in message.text.split("\n") if line.strip()]
    await state.update_data(features=features)
    await message.answer("🔌 أرسل *التوافق* (مثال: H4, H7, 9005) أو اكتب `تخطي`", parse_mode="Markdown")
    await state.set_state(PosterFlow.waiting_socket)


@router.message(PosterFlow.waiting_socket, F.text)
async def got_socket(message: Message, state: FSMContext):
    socket = "" if message.text.strip() in ("تخطي", "skip") else message.text.strip()
    await state.update_data(socket=socket)
    await message.answer("📣 أرسل *نص العرض الترويجي* (مثال: Limited Time Offer) أو اكتب `تخطي`", parse_mode="Markdown")
    await state.set_state(PosterFlow.waiting_promo)


@router.message(PosterFlow.waiting_promo, F.text)
async def got_promo(message: Message, state: FSMContext):
    promo = "" if message.text.strip() in ("تخطي", "skip") else message.text.strip()
    await state.update_data(promo_text=promo)
    await message.answer("🎨 اختر القالب (Template):", reply_markup=_template_keyboard())
    await state.set_state(PosterFlow.waiting_template)


@router.callback_query(PosterFlow.waiting_template, F.data.startswith("tpl:"))
async def got_template(callback: CallbackQuery, state: FSMContext):
    template_key = callback.data.split(":", 1)[1]
    await state.update_data(template_key=template_key)
    await callback.message.edit_text("📐 اختر مقاس الإخراج:")
    await callback.message.answer("اختر المقاس:", reply_markup=_size_keyboard())
    await state.set_state(PosterFlow.waiting_size)
    await callback.answer()


@router.callback_query(PosterFlow.waiting_size, F.data.startswith("size:"))
async def got_size(callback: CallbackQuery, state: FSMContext):
    size_key = callback.data.split(":", 1)[1]
    data = await state.get_data()

    await callback.message.edit_text("🖌️ جاري تصميم البوستر النهائي، ثوانٍ...")

    company = get_company_settings()
    output_path = generate_poster(
        product_image_path=data["product_image"],
        product_name=data.get("product_name", ""),
        price=data.get("price", ""),
        features=data.get("features", []),
        socket=data.get("socket", ""),
        promo_text=data.get("promo_text", ""),
        company=company,
        template_key=data.get("template_key", "luxury_black"),
        size_key=size_key,
    )

    photo = FSInputFile(output_path)
    await callback.message.answer_photo(
        photo,
        caption="✅ البوستر جاهز! أرسل /start لتصميم منتج جديد.",
    )
    await state.clear()
    await callback.answer()
