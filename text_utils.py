"""
Pillow لا يفهم تشكيل الحروف العربية ولا اتجاه الكتابة من اليمين لليسار.
هذا الملف يجهّز أي نص (عربي أو إنجليزي) قبل رسمه على الصورة.
"""
import arabic_reshaper
from bidi.algorithm import get_display


def is_arabic(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06FF" for ch in text)


def shape_text(text: str) -> str:
    """يحوّل النص العربي لشكل متصل وبالاتجاه الصحيح للرسم على الصورة."""
    if not text:
        return text
    if is_arabic(text):
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    return text
