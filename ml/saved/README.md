# ml/saved/ — คู่มือโฟลเดอร์

โฟลเดอร์นี้เก็บทั้งโมเดล AI ที่ระบบใช้งานจริง และไฟล์ทดลอง/วิเคราะห์ของทีม ML
`saved_meta*` และ `saved_models*` ทั้งหมดอยู่ใน `.gitignore` (ไม่ถูก commit) — ลบ/ย้ายได้โดยไม่กระทบ git history

## โมเดลที่ใช้งานจริง (production)

- **`saved_models/`, `saved_meta/`** — โมเดลจริงที่ `forecast.py` โหลดมาใช้พยากรณ์ในเว็บ (`MODEL_DIR`/`META_DIR`) ห้ามลบ/ย้าย
- **`forecast.py`** — สคริปต์เทรน/รันโมเดลจริง เรียกผ่าน `booking/scheduler.py` (`ml/saved/forecast.py --retrain`)

## ชุดทดลอง A–E (คำสั่ง run_abcd_experiment.sh)

- **`saved_models_{A-E}/`, `saved_meta_{A-E}/`** — ผลเทรนชุดไฮเปอร์พารามิเตอร์ A–E เวอร์ชันแรก ใช้โดย `compare_hyperparams.py`
- **`saved_models_{A-E}_new/`, `saved_meta_{A-E}_new/`** — อาร์ไคฟ์ผลเทรน A–E ที่ "แช่แข็ง" ไว้ ใช้โดย `analyze_adaptive_weights_all_sets.py`, `analyze_ensemble_weights.py`, `train_d_with_checkpoints.py`, `param_sets.py`, `plotting.py`, `build_adaptive_vs_fixed_current.py`
- **`saved_models_{A-E}_excel_split/`, `saved_meta_{A-E}_excel_split/`** — ชุดทดลองล่าสุด (แยก train/test ตาม Excel) ใช้โดย `train_from_excel.py`, `test_from_excel.py`, `plot_training_curves_by_set.py`, `plot_training_loss_by_set.py`, `plot_test_curves_by_set.py`, `plot_train_vs_test_gap.py`, `consolidate_results.py`, `build_adaptive_vs_fixed_current.py`

ทั้งสามชุดถูกอ้างอิงโดยสคริปต์จริง — **อย่าลบ**

## อื่นๆ

- **`metrics_plots/`** — รูป PNG ผลลัพธ์ทั้งหมด (กราฟ accuracy/loss/comparison)
- **`data_split/`** — ไฟล์ข้อมูล train/test ที่แบ่งไว้แล้ว
- **`test_only_results.csv`** — ผล Test accuracy ล่าสุดของแต่ละชุด A–E (ที่มาของตัวเลขในกราฟเปรียบเทียบ)
- **`lstm_summary.txt`** — สรุปสถาปัตยกรรม/ผลลัพธ์ LSTM แบบข้อความล้วน

## ประวัติการล้าง (2026-08-25)

ลบโฟลเดอร์ที่ไม่มีสคริปต์ไหนอ้างอิงแล้วออก รวม ~7.4GB:
`saved_models_backup_pretrain4_20260807`, `saved_models_backup_before_A_C`, `saved_models_backup_B`,
`saved_meta_backup_pretrain4_20260807`, `saved_meta_backup_before_A_C`, `saved_meta_backup_B`, `saved_meta_backup` (backup ที่ `run_abcd_experiment.sh` สร้างไว้ก่อนรันแต่ละครั้ง หมดอายุการใช้งานแล้ว),
`saved_models_A_real`, `saved_meta_A_real` (ทดลองเก่า ไม่มีการอ้างอิง),
โฟลเดอร์ `room_XXX/` เดี่ยวๆ 78 อัน (~30MB, cache โมเดลของห้องเก่าที่ถูกลบออกจากฐานข้อมูลแล้ว ไม่ตรงกับ 8 ห้องจริงที่ใช้ AI), โฟลเดอร์ว่างเปล่า 4 อัน, และไฟล์เดี่ยว `lstm_model.keras`/`scaler.pkl` ที่หลงเหลือจากรูปแบบเดิมช่วงเดียวกัน (ไม่มีสคริปต์ไหนอ้างอิง)
