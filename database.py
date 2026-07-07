"""
قاعدة بيانات بسيطة (SQLite) تخزن بيانات الشركة القابلة للتعديل
بدون الحاجة لتعديل الكود. تُستخدم من طرف لوحة تحكم الأدمن.
"""
import sqlite3
import os
from config import BASE_DIR, DEFAULT_COMPANY

DB_PATH = os.path.join(BASE_DIR, "database.sqlite3")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS company_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.commit()
    # إدخال القيم الافتراضية أول مرة فقط
    for key, value in DEFAULT_COMPANY.items():
        cur.execute(
            "INSERT OR IGNORE INTO company_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.commit()
    conn.close()


def get_company_settings() -> dict:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM company_settings")
    rows = cur.fetchall()
    conn.close()
    settings = {row["key"]: row["value"] for row in rows}
    # في حال أي مفتاح ناقص، نرجع الافتراضي
    for key, value in DEFAULT_COMPANY.items():
        settings.setdefault(key, value)
    return settings


def update_company_setting(key: str, value: str):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO company_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()
