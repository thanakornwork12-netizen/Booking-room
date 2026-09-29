"""วาด ER diagram ของแอป booking แบบ crow's foot ขาวดำ เส้นหักมุมฉากแบบ draw.io

รัน:  tf-env/bin/python scripts/erd_crowsfoot.py            -> erd_crowsfoot.png
      tf-env/bin/python scripts/erd_crowsfoot.py out.png

ตำแหน่งตารางและเส้นทางของทุกเส้นกำหนดเองใน LAYOUT / EDGES เพื่อไม่ให้เส้นซ้อนกัน
(คอลัมน์ในตารางดึงจาก Django models สด ๆ) ถ้าเพิ่ม/ลบ FK ต้องมาเพิ่มเส้นใน EDGES เอง

ความสัมพันธ์ชุดนี้มี K3,3 ซ่อนอยู่ ({user, booking, termbooking} x {bookinglog,
notification, room}) จึงวาดแบบไม่มีเส้นตัดกันเลยไม่ได้ จุดตัดที่เลี่ยงไม่ได้จะวาดเป็น
เส้นกระโดด (line jump) แทนการทับกัน

ปลายเส้น:  ||  = หนึ่งเสมอ   o|  = ศูนย์หรือหนึ่ง (FK null ได้)   >o  = ศูนย์หรือหลายรายการ
"""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402

APP = 'booking'
S = 3            # ตัวคูณความละเอียด
RH = 22          # ความสูงแถว (หน่วย logical)
PAD = 6
FONT = '/System/Library/Fonts/Supplemental/Arial.ttf'
FONT_B = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'

# มุมซ้ายบนของแต่ละตาราง (ชื่อย่อ -> (x, y))
LAYOUT = {
    'notification':     (90, 450),
    'user':             (400, 380),
    'booking':          (820, 40),
    'bookinglog':       (820, 470),
    'termbooking':      (820, 720),
    'room':             (1330, 420),
    'maintenanceblock': (1330, 960),
    'building':         (1780, 442),
    'roomfacility':     (1780, 600),
    'facility':         (2140, 600),
    'demandforecast':   (1780, 750),
    'roomusagestat':    (1780, 1040),
}

# เส้นแต่ละเส้น: (ตารางลูก, คอลัมน์ FK, ด้านที่ออกจากลูก, จุดเลี้ยว, ตารางแม่, ด้านที่เข้าแม่, ตำแหน่งบนด้านแม่)
#   จุดเลี้ยว: ('x', v) = เดินแนวนอนไปที่ x=v, ('y', v) = เดินแนวตั้งไปที่ y=v
#   ตำแหน่งบนด้านแม่: เลขแถว (ด้านซ้าย/ขวา), เศษส่วนความกว้าง (ด้านบน/ล่าง) หรือ None = ตรงกับเส้นที่มา
EDGES = [
    ('booking', 'user_id', 'L', [('x', 730)], 'user', 'R', 1),
    ('booking', 'approved_by_id', 'L', [('x', 760)], 'user', 'R', 2),
    ('booking', 'room_id', 'R', [('x', 1450)], 'room', 'T', None),
    ('termbooking', 'user_id', 'L', [('x', 770)], 'user', 'R', 13),
    ('termbooking', 'approved_by_id', 'L', [('x', 730)], 'user', 'R', 16),
    ('termbooking', 'room_id', 'R', [('x', 1400)], 'room', 'B', None),
    ('bookinglog', 'booking_id', 'R', [('x', 1070)], 'booking', 'R', 16),
    ('bookinglog', 'term_booking_id', 'R', [('x', 1090)], 'termbooking', 'R', 1),
    ('bookinglog', 'changed_by_id', 'L', [], 'user', 'R', None),
    ('notification', 'user_id', 'R', [], 'user', 'L', None),
    ('notification', 'booking_id', 'L', [('x', 30), ('y', 10), ('x', 850)], 'booking', 'T', None),
    ('notification', 'term_booking_id', 'L', [('x', 50), ('y', 1140), ('x', 850)], 'termbooking', 'B', None),
    ('maintenanceblock', 'room_id', 'R', [('x', 1600), ('y', 750), ('x', 1440)], 'room', 'B', None),
    ('maintenanceblock', 'created_by_id', 'L', [('x', 560)], 'user', 'B', None),
    ('room', 'building_id', 'R', [], 'building', 'L', None),
    ('roomfacility', 'room_id', 'L', [], 'room', 'R', None),
    ('roomfacility', 'facility_id', 'R', [], 'facility', 'L', None),
    ('demandforecast', 'room_id', 'L', [('x', 1740)], 'room', 'R', 11),
    ('roomusagestat', 'room_id', 'L', [('x', 1640), ('y', 710), ('x', 1470)], 'room', 'B', None),
]


def load_tables():
    tables = {}
    for m in apps.get_app_config(APP).get_models():
        if m._meta.auto_created:
            continue
        rows = []
        for f in m._meta.concrete_fields:
            key = 'PK' if f.primary_key else ('FK' if f.is_relation else '')
            ftype = f.get_internal_type().replace('Field', '')
            if f.is_relation:
                ftype = f.target_field.get_internal_type().replace('Field', '').replace('Auto', 'Int')
            rows.append((key, f.column, ftype + (' NULL' if f.null else ''), f))
        tables[m._meta.model_name] = {'title': m._meta.db_table, 'rows': rows}
    return tables


def measure(tables, font, font_b):
    for t in tables.values():
        w1 = 30
        w2 = max(font.getlength(r[1]) for r in t['rows']) / S + 2 * PAD
        w3 = max(font.getlength(r[2]) for r in t['rows']) / S + 2 * PAD
        wt = font_b.getlength(t['title']) / S + 2 * PAD
        t['cols'] = [w1, w2, max(w3, wt - w1 - w2)]
        t['w'] = sum(t['cols'])
        t['h'] = RH * (len(t['rows']) + 1)


def row_y(t, idx):
    """y กลางแถว idx (0 = หัวตาราง)"""
    return t['y'] + RH * idx + RH / 2


def anchor(t, side, pos=None, other=None):
    if side in 'LR':
        x = t['x'] if side == 'L' else t['x'] + t['w']
        y = row_y(t, pos) if isinstance(pos, int) else (other if other is not None else t['y'] + t['h'] / 2)
        return (x, y)
    y = t['y'] if side == 'T' else t['y'] + t['h']
    x = t['x'] + t['w'] * pos if isinstance(pos, float) else (other if other is not None else t['x'] + t['w'] / 2)
    return (x, y)


def route(tables, e):
    child, col, cside, vias, parent, pside, ppos = e
    c, p = tables[child], tables[parent]
    idx = 1 + [r[1] for r in c['rows']].index(col)
    pts = [anchor(c, cside, idx)]
    for axis, v in vias:
        x, y = pts[-1]
        pts.append((v, y) if axis == 'x' else (x, v))
    x, y = pts[-1]
    end = anchor(p, pside, ppos, other=(y if pside in 'LR' else x))
    if pside in 'LR':
        if end[1] != y:
            pts.append((x, end[1]))
    else:
        if end[0] != x:
            pts.append((end[0], y))
    pts.append(end)
    # ด้านที่เข้า: ทิศทางชี้เข้าตาราง
    dirs = {'L': (1, 0), 'R': (-1, 0), 'T': (0, 1), 'B': (0, -1)}
    cdir = dirs[cside]
    nullable = next(r[3] for r in c['rows'] if r[1] == col).null
    return pts, cdir, dirs[pside], nullable


def segments(pts):
    return list(zip(pts, pts[1:]))


def crossings(paths):
    """หาจุดที่เส้นแนวนอนตัดเส้นแนวตั้งของเส้นอื่น -> ใส่เส้นกระโดดบนเส้นแนวนอน"""
    jumps = {}
    for i, a in enumerate(paths):
        for (x1, y1), (x2, y2) in segments(a):
            if y1 != y2:
                continue
            for j, b in enumerate(paths):
                if i == j:
                    continue
                for (u1, v1), (u2, v2) in segments(b):
                    if u1 != u2:
                        continue
                    if min(x1, x2) < u1 < max(x1, x2) and min(v1, v2) < y1 < max(v1, v2):
                        jumps.setdefault(i, []).append((u1, y1))
    return jumps


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'erd_crowsfoot.png'
    font = ImageFont.truetype(FONT, 12 * S)
    font_b = ImageFont.truetype(FONT_B, 12 * S)
    tables = load_tables()
    measure(tables, font, font_b)
    for name, (x, y) in LAYOUT.items():
        tables[name]['x'], tables[name]['y'] = x, y

    W = max(t['x'] + t['w'] for t in tables.values()) + 40
    H = max(t['y'] + t['h'] for t in tables.values()) + 40
    img = Image.new('RGB', (int(W * S), int(H * S)), 'white')
    d = ImageDraw.Draw(img)
    s = lambda v: v * S  # noqa: E731
    LW = int(1.3 * S)

    routed = [route(tables, e) for e in EDGES]
    paths = [r[0] for r in routed]
    jumps = crossings(paths)
    JR = 6

    # เส้น
    for i, (pts, cdir, pdir, nullable) in enumerate(routed):
        for (x1, y1), (x2, y2) in segments(pts):
            if y1 == y2 and i in jumps:
                xs = sorted([jx for jx, jy in jumps[i] if jy == y1 and min(x1, x2) < jx < max(x1, x2)])
                cur = min(x1, x2)
                for jx in xs:
                    d.line([s(cur), s(y1), s(jx - JR), s(y1)], fill='black', width=LW)
                    d.arc([s(jx - JR), s(y1 - JR), s(jx + JR), s(y1 + JR)], 180, 360, fill='black', width=LW)
                    cur = jx + JR
                d.line([s(cur), s(y1), s(max(x1, x2)), s(y1)], fill='black', width=LW)
            else:
                d.line([s(x1), s(y1), s(x2), s(y2)], fill='black', width=LW)

    def circle(cx, cy, r=4.5):
        d.ellipse([s(cx - r), s(cy - r), s(cx + r), s(cy + r)], fill='white', outline='black', width=LW)

    def bar(px, py, dx, dy, k, half=7):
        cx, cy = px - dx * k, py - dy * k
        d.line([s(cx - dy * half), s(cy - dx * half), s(cx + dy * half), s(cy + dx * half)], fill='black', width=LW)

    for pts, cdir, pdir, nullable in routed:
        # ฝั่งลูก: ศูนย์หรือหลายรายการ (crow + วงกลม)
        (ex, ey), (dx, dy) = pts[0], cdir
        dx, dy = -dx, -dy  # ชี้ออกจากตาราง
        base = (ex + dx * 14, ey + dy * 14)
        for off in (-7, 0, 7):
            d.line([s(base[0]), s(base[1]), s(ex + dy * off), s(ey + dx * off)], fill='black', width=LW)
        circle(ex + dx * 20, ey + dy * 20)
        # ฝั่งแม่: หนึ่งเสมอ (||) หรือศูนย์หรือหนึ่ง (o|)
        (ex, ey), (dx, dy) = pts[-1], pdir
        bar(ex, ey, dx, dy, 8)
        if nullable:
            circle(ex - dx * 18, ey - dy * 18)
        else:
            bar(ex, ey, dx, dy, 14)

    # ตาราง
    for t in tables.values():
        x, y, w = t['x'], t['y'], t['w']
        d.rectangle([s(x), s(y), s(x + w), s(y + t['h'])], fill='white', outline='black', width=LW)
        d.text((s(x + w / 2), s(y + RH / 2)), t['title'], font=font_b, fill='black', anchor='mm')
        d.line([s(x), s(y + RH), s(x + w), s(y + RH)], fill='black', width=LW)
        c1, c2 = x + t['cols'][0], x + t['cols'][0] + t['cols'][1]
        d.line([s(c1), s(y + RH), s(c1), s(y + t['h'])], fill='black', width=max(1, LW // 2))
        d.line([s(c2), s(y + RH), s(c2), s(y + t['h'])], fill='black', width=max(1, LW // 2))
        for i, (key, colname, ftype, _) in enumerate(t['rows'], start=1):
            cy = row_y(t, i)
            if i > 1:
                d.line([s(x), s(y + RH * i), s(x + w), s(y + RH * i)], fill='#999999', width=max(1, LW // 3))
            if key:
                d.text((s(x + t['cols'][0] / 2), s(cy)), key, font=font_b, fill='black', anchor='mm')
            d.text((s(c1 + PAD), s(cy)), colname, font=font_b if key == 'PK' else font, fill='black', anchor='lm')
            d.text((s(c2 + PAD), s(cy)), ftype, font=font, fill='black', anchor='lm')

    img.save(target, dpi=(300, 300))
    print(f'saved {target}  ({len(sum(jumps.values(), []))} line jump)')
    for name, t in tables.items():
        print(f"  {name:17s} x={t['x']:5} y={t['y']:5} w={t['w']:6.0f} h={t['h']:4}")


if __name__ == '__main__':
    main()
