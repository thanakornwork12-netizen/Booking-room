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
TRAIN_XLSX = os.path.join(SAVED_DIR, 'data_split', 'booking_data_train.xlsx')
TEST_XLSX = os.path.join(SAVED_DIR, 'data_split', 'booking_data_test.xlsx')
ACC_PNG = os.path.join(METRICS_DIR, 'test_curves_by_set.png')
LOSS_PNG = os.path.join(METRICS_DIR, 'test_loss_by_set.png')

ROOM_IDS = {
    '2C05-06': 443, '2C09': 445, '2C10-11': 446, '2C16-17': 447,
    '3C05-06': 448, '1C-MEETING': 487, '3C16-17': 505, '4C05': 506,
}
SETS = ['A', 'B', 'C', 'D', 'E']
SET_NAMES = {'A': 'Fast', 'B': 'Balanced', 'C': 'High Quality', 'D': 'Extra Deep', 'E': 'Max Depth'}
COLORS = {'A': '#f59e0b', 'B': '#10b981', 'C': '#3b82f6', 'D': '#8b5cf6', 'E': '#ef4444'}


def to_rdf(df, room_id):
    out = df.copy()
    out['room_id'] = room_id
    out['duration'] = out['duration_hours']
    out['date'] = pd.to_datetime(out['date']).dt.date
    return out


def room_test_curve(code, room_id, set_name, train_all, test_all):
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

    calib_len = max(1, int(round(n_train_days * 0.125)))
    train_end = max(n_train_days - calib_len, F.MIN_TRAIN_ROWS)
    calib_end = min(n_train_days, len(feat_df) - 1)
    train_end = min(train_end, calib_end)

    X = feat_df.drop(columns='y')
    y = feat_df['y'].values
    X_te = X.iloc[calib_end:]
    y_te = y[calib_end:]
    if len(y_te) == 0:
        return None

    feat_names = getattr(model, 'feature_name_', None) or getattr(model, 'feature_names_in_', None)
    X_te_sel = X_te[list(feat_names)] if feat_names is not None else X_te

    n_rounds = model.n_estimators_ if hasattr(model, 'n_estimators_') else PARAM_SETS[set_name][f'{"lgb" if winner == "lightgbm" else "xgb"}_estimators']
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


def plot_single(curves, ylabel, title, out_png, legend_loc):
    plt.rcParams.update({
        'savefig.facecolor': 'white', 'font.family': 'DejaVu Sans',
        'font.size': 11, 'axes.titlesize': 13, 'legend.fontsize': 9.5,
    })
    fig, ax = plt.subplots(figsize=(9, 6), dpi=300)
    for set_name in SETS:
        if set_name not in curves:
            continue
        c = COLORS[set_name]
        vals = curves[set_name]
        ax.plot(range(1, len(vals) + 1), vals, color=c, marker='o', markersize=3, linewidth=2,
                 label=f'{set_name} ({SET_NAMES[set_name]})')
    ax.set_title(title, fontweight='bold')
    ax.set_xlabel('Boosting Round')
    ax.set_ylabel(ylabel)
    ax.legend(loc=legend_loc)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(alpha=0.25)
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


if __name__ == '__main__':
    main()
