# ml/saved/archive/ — สคริปต์ยุค LSTM ที่เลิกใช้แล้ว

เก็บไว้อ้างอิงเท่านั้น **รันไม่ได้แล้ว** เพราะโหลดโมเดลจาก `saved_models_{A-E}_new/`, `saved_models_{A-C}/`
และ `saved_models/` ซึ่งถูกลบออกเมื่อ 2026-10-22 (ระบบจริงใช้ `serve_direct.py` + `saved_direct_sets/C/` แทน)
และ import `forecast` แบบ path เดียวกับ `ml/saved/` ซึ่งไม่ตรงหลังย้ายมาโฟลเดอร์นี้

- `analyze_adaptive_weights_all_sets.py`, `analyze_ensemble_weights.py` — วิเคราะห์น้ำหนัก ensemble จากโมเดล `_new`
- `train_d_with_checkpoints.py` — กราฟ checkpoint ของชุด D (`saved_models_D_new`)
- `run_abcd_experiment.sh` — รันเทรนชุด A–E แล้วสำรองไปไว้ที่ `_new`
- `test_lstm_improvements.py` — ทดสอบ LSTM จาก `saved_models/`
