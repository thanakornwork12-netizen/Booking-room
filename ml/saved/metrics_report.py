import os

import joblib
import numpy as np
import pandas as pd


def aggregate_model_metrics(room_metas):
    models = ['ensemble', 'lightgbm', 'xgboost', 'lstm']
    agg = {
        model: {
            'count': 0,
            'r2': [], 'mae': [], 'rmse': [], 'smape': [],
            'accuracy': [], 'f1': [], 'recall': [], 'precision': [], 'loss': [],
        }
        for model in models
    }
    for _, meta in room_metas:
        if not isinstance(meta, dict):
            continue
        model_metrics = meta.get('model_metrics') or {}
        for model in models:
            metrics = model_metrics.get(model)
            if not isinstance(metrics, dict):
                continue
            reg = metrics.get('regression') or {}
            cls = metrics.get('classification') or {}
            if not reg and not cls:
                continue
            agg[model]['count'] += 1
            for metric_name in ['r2', 'mae', 'rmse', 'smape']:
                if isinstance(reg.get(metric_name), (int, float)):
                    agg[model][metric_name].append(reg[metric_name])
            for metric_name in ['accuracy', 'f1', 'recall', 'precision', 'loss']:
                if isinstance(cls.get(metric_name), (int, float)):
                    agg[model][metric_name].append(cls[metric_name])

    summary = {}
    for model, values in agg.items():
        if values['count'] == 0:
            continue
        summary[model] = {'count': values['count']}
        for metric_name in ['r2', 'mae', 'rmse', 'smape', 'accuracy', 'f1', 'recall', 'precision', 'loss']:
            summary[model][metric_name] = np.nanmean(values[metric_name]) if values[metric_name] else np.nan
    return summary


def _print_model_summary(model_summary):
    if not model_summary:
        return
    print("\n📊 Summary Metrics by Model (average across rooms with data)")
    print("-------------------------------------------------------------------------------")
    print(
        f"{'Model':<9} {'Cnt':>4} {'R2':>6} {'MAE':>6} {'RMSE':>6} {'sMAPE':>6} "
        f"{'Acc':>6} {'F1':>6} {'Rec':>6} {'Prec':>6} {'Loss':>6}"
    )
    print("-------------------------------------------------------------------------------")
    for name in ['ensemble', 'lightgbm', 'xgboost', 'lstm']:
        summary = model_summary.get(name)
        if not summary:
            continue
        print(
            f"{name.title():<9} {summary['count']:>4} "
            f"{summary['r2']:>6.3f} {summary['mae']:>6.3f} {summary['rmse']:>6.3f} "
            f"{summary['smape']:>6.3f} {summary['accuracy']:>6.3f} {summary['f1']:>6.3f} "
            f"{summary['recall']:>6.3f} {summary['precision']:>6.3f} {summary['loss']:>6.3f}"
        )
    print("=" * 118)


def show_saved_metrics(room_model, meta_dir, metrics_dir, compact: bool = False):
    print("\n📊 METRICS ภาพรวมทั้งหมด – ผลการเทรนครั้งล่าสุด")
    print("=" * 75)
    all_stats = []
    room_metas = []

    for room in room_model.objects.all():
        row = {
            'RoomID': room.id,
            'Room': room.name,
            'Type': getattr(room, 'room_type', 'unknown'),
            'Status': 'NO_META',
            'HasLSTM': False,
            'Robust': False,
            'Fallback': False,
            'R2': np.nan,
            'MAE': np.nan,
            'RMSE': np.nan,
            'sMAPE': np.nan,
            'Accuracy': np.nan,
            'F1': np.nan,
            'Recall': np.nan,
            'Precision': np.nan,
            'Loss': np.nan,
            'Conf': np.nan,
            'Acc_ensemble': np.nan,
            'Acc_lgb': np.nan,
            'Acc_xgb': np.nan,
            'Acc_lstm': np.nan,
        }

        meta_path = os.path.join(meta_dir, f"{room.id}_meta.pkl")
        if not os.path.exists(meta_path):
            all_stats.append(row)
            continue

        meta = joblib.load(meta_path)
        reg = meta.get('reg_metrics')
        cls = meta.get('cls_metrics')
        row.update({
            'Status': 'NO_METRICS',
            'HasLSTM': meta.get('has_lstm', False),
            'Robust': meta.get('robust', False),
            'Fallback': meta.get('used_fallback', False),
            'Conf': meta.get('confidence', np.nan),
        })
        if reg and cls:
            room_metas.append((room.name, meta))
            row.update({
                'Status': 'OK',
                'R2': reg['r2'],
                'MAE': reg['mae'],
                'RMSE': reg['rmse'],
                'sMAPE': reg['smape'],
                'Accuracy': cls['accuracy'],
                'F1': cls['f1'],
                'Recall': cls['recall'],
                'Precision': cls['precision'],
                'Loss': cls['loss'],
            })
            model_metrics = meta.get('model_metrics', {}) if isinstance(meta, dict) else {}
            for col, model_name in [
                ('Acc_ensemble', 'ensemble'),
                ('Acc_lgb', 'lightgbm'),
                ('Acc_xgb', 'xgboost'),
                ('Acc_lstm', 'lstm'),
            ]:
                try:
                    row[col] = float(model_metrics.get(model_name, {}).get('classification', {}).get('accuracy', np.nan))
                except Exception:
                    row[col] = np.nan
        all_stats.append(row)

    if not all_stats:
        print("❌ ไม่พบข้อมูล กรุณารัน --retrain ก่อนครับ")
        return

    model_summary = aggregate_model_metrics(room_metas)
    if compact:
        _print_model_summary(model_summary)
        return

    df = pd.DataFrame(all_stats)
    df_ok = df[df['Status'] == 'OK'].copy()
    print(f"📌 ห้องทั้งหมดในระบบ: {len(df)} | มี metrics ครบ: {len(df_ok)} | ยังไม่มี metrics: {len(df) - len(df_ok)}")

    if df_ok.empty:
        print("\n❌ ยังไม่มีห้องที่มี metrics ครบ กรุณารัน --retrain ก่อนครับ")
    else:
        print(f"\n{'Room':<20} {'LSTM':>5} {'ROB':>4} {'FB':>3} "
              f"{'R²':>6} {'MAE':>7} {'RMSE':>7} {'sMAPE':>7} "
              f"{'Acc':>6} {'LGB':>6} {'XGB':>6} {'LSTM':>6} {'F1':>6} {'Recall':>7} {'Prec':>7} {'Loss':>7} {'Conf':>6}")
        print("  (Acc = ensemble, LGB = LightGBM, XGB = XGBoost, LSTM = LSTM)")
        print("-" * 118)
        for _, r in df_ok.iterrows():
            print(
                f"  {r['Room']:<18} "
                f"{'✓' if r['HasLSTM'] else '✗':>5} "
                f"{'✓' if r['Robust'] else '-':>4} "
                f"{'✓' if r['Fallback'] else '-':>3} "
                f"{r['R2']:>6.3f} {r['MAE']:>6.3f}ชม {r['RMSE']:>6.3f}ชม "
                f"{r['sMAPE']:>6.1f}% {r['Accuracy']:>6.3f} "
                f"{r.get('Acc_lgb', np.nan):>6.3f} {r.get('Acc_xgb', np.nan):>6.3f} "
                f"{r.get('Acc_lstm', np.nan):>6.3f} {r['F1']:>6.3f} "
                f"{r['Recall']:>7.3f} {r['Precision']:>7.3f} {r['Loss']:>7.4f} "
                f"{r['Conf']:>5.1f}%"
            )
        print("-" * 118)
        print(
            f"  {'📊 เฉลี่ย':<18} {'':>5} {'':>4} {'':>3} "
            f"{df_ok['R2'].mean():>6.3f} {df_ok['MAE'].mean():>6.3f}ชม "
            f"{df_ok['RMSE'].mean():>6.3f}ชม {df_ok['sMAPE'].mean():>6.1f}% "
            f"{df_ok['Accuracy'].mean():>6.3f} {df_ok.get('Acc_lgb', pd.Series(dtype=float)).mean():>6.3f} "
            f"{df_ok.get('Acc_xgb', pd.Series(dtype=float)).mean():>6.3f} "
            f"{df_ok.get('Acc_lstm', pd.Series(dtype=float)).mean():>6.3f} "
            f"{df_ok['F1'].mean():>6.3f} {df_ok['Recall'].mean():>7.3f} "
            f"{df_ok['Precision'].mean():>7.3f} {df_ok['Loss'].mean():>7.4f} "
            f"{df_ok['Conf'].mean():>5.1f}%"
        )
        print("=" * 118)
        _print_model_summary(model_summary)

    print("\n📄 ข้อมูล metrics ทั้งหมด (ค่าจริงจาก meta ล่าสุด)")
    print("-" * 118)
    full_formatters = {
        'RoomID': lambda v: f"{int(v)}",
        'R2': lambda v: f"{v:.4f}",
        'MAE': lambda v: f"{v:.4f}",
        'RMSE': lambda v: f"{v:.4f}",
        'sMAPE': lambda v: f"{v:.4f}",
        'Accuracy': lambda v: f"{v:.4f}",
        'Acc_ensemble': lambda v: f"{v:.4f}",
        'Acc_lgb': lambda v: f"{v:.4f}",
        'Acc_xgb': lambda v: f"{v:.4f}",
        'Acc_lstm': lambda v: f"{v:.4f}",
        'F1': lambda v: f"{v:.4f}",
        'Recall': lambda v: f"{v:.4f}",
        'Precision': lambda v: f"{v:.4f}",
        'Loss': lambda v: f"{v:.4f}",
        'Conf': lambda v: f"{v:.1f}",
    }
    with pd.option_context('display.max_columns', None, 'display.max_rows', None, 'display.width', 240):
        print(df.to_string(index=False, formatters=full_formatters))
    print("-" * 118)

    if not df_ok.empty:
        total_rooms = len(df)
        ok_rooms = len(df_ok)
        print(f"\n🧠 LSTM (Primary)  : {int(df_ok['HasLSTM'].sum())}/{total_rooms} ห้องทั้งหมด")
        print(f"🔧 Robust+Huber    : {int(df_ok['Robust'].sum())}/{total_rooms} ห้องทั้งหมด")
        print(f"📅 Seasonal Fallbk : {int(df_ok['Fallback'].sum())}/{total_rooms} ห้องทั้งหมด")
        print(f"🏆 R² ดีที่สุด    : {df_ok.loc[df_ok['R2'].idxmax(), 'Room']}  ({df_ok['R2'].max():.4f})")
        print(f"⚠️  R² ต่ำที่สุด   : {df_ok.loc[df_ok['R2'].idxmin(), 'Room']}  ({df_ok['R2'].min():.4f})")
        print(f"🏆 Accuracy สูงสุด : {df_ok.loc[df_ok['Accuracy'].idxmax(), 'Room']}  ({df_ok['Accuracy'].max():.4f})")
        print(f"🏆 Loss ต่ำสุด     : {df_ok.loc[df_ok['Loss'].idxmin(), 'Room']}  ({df_ok['Loss'].min():.4f})")

    summary_csv = os.path.join(metrics_dir, 'metrics_summary.csv')
    df.to_csv(summary_csv, index=False)
    print(f"\n📄 Saved metrics CSV: {summary_csv}")
    print("🖼️  Plots are not generated here. Run: python ml/saved/generate_plots.py to create PNGs.")
