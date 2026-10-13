"""Weighted blend vs single model, for the direct-model sets A-D.

The pipeline never scores a LightGBM/XGBoost blend: each room is served by
whichever single engine has the higher calibration accuracy. This script
runs the comparison the thesis (section 7.1.6) describes:

  1. Refit both engines on TRAIN ONLY, with each set's served params, up to
     the round each engine was served at (read from the saved bundle). The
     saved served models were refit on train+calibration, so they cannot be
     used to choose a weight on calibration without scoring in-sample.
  2. Per room, try w = 0.0, 0.1, ..., 1.0 on the calibration window:
         Q_blend = w * Q_lightgbm + (1 - w) * Q_xgboost   (per quantile)
     scored exactly as the engine choice is (argmax_class accuracy, block
     floor applied). The blend weight is the calibration-best w; an interior
     w is only taken if it beats the best single engine outright.
  3. On TEST, score LightGBM alone, XGBoost alone, the served engine and the
     blend at the calibration-chosen w, using the saved served models and the
     room's saved band strategy -- the same read-out as test_direct_sets.py,
     so the 'served' columns reproduce test_only_results_direct.csv.

Also written, as diagnostics that choose nothing:
  - test accuracy for every w (shows whether ANY blend would have helped),
  - correlation of LightGBM and XGBoost test errors in hours, per room.

The test split is never used to choose w or anything else.

Outputs go to a NEW folder per run, ml/saved/logs/blend_<timestamp>/, and
nothing outside it is written -- the single-model logs, CSVs, metas and
model bundles are only read:
  run.log                            full stdout of this run
  blend_vs_single_direct.csv         one row per (set, room)
  blend_vs_single_direct_curve.csv   calibration and test accuracy per w
Usage:
  python ml/saved/compare_blend_direct.py [--sets A,B,C,D]
"""
import os
import sys
import time

import numpy as np
import pandas as pd
import joblib

import train_direct as TD   # sets up Django and paths
import train_direct_sets as TS

D = TD.D
F = D.F

WEIGHTS = [round(w, 1) for w in np.linspace(0.0, 1.0, 11)]   # weight on LightGBM
RUN_DIR = os.path.join(TS.SAVED_DIR, 'logs', time.strftime('blend_%Y%m%d-%H%M%S'))
OUT_CSV = os.path.join(RUN_DIR, 'blend_vs_single_direct.csv')
CURVE_CSV = os.path.join(RUN_DIR, 'blend_vs_single_direct_curve.csv')
ENGINES = ('lightgbm', 'xgboost')


class _Tee:
    """Mirror stdout into the run folder's log."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)
            st.flush()

    def flush(self):
        for st in self.streams:
            st.flush()


def blend(Q_lgb, Q_xgb, w):
    return w * Q_lgb + (1.0 - w) * Q_xgb


def score(data, code, Q_band, Q_hours, X, Y, sub_meta, strategy):
    """(accuracy, balanced_accuracy, f1, r2, mae, hours) for one room."""
    cands = D.strategies(data, code, Q_band, X, sub_meta)
    band = D.apply_block_floor(cands.get(strategy, cands['argmax_class']), X, sub_meta, data)
    hours = np.maximum(0.0, D.apply_block_floor(D.median_forecast(Q_hours), X, sub_meta, data))
    r = data.rooms[code]
    y = Y * r['scale']
    cls = F.compute_classification_metrics(
        y, np.maximum(0.0, band) * r['scale'], r['thr_high'], r['thr_med'], r['peak'])
    h = hours * r['scale']
    return dict(acc=float(cls['accuracy']), bal_acc=float(cls['balanced_accuracy']),
                f1=float(cls['f1']), r2=float(F.r2_score(y, h)),
                mae=float(F.mean_absolute_error(y, h)), hours=h, y=y)


def train_only_quantiles(set_name, bundle, train, calib):
    """Train-only models for both engines -> calibration quantile matrices at
    each engine's served accuracy and MAE rounds."""
    Xtr, Ytr, _ = train
    Xca = calib[0]
    out = {}
    for e in ENGINES:
        spec = bundle['engines'].get(e)
        if spec is None:
            raise SystemExit(f'set {set_name}: no {e} in bundle -- both engines are needed')
        scan = spec['calib_scan']
        n_acc, n_mae = int(scan['best_acc_round']), int(scan['best_mae_round'])
        print(f"   [{e}] train-only refit to {max(n_acc, n_mae)} rounds "
              f"(acc round {n_acc}, mae round {n_mae}; logged calib acc {scan['best_acc']:.4f})",
              flush=True)
        models = TD.fit_config(e, spec['params'], Xtr, Ytr, max(n_acc, n_mae))
        out[e] = dict(acc=TD.quantiles_at(e, models, Xca, n_acc),
                      mae=TD.quantiles_at(e, models, Xca, n_mae),
                      logged_acc=float(scan['best_acc']))
    return out


def served_test_quantiles(bundle, Xte):
    out = {}
    for e in ENGINES:
        spec = bundle['engines'][e]
        out[e] = {kind: np.column_stack([spec[f'quantile_models_{kind}'][q].predict(Xte)
                                         for q in bundle['quantiles']])
                  for kind in ('acc', 'mae')}
    return out


def run_set(set_name, data, train, calib, test):
    path = os.path.join(TS.MODEL_ROOT, set_name, 'model.pkl')
    if not os.path.exists(path):
        print(f"⏭️  Set {set_name}: no model at {path}")
        return [], []
    bundle = joblib.load(path)
    print(f"\n{'=' * 80}\n SET {bundle['param_set_name']}  (config {bundle['config_name']}, "
          f"{bundle['rounds_budget']} rounds x lr {bundle['learning_rate']})\n{'=' * 80}", flush=True)

    Qca = train_only_quantiles(set_name, bundle, train, calib)
    Qte = served_test_quantiles(bundle, test[0])

    Xca, Yca, Mca = calib
    Xte, Yte, Mte = test
    ca_codes = np.array([m[0] for m in Mca])
    te_codes = np.array([m[0] for m in Mte])

    rows, curve = [], []
    endpoint_acc = {e: [] for e in ENGINES}
    for code in data.codes:
        kc, kt = ca_codes == code, te_codes == code
        if not kc.any() or not kt.any():
            continue
        served = bundle['room_engine'][code]
        strategy = bundle['strategy'].get(code, 'argmax_class')
        mc = [m for m in Mca if m[0] == code]
        mt = [m for m in Mte if m[0] == code]

        # Calibration: argmax_class, as the engine choice is scored.
        ca = {}
        for w in WEIGHTS:
            ca[w] = score(data, code,
                          blend(Qca['lightgbm']['acc'][kc], Qca['xgboost']['acc'][kc], w),
                          blend(Qca['lightgbm']['mae'][kc], Qca['xgboost']['mae'][kc], w),
                          Xca[kc], Yca[kc], mc, 'argmax_class')
        endpoint_acc['lightgbm'].append(ca[1.0]['acc'])
        endpoint_acc['xgboost'].append(ca[0.0]['acc'])

        # Chosen w: best single unless an interior w beats it outright.
        w_single = 1.0 if ca[1.0]['acc'] >= ca[0.0]['acc'] else 0.0
        w_star = w_single
        for w in WEIGHTS:
            if ca[w]['acc'] > ca[w_star]['acc']:
                w_star = w

        # Test, every w (diagnostic only).
        te = {}
        for w in WEIGHTS:
            te[w] = score(data, code,
                          blend(Qte['lightgbm']['acc'][kt], Qte['xgboost']['acc'][kt], w),
                          blend(Qte['lightgbm']['mae'][kt], Qte['xgboost']['mae'][kt], w),
                          Xte[kt], Yte[kt], mt, strategy)
            curve.append({'param_set': set_name, 'room': code, 'w_lightgbm': w,
                          'calib_accuracy': ca[w]['acc'], 'calib_mae': ca[w]['mae'],
                          'test_accuracy': te[w]['acc'], 'test_mae': te[w]['mae']})

        y = te[1.0]['y']
        err_l, err_x = te[1.0]['hours'] - y, te[0.0]['hours'] - y
        err_corr = (float(np.corrcoef(err_l, err_x)[0, 1])
                    if err_l.std() > 0 and err_x.std() > 0 else np.nan)
        w_served = 1.0 if served == 'lightgbm' else 0.0
        oracle_w = max(WEIGHTS, key=lambda w: te[w]['acc'])

        row = {
            'param_set': set_name, 'room': code, 'served_engine': served, 'strategy': strategy,
            'calib_acc_lightgbm': ca[1.0]['acc'], 'calib_acc_xgboost': ca[0.0]['acc'],
            'w_star_lightgbm': w_star, 'calib_acc_blend': ca[w_star]['acc'],
            'blend_is_interior': 0.0 < w_star < 1.0,
            'calib_gain_blend_vs_best_single': ca[w_star]['acc'] - ca[w_single]['acc'],
            'test_acc_lightgbm': te[1.0]['acc'], 'test_acc_xgboost': te[0.0]['acc'],
            'test_acc_served': te[w_served]['acc'], 'test_acc_blend': te[w_star]['acc'],
            'test_bal_acc_served': te[w_served]['bal_acc'], 'test_bal_acc_blend': te[w_star]['bal_acc'],
            'test_mae_lightgbm': te[1.0]['mae'], 'test_mae_xgboost': te[0.0]['mae'],
            'test_mae_served': te[w_served]['mae'], 'test_mae_blend': te[w_star]['mae'],
            'test_r2_served': te[w_served]['r2'], 'test_r2_blend': te[w_star]['r2'],
            'test_error_corr_lgb_xgb': err_corr,
            'diag_test_oracle_w': oracle_w, 'diag_test_oracle_acc': te[oracle_w]['acc'],
            'n_calib': int(kc.sum()), 'n_test': int(kt.sum()),
        }
        rows.append(row)
        print(f"   {code:12s} served={served:8s} calib LGB={ca[1.0]['acc']:.3f} XGB={ca[0.0]['acc']:.3f} "
              f"-> w*={w_star:.1f} (blend {ca[w_star]['acc']:.3f})  |  test served={te[w_served]['acc']:.3f} "
              f"blend={te[w_star]['acc']:.3f}  MAE {te[w_served]['mae']:.2f}->{te[w_star]['mae']:.2f}h  "
              f"err corr={err_corr:.2f}", flush=True)

    for e in ENGINES:
        print(f"   sanity: {e} train-only calib acc (mean of rooms) = {np.mean(endpoint_acc[e]):.4f}  "
              f"vs logged {Qca[e]['logged_acc']:.4f}", flush=True)
    return rows, curve


def main():
    sets = [s.upper() for s in TS._arg_list('--sets', list(TS.SETS))]
    os.makedirs(RUN_DIR, exist_ok=False)   # never reuse a folder
    sys.stdout = _Tee(sys.__stdout__, open(os.path.join(RUN_DIR, 'run.log'), 'w', encoding='utf-8'))
    print(f"run folder: {RUN_DIR}\nsets: {sets}", flush=True)
    data = D.Dataset(TD.TRAIN_XLSX, TD.TEST_XLSX)
    train, calib, test = data.matrix('train'), data.matrix('calib'), data.matrix('test')
    print(f"train {train[0].shape}  calib {calib[0].shape}  test {test[0].shape}  "
          f"(test origin step {D.TEST_ORIGIN_STEP})", flush=True)

    rows, curve = [], []
    for s in sets:
        r, c = run_set(s, data, train, calib, test)
        rows.extend(r)
        curve.extend(c)
        # Save after every set so a long run keeps what it has finished.
        pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
        pd.DataFrame(curve).to_csv(CURVE_CSV, index=False)

    df = pd.DataFrame(rows)
    if df.empty:
        return
    print(f"\n{'=' * 80}\n SUMMARY -- mean of rooms per set (test)\n{'=' * 80}")
    summary = df.groupby('param_set').agg(
        rooms=('room', 'count'),
        interior_w_rooms=('blend_is_interior', 'sum'),
        acc_lightgbm=('test_acc_lightgbm', 'mean'),
        acc_xgboost=('test_acc_xgboost', 'mean'),
        acc_served=('test_acc_served', 'mean'),
        acc_blend=('test_acc_blend', 'mean'),
        mae_served=('test_mae_served', 'mean'),
        mae_blend=('test_mae_blend', 'mean'),
        err_corr=('test_error_corr_lgb_xgb', 'mean'),
    )
    print(summary.round(4).to_string())
    n = len(df)
    n_int = int(df['blend_is_interior'].sum())
    print(f"\nCases (set x room): {n}.  Calibration chose an interior blend weight in {n_int}; "
          f"best single engine in {n - n_int} "
          f"(LightGBM {int((df['w_star_lightgbm'] == 1.0).sum())}, "
          f"XGBoost {int((df['w_star_lightgbm'] == 0.0).sum())}).")
    if n_int:
        sub = df[df['blend_is_interior']]
        print(f"Where blend was chosen, test acc served {sub['test_acc_served'].mean():.4f} "
              f"-> blend {sub['test_acc_blend'].mean():.4f}")
    print(f"\n📄 Saved: {OUT_CSV}\n📄 Saved: {CURVE_CSV}")


if __name__ == '__main__':
    main()
