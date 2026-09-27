"""ช่วยเขียนไฟล์ Excel ที่ export จากระบบให้ปลอดภัย"""
import re

_NUMBER = re.compile(r'[-+]?\d+(\.\d+)?([eE][-+]?\d+)?')


def excel_safe(text):
    """ข้อความที่ขึ้นต้นด้วย = + - @ Excel จะตีความเป็นสูตร (เช่นชื่อกิจกรรม
    '=HYPERLINK(...)' กลายเป็นลิงก์ที่กดได้ในไฟล์ของแอดมิน) — เติม ' นำหน้าให้
    เป็นข้อความธรรมดา ยกเว้นตัวเลขจริงอย่าง -0.5"""
    if not isinstance(text, str):
        return text
    if text[:1] in ('=', '+', '-', '@', '\t', '\r') and not _NUMBER.fullmatch(text):
        return "'" + text
    return text


def safe_frame(df):
    """ใช้ excel_safe กับทุกคอลัมน์ข้อความของ DataFrame ก่อน to_excel"""
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(excel_safe)
    return df
