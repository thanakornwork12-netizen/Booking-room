"""Rolling-origin calibration for the direct sets — REPORTING ONLY.

The single calibration window (2025-05-24 .. 09-09) is the summer break and
is measurably harder than test for every predictor, learned or not (see
check_calib_vs_test_gap.py / check_cv_windows.py). This script adds earlier
calibration windows so the reported calibration accuracy is an average over
several parts of the year instead of one unlucky slice.

What it does NOT touch: the train/test split, saved_direct_sets/ (the served
models), and therefore every test number. Nothing is saved except the CSV —
fold models live in memory only and are discarded.

Per fold k (window = the current calibration window shifted back k lengths):
  * train  = rows whose target day is before the window (origins before it)
  * calib  = rows whose target day falls in the window
  * both engines are fit at the set's exact config / rounds / lr, the round
    is chosen with train_direct_sets' rule (last checkpoint within
    ACC_TOLERANCE of the best), each room takes the engine that scores
    higher for it, and the reported number is the mean per-room accuracy at
    that round — the same definition as "Calibration Accuracy" in
    adaptive_vs_fixed_by_set_current_direct.csv, which supplies fold 0.

Known caveat: class thresholds and each room's scale come from the full
original train span (up to 2025-05-24), which overlaps the earlier windows.
They are kept so every window is graded with the same ruler as test; they
are percentile cut points, not targets, so this is not a label leak.

Why folds 1-2 only by default: each fold trains on what precedes its window,
and MIN_HISTORY (400 days) must pass before a room produces any origin, so
training data shrinks fast going back — 38,402 rows for the real model,
26,362 for fold 1 (69%), 14,322 for fold 2 (37%), 2,415 for fold 3 (6%, one
room with none at all). Fold 3 would measure a model starved of data, not
the window. The cut is on training size, decided before any fold was run,
not on how easy the window is (fold 3's window is one of the easier ones).
Fold 2 is still trained on about a third of the data, which biases it
DOWN — say so when quoting it.

Usage (from the repo root):
  python ml/saved/cv_calibration_direct.py                 # sets A-D, folds 1-2
  python ml/saved/cv_calibration_direct.py --sets C --folds 1,2
"""
import os
import sys
import time

import numpy as np
import pandas as pd

import train_direct as TD   # sets up Django and paths
import train_direct_sets as TS

D = TD.D
F = D.F
MP = os.path.join(TS.SAVED_DIR, 'metrics_plots')
OUT_CSV = os.path.join(MP, 'cv_calibration_direct.csv')
SUMMARY_CSV = os.path.join(MP, 'cv_calibration_direct_summary.csv')
FOLD0_CSV = os.path.join(MP, 'adaptive_vs_fixed_by_set_current_direct.csv')
TEST_CSV = os.path.join(MP, 'test_only_results_direct.csv')


def fold_matrices(data, orig, k):
    """Shift every room's calibration window back k lengths and build the
    train/calib matrices for it. Restores nothing — caller passes `orig`."""
    for code, r in data.rooms.items():
        te, ce = orig[code]
        L = ce - te
        r['train_end'], r['calib_end'] = te - k * L, te - (k - 1) * L
    windows = {c: (data.calendar[r['train_end']].date(), data.calendar[r['calib_end'] - 1].date())
               for c, r in data.rooms.items()}
    return data.matrix('train'), data.matrix('calib'), windows


def scan_calib(engine, models, calib, data, rounds_budget):
    """Calibration-only version of train_direct_sets.scan (train is not
    scored — it is not needed here and costs most of the time)."""
    Xca, Yca, Mca = calib
    rounds, curve, per_room = [], [], []
    for n in range(TS.CHECKPOINT_STEP, rounds_budget + 1, TS.CHECKPOINT_STEP):
        ca = TS.per_room_scores(TD.quantiles_at(engine, models, Xca, n), Xca, Yca, Mca, data)
        rounds.append(n)
        curve.append(float(np.mean([v[0] for v in ca.values()])))
        per_room.append({c: v[0] for c, v in ca.items()})
    best = max(curve)
    i = [j for j, a in enumerate(curve) if a >= best - TS.ACC_TOLERANCE][-1]
    return dict(round=rounds[i], acc=curve[i], per_room=per_room[i])


def main():
    sets = [s.upper() for s in TS._arg_list('--sets', list(TS.SETS))]
    folds = [int(f) for f in TS._arg_list('--folds', ['1', '2'])]
    t0 = time.time()
    print(f'sets={sets} folds={folds}', flush=True)
    print('Loading and aligning the 8 rooms...', flush=True)
    data = D.Dataset(TD.TRAIN_XLSX, TD.TEST_XLSX)
    orig = {c: (r['train_end'], r['calib_end']) for c, r in data.rooms.items()}

    rows = []
    if os.path.exists(OUT_CSV) and '--fresh' not in sys.argv:
        rows = pd.read_csv(OUT_CSV).to_dict('records')
        print(f'resuming: {len(rows)} rows already in {OUT_CSV} (pass --fresh to start over)')
    done = {(r['set'], int(r['fold'])) for r in rows}

    for k in folds:
        train, calib, windows = fold_matrices(data, orig, k)
        span = f"{min(w[0] for w in windows.values())} .. {max(w[1] for w in windows.values())}"
        print(f"\n{'=' * 78}\n FOLD {k}: calibration window {span}\n"
              f"  train rows {train[0].shape}  calib rows {calib[0].shape}\n{'=' * 78}", flush=True)
        for set_name in sets:
            if (set_name, k) in done:
                print(f'  set {set_name}: already done, skipping', flush=True)
                continue
            spec = TS.SETS[set_name]
            budget = spec.get('rounds', TS.N_ESTIMATORS)
            print(f"\n  SET {spec['name']}  ({budget} rounds x lr {spec['lr']})", flush=True)
            res = {}
            for engine in TD.ENGINES:
                params = dict(TD.ENGINES[engine]['grid'][spec['grid_key']])
                params['learning_rate'] = spec['lr']
                print(f'   [{engine}] fitting...', flush=True)
                models = TD.fit_config(engine, params, train[0], train[1], budget)
                res[engine] = scan_calib(engine, models, calib, data, budget)
                print(f"   [{engine}] calib acc={res[engine]['acc']:.4f} @ round {res[engine]['round']}",
                      flush=True)
                del models
            winner = max(res, key=lambda e: res[e]['acc'])
            for code in res[winner]['per_room']:
                accs = {e: res[e]['per_room'][code] for e in res if code in res[e]['per_room']}
                best = max(accs, key=accs.get)
                if accs[winner] == accs[best]:
                    best = winner
                rows.append(dict(set=set_name, fold=k, room=code, engine=best,
                                 round=res[best]['round'], calib_acc=round(accs[best], 4),
                                 window_start=windows[code][0], window_end=windows[code][1]))
                print(f'      {code:12s} -> {best:9s} acc={accs[best]:.4f}', flush=True)
            pd.DataFrame(rows).to_csv(OUT_CSV, index=False)   # checkpoint after every set
            m = np.mean([r['calib_acc'] for r in rows if r['set'] == set_name and r['fold'] == k])
            print(f'  -> set {set_name} fold {k}: mean calib acc {m:.4f}  '
                  f'(elapsed {(time.time() - t0) / 60:.0f} min)', flush=True)

    df = pd.DataFrame(rows)
    per_fold = df.groupby(['set', 'fold'])['calib_acc'].mean().unstack('fold')
    per_fold.columns = [f'fold_{c}' for c in per_fold.columns]
    fold0 = pd.read_csv(FOLD0_CSV).set_index('Set')
    test = pd.read_csv(TEST_CSV).groupby('param_set')['test_accuracy'].mean()
    per_fold['fold_0_current'] = fold0['Calibration Accuracy']
    windows_cols = [c for c in per_fold.columns]
    per_fold['cv_mean'] = per_fold[windows_cols].mean(axis=1)
    per_fold['cv_sd'] = per_fold[windows_cols].std(axis=1)
    per_fold['train'] = fold0['Train Accuracy']
    per_fold['test'] = test
    per_fold = per_fold.round(4)
    per_fold.to_csv(SUMMARY_CSV, index_label='set')
    print('\n=== calibration accuracy per window, and the CV mean ===')
    print(per_fold.to_string())
    print(f'\nsaved {OUT_CSV}\nsaved {SUMMARY_CSV}\n'
          f'total {(time.time() - t0) / 60:.0f} min — test numbers are unchanged by design')


if __name__ == '__main__':
    main()
