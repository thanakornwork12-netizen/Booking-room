"""เช็คว่าเลขบรรทัดในตาราง "แก้พารามิเตอร์" ของ README.md ยังชี้ถูกที่

รัน: python scripts/check_readme_params.py
แต่ละแถวในตารางมีรูปแบบ | `ชื่อ` | [ไฟล์:บรรทัด](ไฟล์#Lบรรทัด) | ... — สคริปต์เปิดไฟล์
แล้วดูว่าบรรทัดนั้นมีชื่อพารามิเตอร์อยู่จริงไหม ถ้าไม่มี (โค้ดเลื่อน) จะบอกบรรทัดใหม่ที่เจอ
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROW = re.compile(r'^\| `([^`]+)` \| \[([^:\]]+):(\d+)\]')


def needle(name):
    """ข้อความที่ต้องเจอในบรรทัด: PARAM_SETS['A'] → 'A':  /  A / B → A"""
    key = re.search(r"\['([^']+)'\]", name)
    if key:
        return f"'{key.group(1)}'"
    return name.split(' /')[0].strip()


def main():
    bad = 0
    for row in (ROOT / 'README.md').read_text(encoding='utf-8').splitlines():
        m = ROW.match(row)
        if not m:
            continue
        name, path, line = m.group(1), m.group(2), int(m.group(3))
        lines = (ROOT / path).read_text(encoding='utf-8').splitlines()
        want = needle(name)
        if line <= len(lines) and want in lines[line - 1]:
            continue
        bad += 1
        found = [i + 1 for i, text in enumerate(lines) if want in text]
        print(f'✗ {name}: {path}:{line} ไม่มี "{want}" — ตอนนี้เจอที่บรรทัด {found[:3] or "ไม่เจอ"}')
    print('ตรงทุกบรรทัด ✓' if not bad else f'{bad} แถวต้องแก้เลขบรรทัด')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
