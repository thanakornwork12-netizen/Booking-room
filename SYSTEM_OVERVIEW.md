# 📚 ระบบจองห้องเรียนและห้องประชุม — ภาพรวมระบบ

**ชื่อเต็ม:** ระบบจองห้องเรียนและห้องประชุมด้วยการพยากรณ์ความต้องการใช้งานด้วยเทคนิค Weighted Averaging Ensemble
**กรณีศึกษา:** สำนักเทคโนโลยีดิจิทัลและทรัพยากรการเรียนรู้

---

## 🧱 สถาปัตยกรรมโดยรวม

```
frontend/ (React 19 + Vite + Tailwind CSS v4)
    │  REST API (axios, JWT)
    ▼
booking/  (Django + Django REST Framework)
    │
    ├── models.py        โมเดลข้อมูลหลัก (User, Room, Booking, TermBooking, MaintenanceBlock, DemandForecast ...)
    ├── views.py          ViewSet ต่างๆ (Room / Booking / TermBooking / MaintenanceBlock / Dashboard / Export)
    ├── serializers.py    Validation + DRF serializers + LDAP login serializer
    ├── ldap_auth.py       เชื่อมต่อ LDAP มหาวิทยาลัยเพื่อยืนยันตัวตน
    ├── signals.py         ส่งอีเมลยืนยัน/ยกเลิกการจอง + broadcast ผ่าน WebSocket (Channels)
    └── management/commands/  คำสั่งเสริม (สร้างแอดมิน, auto no-show ฯลฯ)

ml/saved/  (การพยากรณ์ความต้องการใช้ห้อง)
    └── forecast.py + param_sets.py   เทรน LSTM + LightGBM + XGBoost แบบ Ensemble
```

---

## 🔑 การยืนยันตัวตน (Authentication)

- **หลัก:** LDAP ของมหาวิทยาลัย (Active Directory) — เชื่อมต่อผ่าน **plain LDAP port 389 + STARTTLS** (ไม่ใช่ LDAPS port 636 เพราะพบว่าพอร์ต 636 ไม่เสถียรกับเซิร์ฟเวอร์นี้)
- รองรับกรอกได้ทั้ง **รหัสนักศึกษา** (`6612345678`), **รหัส@ubu.ac.th** และ **อีเมลจริงของมหาวิทยาลัย** (เช่น `firstname.lastname.66@ubu.ac.th`) — ทุกรูปแบบ map กลับไปที่ Django User คนเดียวกันเสมอ (ยึด `sAMAccountName` จาก LDAP เป็นหลัก)
- **สำรอง (fallback):** ถ้า LDAP ล้มเหลว ระบบจะเช็คบัญชี local ที่สมัครผ่านหน้า `/register` แทน — มีประโยชน์เวลาพัฒนา/ทดสอบแบบออฟไลน์ที่ต่อ LDAP มหาวิทยาลัยไม่ได้
- ป้องกัน login ซ้ำซ้อน (double-submit) ทั้งระดับ UI (ref lock) และระดับ API call (module-level dedup ใน `axios.js`)

---

## 📅 ระบบจองห้อง

| ประเภท | คำอธิบาย |
|---|---|
| **จองรายวัน (Dynamic Booking)** | จองห้องแบบครั้งเดียว เลือกวัน/เวลา/ระยะเวลา |
| **จองทั้งเทอม (Term Booking)** | จองห้องซ้ำทุกสัปดาห์ตลอดช่วงเทอม เหมาะกับรายวิชา |
| **จองซ้ำ (Rebook)** | จองห้อง/ข้อมูลเดิมจากประวัติการจองเก่าได้อีกครั้งในวันที่ใหม่ |
| **ปิดซ่อมบำรุง (Maintenance Block)** | แอดมิน/เจ้าหน้าที่ปิดห้องชั่วคราว |

### ป้องกันการจองซ้อน (Overlap Prevention)
- ใช้ `transaction.atomic()` + `Room.objects.select_for_update()` ล็อกแถวห้องก่อนตรวจสอบ กันปัญหา race condition เวลามีคนจองพร้อมกัน
- ตรวจสอบซ้อนกันครบทั้ง 3 ทาง: Booking ↔ Booking, Booking ↔ TermBooking, Booking ↔ MaintenanceBlock (ทั้งสองทิศทาง)
- นับสถานะ `pending` / `approved` / `checked_in` เป็น "ห้องไม่ว่าง" ทั้งหมด
- Serializer มีการตรวจเบื้องต้นอีกชั้น (ก่อนแตะฐานข้อมูลจริง) เพื่อ UX ที่ดี ส่วนชั้นที่ป้องกัน race condition ได้จริงอยู่ที่ views.py

---

## 🤖 การพยากรณ์ความต้องการใช้ห้อง (Demand Forecasting)

- **โมเดล:** Weighted Averaging Ensemble ของ 3 โมเดล — LSTM, LightGBM, XGBoost
- **น้ำหนัก Prior:** LSTM 25% / LightGBM 40% / XGBoost 35% (ปรับจาก 20/40/40 เดิม เพื่อให้ LSTM มีบทบาทจริงในการตัดสินใจ ไม่ใช่แค่ ~1%)
- น้ำหนักจริงต่อห้อง **คำนวณหลังเทรนเสร็จ** จากคะแนนความแม่นยำ (R² และ MAE) ของแต่ละโมเดลในห้องนั้นๆ ไม่ใช่น้ำหนักตายตัว — เป็นระบบ Adaptive Weighting ที่ปรับเชื่อถือโมเดลต่างกันไปตามแต่ละห้อง
- ชุด hyperparameter ที่ทดลอง: A / B / C / **D (ใช้งานจริง)** / E — Set D ให้ความแม่นยำสูงสุดในทุกการทดลอง (Ensemble Accuracy ~0.977)
- ผลการพยากรณ์แสดงเป็น badge ในหน้าค้นหาห้อง: "จองได้เลย" / "ควรจองตอนนี้" / "รีบจองด่วน!"

---

## 🖥️ Frontend

| หน้า | หน้าที่ |
|---|---|
| `LoginPage` | เข้าสู่ระบบผ่าน LDAP/บัญชี local |
| `HomePage` | สรุปการจองของฉัน, จองซ้ำ, การจองรายเทอม |
| `SearchPage` | ค้นหา + จองห้อง (3 ขั้นตอน: ค้นหา → เลือกห้อง → ยืนยัน) |
| `AdminPage` | Dashboard, จัดการห้อง/อาคาร, ดูสถิติ, Export Excel |
| `GuidePage` | คู่มือการใช้งาน |

- ใช้ Tailwind CSS v4 (ผ่าน `@tailwindcss/vite`) ธีมสีน้ำเงิน-ม่วง
- Responsive/mobile-friendly (การ์ดห้องมีรูปประกอบ, ปุ่มขนาดกดง่ายบนมือถือ)
- Auth token เก็บใน localStorage (จำการเข้าสู่ระบบ) หรือ sessionStorage (ไม่จำ) พร้อม auto-refresh token เมื่อหมดอายุ

---

## ⚙️ การรันระบบ (Local Dev)

```bash
# Backend
source tf-env/bin/activate
python manage.py runserver

# Frontend
cd frontend
npm run dev
```

- ฐานข้อมูล default = SQLite (`db.sqlite3`) — ตั้งค่า `DATABASE_URL` เพื่อสลับไป PostgreSQL ได้ (รองรับทั้งคู่ ผ่าน `dj_database_url`)
- ต้องอยู่ในเครือข่ายที่เชื่อมต่อ LDAP มหาวิทยาลัยได้ (`202.28.50.28:389`) จึง login ด้วยบัญชีจริงได้ ถ้าไม่ได้ต่อ ให้ใช้บัญชี local ผ่าน `/register` แทนสำหรับทดสอบออฟไลน์

---

## 📌 หมายเหตุที่ยังค้างอยู่ (Known Follow-ups)

- **[ความปลอดภัย]** หน้า `/register` ยังให้ผู้ใช้เลือก role เป็น `admin`/`staff` เองได้โดยไม่มีการตรวจสอบสิทธิ์ฝั่ง server — ควรบังคับให้สมัครสมาชิกใหม่เป็น `student` เสมอ แล้วให้แอดมินเปลี่ยน role ทีหลังแทน
- `TermBookingCreateSerializer` ยังไม่เช็คซ้อนกับ `Booking`/`MaintenanceBlock` (เช็คซ้อนกับ TermBooking ด้วยกันเองแล้ว)
- `booking/signals.py` ส่งอีเมลจริงผ่าน SMTP (Gmail) ทุกครั้งที่มีการจอง — ควรระวังเวลาทำ bulk operation กับข้อมูลจำนวนมาก (เช่น `loaddata`) เพราะจะยิงอีเมลจริงทุกแถว
