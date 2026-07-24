"""Train only LSTM for all rooms and append LSTM history to centralized log.

Usage:
  python ml/saved/train_lstm_only.py --param-set B

This script imports the existing `forecast.py` helpers (without modifying them),
builds per-room feature series, runs `train_lstm()` where applicable, and calls
`_append_training_history_log()` with a result object that contains only
`lstm_history` so LSTM records are appended to the centralized log.

Warning: training LSTM for many rooms may be slow and uses TensorFlow.
"""
import argparse
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
FORECAST_PY = ROOT / 'forecast.py'


def load_forecast_module():
    spec = importlib.util.spec_from_file_location('forecast_module', str(FORECAST_PY))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    parser = argparse.ArgumentParser(description='Train only LSTM and append history')
    parser.add_argument('--param-set', choices=['A', 'B', 'C'], default='B')
    parser.add_argument('--rooms', nargs='*', help='Optional list of room names to limit training')
    parser.add_argument('--dry-run', action='store_true', help='Do not append logs; show planned actions')
    args = parser.parse_args()

    fc = load_forecast_module()

    # set parameter set globals in the module
    fc.CURRENT_PARAM_SET = args.param_set
    params = fc.PARAM_SETS.get(args.param_set, fc.PARAM_SETS['B'])
    fc.LSTM_EPOCHS = params.get('lstm_epochs', fc.LSTM_EPOCHS)
    fc.LSTM_BATCH = params.get('lstm_batch', fc.LSTM_BATCH)

    print(f"Using PARAM_SET {args.param_set}: LSTM epochs={fc.LSTM_EPOCHS}, batch={fc.LSTM_BATCH}")

    # Load bookings and prepare daily series exactly like retrain flow
    raw_qs = fc.Booking.objects.exclude(status='cancelled').values('start_time', 'end_time', 'room_id')
    raw = fc.pd.DataFrame(list(raw_qs))
    if len(raw) == 0:
        print('No bookings found; aborting')
        return 1

    for col in ['start_time', 'end_time']:
        raw[col] = fc.pd.to_datetime(raw[col])
        if raw[col].dt.tz is None:
            raw[col] = raw[col].dt.tz_localize('UTC')
        raw[col] = raw[col].dt.tz_convert('Asia/Bangkok')

    raw['duration'] = (raw['end_time'] - raw['start_time']).dt.total_seconds() / 3600
    raw['duration'] = raw['duration'].clip(lower=0.25, upper=12.0)
    raw['date'] = raw['start_time'].dt.date

    # build all_rooms_daily map
    all_rooms_daily = {}
    for r in fc.Room.objects.all():
        rdf_r = raw[raw['room_id'] == r.id]
        if len(rdf_r) == 0:
            all_rooms_daily[r] = fc.pd.Series(dtype=float)
            continue
        daily_r = (
            rdf_r.groupby('date')['duration'].sum()
                 .reindex(fc.pd.date_range(rdf_r['date'].min(), rdf_r['date'].max(), freq='D').date,
                          fill_value=0.0)
                 .astype(float)
        )
        daily_r.index = fc.pd.to_datetime(daily_r.index)
        all_rooms_daily[r] = daily_r

    rooms = list(fc.Room.objects.all())
    if args.rooms:
        names = set(args.rooms)
        rooms = [r for r in rooms if r.name in names or str(r.id) in names]

    planned = []
    for room in rooms:
        rdf = raw[raw['room_id'] == room.id]
        if len(rdf) == 0:
            continue
        daily = fc._prepare_daily_series(rdf, room, all_rooms_daily)
        if daily is None:
            continue
        use_log = fc._needs_log_transform(room)
        if not fc.LSTM_AVAILABLE:
            print(f"Skipping LSTM for {room.name} (TF available={fc.LSTM_AVAILABLE})")
            continue

        term_df = fc.build_term_daily_features(daily.index, fc.load_term_schedule(room.id))
        term_df.index = daily.index
        feat_df = fc.build_features(daily, term_df, use_log=use_log).dropna()
        X = feat_df.drop(columns='y')
        y = feat_df['y'].values
        split = fc._split_time_series(X, y)
        if split is None:
            print(f"Skipping {room.name}: insufficient split")
            continue
        X_tr, X_cal, X_te, y_tr, y_cal, y_te, train_end, calib_end = split
        if len(y_tr) < fc.LSTM_LOOKBACK + 10:
            print(f"Skipping {room.name}: not enough train rows for LSTM")
            continue

        print(f"Training LSTM for {room.name}...")
        model, scaler, history = fc.train_lstm(
            y_tr, y_cal,
            lookback=fc.LSTM_LOOKBACK,
            epochs=fc.LSTM_EPOCHS,
            patience=fc.LSTM_PATIENCE,
            feat_train_df=feat_df.iloc[:train_end],
            feat_val_df=feat_df.iloc[train_end:calib_end],
        )
        if model is None or history is None:
            print(f"LSTM training failed for {room.name}")
            continue

        result = {'lstm_history': history, 'lgb_history': {}, 'xgb_history': {}}
        planned.append((room.name, room, result))

        if not args.dry_run:
            fc._append_training_history_log(room, result)
            print(f"Appended LSTM history for {room.name}")

    print(f"Done. Trained LSTM for {len(planned)} rooms (dry_run={args.dry_run})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
