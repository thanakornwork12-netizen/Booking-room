"""Test-set accuracy/loss per round, one line per param set (A-E), averaged
across all 8 rooms' winning model (LGB or XGB — LSTM never wins any room in
the current results, so it's skipped entirely; no retraining involved).

Unlike train_accuracy/valid_accuracy (free — already recorded round-by-round
in meta.pkl during training), a per-round TEST metric was never computed or
cached anywhere. But since LightGBM/XGBoost's already-trained boosters can
predict using only their first K trees (num_iteration / iteration_range),
getting "test accuracy as if training stopped at round K" needs no
retraining — just repeated prediction with the saved lgb.pkl/xgb.pkl.

Outputs:
  metrics_plots/test_curves_by_set.png  (TestAcc per round)
  metrics_plots/test_loss_by_set.png    (TestLoss per round)

Usage: python ml/saved/plot_test_curves_by_set.py
"""
import os, sys, warnings
warnings.filterwarnings('ignore')

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
import glob
import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import forecast as F
from param_sets import PARAM_SETS
from booking.models import Room

SAVED_DIR = os.path.join(BASE_DIR, 'ml', 'saved')
METRICS_DIR = F.METRICS_DIR
TRAIN_XLSX = os.path.join(SAVED_DIR, 'data_split', 'dataset_train.xlsx')
TEST_XLSX = os.path.join(SAVED_DIR, 'data_split', 'dataset_test.xlsx')
ACC_PNG = os.path.join(METRICS_DIR, 'test_curves_by_set.png')
LOSS_PNG = os.path.join(METRICS_DIR, 'test_loss_by_set.png')
BOTH_PNG = os.path.join(METRICS_DIR, 'test_curves_and_loss_by_set.png')

# --direct plots the direct-model sets from the test curves that
# test_direct_sets.py stored in saved_meta_{SET}_direct, and writes separate
# files so the pipeline figures are kept.
DIRECT = '--direct' in sys.argv or '--blocked' in sys.argv
if DIRECT:
    ACC_PNG = ACC_PNG.replace('.png', '_direct.png')
    LOSS_PNG = LOSS_PNG.replace('.png', '_direct.png')
    BOTH_PNG = BOTH_PNG.replace('.png', '_direct.png')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blocked_variant  # noqa: E402
blocked_variant.apply(globals())
CURVE_ROUNDS = {}   # set -> boosting round of each point, when not one per round

ROOM_IDS = {
    '2C05-06': 443, '2C09': 445, '2C10-11': 446, '2C16-17': 447,
    '3C05-06': 448, '1C-MEETING': 487, '3C16-17': 505, '4C05': 506,
}
# Only A/B/C are trained now: those three vary the training schedule
# (300/800/1500 trees at lr .05/.03/.01) with capacity held fixed. D/E belong
# to an older experiment and have no current metas, so leaving them in this
# list drew empty series.
# D is a direct-pipeline set only. saved_meta_D_excel_split exists but holds
# metas from a run that predates the daily-occupancy fix, so pulling it into the
# recursive figures would put two different datasets in one chart.
SETS = ['A', 'B', 'C', 'D'] if DIRECT else ['A', 'B', 'C']
SET_NAMES = ({'A': 'Fast', 'B': 'Balanced', 'C': 'Wide', 'D': 'Overfit probe'} if DIRECT else
             {'A': 'Fast', 'B': 'Balanced', 'C': 'High Quality', 'D': 'Extra Deep', 'E': 'Max Depth'})
COLORS = {'A': '#f59e0b', 'B': '#10b981', 'C': '#3b82f6', 'D': '#8b5cf6', 'E': '#ef4444'}


def to_rdf(df, room_id):
    out = df.copy()
    out['room_id'] = room_id
    out['duration'] = out['duration_hours']
    out['date'] = pd.to_datetime(out['date']).dt.date
    return out


def actual_boost_rounds(model, winner, set_name):
    """จำนวนรอบ boosting ที่โมเดล "มีอยู่จริง" ไม่ใช่ค่าที่ตั้งไว้ใน PARAM_SETS

    forecast.py เทรนด้วย early stopping ทั้งสองโมเดล โมเดลจึงมักมีต้นไม้น้อย
    กว่า n_estimators ที่ตั้งไว้ — ถ้าไล่ predict ตามค่า config จะขอเกินจำนวน
    ต้นไม้จริง ซึ่ง XGBoost จะโยน "Check failed: end <= model.BoostedRounds()"
    ทำให้สคริปต์ตายทั้งตัว (LightGBM ไม่ตาย มันคลิปให้เงียบๆ แต่กราฟช่วงท้าย
    จะเป็นเส้นแบนซ้ำค่าเดิม ซึ่งก็ไม่ถูกอยู่ดี)

    LGBMRegressor มี n_estimators_ ที่สะท้อนจำนวนจริงหลัง early stopping แล้ว
    ส่วน XGBRegressor ไม่มี ต้องถามจาก booster โดยตรง
    """
    if winner == 'lightgbm':
        n = getattr(model, 'n_estimators_', None)
        if n:
            return int(n)
        booster = getattr(model, 'booster_', None)
        if booster is not None:
            return int(booster.num_trees())
    else:
        try:
            return int(model.get_booster().num_boosted_rounds())
        except Exception:
            best = getattr(model, 'best_iteration', None)
            if best is not None:
                return int(best) + 1
        # ถามจากโมเดลไม่ได้เลย — คืน None ให้ผู้เรียกข้ามห้องนี้ไป ห้ามคืนค่าจาก
        # PARAM_SETS เพราะนั่นคือค่าที่ทำให้ XGBoost crash ตั้งแต่แรก (ขอ predict
        # เกินจำนวนต้นไม้ที่มีจริง) การข้ามหนึ่งห้องดีกว่าทำทั้งสคริปต์ตาย
        return None
    return int(PARAM_SETS[set_name][f'{"lgb" if winner == "lightgbm" else "xgb"}_estimators'])


def room_test_curve(code, room_id, set_name, train_all, test_all):
    if DIRECT:
        # The pooled direct model cannot be re-run per room like a lgb.pkl;
        # test_direct_sets.py already scored it every 10 rounds.
        meta_path = os.path.join(SAVED_DIR, f'saved_meta_{set_name}_direct', f'{room_id}_meta.pkl')
        if not os.path.exists(meta_path):
            return None
        tc = joblib.load(meta_path).get('test_curve')
        if not tc:
            return None
        # Rooms are served by different engines at different round counts, and the
        # averaged curve is as long as the longest room. Keep that room's rounds:
        # keeping the last room's left the x-axis shorter than the curve, so it fell
        # back to point indices and A/D were drawn ~10x too narrow.
        if len(tc['rounds']) > len(CURVE_ROUNDS.get(set_name, [])):
            CURVE_ROUNDS[set_name] = tc['rounds']
        return list(tc['accuracy']), list(tc['loss'])
    meta_path = os.path.join(SAVED_DIR, f'saved_meta_{set_name}_excel_split', f'{room_id}_meta.pkl')
    if not os.path.exists(meta_path):
        return None
    meta = joblib.load(meta_path)
    use_log = meta.get('use_log', False)
    weights = meta.get('ensemble_weights', {}) or {}
    winner = max(weights, key=weights.get) if weights else 'lightgbm'
    if winner not in ('lightgbm', 'xgboost'):
        return None  # LSTM winner would need retraining — skip (none in current data)

    model_dir = os.path.join(SAVED_DIR, f'saved_models_{set_name}_excel_split', str(room_id))
    model_path = os.path.join(model_dir, 'lgb.pkl' if winner == 'lightgbm' else 'xgb.pkl')
    if not os.path.exists(model_path):
        return None
    model = joblib.load(model_path)

    tr = train_all[train_all['room_code'] == code]
    te = test_all[test_all['room_code'] == code]
    if len(te) == 0:
        return None
    rdf_full = pd.concat([to_rdf(tr, room_id), to_rdf(te, room_id)], ignore_index=True)
    daily_full = F._prepare_daily_series(rdf_full, None, None)
    # Same boundary test_from_excel.py uses: length of the train-ONLY daily
    # series marks where the real held-out test_xlsx rows begin — NOT an
    # arbitrary fraction split of the recombined train+test data (that would
    # leak rows the model was actually trained on into the "test" evaluation).
    daily_train_only = F._prepare_daily_series(to_rdf(tr, room_id), None, None)
    n_train_days = len(daily_train_only) if daily_train_only is not None else 0
    room = Room.objects.get(id=room_id)
    schedule = F.load_term_schedule(room.id)
    cap95 = float(daily_full.quantile(0.95)) or 1.0
    daily_clipped = daily_full.clip(upper=cap95)
    term_df = F.build_term_daily_features(daily_clipped.index, schedule)
    term_df.index = daily_clipped.index
    feat_df = F.build_features(daily_clipped, term_df, use_log=use_log).dropna()

    # สคริปต์นี้ใช้แค่ขอบของ test set (calib_end) — ไม่ต้องคำนวณขอบ train
    # (ต่างจาก test_from_excel.py ที่ยกโค้ดส่วนนี้มา ซึ่งใช้ train_end จริง)
    calib_end = min(n_train_days, len(feat_df) - 1)

    X = feat_df.drop(columns='y')
    y = feat_df['y'].values
    X_te = X.iloc[calib_end:]
    y_te = y[calib_end:]
    if len(y_te) == 0:
        return None

    feat_names = getattr(model, 'feature_name_', None) or getattr(model, 'feature_names_in_', None)
    X_te_sel = X_te[list(feat_names)] if feat_names is not None else X_te

    n_rounds = actual_boost_rounds(model, winner, set_name)
    if not n_rounds:
        print(f'   ! ข้าม {code} ({set_name}): หาจำนวนรอบ boosting ของโมเดลไม่ได้')
        return None
    y_eval = np.expm1(y_te) if use_log else y_te.copy()

    accs, losses = [], []
    for k in range(1, n_rounds + 1):
        if winner == 'lightgbm':
            pred = np.asarray(model.predict(X_te_sel, num_iteration=k), dtype=float)
        else:
            pred = np.asarray(model.predict(X_te_sel, iteration_range=(0, k)), dtype=float)
        pred_eval = np.expm1(np.maximum(0, pred)) if use_log else np.maximum(0, pred)
        cls = F.compute_classification_metrics(y_eval, pred_eval, meta['thr_high'], meta['thr_med'], meta['peak_ref'])
        accs.append(cls['accuracy'])
        losses.append(cls['loss'])
    return accs, losses


def collect_set(set_name, train_all, test_all):
    F.LSTM_LOOKBACK = PARAM_SETS[set_name]['lstm_lookback']  # unused here, kept for parity with other scripts
    per_room_acc, per_room_loss = [], []
    for code, room_id in ROOM_IDS.items():
        result = room_test_curve(code, room_id, set_name, train_all, test_all)
        if result is None:
            continue
        accs, losses = result
        per_room_acc.append(accs)
        per_room_loss.append(losses)
    if not per_room_acc:
        return None
    max_len = max(len(a) for a in per_room_acc)
    padded_acc = np.array([a + [a[-1]] * (max_len - len(a)) for a in per_room_acc])
    padded_loss = np.array([a + [a[-1]] * (max_len - len(a)) for a in per_room_loss])
    return padded_acc.mean(axis=0) * 100, padded_loss.mean(axis=0)


def _style():
    plt.rcParams.update({
        'savefig.facecolor': 'white', 'font.family': 'DejaVu Sans',
        'font.size': 11, 'axes.titlesize': 13, 'legend.fontsize': 9.5,
    })


def _draw(ax, curves, ylabel, title, legend_loc):
    for set_name in SETS:
        if set_name not in curves:
            continue
        c = COLORS[set_name]
        vals = curves[set_name]
        rounds = CURVE_ROUNDS.get(set_name)
        xs = rounds if rounds and len(rounds) == len(vals) else range(1, len(vals) + 1)
        ax.plot(xs, vals, color=c, marker='o', markersize=3, linewidth=2,
                 label=f'{set_name} ({SET_NAMES[set_name]})')
    ax.set_title(title, fontweight='bold')
    ax.set_xlabel('Boosting Round')
    ax.set_ylabel(ylabel)
    ax.legend(loc=legend_loc)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(alpha=0.25)


def plot_single(curves, ylabel, title, out_png, legend_loc):
    _style()
    fig, ax = plt.subplots(figsize=(9, 6), dpi=300)
    _draw(ax, curves, ylabel, title, legend_loc)
    fig.suptitle('Test Curves by Param Set — Winning Model per Room', fontweight='bold', fontsize=14)
    fig.tight_layout()
    plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close(fig)
    print(f'Saved: {out_png}')


def plot_both(acc_curves, loss_curves, out_png):
    """Accuracy on the left, loss on the right, one figure. Both panels come from
    the same _draw so a set keeps the same colour/label in each."""
    _style()
    fig, (ax_acc, ax_loss) = plt.subplots(1, 2, figsize=(17, 6), dpi=300)
    _draw(ax_acc, acc_curves, 'Accuracy (%)', 'TestAcc per Round (avg. across 8 rooms)', 'lower right')
    _draw(ax_loss, loss_curves, 'Loss (MAE, hours)', 'Test Loss per Round (avg. across 8 rooms)', 'upper right')
    fig.suptitle('Test Curves by Param Set — Winning Model per Room', fontweight='bold', fontsize=14)
    fig.tight_layout()
    plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close(fig)
    print(f'Saved: {out_png}')


def main():
    train_all = pd.read_excel(TRAIN_XLSX)
    test_all = pd.read_excel(TEST_XLSX)
    train_all['date'] = pd.to_datetime(train_all['date']).dt.date
    test_all['date'] = pd.to_datetime(test_all['date']).dt.date

    acc_curves, loss_curves = {}, {}
    for set_name in SETS:
        print(f"Processing Set {set_name}...")
        result = collect_set(set_name, train_all, test_all)
        if result is None:
            continue
        acc_curves[set_name], loss_curves[set_name] = result

    plot_single(acc_curves, 'Accuracy (%)', 'TestAcc per Round (avg. across 8 rooms)', ACC_PNG, 'lower right')
    plot_single(loss_curves, 'Loss (MAE)', 'Test Loss per Round (avg. across 8 rooms)', LOSS_PNG, 'upper right')
    plot_both(acc_curves, loss_curves, BOTH_PNG)


if __name__ == '__main__':
    main()
