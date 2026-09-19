"""Before paying for rolling-origin CV: would earlier calibration windows be
easier than the current one (the summer break)?

Read-only, no model. Slides the calibration window back in steps of its own
length (~12.5% of each room's train span) and scores two no-learning
predictors on every target day of each window, plus the current window and
test with the same day-level scoring so all rows compare directly:

  majority  — most common class in the days BEFORE the window (as a fold
              would see it)
  snaive7   — the class of the same weekday one week earlier

If snaive7 on the earlier windows sits near its test value, CV calibration
should land nearer test and the retraining is worth running.

Usage: python ml/saved/check_cv_windows.py [N_FOLDS]   (default 3)
"""
import os
import sys
import numpy as np
import pandas as pd

import train_direct as TD   # sets up Django and paths

D = TD.D
F = D.F
N_FOLDS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
OUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'metrics_plots', 'cv_windows_check.csv')


def acc(y, p, r):
    return float(F.compute_classification_metrics(
        y, p, r['thr_high'], r['thr_med'], r['peak'])['accuracy'])


def score(code, r, data, lo, hi):
    v = r['v']
    cut_lo, cut_hi = data.cuts(code)
    days = np.arange(max(lo, 7), hi)
    if len(days) == 0:
        return None
    before = v[r['start']:lo] / r['scale']
    lab = np.where(before >= cut_hi, 2, np.where(before >= cut_lo, 1, 0))
    centre = [cut_lo * 0.5, (cut_lo + cut_hi) / 2, cut_hi * 1.05][
        int(np.bincount(lab, minlength=3).argmax())] * r['scale']
    y = v[days]
    yn = y / r['scale']
    cls = np.where(yn >= cut_hi, 2, np.where(yn >= cut_lo, 1, 0))
    return dict(first_day=data.calendar[days[0]].date(), last_day=data.calendar[days[-1]].date(),
                n_days=len(days), pct_medium=round(100 * np.mean(cls == 1), 1),
                majority_acc=round(acc(y, np.full(len(days), centre), r), 4),
                snaive7_acc=round(acc(y, v[days - 7], r), 4))


def main():
    data = D.Dataset(TD.TRAIN_XLSX, TD.TEST_XLSX)
    rows = []
    for code in data.codes:
        r = data.rooms[code]
        L = r['calib_end'] - r['train_end']
        windows = [(f'fold-{k}', r['train_end'] - k * L, r['train_end'] - (k - 1) * L)
                   for k in range(N_FOLDS, 0, -1)]
        windows += [('calib (current)', r['train_end'], r['calib_end']),
                    ('test', r['calib_end'], r['last'] + 1)]
        for name, lo, hi in windows:
            if lo - r['start'] < D.MIN_HISTORY:
                print(f'  {code} {name}: skipped, <{D.MIN_HISTORY} days of history before it')
                continue
            s = score(code, r, data, lo, hi)
            if s:
                rows.append(dict(window=name, room=code, **s))
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    pd.set_option('display.width', 200)
    print(df.to_string(index=False))
    order = [f'fold-{k}' for k in range(N_FOLDS, 0, -1)] + ['calib (current)', 'test']
    summ = df.groupby('window').agg(rooms=('room', 'count'), first=('first_day', 'min'),
                                    last=('last_day', 'max'), pct_medium=('pct_medium', 'mean'),
                                    majority=('majority_acc', 'mean'),
                                    snaive7=('snaive7_acc', 'mean')).reindex(order).round(3)
    print('\n=== mean over rooms (day-level) ===')
    print(summ.to_string())
    folds = df[df.window.str.startswith('fold') | (df.window == 'calib (current)')]
    print(f"\nall {N_FOLDS}+1 CV windows pooled: snaive7={folds.snaive7_acc.mean():.3f}  "
          f"majority={folds.majority_acc.mean():.3f}")
    print(f'saved {OUT_CSV}')


if __name__ == '__main__':
    main()
