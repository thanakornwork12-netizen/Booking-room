"""Why is calibration accuracy (~0.726) below test accuracy (~0.813)?

Read-only: loads the same Dataset and the exact calib/test rows the direct
sets are scored on, then measures how HARD each window is with predictors
that involve no trained model, so the answer cannot come from the model:

  majority   — always the room's most common train-period class
  snaive7    — the class of the same weekday one week before the target day
  class mix  — share of low / medium / urgent days in the window

If these simple predictors also score higher on test than on calibration,
the gap is the windows, not the model.

Usage: python ml/saved/check_calib_vs_test_gap.py
"""
import os
import numpy as np
import pandas as pd

import train_direct as TD   # sets up Django and paths

D = TD.D
F = D.F
OUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'metrics_plots', 'calib_vs_test_gap_check.csv')


def acc(y_hours, p_hours, r):
    return float(F.compute_classification_metrics(
        y_hours, p_hours, r['thr_high'], r['thr_med'], r['peak'])['accuracy'])


def main():
    data = D.Dataset(TD.TRAIN_XLSX, TD.TEST_XLSX)
    rows = []
    for split in ('calib', 'test'):
        X, Y, M = data.matrix(split)
        codes = np.array([m[0] for m in M])
        for code in data.codes:
            k = np.where(codes == code)[0]
            if not len(k):
                continue
            r = data.rooms[code]
            lo, hi = data.cuts(code)
            y_norm = Y[k]
            y = y_norm * r['scale']
            cls = np.where(y_norm >= hi, 2, np.where(y_norm >= lo, 1, 0))
            # majority class of the train period, emitted as that band's centre
            train_norm = r['v'][:r['train_end']] / r['scale']
            tl = np.where(train_norm >= hi, 2, np.where(train_norm >= lo, 1, 0))
            centre = [lo * 0.5, (lo + hi) / 2, hi * 1.05][int(np.bincount(tl, minlength=3).argmax())]
            maj = np.full(len(k), centre * r['scale'])
            targets = np.array([M[i][3] for i in k])
            snaive = r['v'][np.maximum(targets - 7, 0)]
            days = pd.DatetimeIndex(data.calendar[np.unique(targets)])
            rows.append(dict(
                split=split, room=code, n_rows=len(k),
                first_day=days.min().date(), last_day=days.max().date(),
                pct_low=round(100 * np.mean(cls == 0), 1),
                pct_medium=round(100 * np.mean(cls == 1), 1),
                pct_urgent=round(100 * np.mean(cls == 2), 1),
                majority_acc=round(acc(y, maj, r), 4),
                snaive7_acc=round(acc(y, snaive, r), 4),
            ))
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    pd.set_option('display.width', 200)
    print(df.to_string(index=False))
    print('\n=== mean over rooms ===')
    print(df.groupby('split')[['pct_low', 'pct_medium', 'pct_urgent',
                               'majority_acc', 'snaive7_acc']].mean().round(3).to_string())
    print(f'\nsaved {OUT_CSV}')


if __name__ == '__main__':
    main()
