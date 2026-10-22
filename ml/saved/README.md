# ml/saved/ — คู่มือโฟลเดอร์

โฟลเดอร์นี้เก็บทั้งโมเดล AI ที่ระบบใช้งานจริง และไฟล์ทดลอง/วิเคราะห์ของทีม ML
`saved_meta*` และ `saved_models*` ทั้งหมดอยู่ใน `.gitignore` (ไม่ถูก commit) — ลบ/ย้ายได้โดยไม่กระทบ git history

## โมเดลที่ใช้งานจริง (production)

- **`serve_direct.py`** — โหลด **`saved_direct_sets/C/model.pkl`** + **`saved_meta_C_direct/`** แล้วเขียนผลพยากรณ์ลง `DemandForecast` ห้ามลบ/ย้าย
- **`train_direct_sets.py`** / **`test_direct_sets.py`** — เทรน/ทดสอบชุด A–D ของ direct pipeline (เขียนลง `saved_direct_sets/{A-D}/`, `saved_meta_{A-D}_direct/`)
- **`direct_forecast.py`**, **`forecast.py`** — ไลบรารีที่สองสคริปต์ข้างบน import (ฟีเจอร์, threshold, metrics) — `MODEL_DIR`/`META_DIR` ใน `forecast.py` ไม่ได้ถูกใช้ในระบบจริงแล้ว

## ผลทดลองที่ยังอ้างอิงอยู่

- **`saved_models_{A-F}_excel_split/`, `saved_meta_{A-F}_excel_split/`** — ชุดทดลองแยก train/test ตาม Excel ใช้โดย `train_from_excel.py`, `test_from_excel.py`, `plot_*_by_set.py`, `plot_train_vs_test_gap.py`, `consolidate_results.py`, `build_adaptive_vs_fixed_current.py`
- **`saved_meta/`, `saved_meta_{A-E}/`, `saved_meta_{A-E}_new/`** — log/ประวัติการเทรนยุค LSTM (ไม่มีไฟล์โมเดลแล้ว) ใช้โดย `compare_hyperparams.py`, `param_sets.py`, `plotting.py`
- **`blocked_calib/saved_meta_*_direct/`** — ผลทดลอง blocked calibration (ใช้โดย `plot_blocked_vs_contiguous.py`)
- **`archive/`** — สคริปต์ยุค LSTM ที่รันไม่ได้แล้ว ดู `archive/README.md`

## อื่นๆ

- **`metrics_plots/`** — รูป PNG ผลลัพธ์ทั้งหมด (กราฟ accuracy/loss/comparison)
- **`data_split/`** — ไฟล์ข้อมูล train/test ที่แบ่งไว้แล้ว
- **`test_only_results.csv`** — ผล Test accuracy ล่าสุดของแต่ละชุด A–E (ที่มาของตัวเลขในกราฟเปรียบเทียบ)
- **`docs/archive_lstm/`** (ที่ root) — เอกสาร/สรุป LSTM เดิม รวม `lstm_summary.txt`

## ประวัติการล้าง (2026-10-22)

ย้ายไฟล์โมเดลที่ไม่มีระบบจริงโหลดแล้วไปถังขยะ (`~/.Trash/room_booking_cleanup_20261022/`) รวม ~25GB:
`saved_models_{A,B,C}/`, `saved_models_{A-E}_new/`, `saved_models/` (และ `/saved_models` ที่ root) — โมเดล LSTM/LGB/XGB ยุคก่อน direct pipeline,
`blocked_calib/saved_direct_sets/`, `runs/backup_before_room_engine/saved_direct_sets/` (โมเดลของการทดลองที่ไม่ได้เลือก — เก็บ meta/CSV ไว้),
`ml_models_backup_20260803_075701.zip`, `db.sqlite3.backup_20260814_020221` ที่ root
โฟลเดอร์ `saved_meta*` (log การเทรน) เก็บไว้ทั้งหมด

## ประวัติการล้าง (2026-08-25)

ลบโฟลเดอร์ที่ไม่มีสคริปต์ไหนอ้างอิงแล้วออก รวม ~7.4GB:
`saved_models_backup_pretrain4_20260807`, `saved_models_backup_before_A_C`, `saved_models_backup_B`,
`saved_meta_backup_pretrain4_20260807`, `saved_meta_backup_before_A_C`, `saved_meta_backup_B`, `saved_meta_backup` (backup ที่ `run_abcd_experiment.sh` สร้างไว้ก่อนรันแต่ละครั้ง หมดอายุการใช้งานแล้ว),
`saved_models_A_real`, `saved_meta_A_real` (ทดลองเก่า ไม่มีการอ้างอิง),
โฟลเดอร์ `room_XXX/` เดี่ยวๆ 78 อัน (~30MB, cache โมเดลของห้องเก่าที่ถูกลบออกจากฐานข้อมูลแล้ว ไม่ตรงกับ 8 ห้องจริงที่ใช้ AI), โฟลเดอร์ว่างเปล่า 4 อัน, และไฟล์เดี่ยว `lstm_model.keras`/`scaler.pkl` ที่หลงเหลือจากรูปแบบเดิมช่วงเดียวกัน (ไม่มีสคริปต์ไหนอ้างอิง)
