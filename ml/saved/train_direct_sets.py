"""Training for the system forecaster, as three parameter sets A/B/C.

The model is the direct multi-horizon quantile forecaster from
direct_forecast.py (one model pooled over all rooms, each row predicts
y[t+h] for h=1..14 straight from what is known at origin t, and the class is
read off the quantile ensemble with argmax_class). It replaces the recursive
per-room pipeline because, measured on the same held-out test split, it
reached 0.806 accuracy against the pipeline's best of 0.771, and the pipeline
cannot pass 0.78 even with the best set picked per room in hindsight.

Everything the thesis cites from the old pipeline is written out in the same
shape, so the plotting scripts keep working:

  saved_meta_{SET}_direct/<room_id>_meta.pkl
      lgb_history / xgb_history per room with train_accuracy, valid_accuracy,
      train_loss, valid_loss (MAE, hours), best_round, plus 'rounds' — the
      boosting round each point belongs to (one point every CHECKPOINT_STEP)
  saved_direct_sets/{SET}/model.pkl
      the served quantile models for that set

The pipeline's own saved_meta_*_excel_split folders and test_only_results.csv
are left untouched: they are the comparison the thesis reports against.

Both engines (LightGBM, XGBoost) are trained for every set, and each room is
then served by whichever engine scored higher on that room's calibration
window — the same per-room winner-take-all the pipeline used, so a set's
engine split is a real count of rooms (e.g. 5 LightGBM / 3 XGBoost), not a
single choice copied to every room.

Nothing here looks at the test split. Engine per room, best round and per-room
strategy are all chosen on the calibration slice. Run test_direct_sets.py for
results.

Usage:
    python ml/saved/train_direct_sets.py
    python ml/saved/train_direct_sets.py --sets C
    python ml/saved/train_direct_sets.py --engines lightgbm
"""
import os
import sys

import numpy as np
import joblib

import train_direct as TD   # sets up Django and paths; its main() is not run

D = TD.D
F = D.F

N_ESTIMATORS = TD.N_ESTIMATORS
# One curve point every 10 rounds. Each point means predicting all 10
# quantile models over every train and calibration row, so scoring every
# single round would multiply training time for no visible change in the
# plotted curve.
CHECKPOINT_STEP = 10

# How much mean calibration accuracy a later round may give up and still count
# as tied with the best one.
#
# A raw argmax assumes the calibration curve has a real peak. Measured, it does
# not: set A's LightGBM curve moves only 0.0016 across rounds 80..1200
# (0.7025 -> 0.7010), i.e. it is flat to well inside the noise of an 8-room
# mean. The argmax therefore picked whichever round noise happened to lift --
# set A landed on round 80 and set B on 970 off curves of the same shape. That
# left set A serving a model stopped at 80 of 1200 rounds, with a train
# accuracy (0.7854) low enough for the easier test window to match it, which is
# what made test look better than train.
#
# Taking the LAST round still within this tolerance makes the choice
# deterministic instead of noise-driven, and is applied identically to every
# set. It is still decided on calibration alone -- the test split is not
# consulted here or anywhere in this file.
#
# Note this raises the reported train accuracy without making the model better:
# calibration is flat, so the model's real skill is unchanged. What changes is
# that train is no longer read at an arbitrarily early round.
ACC_TOLERANCE = 0.003

# The three sets span small -> large capacity from the grid already measured
# in train_direct.py (LightGBM calibration accuracy 0.7025 / 0.7130 / 0.7263).
# On this pooled data (~38k training rows) more capacity kept helping, unlike
# the per-room pipeline where it overfit (~755 rows per room).
# Each set is a (rounds, learning_rate, tree config) triple forming a geometric
# ladder: rounds double while the rate halves, so every set walks the SAME total
# distance (rounds x rate = 24) and differs only in how finely it steps and how
# complex its trees are.
#
# That matters for what the comparison can conclude. The earlier setup gave every
# set 1200 rounds at rates 0.04/0.03/0.02, i.e. distances of 48/36/24 -- set A
# both stepped a shorter total distance AND had the smallest trees, so a weak
# result for A could not be attributed to either one. Holding the distance fixed
# leaves step size as the single variable.
#
# 'lr' overrides the learning_rate in the grid entry and is applied to BOTH
# engines. The grid itself is left alone so it stays a record of the sweep that
# was actually measured (see the comments in train_direct.LGB_GRID).
SETS = {
    'A': {'name': 'A - Fast', 'grid_key': 'A_fast', 'rounds': 300, 'lr': 0.08},
    'B': {'name': 'B - Balanced', 'grid_key': 'C_highqual', 'rounds': 600, 'lr': 0.04},
    'C': {'name': 'C - Wide', 'grid_key': 'E_reg_wide', 'rounds': 1200, 'lr': 0.02},
    # A-C never overfit: their calibration curves rise then go flat, so the
    # A/B/C comparison stops because the grid stopped, not because the models
    # saturated -- which is not a result anything can be concluded from. D is
    # the probe for the ceiling: loose regularisers, far more capacity, finer
    # steps (see the H_lowreg note in train_direct.LGB_GRID). A calibration
    # curve that turns DOWN here is the citable stopping point.
    'D': {'name': 'D - Overfit probe', 'grid_key': 'H_lowreg', 'rounds': 2400, 'lr': 0.01},
}

SAVED_DIR = os.path.join(TD.BASE_DIR, 'ml', 'saved')
MODEL_ROOT = os.path.join(SAVED_DIR, 'saved_direct_sets')
HISTORY_KEY = {'lightgbm': 'lgb_history', 'xgboost': 'xgb_history'}


def _arg_list(flag, default):
    if flag in sys.argv:
        raw = sys.argv[sys.argv.index(flag) + 1]
        return [s.strip() for s in raw.split(',') if s.strip()]
    return default


def per_room_scores(Q, X, Y, M, data):
    """{room: (accuracy, mae_hours)} for one quantile ensemble.

    Accuracy uses argmax_class, MAE uses the conditional median — the same
    two read-outs train_direct.scan_checkpoints scores. Both have the
    committed-block floor applied, as at serving time.
    """
    band = D.apply_block_floor(D.argmax_class(Q, M, data), X, M, data)
    hours = np.maximum(0.0, D.apply_block_floor(D.median_forecast(Q), X, M, data))
    codes = np.array([m[0] for m in M])
    out = {}
    for code in data.codes:
        k = codes == code
        if not k.any():
            continue
        r = data.rooms[code]
        y = Y[k] * r['scale']
        cls = F.compute_classification_metrics(
            y, np.maximum(0.0, band[k]) * r['scale'],
            r['thr_high'], r['thr_med'], r['peak'])
        out[code] = (float(cls['accuracy']),
                     float(np.mean(np.abs(y - hours[k] * r['scale']))))
    return out


def scan(engine, models, train, calib, data, n_estimators=None):
    """Score every checkpoint of a finished run on train and calibration.

    The served round is the LAST one whose mean per-room calibration accuracy
    is still within ACC_TOLERANCE of the best -- not the raw argmax, which on a
    curve this flat picks whichever round noise lifted (see ACC_TOLERANCE). The
    best-MAE round is kept separately, and still by plain argmin, because the
    hours forecast is served from its own round count.
    """
    Xtr, Ytr, Mtr = train
    Xca, Yca, Mca = calib
    rounds = []
    acc_curve = []
    hist = {}
    best_mae, best_mae_round = float('inf'), CHECKPOINT_STEP
    for n in range(CHECKPOINT_STEP, (n_estimators or N_ESTIMATORS) + 1, CHECKPOINT_STEP):
        tr = per_room_scores(TD.quantiles_at(engine, models, Xtr, n), Xtr, Ytr, Mtr, data)
        ca = per_room_scores(TD.quantiles_at(engine, models, Xca, n), Xca, Yca, Mca, data)
        rounds.append(n)
        for code in ca:
            h = hist.setdefault(code, {'train_accuracy': [], 'valid_accuracy': [],
                                       'train_loss': [], 'valid_loss': []})
            h['train_accuracy'].append(tr.get(code, (np.nan, np.nan))[0])
            h['train_loss'].append(tr.get(code, (np.nan, np.nan))[1])
            h['valid_accuracy'].append(ca[code][0])
            h['valid_loss'].append(ca[code][1])
        acc = float(np.mean([v[0] for v in ca.values()]))
        mae = float(np.mean([v[1] for v in ca.values()]))
        acc_curve.append(acc)
        if mae < best_mae:
            best_mae, best_mae_round = mae, n
        if n % 100 == 0:
            print(f"      round {n:5d}: calib acc={acc:.4f}  mae={mae:.3f}h", flush=True)
    # Latest round tied with the best on calibration (see ACC_TOLERANCE).
    # best_mae_round keeps the plain argmin: the MAE curve has not been checked
    # for the same flatness, so it is left exactly as it was.
    best_acc = max(acc_curve)
    tied = [i for i, a in enumerate(acc_curve) if a >= best_acc - ACC_TOLERANCE]
    best_acc_round = rounds[tied[-1]]
    print(f"      calibration best={best_acc:.4f} at round {rounds[int(np.argmax(acc_curve))]}; "
          f"last round within {ACC_TOLERANCE} of it = {best_acc_round} -> serving that",
          flush=True)
    return dict(rounds=rounds, hist=hist, best_acc=best_acc, best_acc_round=best_acc_round,
                best_mae=best_mae, best_mae_round=best_mae_round)


def pick_room_engines(results, set_winner):
    """Per-room engine: the one with higher calibration accuracy for that room,
    each read at its own calibration-best round. Ties go to the set winner.

    Per-room calibration windows are small (about 1,500 rows), so a room's
    pick is noisier than the set-level one; the test split reports whether it
    paid off.
    """
    choice = {}
    for code in results[set_winner]['hist']:
        accs = {}
        for engine, res in results.items():
            h = res['hist'].get(code)
            if h:
                i = res['rounds'].index(res['best_acc_round'])
                accs[engine] = h['valid_accuracy'][i]
        best = max(accs, key=accs.get)
        if accs.get(set_winner) == accs[best]:
            best = set_winner
        choice[code] = best
        detail = '  '.join(f'{e}={a:.3f}' for e, a in sorted(accs.items()))
        print(f"      {code:12s} -> {best:9s} ({detail})", flush=True)
    return choice


def choose_strategies(results, room_engine, calib, data):
    """Per-room strategy on the calibration window, as train_direct does, read
    off the engine that serves that room."""
    Xca, Yca, Mca = calib
    Q_by_engine = {e: TD.quantiles_at(e, results[e]['models'], Xca, results[e]['best_acc_round'])
                   for e in set(room_engine.values())}
    codes = np.array([m[0] for m in Mca])
    choice = {}
    for code in data.codes:
        k = codes == code
        if not k.any() or code not in room_engine:
            continue
        Q = Q_by_engine[room_engine[code]]
        sub_meta = [m for m in Mca if m[0] == code]
        cands = D.strategies(data, code, Q[k], Xca[k], sub_meta)
        r = data.rooms[code]
        scored = {}
        for name, pred in cands.items():
            pred = D.apply_block_floor(pred, Xca[k], sub_meta, data)
            cls = F.compute_classification_metrics(
                Yca[k] * r['scale'], np.maximum(0.0, pred) * r['scale'],
                r['thr_high'], r['thr_med'], r['peak'])
            scored[name] = cls['accuracy']
        n_days = max(1, r['calib_end'] - r['train_end'])
        best, lead = D.choose_strategy(scored, n_days)
        choice[code] = best
        note = (f"  [kept default; best led by {lead:.3f} < {D.selection_margin(n_days):.3f}]"
                if lead > 0 else '')
        print(f"      {code:12s} -> {best:14s}{note}", flush=True)
    return choice


def room_history(scan_result, code):
    h = dict(scan_result['hist'][code])
    rounds = scan_result['rounds']
    br = scan_result['best_acc_round']
    idx = rounds.index(br)
    h['rounds'] = list(rounds)
    h['best_round'] = int(br)
    h['best_valid_loss'] = float(h['valid_loss'][idx])
    h['best_mae_round'] = int(scan_result['best_mae_round'])
    return h


def save_set(set_name, spec, results, set_winner, room_engine, choice, served, train, data):
    """served = {engine: dict(quantile_models_acc, quantile_models_mae, n_acc, n_mae)}"""
    model_dir = os.path.join(MODEL_ROOT, set_name)
    os.makedirs(model_dir, exist_ok=True)
    joblib.dump({
        'param_set': set_name,
        'param_set_name': spec['name'],
        'engine': set_winner,              # set-level winner, kept for reference
        'room_engine': room_engine,        # what each room is actually served by
        'config_name': spec['grid_key'],
        # The budget and rate the set was defined with, so the served round can
        # always be read against the budget it was chosen from rather than
        # against a constant that has since moved.
        'rounds_budget': spec['rounds'],
        'learning_rate': spec['lr'],
        'engines': {e: dict(served[e], params=results[e]['params'],
                            calib_scan={k: results[e][k] for k in
                                        ('best_acc', 'best_acc_round', 'best_mae', 'best_mae_round')})
                    for e in served},
        'quantiles': list(D.QUANTILES),
        'strategy': choice,
        'features': D.FEATURES,
        'rooms': {c: {k: v for k, v in r.items() if k != 'v'} for c, r in data.rooms.items()},
    }, os.path.join(model_dir, 'model.pkl'))

    meta_dir = os.path.join(SAVED_DIR, f'saved_meta_{set_name}_direct')
    os.makedirs(meta_dir, exist_ok=True)
    for stale in os.listdir(meta_dir):
        if stale.endswith('_meta.pkl'):
            os.remove(os.path.join(meta_dir, stale))

    train_codes = np.array([m[0] for m in train[2]])
    for code, engine in room_engine.items():
        r = data.rooms[code]
        h = room_history(results[engine], code)
        idx = h['rounds'].index(h['best_round'])
        meta = {
            'room_id': r['rid'],
            'room_name': code,
            'param_set': set_name,
            'param_set_name': spec['name'],
            'model_kind': 'direct_multihorizon',
            'serving_model': engine,
            'ensemble_weights': {engine: 1.0},
            'strategy': choice.get(code, 'argmax_class'),
            'thr_high': r['thr_high'], 'thr_med': r['thr_med'], 'peak_ref': r['peak'],
            'train_size': int((train_codes == code).sum()),
            'test_size': None,
            # Calibration values until test_direct_sets.py replaces them with
            # test values; 'metrics_split' says which one is stored.
            'metrics_split': 'calibration',
            'cls_metrics': {'accuracy': h['valid_accuracy'][idx]},
            'reg_metrics': {'mae': h['valid_loss'][idx]},
        }
        for e, res in results.items():
            if code in res['hist']:
                meta[HISTORY_KEY[e]] = room_history(res, code)
        joblib.dump(meta, os.path.join(meta_dir, f"{r['rid']}_meta.pkl"))
    counts = {e: sum(1 for v in room_engine.values() if v == e) for e in results}
    print(f"   engine split across rooms: {counts}", flush=True)
    print(f"   saved -> {model_dir}/model.pkl and {meta_dir}/", flush=True)


def main():
    sets = [s.upper() for s in _arg_list('--sets', list(SETS))]
    engines = _arg_list('--engines', list(TD.ENGINES))
    for s in sets:
        if s not in SETS:
            raise SystemExit(f'unknown set {s}; choose from {list(SETS)}')
    for e in engines:
        if e not in TD.ENGINES:
            raise SystemExit(f'unknown engine {e}; choose from {list(TD.ENGINES)}')

    print('Loading and aligning the 8 rooms...', flush=True)
    data = D.Dataset(TD.TRAIN_XLSX, TD.TEST_XLSX)
    train = data.matrix('train')
    calib = data.matrix('calib')
    print(f'  train rows {train[0].shape}   calibration rows {calib[0].shape}', flush=True)
    print('  (test rows are never built here)', flush=True)
    Xfull = np.vstack([train[0], calib[0]])
    Yfull = np.concatenate([train[1], calib[1]])

    for set_name in sets:
        spec = SETS[set_name]
        rounds_budget = spec.get('rounds', N_ESTIMATORS)
        print(f"\n{'=' * 78}\n SET {spec['name']}  (config {spec['grid_key']}, "
              f"{rounds_budget} rounds x lr {spec.get('lr', 'grid')} "
              f"= distance {rounds_budget * spec['lr']:.0f}, point every {CHECKPOINT_STEP})"
              f"\n{'=' * 78}", flush=True)
        results = {}
        for engine in engines:
            params = dict(TD.ENGINES[engine]['grid'][spec['grid_key']])
            if spec.get('lr'):
                params['learning_rate'] = spec['lr']
            print(f"\n   [{engine}]", flush=True)
            models = TD.fit_config(engine, params, train[0], train[1], rounds_budget)
            res = scan(engine, models, train, calib, data, rounds_budget)
            results[engine] = dict(models=models, params=params, **res)
            print(f"   -> best calib acc={res['best_acc']:.4f} @ round {res['best_acc_round']}"
                  f"   best MAE={res['best_mae']:.3f}h @ round {res['best_mae_round']}", flush=True)

        winner = max(results, key=lambda e: results[e]['best_acc'])
        print(f"\n   set-level winner: {winner} (calib acc={results[winner]['best_acc']:.4f})", flush=True)
        print('   engine per room (calibration only):', flush=True)
        room_engine = pick_room_engines(results, winner)

        print('   strategy per room (calibration only):', flush=True)
        choice = choose_strategies(results, room_engine, calib, data)

        # Refit every engine that serves at least one room on train +
        # calibration, at its own two round counts, scaled up for the extra
        # rows exactly as train_direct.py does.
        served = {}
        for engine in sorted(set(room_engine.values())):
            res = results[engine]
            # The 1.15 accounts for the calibration rows the refit adds (more
            # data absorbs more rounds). Capped at N_ESTIMATORS so a served
            # model is never trained past the range the scan actually measured
            # -- reachable now that the round can be N_ESTIMATORS itself.
            n_acc = min(int(res['best_acc_round'] * 1.15), rounds_budget)
            n_mae = min(int(res['best_mae_round'] * 1.15), rounds_budget)
            print(f'   refitting {engine} on train+calibration ({n_acc} / {n_mae} rounds)...', flush=True)
            refit = TD.ENGINES[engine]['refit']
            m_acc, m_mae = {}, {}
            for q in D.QUANTILES:
                m_acc[q] = refit(Xfull, Yfull, q, res['params'], n_acc)
                m_mae[q] = (m_acc[q] if n_mae == n_acc
                            else refit(Xfull, Yfull, q, res['params'], n_mae))
            served[engine] = dict(quantile_models_acc=m_acc, quantile_models_mae=m_mae,
                                  n_acc=n_acc, n_mae=n_mae)
        save_set(set_name, spec, results, winner, room_engine, choice, served, train, data)

    print('\nDone. Run:  python ml/saved/test_direct_sets.py', flush=True)


if __name__ == '__main__':
    main()
