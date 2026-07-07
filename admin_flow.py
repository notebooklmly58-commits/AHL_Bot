"""
لوحة تحكم بسيطة داخل تيليجرام. فقط صاحب الآيدي المحدد في ADMIN_ID
(بملف .env) يقدر يستخدمها. تسمح بتغيير بيانات الشركة بدون فتح الكود.
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import ADMIN_ID
from database import get_company_settings, update_company_setting

router = Router()

FIELD_LABELS = {
    "company_name": "اسم الشركة",
    "company_slogan": "الشعار النصي (Slogan)",
    "phone1": "رقم الهاتف 1",
    "phone2": "رقم الهاتف 2",
    "address": "العنوان",
}


class AdminFlow(StatesGroup):
    waiting_value = State()


def _is_admin(user_id: int) -> bool:
    return ADMIN_ID != 0 and user_id == ADMIN_ID


def _admin_keyboard():
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"edit:{key}")]
        for key, label in FIELD_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ هذا الأمر مخصص للأدمن فقط.")
        return

    settings = get_company_settings()
    text = "⚙️ لوحة التحكم - اختر ما تريد تعديله:\n\n" + "\n".join(
        f"• {label}: {settings.get(key, '')}" for key, label in FIELD_LABELS.items()
    )
    await message.answer(text, reply_markup=_admin_keyboard())


@router.callback_query(F.data.startswith("edit:"))
async def choose_field(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ غير مسموح", show_alert=True)
        return
    field = callback.data.split(":", 1)[1]
    await state.update_data(field=field)
    await callback.message.answer(f"أرسل القيمة الجديدة لـ: {FIELD_LABELS[field]}")
    await state.set_state(AdminFlow.waiting_value)
    await callback.answer()


@router.message(AdminFlow.waiting_value, F.text)
async def save_field(message: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("field")
    if field:
        update_company_setting(field, message.text.strip())
        await message.answer(f"✅ تم تحديث {FIELD_LABELS[field]} بنجاح.")
    await state.clear()
