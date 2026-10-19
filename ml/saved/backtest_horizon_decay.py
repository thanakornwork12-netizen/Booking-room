"""ความแม่นยำลดลงแค่ไหนเมื่อพยากรณ์ไกลกว่า 14 วัน — backtest บนช่วงชุดทดสอบ

จำลองสิ่งที่ serve_direct.py ทำจริงทุกขั้น แต่ย้อนไปทำบนช่วงที่รู้คำตอบแล้ว:
  1. ยืนที่วันเริ่ม t0 (อยู่ในช่วงชุดทดสอบ) ใช้ข้อมูลจริงถึง t0 เท่านั้น
  2. ทุกวันหลัง t0 เติมด้วยสถิติปีก่อน (serve_direct.seasonal_hours, เห็นข้อมูลถึง t0 เท่านั้น)
  3. ทำนายด้วยแบบจำลองชุด C รอบละ 14 วัน เลื่อนจุดเริ่มทีละ 14 วัน (serve_direct.predict_model_c)
  4. เทียบกับการใช้ห้องจริง แล้วสรุป Accuracy / MAE แยกตามสัปดาห์นับจาก t0

ไม่เทรนใหม่ — โหลด saved_direct_sets/C/model.pkl ที่ใช้งานจริง
สัปดาห์ 1–2 คือรอบแรก (ข้อมูลนำเข้าเป็นข้อมูลจริง) ส่วนสัปดาห์ 3 ขึ้นไปคือรอบที่ใช้สถิติปีก่อน

ชุดทดสอบยาว ~232 วัน วันเริ่มที่อยู่ท้ายช่วงจึงวัดได้แค่สัปดาห์ต้น ๆ — คอลัมน์ n_days บอกจำนวนวัน
ที่ใช้คำนวณแต่ละสัปดาห์ สัปดาห์ท้าย ๆ มีจำนวนน้อยกว่าจึงแกว่งมากกว่า

Usage:
    python ml/saved/backtest_horizon_decay.py                    # วันเริ่มทุก 7 วันตลอดชุดทดสอบ
    python ml/saved/backtest_horizon_decay.py --origin-step 14 --weeks 26
    python ml/saved/backtest_horizon_decay.py --max-origins 1    # ลองรันเร็ว ๆ

Output (โฟลเดอร์ใหม่ทุกครั้ง ไม่ทับของเดิม):
    ml/saved/metrics_plots/horizon_decay_<timestamp>/by_week.csv
    ml/saved/metrics_plots/horizon_decay_<timestamp>/by_room_week.csv
    ml/saved/metrics_plots/horizon_decay_<timestamp>/run.log
"""
import argparse
import os
import sys
from datetime import datetime

import serve_direct as S   # sets up Django and paths

import joblib
import numpy as np
import pandas as pd

D, F = S.D, S.F


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--origin-step', type=int, default=7, help='ระยะห่างของวันเริ่ม (วัน)')
    ap.add_argument('--weeks', type=int, default=26, help='พยากรณ์ไกลสุดกี่สัปดาห์')
    ap.add_argument('--max-origins', type=int, default=0, help='จำกัดจำนวนวันเริ่ม (0 = ทั้งหมด)')
    args = ap.parse_args()

    out_dir = os.path.join(S.BASE_DIR, 'ml/saved/metrics_plots',
                           'horizon_decay_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    os.makedirs(out_dir, exist_ok=True)
    log = open(os.path.join(out_dir, 'run.log'), 'w', encoding='utf8')

    def say(msg=''):
        print(msg, flush=True)
        log.write(msg + '\n')

    empty = pd.DataFrame(columns=['room_code', 'date', 'start_time', 'end_time', 'duration_hours', 'status'])
    te_last = pd.read_excel(S.TEST_XLSX)['date'].max()
    data = S.ServeData(S.TRAIN_XLSX, S.TEST_XLSX, empty, te_last)
    bundle = joblib.load(S.MODEL_PATH)
    real = {c: r['v'].copy() for c, r in data.rooms.items()}
    last_day = len(data.calendar) - 1

    # ช่วงชุดทดสอบ = วันแรกในไฟล์ dataset_test.xlsx (10 ก.ย. 2568)
    test_start = data.pos[pd.read_excel(S.TEST_XLSX)['date'].min().normalize()]
    origins = list(range(test_start, last_day - 14, args.origin_step))
    if args.max_origins:
        origins = origins[:args.max_origins]
    horizon = args.weeks * 7
    say(f'ชุดทดสอบ {data.calendar[test_start].date()} – {data.calendar[last_day].date()} | '
        f'วันเริ่ม {len(origins)} จุด (ทุก {args.origin_step} วัน) | พยากรณ์ไกลสุด {args.weeks} สัปดาห์')

    rows = []
    for n, t0 in enumerate(origins, 1):
        # ข้อมูลนำเข้า: จริงถึง t0, หลังจากนั้นสถิติปีก่อน (เห็นข้อมูลถึง t0 เท่านั้น)
        for code, r in data.rooms.items():
            v = real[code].copy()
            for p in range(t0 + 1, last_day + 1):
                v[p] = S.seasonal_hours(real[code], r['start'], p, t0)
            r['v'] = v
        data._precompute_rollups()

        for origin in range(t0, min(t0 + horizon, last_day), D.HORIZON):
            for code, preds in S.predict_model_c(data, bundle, origin).items():
                for j, band, hours in preds:
                    h = j - t0
                    if j > last_day or h < 1 or h > horizon:
                        continue
                    rows.append((code, t0, j, h, band, hours, real[code][j]))
        say(f'  [{n}/{len(origins)}] วันเริ่ม {data.calendar[t0].date()} เสร็จ')

    df = pd.DataFrame(rows, columns=['room', 't0', 'day', 'h', 'band', 'hours', 'actual'])
    df['week'] = (df['h'] - 1) // 7 + 1
    df['input'] = np.where(df['h'] <= D.HORIZON, 'real', 'seasonal')

    per = []
    for (code, wk), g in df.groupby(['room', 'week']):
        r = data.rooms[code]
        cls = F.compute_classification_metrics(g['actual'].to_numpy(), g['band'].to_numpy() * r['scale'],
                                               r['thr_high'], r['thr_med'], r['peak'])
        per.append({'room': code, 'week': wk, 'n_days': len(g), 'accuracy': cls['accuracy'],
                    'mae': float(np.mean(np.abs(g['actual'] - g['hours'])))})
    per = pd.DataFrame(per)
    per.to_csv(os.path.join(out_dir, 'by_room_week.csv'), index=False)

    # ค่าเฉลี่ย 8 ห้อง เหมือนตัวเลขที่รายงานในเล่ม
    wk = per.groupby('week').agg(rooms=('room', 'nunique'), n_days=('n_days', 'sum'),
                                 accuracy=('accuracy', 'mean'), mae=('mae', 'mean')).reset_index()
    base = wk.loc[wk['week'] <= 2, 'accuracy'].mean()
    wk['input'] = np.where(wk['week'] <= 2, 'real (รอบแรก)', 'seasonal')
    wk['drop_vs_wk1_2_pts'] = (wk['accuracy'] - base) * 100
    wk['accuracy_pct'] = wk['accuracy'] * 100
    wk.to_csv(os.path.join(out_dir, 'by_week.csv'), index=False)

    say('\nAccuracy แยกตามสัปดาห์นับจากวันเริ่ม (เฉลี่ย 8 ห้อง)')
    say(wk[['week', 'input', 'n_days', 'accuracy_pct', 'drop_vs_wk1_2_pts', 'mae']]
        .round(2).to_string(index=False))
    seas = wk[wk['week'] > 2]
    if len(seas) > 1:
        slope = np.polyfit(seas['week'], seas['accuracy_pct'], 1)[0]
        say(f'\nสัปดาห์ 1–2 (ข้อมูลจริง): {base * 100:.1f}%')
        say(f'สัปดาห์ 3 ขึ้นไป (สถิติปีก่อน): เฉลี่ย {seas["accuracy_pct"].mean():.1f}% '
            f'| แนวโน้มเปลี่ยน {slope:+.2f} จุดร้อยละต่อสัปดาห์')
    say(f'\nบันทึกไว้ที่ {out_dir}')
    log.close()


if __name__ == '__main__':
    main()
