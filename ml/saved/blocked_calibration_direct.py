"""Direct sets A-D retrained with a BLOCKED calibration slice — a parallel
experiment, stored separately. Nothing of the original run is touched.

Why: the original calibration slice is one contiguous block at the end of
train (2025-05-24 .. 09-09, the break -> new-term transition). Train spans
every season; calibration saw one, and a hard one (check_calib_vs_test_gap.py,
check_cv_windows.py). Here calibration is N_BLOCKS short blocks spread evenly
over the train span, ~10% of the usable target days, so it covers the seasons
roughly in train's own proportions.

The ONLY difference from train_direct_sets.py is which rows choose the served
round, engine per room and strategy per room:
  * the final refit uses exactly the same rows as the original
    (every row whose target precedes the original calibration end), so both
    variants are trained on identical data;
  * the test split, thresholds, configs, rounds, rates and selection rules are
    unchanged (TS.scan, TS.pick_room_engines, TS.choose_strategies).

Leakage guard: a training row is dropped if its origin OR its target lies
within GAP days of a calibration block (GAP = HORIZON), so no fitted row
predicts into, or starts from inside, a block. Residual overlap that remains
and must be stated when quoting results: rows after a block still carry that
block's days as lag/rolling INPUTS (never as labels), and the 'constant'
strategy's majority class is counted over the original train span.

PRE-REGISTERED (written before any result exists):
  The original contiguous-calibration run stays the primary result and the
  production default whatever this run scores. This run is reported beside it
  as the comparison "contiguous vs blocked calibration", both test columns
  shown. Choosing between them by test accuracy would be selecting on test.

Outputs (the original saved_direct_sets/ and saved_meta_*_direct/ are never written):
  blocked_calib/saved_direct_sets/{SET}/model.pkl
  blocked_calib/saved_meta_{SET}_direct/*_meta.pkl
  metrics_plots/test_only_results_direct_blocked.csv        (--test)
  metrics_plots/blocked_calibration_blocks.csv              (the blocks used)

Usage (from the repo root):
  python ml/saved/blocked_calibration_direct.py            # train A-D
  python ml/saved/blocked_calibration_direct.py --sets C   # one set
  python ml/saved/blocked_calibration_direct.py --test     # evaluate on test
"""
import os
import sys

import numpy as np
import pandas as pd

import train_direct as TD   # sets up Django and paths
import train_direct_sets as TS
import test_direct_sets as TT

D = TD.D
F = D.F

N_BLOCKS = 4          # spread evenly across each room's usable span
CALIB_SHARE = 0.10    # of the usable target days
GAP = D.HORIZON       # purge distance around each block, in days

ORIG_SAVED_DIR = TS.SAVED_DIR
MP = os.path.join(ORIG_SAVED_DIR, 'metrics_plots')
TT.OUT_CSV = os.path.join(MP, 'test_only_results_direct_blocked.csv')
BLOCKS_CSV = os.path.join(MP, 'blocked_calibration_blocks.csv')
# Everything this run writes besides those CSVs goes under one sandbox dir.
# save_set() and test_direct_sets both build saved_meta_{SET}_direct from
# TS.SAVED_DIR, and save_set DELETES the metas already there — left pointing
# at ml/saved it would wipe the original run's metas.
BLOCKED_DIR = os.path.join(ORIG_SAVED_DIR, 'blocked_calib')
TS.SAVED_DIR = BLOCKED_DIR
TS.MODEL_ROOT = os.path.join(BLOCKED_DIR, 'saved_direct_sets')
for _p in (TS.MODEL_ROOT, os.path.join(TS.SAVED_DIR, 'saved_meta_A_direct'), TT.OUT_CSV):
    assert os.path.abspath(_p) not in {
        os.path.join(ORIG_SAVED_DIR, 'saved_direct_sets'),
        os.path.join(ORIG_SAVED_DIR, 'saved_meta_A_direct'),
        os.path.join(MP, 'test_only_results_direct.csv')}, f'would overwrite the original run: {_p}'


def make_blocks(data):
    """{room: [(lo, hi), ...]} calendar positions of the calibration blocks."""
    blocks = {}
    for code, r in data.rooms.items():
        first = r['start'] + D.MIN_HISTORY + 1          # first target any origin reaches
        last = r['calib_end']                           # original train+calib end (exclusive)
        span = last - first
        length = max(7, int(round(span * CALIB_SHARE / N_BLOCKS)))
        centres = [first + span * (i + 0.5) / N_BLOCKS for i in range(N_BLOCKS)]
        blocks[code] = [(int(c - length / 2), int(c - length / 2) + length) for c in centres]
    return blocks


def blocked_matrices(data, blocks):
    """(train, calib, full): full is exactly the original train+calib rows."""
    parts = {'train': ([], [], []), 'calib': ([], [], []), 'full': ([], [], [])}
    for code in data.codes:
        r = data.rooms[code]
        origins = list(range(r['start'] + D.MIN_HISTORY, r['calib_end'] - 1))
        x, y, m = data.build_rows(code, origins)
        if len(x) == 0:
            continue
        tgt = np.array([q[3] for q in m])
        org = np.array([q[1] for q in m])
        in_full = tgt < r['calib_end']
        in_cal = np.zeros(len(m), bool)
        near = np.zeros(len(m), bool)
        for lo, hi in blocks[code]:
            in_cal |= (tgt >= lo) & (tgt < hi)
            near |= ((tgt >= lo - GAP) & (tgt < hi + GAP)) | ((org >= lo - GAP) & (org < hi + GAP))
        masks = {'full': in_full, 'calib': in_full & in_cal, 'train': in_full & ~near}
        for name, keep in masks.items():
            if keep.any():
                parts[name][0].append(x[keep])
                parts[name][1].append(y[keep] / r['scale'])
                parts[name][2].extend(m[i] for i in np.where(keep)[0])
    return {k: (np.vstack(v[0]), np.concatenate(v[1]), v[2]) for k, v in parts.items()}


def train_main():
    sets = [s.upper() for s in TS._arg_list('--sets', list(TS.SETS))]
    print('Loading and aligning the 8 rooms...', flush=True)
    data = D.Dataset(TD.TRAIN_XLSX, TD.TEST_XLSX)
    blocks = make_blocks(data)
    pd.DataFrame([dict(room=c, block=i + 1, start=data.calendar[lo].date(), end=data.calendar[hi - 1].date(),
                       days=hi - lo) for c, bl in blocks.items() for i, (lo, hi) in enumerate(bl)]
                 ).to_csv(BLOCKS_CSV, index=False)
    for c, bl in blocks.items():
        print(f"  {c:12s} " + '  '.join(f"{data.calendar[lo].date()}..{data.calendar[hi - 1].date()}"
                                        for lo, hi in bl), flush=True)
    mats = blocked_matrices(data, blocks)
    train, calib, (Xfull, Yfull, _) = mats['train'], mats['calib'], mats['full']
    orig_train = data.matrix('train')
    print(f"  train rows {train[0].shape[0]} ({100 * train[0].shape[0] / orig_train[0].shape[0]:.0f}% of the "
          f"original {orig_train[0].shape[0]})   calib rows {calib[0].shape[0]}   "
          f"refit rows {Xfull.shape[0]} (same as original)", flush=True)
    del orig_train

    # Strategy margin from the real number of calibration days per room.
    cal_days = int(np.mean([sum(hi - lo for lo, hi in bl) for bl in blocks.values()]))
    orig_choose = D.choose_strategy
    D.choose_strategy = lambda scores, n_days, default='argmax_class': orig_choose(scores, cal_days, default)
    print(f'  strategy margin uses {cal_days} calibration days/room '
          f'(margin {D.selection_margin(cal_days):.3f})', flush=True)

    for set_name in sets:
        spec = TS.SETS[set_name]
        budget = spec.get('rounds', TS.N_ESTIMATORS)
        print(f"\n{'=' * 78}\n SET {spec['name']} [BLOCKED calibration]  "
              f"({budget} rounds x lr {spec['lr']})\n{'=' * 78}", flush=True)
        results = {}
        for engine in TD.ENGINES:
            params = dict(TD.ENGINES[engine]['grid'][spec['grid_key']])
            params['learning_rate'] = spec['lr']
            print(f"\n   [{engine}]", flush=True)
            models = TD.fit_config(engine, params, train[0], train[1], budget)
            res = TS.scan(engine, models, train, calib, data, budget)
            results[engine] = dict(models=models, params=params, **res)
            print(f"   -> best calib acc={res['best_acc']:.4f} @ round {res['best_acc_round']}"
                  f"   best MAE={res['best_mae']:.3f}h @ round {res['best_mae_round']}", flush=True)
        winner = max(results, key=lambda e: results[e]['best_acc'])
        print(f"\n   set-level winner: {winner}", flush=True)
        print('   engine per room (calibration only):', flush=True)
        room_engine = TS.pick_room_engines(results, winner)
        print('   strategy per room (calibration only):', flush=True)
        choice = TS.choose_strategies(results, room_engine, calib, data)
        served = {}
        for engine in sorted(set(room_engine.values())):
            res = results[engine]
            n_acc = min(int(res['best_acc_round'] * 1.15), budget)
            n_mae = min(int(res['best_mae_round'] * 1.15), budget)
            print(f'   refitting {engine} on the original train+calibration rows ({n_acc} / {n_mae} rounds)...',
                  flush=True)
            refit = TD.ENGINES[engine]['refit']
            m_acc, m_mae = {}, {}
            for q in D.QUANTILES:
                m_acc[q] = refit(Xfull, Yfull, q, res['params'], n_acc)
                m_mae[q] = m_acc[q] if n_mae == n_acc else refit(Xfull, Yfull, q, res['params'], n_mae)
            served[engine] = dict(quantile_models_acc=m_acc, quantile_models_mae=m_mae, n_acc=n_acc, n_mae=n_mae)
        TS.save_set(set_name, spec, results, winner, room_engine, choice, served, train, data)
        print(f'   saved -> {os.path.join(TS.MODEL_ROOT, set_name)}', flush=True)
    print('\nDone. Next:  python ml/saved/blocked_calibration_direct.py --test', flush=True)


if __name__ == '__main__':
    if '--test' in sys.argv:
        TT.main()
    else:
        train_main()
