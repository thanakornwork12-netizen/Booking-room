#!/usr/bin/env python3
"""
Test LSTM improvements: Compare old vs new hyperparameters/architecture
วิธีใช้:
  python test_lstm_improvements.py --param-set B --room "ห้องกันเกรา"
"""
import os
import sys
import argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(ROOT)
os.environ.setdefault('DISABLE_DJANGO_SCHEDULER', '1')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')

import django
django.setup()

from booking.models import Booking, Room
from ml.saved import forecast as fc
import numpy as np
import pandas as pd

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--param-set', choices=['A', 'B', 'C'], default='B')
    parser.add_argument('--room', type=str, help='ชื่อห้องเพื่อทดสอบ')
    args = parser.parse_args()

    # Set param set
    fc.CURRENT_PARAM_SET = args.param_set
    params = fc.PARAM_SETS.get(args.param_set, fc.PARAM_SETS['B'])
    fc.LSTM_EPOCHS = params.get('lstm_epochs', fc.LSTM_EPOCHS)
    fc.LSTM_BATCH = params.get('lstm_batch', fc.LSTM_BATCH)
    fc.LSTM_LOOKBACK = params.get('lstm_lookback', 30)  # Default 30 if not specified
    fc.LSTM_PATIENCE = 15
    
    print(f"\n{'='*80}")
    print(f"🧪 LSTM IMPROVEMENT TEST - Param Set {args.param_set}")
    print(f"{'='*80}")
    print(f"\n📋 Configuration:")
    print(f"   LSTM Epochs     : {fc.LSTM_EPOCHS}")
    print(f"   LSTM Batch Size : {fc.LSTM_BATCH}")
    print(f"   LSTM Lookback   : {fc.LSTM_LOOKBACK}")
    print(f"   LSTM Patience   : {fc.LSTM_PATIENCE}")
    print(f"   Model Dir       : {fc.MODEL_DIR}")
    
    # Load booking data
    raw_qs = Booking.objects.exclude(status='cancelled').values('start_time', 'end_time', 'room_id')
    raw = pd.DataFrame(list(raw_qs))
    
    if len(raw) == 0:
        print("❌ ไม่พบข้อมูล booking")
        return 1
    
    # Process timestamps
    for col in ['start_time', 'end_time']:
        raw[col] = pd.to_datetime(raw[col])
        if raw[col].dt.tz is None:
            raw[col] = raw[col].dt.tz_localize('UTC')
        raw[col] = raw[col].dt.tz_convert('Asia/Bangkok')
    
    raw['duration'] = (raw['end_time'] - raw['start_time']).dt.total_seconds() / 3600
    raw['duration'] = raw['duration'].clip(lower=0.25, upper=12.0)
    raw['date'] = raw['start_time'].dt.date
    
    # Build room list
    rooms = list(Room.objects.all())
    if args.room:
        rooms = [r for r in rooms if args.room.lower() in r.name.lower()]
    
    if not rooms:
        print(f"❌ ไม่พบห้อง: {args.room}")
        return 1
    
    print(f"\n🏢 Testing {len(rooms)} room(s):")
    
    # Build all_rooms_daily
    all_rooms_daily = {}
    for r in Room.objects.all():
        rdf_r = raw[raw['room_id'] == r.id]
        if len(rdf_r) == 0:
            all_rooms_daily[r] = pd.Series(dtype=float)
            continue
        daily_r = (
            rdf_r.groupby('date')['duration'].sum()
                 .reindex(pd.date_range(rdf_r['date'].min(), rdf_r['date'].max(), freq='D').date,
                          fill_value=0.0)
                 .astype(float)
        )
        daily_r.index = pd.to_datetime(daily_r.index)
        all_rooms_daily[r] = daily_r
    
    # Train LSTM for selected room(s)
    for room in rooms:
        rdf = raw[raw['room_id'] == room.id]
        if len(rdf) == 0:
            print(f"   ⊘ {room.name}: ไม่มี booking")
            continue
        
        print(f"\n   📍 {room.name}")
        daily = fc._prepare_daily_series(rdf, room, all_rooms_daily)
        if daily is None:
            print(f"      ⊘ ข้อมูลไม่พอ")
            continue
        
        use_log = fc._needs_log_transform(room)
        if not fc.LSTM_AVAILABLE:
            print(f"      ⊘ TensorFlow ไม่พบ")
            continue
        
        term_df = fc.build_term_daily_features(daily.index, fc.load_term_schedule(room.id))
        term_df.index = daily.index
        feat_df = fc.build_features(daily, term_df, use_log=use_log).dropna()
        X = feat_df.drop(columns='y')
        y = feat_df['y'].values
        
        split = fc._split_time_series(X, y)
        if split is None:
            print(f"      ⊘ ข้อมูลแบ่ง train/val ไม่ได้")
            continue
        
        X_tr, X_cal, X_te, y_tr, y_cal, y_te, train_end, calib_end = split
        
        if len(y_tr) < fc.LSTM_LOOKBACK + 10:
            print(f"      ⊘ ข้อมูล train ไม่พอสำหรับ lookback={fc.LSTM_LOOKBACK}")
            continue
        
        print(f"      ▸ Train size: {len(y_tr)}, Val size: {len(y_cal)}, Test size: {len(y_te)}")
        print(f"      ▸ Training LSTM with improved architecture...")
        
        model, scaler, history = fc.train_lstm(
            y_tr, y_cal,
            lookback=fc.LSTM_LOOKBACK,
            epochs=fc.LSTM_EPOCHS,
            patience=fc.LSTM_PATIENCE,
            feat_train_df=feat_df.iloc[:train_end],
            feat_val_df=feat_df.iloc[train_end:calib_end],
        )
        
        if model is None or history is None:
            print(f"      ❌ LSTM training failed")
            continue
        
        # Print final metrics
        train_acc = history.get('accuracy', [np.nan])[-1]
        val_acc = history.get('val_accuracy', [np.nan])[-1]
        train_loss = history.get('train_loss', [np.nan])[-1]
        val_loss = history.get('val_loss', [np.nan])[-1]
        
        print(f"      ✅ Training complete!")
        print(f"         Train Acc : {train_acc:.4f} | Val Acc : {val_acc:.4f}")
        print(f"         Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f}")
        
        # Save model
        model_file = f"{fc.MODEL_DIR}/{room.id}_lstm.keras"
        model.save(model_file)
        print(f"         Saved: {model_file}")
    
    print(f"\n{'='*80}")
    print(f"✅ Test complete!")
    print(f"{'='*80}\n")
    return 0

if __name__ == '__main__':
    sys.exit(main())
