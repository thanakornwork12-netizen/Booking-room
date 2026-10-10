# ระบบจองห้องเรียน/ห้องประชุม + AI พยากรณ์ความต้องการ

ระบบจองห้องของสำนักคอมพิวเตอร์และเครือข่าย มหาวิทยาลัยอุบลราชธานี: จองรายครั้ง จองทั้งเทอม
อนุมัติ เช็คอิน ปิดซ่อมบำรุง และใช้ AI พยากรณ์ว่าห้องไหนช่วงไหนคนจะจองเยอะ

เอกสารนี้ตอบคำถามเดียว: **อยากแก้ค่าอะไร ต้องไปแก้ไฟล์ไหน บรรทัดไหน**
(อธิบายระบบละเอียดสำหรับสอบอยู่ที่ [exam_guide.html](exam_guide.html))

## โครงสร้างโปรเจกต์

| โฟลเดอร์ / ไฟล์ | คืออะไร |
|---|---|
| [room_booking/settings.py](room_booking/settings.py) | ตั้งค่า Django: ฐานข้อมูล, อีเมล, JWT, กฎที่ตั้งผ่าน env ได้ |
| [booking/config.py](booking/config.py) | **ค่าที่ปรับได้ของระบบจอง** รวมไว้ที่เดียว |
| [booking/models.py](booking/models.py) | ตารางฐานข้อมูล (11 ตาราง) |
| [booking/views.py](booking/views.py) | API ทั้งหมด (ค้นหา จอง อนุมัติ ยกเลิก แดชบอร์ด export) |
| [booking/serializers.py](booking/serializers.py) | ตรวจข้อมูลที่ส่งเข้ามา (กฎการจอง, รหัสผ่าน, ล็อกอิน LDAP) |
| [booking/overlap.py](booking/overlap.py) | ตรวจการจองชนกัน (รายครั้ง / ทั้งเทอม / ช่วงซ่อม) |
| [booking/signals.py](booking/signals.py) | ส่งอีเมลเมื่อสถานะการจองเปลี่ยน |
| [booking/scheduler.py](booking/scheduler.py) | งานเบื้องหลัง: อีเมลเตือนก่อนเช็คอิน และอัปเดตสถานะช่วงซ่อม |
| [booking/throttles.py](booking/throttles.py) | จำกัดการยิงล็อกอิน/ลืมรหัสผ่านซ้ำ |
| [booking/maintenance.py](booking/maintenance.py) | ปิดช่วงซ่อมที่หมดเวลา และตั้งสถานะห้องตามช่วงซ่อม |
| [frontend/src/config.js](frontend/src/config.js) | **ค่าที่ปรับได้ของหน้าเว็บ** รวมไว้ที่เดียว |
| [frontend/src/pages/](frontend/src/pages/) | หน้าเว็บแต่ละหน้า (React) |
| [ml/saved/forecast.py](ml/saved/forecast.py) | AI ที่ใช้งานจริง: เทรน + เขียนผลพยากรณ์ลงฐานข้อมูล |
| [ml/saved/param_sets.py](ml/saved/param_sets.py) | ชุด hyperparameter A–F ของ forecast.py |
| [ml/saved/direct_forecast.py](ml/saved/direct_forecast.py) | AI งานวิจัย (direct multi-horizon) |

## รันในเครื่อง

```bash
# backend (ใช้ PostgreSQL ตาม DATABASE_URL ใน .env)
source tf-env/bin/activate
python manage.py migrate
python manage.py runserver

# หน้าเว็บ
cd frontend && npm run dev

# test ทั้งหมด (ควรผ่านทุกครั้งหลังแก้ค่า)
python manage.py test booking --noinput
```

## แก้พารามิเตอร์

> เลขบรรทัดตรงกับโค้ด ณ วันที่ 10/10/2026 (commit `e3a2486` + การแก้ในเครื่อง) ถ้าบรรทัดเลื่อน
> ให้ค้นด้วยชื่อพารามิเตอร์ (`Ctrl+F` / `grep -n ชื่อ ไฟล์`) แล้วรัน
> `python scripts/check_readme_params.py` เพื่อเช็คว่าเลขบรรทัดใน README ยังตรงไหม

### 1. กฎการจองและระบบ — `room_booking/settings.py`

ค่ากลุ่มนี้ตั้งผ่าน environment variable ได้ (บน Render ตั้งในหน้า Environment ไม่ต้องแก้โค้ด)
แก้แล้วต้องรีสตาร์ต server

| พารามิเตอร์ | ไฟล์:บรรทัด | ค่าตอนนี้ | ทำอะไร | แก้แล้วต้องทำอะไรต่อ |
|---|---|---|---|---|
| `MAX_BOOKING_DAYS` | [room_booking/settings.py:237](room_booking/settings.py#L237) | `21` | จองรายครั้งได้ยาวสุดกี่วันต่อครั้ง | ตั้งผ่าน env `MAX_BOOKING_DAYS` ได้ |
| `MAX_TERM_BOOKING_DAYS` | [room_booking/settings.py:239](room_booking/settings.py#L239) | `366` | จองทั้งเทอมได้ยาวสุดกี่วัน | ตั้งผ่าน env `MAX_TERM_BOOKING_DAYS` ได้ |
| `MAX_ADVANCE_BOOKING_DAYS` | [room_booking/settings.py:242](room_booking/settings.py#L242) | `365` | จองล่วงหน้าได้ไกลสุดกี่วัน (ใช้เป็นเพดาน days ของหน้าหาช่วงซ่อมด้วย) | ตั้งผ่าน env `MAX_ADVANCE_BOOKING_DAYS` ได้ |
| `BOOKING_THROTTLE_RATES['login']` | [room_booking/settings.py:233](room_booking/settings.py#L233) | `(10, 5 * 60) = 10 ครั้ง / 5 นาที` | ล็อกอินได้กี่ครั้งภายในกี่วินาที ต่อบัญชี | นับต่อบัญชี ไม่ใช่ต่อ IP (NAT ทั้งตึก) |
| `BOOKING_THROTTLE_RATES['password_reset']` | [room_booking/settings.py:234](room_booking/settings.py#L234) | `(3, 60 * 60) = 3 ครั้ง / ชม.` | ขอลิงก์รีเซ็ตรหัสได้กี่ครั้งภายในกี่วินาที ต่อบัญชี |  |
| `AUTH_PASSWORD_VALIDATORS` | [room_booking/settings.py:154](room_booking/settings.py#L154) | `4 ตัวตรวจของ Django` | กฎรหัสผ่าน (ยาว ≥8, ไม่เป็นเลขล้วน, ไม่ใช่รหัสยอดนิยม, ไม่คล้ายชื่อ) | ถ้าเปลี่ยนความยาว แก้ `PASSWORD_MIN_LENGTH` หน้าเว็บ และข้อความใน `_PASSWORD_ERRORS` (booking/serializers.py) |
| `ACCESS_TOKEN_LIFETIME` | [room_booking/settings.py:199](room_booking/settings.py#L199) | `1 วัน` | token เข้าระบบใช้ได้นานเท่าไร |  |
| `REFRESH_TOKEN_LIFETIME` | [room_booking/settings.py:200](room_booking/settings.py#L200) | `30 วัน` | ไม่ต้องล็อกอินใหม่ได้นานสุดเท่าไร |  |
| `PAGE_SIZE` | [room_booking/settings.py:194](room_booking/settings.py#L194) | `20` | รายการต่อหน้าของ API ที่แบ่งหน้า | หน้าเว็บบางหน้าดึงทีละหน้า |
| `APPROVER_EMAIL` | [room_booking/settings.py:225](room_booking/settings.py#L225) | `thanakorn.tho.66@ubu.ac.th` | อีเมลผู้อนุมัติที่ได้รับแจ้งคำขอจองใหม่ | ตั้งผ่าน env `APPROVER_EMAIL` ได้ |
| `EMAIL_HOST_USER` | [room_booking/settings.py:217](room_booking/settings.py#L217) | `nookkup47@gmail.com` | อีเมลผู้ส่ง | ส่งจริงผ่าน Brevo (env `BREVO_API_KEY`) |
| `SITE_URL / FRONTEND_URL` | [room_booking/settings.py:244](room_booking/settings.py#L244) | `http://127.0.0.1:8000` | URL ที่ใส่ในลิงก์อีเมล (เช็คอิน/ยกเลิก/รีเซ็ตรหัส) | FRONTEND_URL อยู่บรรทัดถัดไป บน server ต้องตั้ง env เป็น URL จริง |
| `ALLOWED_HOSTS` | [room_booking/settings.py:43](room_booking/settings.py#L43) | `['room-booking-1-7u7e.onrender.com', 'localhost', '127.0.0.1', '*']` | โดเมนที่ backend รับ request |  |
| `CORS_ALLOWED_ORIGINS` | [room_booking/settings.py:136](room_booking/settings.py#L136) | `[...]` | โดเมนหน้าเว็บที่เรียก API ได้ | เปลี่ยนโดเมนหน้าเว็บต้องเพิ่มที่นี่ |
| `AUTH_LDAP_SERVER_HOST` | [room_booking/settings.py:247](room_booking/settings.py#L247) | `'202.28.50.28'` | เซิร์ฟเวอร์ LDAP ของมหาวิทยาลัย | OU ที่ค้นอยู่บรรทัดถัดไป |
| `TIME_ZONE` | [room_booking/settings.py:170](room_booking/settings.py#L170) | `'Asia/Bangkok'` | เขตเวลาของระบบ | ห้ามเปลี่ยน — ทุกกฎเรื่องวัน/เวลาคิดตามเวลาไทย |

### 2. ค่าการทำงานของระบบจอง — `booking/config.py`

| พารามิเตอร์ | ไฟล์:บรรทัด | ค่าตอนนี้ | ทำอะไร | แก้แล้วต้องทำอะไรต่อ |
|---|---|---|---|---|
| `AI_FORECAST_ROOM_IDS` | [booking/config.py:13](booking/config.py#L13) | `{443, 445, 446, 447, 448, 487, 505, 506}` | ห้องที่ผู้ใช้ทั่วไปค้นหา/จองได้ (ห้องที่ AI พยากรณ์ได้) | ถ้าจะให้ AI พยากรณ์ห้องใหม่ เพิ่มใน `ROOM_IDS` ของ ml/saved/direct_forecast.py ด้วย |
| `BUILDING_CLOSING_TIME` | [booking/config.py:16](booking/config.py#L16) | `time(21, 0)` | เวลาปิดอาคาร ใช้แสดง "ว่างถึงกี่โมง" ในฟีดหน้าแรก | ไม่ได้บังคับตอนจอง |
| `CHECKIN_OPENS_MINUTES_BEFORE` | [booking/config.py:19](booking/config.py#L19) | `15` | เช็คอินได้ก่อนเวลาเริ่มกี่นาที | แก้ค่าเดียวกันใน frontend/src/config.js |
| `REMINDER_MINUTES_BEFORE` | [booking/config.py:20](booking/config.py#L20) | `15` | ส่งอีเมลเตือนก่อนเวลาเริ่มกี่นาที | ข้อความในอีเมลเปลี่ยนตามเอง |
| `REMINDER_CHECK_EVERY_MINUTES` | [booking/config.py:21](booking/config.py#L21) | `1` | งานเบื้องหลังตรวจหาการจองที่ต้องเตือนทุกกี่นาที | ต้องรีสตาร์ต server |
| `STARTING_SOON_MINUTES` | [booking/config.py:24](booking/config.py#L24) | `30` | จะเริ่มภายในกี่นาทีนับเป็น "จะเริ่มเร็วๆ" | แก้ค่าเดียวกันใน frontend/src/config.js |
| `DEMAND_LEVEL_THRESHOLDS` | [booking/config.py:29](booking/config.py#L29) | `0.70 / 0.50 / 0.30` | เกณฑ์ค่าพยากรณ์ → ระดับ urgent / high / medium | test `DemandLevelTests` ใน booking/tests_admin.py ล็อกเกณฑ์ไว้ ต้องแก้ตาม |
| `TODAY_FEED_DEFAULT_LIMIT` | [booking/config.py:36](booking/config.py#L36) | `5` | ฟีด "ห้องว่างวันนี้" หน้าแรกโชว์กี่ห้อง |  |
| `SIMILAR_ROOMS_MAX` | [booking/config.py:37](booking/config.py#L37) | `8` | แนะนำห้องใกล้เคียงได้มากสุดกี่ห้อง |  |
| `NEARBY_TIME_OFFSETS_MINUTES` | [booking/config.py:38](booking/config.py#L38) | `(30, -30, 60, -60)` | ถ้าเวลาเดิมไม่ว่าง ลองเลื่อนกี่นาที (ตามลำดับ) |  |
| `OTHER_DAY_OFFSETS` | [booking/config.py:39](booking/config.py#L39) | `(1, 2, 3)` | ถ้าวันเดิมไม่มีห้อง ลองวันถัดไปกี่วัน |  |
| `SPLIT_ROOMS_PER_HALF` | [booking/config.py:40](booking/config.py#L40) | `8` | แผนจองสลับห้อง: ห้องที่พิจารณาต่อครึ่งเทอม |  |
| `SPLIT_SUGGESTIONS_MAX` | [booking/config.py:41](booking/config.py#L41) | `8` | แผนจองสลับห้อง: ส่งกลับกี่แผน |  |
| `MAINTENANCE_MAX_DEMAND` | [booking/config.py:44](booking/config.py#L44) | `0.10` | หาช่วงปิดซ่อม: demand ต่ำกว่านี้นับว่าว่าง | ค่าเริ่มต้น แอดมินส่งค่าอื่นทาง URL ได้ |
| `MAINTENANCE_MIN_HOURS` | [booking/config.py:45](booking/config.py#L45) | `3` | หาช่วงปิดซ่อม: ต้องว่างติดกันอย่างน้อยกี่ชั่วโมง | ค่าเริ่มต้น |
| `MAINTENANCE_DAYS_AHEAD` | [booking/config.py:46](booking/config.py#L46) | `14` | หาช่วงปิดซ่อม: มองล่วงหน้ากี่วัน | ค่าเริ่มต้น |
| `MAINTENANCE_SYNC_EVERY_MINUTES` | [booking/config.py:47](booking/config.py#L47) | `1` | งานเบื้องหลังปิดช่วงซ่อมที่หมดเวลาและอัปเดตสถานะห้องทุกกี่นาที | ต้องรีสตาร์ต server |

### 3. หน้าเว็บ — `frontend/src/config.js`

แก้แล้วต้อง build ใหม่ (`npm run build`) หรือ deploy หน้าเว็บใหม่

| พารามิเตอร์ | ไฟล์:บรรทัด | ค่าตอนนี้ | ทำอะไร | แก้แล้วต้องทำอะไรต่อ |
|---|---|---|---|---|
| `DEFAULT_API_URL` | [frontend/src/config.js:6](frontend/src/config.js#L6) | `'http://127.0.0.1:8000/api/'` | URL ของ backend ตอนรันในเครื่อง | บน server ตั้ง env `VITE_API_URL` แทน |
| `REQUEST_TIMEOUT_MS` | [frontend/src/config.js:8](frontend/src/config.js#L8) | `60000` | รอ backend ตอบนานสุดกี่มิลลิวินาที | Render หลับแล้วตื่นช้า อย่าตั้งต่ำ |
| `SLOW_REQUEST_MS` | [frontend/src/config.js:10](frontend/src/config.js#L10) | `4000` | ช้ากว่านี้ขึ้นแถบ "เซิร์ฟเวอร์กำลังตื่น" |  |
| `TIME_SLOTS` | [frontend/src/config.js:14](frontend/src/config.js#L14) | `['08:00', '09:00', '10:00', '11:00', '13:00', '14:00', '15:00', '16:00']` | ปุ่มเวลาเริ่มในหน้าค้นหา |  |
| `DURATIONS` | [frontend/src/config.js:16](frontend/src/config.js#L16) | `1 / 2 / 3 ชม.` | ปุ่มระยะเวลาจอง (ชม.) | กำหนดเองได้อีกทางผ่านปุ่ม "กำหนดเอง" |
| `CHECKIN_OPENS_MINUTES_BEFORE` | [frontend/src/config.js:24](frontend/src/config.js#L24) | `15` | ปุ่มเช็คอินขึ้นก่อนเวลาเริ่มกี่นาที | ต้องตรงกับ booking/config.py |
| `CHECKIN_BUTTON_MINUTES_AFTER` | [frontend/src/config.js:26](frontend/src/config.js#L26) | `15` | ปุ่มเช็คอินโชว์ถึงกี่นาทีหลังเวลาเริ่ม | backend รับเช็คอินได้ถึงเวลาจบ (ดู "เรื่องที่ควรรู้") |
| `STARTING_SOON_MINUTES` | [frontend/src/config.js:29](frontend/src/config.js#L29) | `30` | หน้าแอดมิน: "จะเริ่มเร็วๆ" ภายในกี่นาที | ต้องตรงกับ booking/config.py |
| `ADMIN_STATUS_REFRESH_MS` | [frontend/src/config.js:31](frontend/src/config.js#L31) | `30000` | หน้าแอดมินคำนวณสถานะห้องใหม่ทุกกี่มิลลิวินาที |  |
| `PASSWORD_MIN_LENGTH` | [frontend/src/config.js:35](frontend/src/config.js#L35) | `8` | ตรวจความยาวรหัสผ่านก่อนส่ง | ต้องตรงกับ `AUTH_PASSWORD_VALIDATORS` ฝั่ง server |

### 4. AI ที่ใช้งานจริง — `ml/saved/forecast.py` และ `ml/saved/param_sets.py`

| พารามิเตอร์ | ไฟล์:บรรทัด | ค่าตอนนี้ | ทำอะไร | แก้แล้วต้องทำอะไรต่อ |
|---|---|---|---|---|
| `CURRENT_PARAM_SET` | [ml/saved/forecast.py:150](ml/saved/forecast.py#L150) | `'D'` | ชุด hyperparameter ที่ใช้ตอน retrain (A–E) | หรือส่ง `--param-set X` ตอนรันแทนการแก้ไฟล์ |
| `SKIP_LSTM` | [ml/saved/forecast.py:106](ml/saved/forecast.py#L106) | `True` | ข้าม LSTM (ใช้แค่ LightGBM + XGBoost) | production ใช้แค่ LGB+XGB |
| `FORECAST_DAYS` | [ml/saved/forecast.py:143](ml/saved/forecast.py#L143) | `14` | พยากรณ์ล่วงหน้ากี่วัน ลงตาราง DemandForecast |  |
| `MIN_DAYS` | [ml/saved/forecast.py:141](ml/saved/forecast.py#L141) | `30` | ห้องต้องมีการจองอย่างน้อยกี่รายการถึงจะเทรน |  |
| `MIN_UNIQUE_DAYS` | [ml/saved/forecast.py:142](ml/saved/forecast.py#L142) | `14` | ห้องต้องมีวันที่ใช้งานอย่างน้อยกี่วัน |  |
| `TRAIN_FRAC / CALIB_FRAC` | [ml/saved/forecast.py:366](ml/saved/forecast.py#L366) | `0.70 / 0.10` | สัดส่วนแบ่งข้อมูล train / calibration (ที่เหลือ 20% = test) | CALIB_FRAC อยู่บรรทัดถัดไป |
| `LGB_WEIGHT_PRIOR / XGB_WEIGHT_PRIOR` | [ml/saved/forecast.py:354](ml/saved/forecast.py#L354) | `0.50 / 0.50` | น้ำหนักเริ่มต้นของ LightGBM / XGBoost ใน ensemble | XGB อยู่บรรทัดถัดไป |
| `LABEL_BUFFER / LABEL_MED_BUFFER` | [ml/saved/forecast.py:361](ml/saved/forecast.py#L361) | `0.03 / 0.06` | ความไวตอนแปลงค่าพยากรณ์เป็นระดับ | MED อยู่บรรทัดถัดไป |
| `ROOM_OPEN_HOUR / ROOM_CLOSE_HOUR` | [ml/saved/forecast.py:374](ml/saved/forecast.py#L374) | `8 / 20 (08:00–20:00)` | ช่วงเวลาที่นับการใช้ห้องในข้อมูลเทรน | CLOSE อยู่บรรทัดถัดไป |
| `DISABLE_EARLY_STOPPING` | [ml/saved/forecast.py:166](ml/saved/forecast.py#L166) | `True` | เทรนครบทุกรอบแล้วเลือกรอบที่ดีที่สุดภายหลัง | หรือส่ง `--enable-early-stop` |
| `PARAM_SETS` | [ml/saved/param_sets.py:31](ml/saved/param_sets.py#L31) | `{...}` | ค่า hyperparameter ของชุด A, A_REG, B, C, D, E, F | ดู "แก้ hyperparameter" ด้านล่าง |
| `PARAM_SETS['A']` | [ml/saved/param_sets.py:35](ml/saved/param_sets.py#L35) | ดูในไฟล์ | ต้นไม้/learning rate/regularization ของชุด A | |
| `PARAM_SETS['B']` | [ml/saved/param_sets.py:61](ml/saved/param_sets.py#L61) | ดูในไฟล์ | ต้นไม้/learning rate/regularization ของชุด B | |
| `PARAM_SETS['C']` | [ml/saved/param_sets.py:73](ml/saved/param_sets.py#L73) | ดูในไฟล์ | ต้นไม้/learning rate/regularization ของชุด C | |
| `PARAM_SETS['D']` | [ml/saved/param_sets.py:100](ml/saved/param_sets.py#L100) | ดูในไฟล์ | ต้นไม้/learning rate/regularization ของชุด D | |
| `PARAM_SETS['E']` | [ml/saved/param_sets.py:113](ml/saved/param_sets.py#L113) | ดูในไฟล์ | ต้นไม้/learning rate/regularization ของชุด E | |

**แก้ hyperparameter (`PARAM_SETS`)**
1. แก้ค่าในชุดที่ต้องการใน [ml/saved/param_sets.py](ml/saved/param_sets.py) (`forecast.py` กับ `plotting.py` อ่านจากไฟล์นี้ที่เดียว)
2. เทรนใหม่: `python ml/saved/forecast.py --retrain --param-set D`
3. **ตาราง/กราฟ/ตัวเลขที่สร้างจากผลเทรนต้องสร้างใหม่ทุกชิ้น** (ไฟล์ใน `ml/saved/metrics_plots/` และตัวเลขใน exam_guide.html) ไม่งั้นตัวเลขในเล่มจะไม่ตรงกับโมเดล
4. production ใช้แค่ LightGBM + XGBoost (`SKIP_LSTM = True`) ค่า `lstm_*` ในแต่ละชุดจึงไม่มีผล

### 5. AI งานวิจัย (direct) — `ml/saved/direct_forecast.py`, `train_direct_sets.py`, `train_direct.py`

| พารามิเตอร์ | ไฟล์:บรรทัด | ค่าตอนนี้ | ทำอะไร | แก้แล้วต้องทำอะไรต่อ |
|---|---|---|---|---|
| `HORIZON` | [ml/saved/direct_forecast.py:43](ml/saved/direct_forecast.py#L43) | `14` | พยากรณ์ล่วงหน้ากี่วัน (โมเดล direct) |  |
| `MIN_HISTORY` | [ml/saved/direct_forecast.py:61](ml/saved/direct_forecast.py#L61) | `400` | ต้องมีข้อมูลย้อนหลังกี่วันก่อนเริ่มพยากรณ์ |  |
| `QUANTILES` | [ml/saved/direct_forecast.py:62](ml/saved/direct_forecast.py#L62) | `(0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95)` | quantile ที่โมเดลทำนาย |  |
| `CALIB_FRACTION` | [ml/saved/direct_forecast.py:63](ml/saved/direct_forecast.py#L63) | `0.125` | สัดส่วนข้อมูล calibration |  |
| `ROOM_IDS` | [ml/saved/direct_forecast.py:65](ml/saved/direct_forecast.py#L65) | `{...8 ห้อง}` | ห้องที่โมเดล direct เทรน (ชื่อ → id) | ต้องตรงกับ `AI_FORECAST_ROOM_IDS` ใน booking/config.py |
| `SETS` | [ml/saved/train_direct_sets.py:97](ml/saved/train_direct_sets.py#L97) | `{...}` | ชุด A–D ของโมเดล direct (rounds × lr = 24 เท่ากันทุกชุด) | แก้ rounds ต้องแก้ lr ให้คูณได้เท่าเดิม |
| `LGB_GRID / XGB_GRID` | [ml/saved/train_direct.py:85](ml/saved/train_direct.py#L85) | `{...}` | รายละเอียดต้นไม้ของแต่ละ grid_key ที่ SETS อ้างถึง | XGB_GRID อยู่ต่อจากนี้ |
| `N_ESTIMATORS` | [ml/saved/train_direct.py:72](ml/saved/train_direct.py#L72) | `1200` | จำนวนต้นไม้สูงสุดของ train_direct.py |  |

## ค่าที่ต้องแก้คู่กัน

| ถ้าแก้ | ต้องแก้ที่นี่ด้วย |
|---|---|
| `CHECKIN_OPENS_MINUTES_BEFORE` (booking/config.py) | `CHECKIN_OPENS_MINUTES_BEFORE` (frontend/src/config.js) |
| `STARTING_SOON_MINUTES` (booking/config.py) | `STARTING_SOON_MINUTES` (frontend/src/config.js) |
| `AI_FORECAST_ROOM_IDS` (booking/config.py) | `ROOM_IDS` (ml/saved/direct_forecast.py) ถ้าจะให้ AI พยากรณ์ห้องนั้น |
| ความยาวรหัสผ่านใน `AUTH_PASSWORD_VALIDATORS` | `PASSWORD_MIN_LENGTH` (frontend) + ข้อความ `_PASSWORD_ERRORS` (booking/serializers.py) |
| `DEMAND_LEVEL_THRESHOLDS` | test `DemandLevelTests` (booking/tests_admin.py) |
| `PARAM_SETS` | เทรนใหม่ + สร้างตาราง/กราฟใหม่ทั้งหมด |
| rounds ใน `SETS` (train_direct_sets.py) | lr ให้ rounds × lr = 24 เท่าเดิม |

## เรื่องที่ควรรู้ (พบตอนทำความสะอาดโค้ด ยังไม่ได้เปลี่ยน)

- **ปุ่มเช็คอินหายเร็วกว่าที่ backend อนุญาต:** หน้าเว็บโชว์ปุ่มถึง 15 นาทีหลังเวลาเริ่ม (`CHECKIN_BUTTON_MINUTES_AFTER`) แต่ backend รับเช็คอินได้ถึงเวลาจบการจอง คนที่มาสายเกิน 15 นาทีจะไม่เห็นปุ่ม ถ้าต้องการให้ตรงกัน แก้ค่านี้หรือเพิ่มกฎฝั่ง backend
- **โค้ด ML ที่เรียกฟังก์ชันที่ไม่มีอยู่จริง** (มีมาตั้งแต่ใน git ไม่เคยมีคนเรียกถึง): `--roomcurve` ใน ml/saved/analyze_adaptive_weights_all_sets.py เรียก `plot_per_room_accuracy_curve` และ ml/saved/plotting.py เรียก `_room_labels_from_metas` เมื่อส่ง `room_metas` เข้ามา ถ้าเรียกสองทางนี้จะ error
