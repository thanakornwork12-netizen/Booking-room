"""TRAINING ONLY for the direct multi-horizon forecaster.  Prints no test
numbers — run test_direct.py for results.

Four things are decided here, all on the calibration slice, never on test:

  1. which ENGINE wins — LightGBM and XGBoost quantile regressors compete
     head-to-head, each getting the same features, same quantiles, same
     evaluation
  2. which hyperparameter CONFIG (within the winning engine's grid) is used
  3. the shared quantile ensemble itself
  4. which STRATEGY each room is served by

No early stopping anywhere.  Every quantile model trains for the full
N_ESTIMATORS rounds.  Afterward, CHECKPOINTS round-counts are read back from
that finished run (LightGBM's `num_iteration=`, XGBoost's `iteration_range=`,
applied to the model that already has all N_ESTIMATORS trees — nothing is
retrained to produce a checkpoint) and at each one the FULL 10-quantile
ensemble is assembled and scored on calibration by the actual target metrics:
classification accuracy (via `argmax_class`) and MAE (via `median_forecast`).
Two round counts are kept — whichever checkpoint maximised accuracy, and
whichever minimised MAE — because those are different questions with
different optima (see `direct_forecast.median_forecast`'s docstring): the
round that best separates low/medium/urgent is usually not the round with the
smallest average error in hours.  This replaces scoring each quantile model in
isolation by its own pinball loss, which is only a proxy for what the system
is actually judged on.

(4) exists because the 8 rooms are not one problem.  1C-MEETING sees a booking
roughly once a fortnight and a flat 'low' beats any model on it; 3C16-17 runs
near capacity and needs the full distribution; 2C09's level halved between
train and test.  With only 8 rooms it is worth letting each pick the predictor
that demonstrably works for it, so every strategy is scored on the calibration
window and the winner is stored per room.

Usage:
    python ml/saved/train_direct.py
    python ml/saved/train_direct.py --rooms 2C05-06,3C16-17
"""
import os
import sys

BASE_DIR = '/Users/macthanakorn/room_booking'
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

import django
django.setup()
from django.conf import settings
settings.DATABASES['default']['OPTIONS'] = {'sslmode': 'disable'}
from django.db import connections
connections['default'].close()

sys.path.insert(0, os.path.join(BASE_DIR, 'ml', 'saved'))

import joblib
import numpy as np
import lightgbm as lgb
import xgboost as xgb

import direct_forecast as D

TRAIN_XLSX = os.path.join(BASE_DIR, 'ml/saved/data_split/dataset_train.xlsx')
TEST_XLSX = os.path.join(BASE_DIR, 'ml/saved/data_split/dataset_test.xlsx')
OUT_DIR = os.path.join(BASE_DIR, 'ml/saved/saved_direct')

# No early stopping: every config trains the full ceiling, and the best round
# is read from the finished run afterward.  Best rounds measured so far top
# out under 300, so this ceiling gives every config room to actually converge
# or overfit — either way the post-hoc scan finds the true optimum, not a guess.
N_ESTIMATORS = 1200
# How many round-counts to actually evaluate along that finished run. Checking
# every single round is wasteful (predicting 10 quantile models x every one of
# 1200 rounds per config); a checkpoint every ~20 rounds is fine-grained enough
# to find the real optimum without the cost of checking every round.
CHECKPOINT_STEP = 20

# Five complexity tiers per engine (A-E, mirroring the old param_sets.py A-E
# spread from fast/shallow to deep/heavily-regularized) x 2 engines = 10
# combos, every one trained the full N_ESTIMATORS rounds with no early
# stopping.  n_estimators/lstm knobs from the old grid are dropped: this
# ceiling already trains past where any of them stopped mattering, and there
# is no LSTM in this pipeline at all.
LGB_GRID = {
    'A_fast':      dict(num_leaves=15, min_child_samples=35, subsample=0.85,
                        subsample_freq=1, colsample_bytree=0.80,
                        reg_alpha=0.3, reg_lambda=0.6, learning_rate=0.04),
    'B_balanced':  dict(num_leaves=23, min_child_samples=40, subsample=0.85,
                        subsample_freq=1, colsample_bytree=0.75,
                        reg_alpha=0.5, reg_lambda=1.0, learning_rate=0.035),
    'C_highqual':  dict(num_leaves=31, min_child_samples=45, subsample=0.85,
                        subsample_freq=1, colsample_bytree=0.75,
                        reg_alpha=0.7, reg_lambda=1.2, learning_rate=0.03),
    'D_reg_med':   dict(num_leaves=31, min_child_samples=60, subsample=0.80,
                        subsample_freq=1, colsample_bytree=0.70,
                        reg_alpha=1.5, reg_lambda=2.5, learning_rate=0.025),
    'E_reg_wide':  dict(num_leaves=47, min_child_samples=70, subsample=0.75,
                        subsample_freq=1, colsample_bytree=0.65,
                        reg_alpha=2.0, reg_lambda=3.5, learning_rate=0.02),
    # F/G extend past E because E won on BOTH engines while sitting at the
    # edge of the old grid (LightGBM calibration accuracy climbed
    # 0.7025 -> 0.7096 -> 0.7130 -> 0.7150 -> 0.7263 with no sign of turning
    # over). The run therefore stopped because the grid ran out, not because
    # the model saturated. Pooling gives ~38k training rows, so even 95
    # leaves leaves ~400 rows per leaf — there is room to keep going. If F/G
    # turn the curve over, that is a real ceiling worth reporting; if they
    # keep climbing, the search should continue.
    # H exists to find the overfitting point, which A-G cannot: every rung of
    # that ladder widens the trees AND tightens every regulariser at the same
    # time (C->F->G raises min_child_samples 70->80->100 and reg_alpha
    # 2.0->2.5->3.0 while lowering subsample), so net capacity barely moves and
    # calibration accuracy flattens instead of turning over. Climbing further
    # up that ladder would most likely produce another flat curve and still no
    # citable stopping point.
    #
    # H therefore holds the regularisers LOOSE and raises capacity on its own:
    # many leaves, small leaf minimum, light L1/L2, little subsampling, and a
    # learning rate half of C's so the curve is walked in finer steps. If
    # calibration accuracy turns down here, that is the ceiling worth citing.
    # If it still does not, the next step is to drop regularisation further
    # rather than to widen again.
    'H_lowreg':    dict(num_leaves=127, min_child_samples=20, subsample=0.85,
                        subsample_freq=1, colsample_bytree=0.85,
                        reg_alpha=0.5, reg_lambda=0.5, learning_rate=0.01),
    'F_wider':     dict(num_leaves=63, min_child_samples=80, subsample=0.75,
                        subsample_freq=1, colsample_bytree=0.65,
                        reg_alpha=2.5, reg_lambda=4.0, learning_rate=0.02),
    'G_widest':    dict(num_leaves=95, min_child_samples=100, subsample=0.70,
                        subsample_freq=1, colsample_bytree=0.60,
                        reg_alpha=3.0, reg_lambda=5.0, learning_rate=0.015),
}
XGB_GRID = {
    'A_fast':      dict(max_depth=3, min_child_weight=5, subsample=0.85,
                        colsample_bytree=0.80, reg_alpha=0.3, reg_lambda=0.6,
                        learning_rate=0.04),
    'B_balanced':  dict(max_depth=4, min_child_weight=8, subsample=0.85,
                        colsample_bytree=0.75, reg_alpha=0.5, reg_lambda=1.0,
                        learning_rate=0.035),
    'C_highqual':  dict(max_depth=5, min_child_weight=10, subsample=0.85,
                        colsample_bytree=0.75, reg_alpha=0.7, reg_lambda=1.2,
                        learning_rate=0.03),
    'D_reg_med':   dict(max_depth=5, min_child_weight=15, subsample=0.80,
                        colsample_bytree=0.70, reg_alpha=1.5, reg_lambda=2.5,
                        learning_rate=0.025),
    'E_reg_wide':  dict(max_depth=6, min_child_weight=20, subsample=0.75,
                        colsample_bytree=0.65, reg_alpha=2.0, reg_lambda=3.5,
                        learning_rate=0.02),
    'F_wider':     dict(max_depth=7, min_child_weight=25, subsample=0.75,
                        colsample_bytree=0.65, reg_alpha=2.5, reg_lambda=4.0,
                        learning_rate=0.02),
    'G_widest':    dict(max_depth=8, min_child_weight=30, subsample=0.70,
                        colsample_bytree=0.60, reg_alpha=3.0, reg_lambda=5.0,
                        learning_rate=0.015),
    # See the H_lowreg note in LGB_GRID.
    'H_lowreg':    dict(max_depth=9, min_child_weight=3, subsample=0.85,
                        colsample_bytree=0.85, reg_alpha=0.5, reg_lambda=0.5,
                        learning_rate=0.01),
}

ROOMS_FILTER = None
if '--rooms' in sys.argv:
    ROOMS_FILTER = {s.strip() for s in sys.argv[sys.argv.index('--rooms') + 1].split(',') if s.strip()}


# ── per-engine: fit the full run; checkpoints are read off it afterward ────

def _lgb_fit_full(Xtr, Ytr, q, params, n_estimators=None):
    m = lgb.LGBMRegressor(objective='quantile', alpha=q,
                          n_estimators=n_estimators or N_ESTIMATORS,
                          verbose=-1, **params)
    m.fit(Xtr, Ytr, feature_name=D.FEATURES, categorical_feature=D.CATEGORICAL)
    return m


def _lgb_predict(model, X, n_iter):
    return model.predict(X, num_iteration=n_iter)


def _lgb_refit(Xfull, Yfull, q, params, n_iter):
    m = lgb.LGBMRegressor(objective='quantile', alpha=q, n_estimators=n_iter,
                          verbose=-1, **params)
    m.fit(Xfull, Yfull, feature_name=D.FEATURES, categorical_feature=D.CATEGORICAL)
    return m


def _xgb_fit_full(Xtr, Ytr, q, params, n_estimators=None):
    m = xgb.XGBRegressor(objective='reg:quantileerror', quantile_alpha=q,
                         n_estimators=n_estimators or N_ESTIMATORS,
                         verbosity=0, **params)
    m.fit(Xtr, Ytr, verbose=False)
    return m


def _xgb_predict(model, X, n_iter):
    return model.predict(X, iteration_range=(0, n_iter))


def _xgb_refit(Xfull, Yfull, q, params, n_iter):
    m = xgb.XGBRegressor(objective='reg:quantileerror', quantile_alpha=q,
                         n_estimators=n_iter, verbosity=0, **params)
    m.fit(Xfull, Yfull)
    return m


ENGINES = {
    'lightgbm': dict(grid=LGB_GRID, fit_full=_lgb_fit_full, predict=_lgb_predict,
                     refit=_lgb_refit),
    'xgboost': dict(grid=XGB_GRID, fit_full=_xgb_fit_full, predict=_xgb_predict,
                    refit=_xgb_refit),
}


def fit_config(engine, params, Xtr, Ytr, n_estimators=None):
    """Full-length training for every quantile under one (engine, config), no
    early stopping.  Returns {q: fitted_model}, each with n_estimators trees.

    n_estimators defaults to N_ESTIMATORS. It is a per-set argument because a
    config with a smaller learning rate needs proportionally more rounds to
    cover the same ground — set D halves C's rate, so comparing the two at one
    shared budget would confound the rate with a half-finished run."""
    n = n_estimators or N_ESTIMATORS
    spec = ENGINES[engine]
    out = {}
    for q in D.QUANTILES:
        out[q] = spec['fit_full'](Xtr, Ytr, q, params, n)
        print(f"      q={q:.2f}  fit {n} rounds", flush=True)
    return out


def quantiles_at(engine, models, X, n_iter):
    """Assemble the 10-quantile ensemble at one round-count, reading it off
    models that are already fully trained — nothing is retrained here."""
    spec = ENGINES[engine]
    return np.column_stack([spec['predict'](models[q], X, n_iter) for q in D.QUANTILES])


def pooled_hours(y_norm, meta, data):
    return y_norm * np.array([data.rooms[m[0]]['scale'] for m in meta])


def room_accuracy(pred_norm, y_norm, meta, data):
    codes = np.array([m[0] for m in meta])
    vals = []
    for code in data.codes:
        k = codes == code
        if not k.any():
            continue
        r = data.rooms[code]
        cls = D.F.compute_classification_metrics(
            y_norm[k] * r['scale'], np.maximum(0.0, pred_norm[k]) * r['scale'],
            r['thr_high'], r['thr_med'], r['peak'])
        vals.append(cls['accuracy'])
    return float(np.mean(vals))


def scan_checkpoints(engine, models, Xca, Yca, Mca, data):
    """Walk the finished run's checkpoints and score each one by the metric
    that actually matters, not by pinball loss.  Accuracy and MAE are scored
    from the SAME underlying quantile ensemble at each checkpoint but read off
    it differently (argmax-class vs. median), so they get their own optimum.

    Returns dict(best_acc_round, best_acc, best_mae_round, best_mae).
    """
    best_acc, best_acc_round = -1.0, CHECKPOINT_STEP
    best_mae, best_mae_round = float('inf'), CHECKPOINT_STEP
    hours_true = pooled_hours(Yca, Mca, data)
    for n_iter in range(CHECKPOINT_STEP, N_ESTIMATORS + 1, CHECKPOINT_STEP):
        Q = quantiles_at(engine, models, Xca, n_iter)
        band = D.apply_block_floor(D.argmax_class(Q, Mca, data), Xca, Mca, data)
        acc = room_accuracy(band, Yca, Mca, data)
        if acc > best_acc:
            best_acc, best_acc_round = acc, n_iter
        hours_pred = np.maximum(0.0, D.apply_block_floor(
            D.median_forecast(Q), Xca, Mca, data))
        mae = float(np.mean(np.abs(hours_true - pooled_hours(hours_pred, Mca, data))))
        if mae < best_mae:
            best_mae, best_mae_round = mae, n_iter
    return dict(best_acc=best_acc, best_acc_round=best_acc_round,
               best_mae=best_mae, best_mae_round=best_mae_round)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print('Loading and aligning the 8 rooms...', flush=True)
    data = D.Dataset(TRAIN_XLSX, TEST_XLSX)
    print(f'  calendar {data.calendar[0].date()} -> {data.calendar[-1].date()} '
          f'({len(data.calendar)} days), {len(data.codes)} rooms', flush=True)

    Xtr, Ytr, Mtr = data.matrix('train')
    Xca, Yca, Mca = data.matrix('calib')
    print(f'  train rows {Xtr.shape}   calibration rows {Xca.shape}', flush=True)
    print('  (test rows are never built here)', flush=True)

    print(f'\n{"=" * 78}\n LGB vs XGB, full {N_ESTIMATORS}-round training, no early stopping\n{"=" * 78}',
          flush=True)
    results = {}
    for engine, spec in ENGINES.items():
        for cfg_name, params in spec['grid'].items():
            print(f"\n[{engine} / {cfg_name}]", flush=True)
            models = fit_config(engine, params, Xtr, Ytr)
            scan = scan_checkpoints(engine, models, Xca, Yca, Mca, data)
            results[(engine, cfg_name)] = dict(models=models, params=params, **scan)
            print(f"   -> best acc={scan['best_acc']:.4f} @ round {scan['best_acc_round']}"
                  f"   best MAE={scan['best_mae']:.3f}h @ round {scan['best_mae_round']}",
                  flush=True)

    print(f"\n{'=' * 78}\n RESULT (selected on calibration; test is never touched here)\n{'=' * 78}")
    for (engine, cfg), r in sorted(results.items(), key=lambda kv: -kv[1]['best_acc']):
        print(f"   {engine:10s} {cfg:10s}  acc={r['best_acc']:.4f}@{r['best_acc_round']:<5d}"
              f"  mae={r['best_mae']:.3f}h@{r['best_mae_round']}")
    (win_engine, win_cfg), win = max(results.items(), key=lambda kv: kv[1]['best_acc'])
    print(f"\n>>> winner (by accuracy): {win_engine} / {win_cfg}  "
          f"(calibration acc={win['best_acc']:.4f}, round={win['best_acc_round']})")
    print(f"    that same config's best-MAE checkpoint: {win['best_mae']:.3f}h "
          f"@ round {win['best_mae_round']}")

    # ── refit the winner on train+calibration, at BOTH chosen round counts ──
    # The accuracy-optimal round serves the demand-band decision; the
    # MAE-optimal round serves the hours forecast.  Same features, same
    # config — only how many trees are kept differs, because the two outputs
    # answer different questions (see direct_forecast.median_forecast).
    print('\nRefitting the winning engine/config on train + calibration...', flush=True)
    spec = ENGINES[win_engine]
    Xfull, Yfull = np.vstack([Xtr, Xca]), np.concatenate([Ytr, Yca])
    n_acc = int(win['best_acc_round'] * 1.15)
    n_mae = int(win['best_mae_round'] * 1.15)
    serve_acc, serve_mae = {}, {}
    for q in D.QUANTILES:
        serve_acc[q] = spec['refit'](Xfull, Yfull, q, win['params'], n_acc)
        serve_mae[q] = (serve_acc[q] if n_mae == n_acc
                        else spec['refit'](Xfull, Yfull, q, win['params'], n_mae))
    predict_fn = spec['predict']

    # ── per-room strategy choice, scored on calibration only ────────────────
    print('\nChoosing a strategy per room (calibration window only):', flush=True)
    Qca_final = quantiles_at(win_engine, win['models'], Xca, win['best_acc_round'])
    ca_codes = np.array([m[0] for m in Mca])
    choice = {}
    for code in data.codes:
        if ROOMS_FILTER and code not in ROOMS_FILTER:
            continue
        k = ca_codes == code
        if not k.any():
            continue
        sub_meta = [m for m in Mca if m[0] == code]
        cands = D.strategies(data, code, Qca_final[k], Xca[k], sub_meta)
        r = data.rooms[code]
        scored = {}
        for name, pred in cands.items():
            pred = D.apply_block_floor(pred, Xca[k], sub_meta, data)
            cls = D.F.compute_classification_metrics(
                Yca[k] * r['scale'], np.maximum(0.0, pred) * r['scale'],
                r['thr_high'], r['thr_med'], r['peak'])
            scored[name] = cls['accuracy']
        n_days = max(1, r['calib_end'] - r['train_end'])
        best_strategy, lead = D.choose_strategy(scored, n_days)
        choice[code] = best_strategy
        detail = '  '.join(f'{k2}={v:.3f}' for k2, v in sorted(scored.items(),
                                                              key=lambda kv: -kv[1]))
        note = ''
        if lead > 0:
            note = (f"  [kept default; best led by {lead:.3f} < "
                    f"{D.selection_margin(n_days):.3f}]")
        print(f"   {code:12s} -> {best_strategy:14s}   ({detail}){note}", flush=True)

    joblib.dump({
        'engine': win_engine,
        'config_name': win_cfg,
        # separate model sets: one round-count for the demand band, another
        # for the hours forecast — see the module docstring for why
        'quantile_models_acc': serve_acc,
        'quantile_models_mae': serve_mae,
        'quantiles': list(D.QUANTILES),
        'strategy': choice,
        'params': win['params'],
        'calib_scan': {k: v for k, v in win.items() if k != 'models' and k != 'params'},
        'features': D.FEATURES,
        'rooms': {c: {k: v for k, v in r.items() if k != 'v'} for c, r in data.rooms.items()},
    }, os.path.join(OUT_DIR, 'model.pkl'))
    print(f"\nSaved -> {os.path.join(OUT_DIR, 'model.pkl')}  (engine={win_engine}, config={win_cfg})")
    print('Run:  python ml/saved/test_direct.py')


if __name__ == '__main__':
    main()
