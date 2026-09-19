"""Evaluate the three direct-model sets (A/B/C) on dataset_test.xlsx.

No training happens here. Each set's served models are loaded from
saved_direct_sets/{SET}/model.pkl and scored with the same protocol as
test_direct.py: forecast origins step 14 days from the calibration end and
each origin predicts its whole horizon, as the scheduled job runs.

Writes, in the shapes the thesis figures already use:
  metrics_plots/test_only_results_direct.csv
      one row per (set, room), same columns as test_only_results.csv
  saved_meta_{SET}_direct/<room_id>_meta.pkl
      cls_metrics / reg_metrics replaced with the test values, and a
      test_curve (accuracy and MAE every 10 rounds) for
      plot_test_curves_by_set.py --direct

The pipeline's test_only_results.csv is not touched.

Usage: python ml/saved/test_direct_sets.py [--sets A,B,C]
"""
import os
import sys

import numpy as np
import pandas as pd
import joblib

import train_direct as TD   # sets up Django and paths
import train_direct_sets as TS

D = TD.D
F = D.F

OUT_CSV = os.path.join(TS.SAVED_DIR, 'metrics_plots', 'test_only_results_direct.csv')
COLUMNS = ['param_set', 'room', 'winner', 'pred_calibrated', 'test_accuracy',
           'balanced_accuracy', 'n_true_classes', 'f1', 'r2', 'mae', 'n_test',
           'origin_step', 'evaluation_mode']
DEGENERATE_NOTE = ('Rooms with <3 label classes present in test '
                   '(plain accuracy is not meaningful)')


def band_and_hours(data, code, Q_band, Q_hours, X, sub_meta, pick):
    """Demand band from the room's chosen strategy, hours from the median —
    the two read-outs test_direct.py serves."""
    cands = D.strategies(data, code, Q_band, X, sub_meta)
    band = D.apply_block_floor(cands.get(pick, cands['argmax_class']), X, sub_meta, data)
    hours = np.maximum(0.0, D.apply_block_floor(D.median_forecast(Q_hours), X, sub_meta, data))
    return band, hours


def evaluate_set(set_name, data, Xte, Yte, Mte):
    path = os.path.join(TS.MODEL_ROOT, set_name, 'model.pkl')
    if not os.path.exists(path):
        print(f"⏭️  Set {set_name}: no model at {path} — run train_direct_sets.py first")
        return []
    bundle = joblib.load(path)
    engines = bundle.get('engines')
    if engines is None:
        # Bundle from before per-room engine choice: one engine for every room.
        engines = {bundle['engine']: {k: bundle[k] for k in
                                      ('quantile_models_acc', 'quantile_models_mae', 'n_acc', 'n_mae')}}
    room_engine = bundle.get('room_engine') or {c: bundle['engine'] for c in data.codes}
    qs = bundle['quantiles']

    # Per serving engine: the band/hours ensembles, plus the test curve — the
    # served accuracy models read at every 10th round. The curve is a
    # diagnostic of the served model; nothing is chosen from it.
    pred = {}
    for engine in sorted(set(room_engine.values())):
        spec = engines[engine]
        predict = TD.ENGINES[engine]['predict']
        m_acc, m_mae = spec['quantile_models_acc'], spec['quantile_models_mae']
        rounds = list(range(TS.CHECKPOINT_STEP, spec['n_acc'] + 1, TS.CHECKPOINT_STEP))
        pred[engine] = {
            'acc': np.column_stack([m_acc[q].predict(Xte) for q in qs]),
            'mae': np.column_stack([m_mae[q].predict(Xte) for q in qs]),
            'rounds': rounds,
            'curve': {n: np.column_stack([predict(m_acc[q], Xte, n) for q in qs]) for n in rounds},
        }

    split = {e: sum(1 for v in room_engine.values() if v == e) for e in engines}
    print(f"\n{'=' * 80}\n TESTING SET {bundle['param_set_name']}  "
          f"(config={bundle['config_name']}, rooms per engine={split})\n{'=' * 80}")

    codes = np.array([m[0] for m in Mte])
    meta_dir = os.path.join(TS.SAVED_DIR, f'saved_meta_{set_name}_direct')
    rows = []
    for code in data.codes:
        k = codes == code
        if not k.any():
            continue
        r = data.rooms[code]
        sub_meta = [m for m in Mte if m[0] == code]
        pick = bundle['strategy'].get(code, 'argmax_class')
        engine = room_engine.get(code, bundle['engine'])
        P = pred[engine]
        band, hours = band_and_hours(data, code, P['acc'][k], P['mae'][k], Xte[k], sub_meta, pick)

        y = Yte[k] * r['scale']
        cls = F.compute_classification_metrics(
            y, np.maximum(0.0, band) * r['scale'], r['thr_high'], r['thr_med'], r['peak'])
        p_hours = hours * r['scale']
        r2 = float(F.r2_score(y, p_hours))
        mae = float(F.mean_absolute_error(y, p_hours))
        rmse = float(F.rmse(y, p_hours))

        accs, losses = [], []
        for n in P['rounds']:
            Qn = P['curve'][n][k]
            bn, hn = band_and_hours(data, code, Qn, Qn, Xte[k], sub_meta, pick)
            c = F.compute_classification_metrics(
                y, np.maximum(0.0, bn) * r['scale'], r['thr_high'], r['thr_med'], r['peak'])
            accs.append(float(c['accuracy']))
            losses.append(float(np.mean(np.abs(y - hn * r['scale']))))

        meta_path = os.path.join(meta_dir, f"{r['rid']}_meta.pkl")
        if os.path.exists(meta_path):
            meta = joblib.load(meta_path)
            meta.update({
                'test_curve': {'rounds': P['rounds'], 'accuracy': accs, 'loss': losses},
                'cls_metrics': {kk: v for kk, v in cls.items() if kk != 'report'},
                'reg_metrics': {'r2': round(r2, 4), 'mae': round(mae, 4), 'rmse': round(rmse, 4)},
                'test_size': int(k.sum()),
                'metrics_split': 'test',
            })
            joblib.dump(meta, meta_path)

        print(f"✅ {code:.<18} winner={engine:10s} TestAcc={cls['accuracy']:.3f}  "
              f"BalAcc={cls['balanced_accuracy']:.3f}  F1={cls['f1']:.3f}  "
              f"R²={r2:.3f}  MAE={mae:.2f}h  (strategy={pick}, n_test={int(k.sum())})")
        rows.append({
            'param_set': set_name, 'room': code, 'winner': engine, 'pred_calibrated': False,
            'test_accuracy': cls['accuracy'], 'balanced_accuracy': cls['balanced_accuracy'],
            'n_true_classes': cls['n_true_classes'], 'f1': cls['f1'], 'r2': r2, 'mae': mae,
            'n_test': int(k.sum()), 'origin_step': D.TEST_ORIGIN_STEP,
            'evaluation_mode': f'direct_{D.HORIZON}d_multihorizon_step{D.TEST_ORIGIN_STEP}',
        })
    print(f"✅ DONE SET {set_name}", flush=True)
    return rows


def main():
    sets = [s.upper() for s in TS._arg_list('--sets', list(TS.SETS))]
    # Default is step 1, which samples test origins the same way train origins
    # are sampled so the two accuracies are comparable. --live-step restores
    # the fortnightly cadence the production job actually runs on.
    if '--live-step' in sys.argv:
        D.TEST_ORIGIN_STEP = D.HORIZON
    print(f"test origin step = {D.TEST_ORIGIN_STEP} "
          f"({'live-job cadence' if D.TEST_ORIGIN_STEP == D.HORIZON else 'matches train sampling'})")
    data = D.Dataset(TD.TRAIN_XLSX, TD.TEST_XLSX)
    Xte, Yte, Mte = data.matrix('test')

    rows = []
    for set_name in sets:
        rows.extend(evaluate_set(set_name, data, Xte, Yte, Mte))

    df = pd.DataFrame(rows, columns=COLUMNS)
    print(f"\n\n================ SUMMARY (direct model, rolling {D.HORIZON}-day forecasts "
          f"on dataset_test.xlsx) ================")
    print(df.to_string(index=False))
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"\n📄 Saved: {OUT_CSV}")
    if len(df):
        print("\n📊 Mean test accuracy per set:")
        print(df.groupby('param_set')[['test_accuracy', 'balanced_accuracy', 'mae', 'r2']]
              .mean().to_string())
        degenerate = df[df['n_true_classes'] < 3]
        if len(degenerate):
            print(f"\n⚠️  {DEGENERATE_NOTE}:")
            print(degenerate[['param_set', 'room', 'test_accuracy', 'balanced_accuracy',
                              'n_true_classes', 'r2']].to_string(index=False))
            keep = df[df['n_true_classes'] >= 3]
            if len(keep):
                print("\n📊 Mean excluding those rooms:")
                print(keep.groupby('param_set')[['test_accuracy', 'balanced_accuracy']]
                      .mean().to_string())
    print("\n🏁 ALL SETS TESTED", flush=True)


if __name__ == '__main__':
    main()
