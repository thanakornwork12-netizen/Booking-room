import os
import sys
import django
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping
import joblib

# ----------------------------
# Setup Django
# ----------------------------
sys.path.append('/Users/macthanakorn/room_booking')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')
django.setup()

from booking.models import Booking, Room, DemandForecast
from django.utils import timezone
from datetime import timedelta

LOOKBACK = 24
EPOCHS   = 50

def create_sequences(data, lookback=24):
    X, y = [], []
    for i in range(len(data) - lookback):
        X.append(data[i:i+lookback])
        y.append(data[i+lookback])
    return np.array(X), np.array(y)

def build_model(lookback=24):
    model = Sequential([
        LSTM(64, return_sequences=True, input_shape=(lookback, 1)),
        Dropout(0.2),
        LSTM(32),
        Dropout(0.2),
        Dense(1)
    ])
    model.compile(optimizer='adam', loss='mse')
    return model

def map_demand(ratio):
    ratio = min(ratio, 1.0)
    if ratio < 0.5:
        return 'low',    'low',    round((1 - ratio) * 100, 1)
    elif ratio < 0.8:
        return 'medium', 'medium', 70.0
    else:
        return 'high',   'high',   round(ratio * 100, 1)
# ----------------------------
# โหลดข้อมูลทั้งหมด
# ----------------------------
print("📦 โหลดข้อมูลจาก DB...")

bookings = Booking.objects.exclude(
    status='cancelled'
).values('start_time', 'room_id')

df = pd.DataFrame(list(bookings))

if df.empty:
    print("❌ ไม่มีข้อมูลการจอง")
    sys.exit(1)

print(f"✅ พบข้อมูล {len(df)} รายการ")

df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
df['date'] = df['start_time'].dt.date
df['hour'] = df['start_time'].dt.hour

rooms = list(Room.objects.filter(status='available'))
print(f"🏢 ห้องทั้งหมด {len(rooms)} ห้อง\n")

today = timezone.now().date()
os.makedirs('ml/saved', exist_ok=True)

# ลบ forecast เก่า
DemandForecast.objects.filter(forecast_date__gte=today).delete()
print("🗑️  ลบ forecast เก่าเรียบร้อย\n")

forecast_objects = []
all_mae, all_rmse = [], []
skipped_rooms = []
trained_rooms = []

# ----------------------------
# เทรน + พยากรณ์ แยกรายห้อง
# ----------------------------
for idx, room in enumerate(rooms):
    print(f"[{idx+1}/{len(rooms)}] 🏠 {room.name}")

    # กรองเฉพาะห้องนี้
    room_df = df[df['room_id'] == room.id].copy()

    # สร้าง time series รายชั่วโมงของห้องนี้
    hourly = room_df.groupby(['date', 'hour']).size().reset_index(name='booking_count')
    hourly = hourly.sort_values(['date', 'hour']).reset_index(drop=True)

    total_bookings = len(room_df)
    print(f"   📋 ประวัติการจอง {total_bookings} ครั้ง | hourly rows = {len(hourly)}")

    # ถ้าข้อมูลน้อยเกินไป → ใช้ค่า default low
    if len(hourly) < LOOKBACK + 5:
        print(f"   ⚠️  ข้อมูลน้อยเกินไป → ใช้ค่า default low\n")
        skipped_rooms.append(room.name)
        for day_offset in range(7):
            forecast_date = today + timedelta(days=day_offset)
            for hour in range(8, 21):
                forecast_objects.append(DemandForecast(
                    room=room,
                    forecast_date=forecast_date,
                    hour=hour,
                    predicted_demand=0.0,
                    demand_level='low',
                    availability='low',
                    confidence=90.0
                ))
        continue

    # floor MAX_BOOKING ที่ 3 เพื่อป้องกัน ratio พุ่งเต็มจากข้อมูลน้อย
    MAX_BOOKING = max(float(hourly['booking_count'].max()), 2.0)
    print(f"   📊 MAX_BOOKING = {MAX_BOOKING}")

    # Normalize
    scaler = MinMaxScaler()
    hourly['scaled'] = scaler.fit_transform(hourly[['booking_count']])
    values = hourly['scaled'].values

    X, y = create_sequences(values, LOOKBACK)
    X = X.reshape((X.shape[0], X.shape[1], 1))

    split   = int(len(X) * 0.8)
    X_train = X[:split]; X_test = X[split:]
    y_train = y[:split]; y_test = y[split:]

    print(f"   🧠 train={len(X_train)} test={len(X_test)}")

    # เทรน
    model = build_model(LOOKBACK)
    early_stop = EarlyStopping(patience=5, restore_best_weights=True)

    model.fit(
        X_train, y_train,
        epochs=EPOCHS,
        batch_size=16,
        validation_split=0.2,
        callbacks=[early_stop],
        verbose=0
    )

    # Evaluate
    if len(X_test) > 0:
        y_pred     = model.predict(X_test, verbose=0)
        y_pred_inv = scaler.inverse_transform(y_pred)
        y_test_inv = scaler.inverse_transform(y_test.reshape(-1, 1))
        mae  = mean_absolute_error(y_test_inv, y_pred_inv)
        rmse = np.sqrt(mean_squared_error(y_test_inv, y_pred_inv))
        all_mae.append(mae)
        all_rmse.append(rmse)
        trained_rooms.append({'name': room.name, 'mae': mae, 'rmse': rmse, 'bookings': total_bookings})
        print(f"   📈 MAE={mae:.4f}  RMSE={rmse:.4f}")

    # บันทึกโมเดลและ scaler รายห้อง
    room_dir = f'ml/saved/room_{room.id}'
    os.makedirs(room_dir, exist_ok=True)
    model.save(f'{room_dir}/model.keras')
    joblib.dump(scaler, f'{room_dir}/scaler.pkl')
    joblib.dump(MAX_BOOKING, f'{room_dir}/max_booking.pkl')

    # พยากรณ์ 7 วันข้างหน้า
    last_seq = values[-LOOKBACK:].reshape(1, LOOKBACK, 1)

    day_forecasts = {'low': 0, 'medium': 0, 'high': 0}

    for day_offset in range(7):
        forecast_date = today + timedelta(days=day_offset)
        for hour in range(8, 21):
            pred_scaled = model.predict(last_seq, verbose=0)[0][0]
            pred_value  = max(0.0, float(scaler.inverse_transform([[pred_scaled]])[0][0]))

            ratio = pred_value / MAX_BOOKING if MAX_BOOKING > 0 else 0
            demand_level, availability, confidence = map_demand(ratio)
            day_forecasts[demand_level] += 1

            forecast_objects.append(DemandForecast(
                room=room,
                forecast_date=forecast_date,
                hour=hour,
                predicted_demand=round(pred_value, 4),
                demand_level=demand_level,
                availability=availability,
                confidence=confidence
            ))

            # เลื่อน sequence
            last_seq = np.append(last_seq[:, 1:, :], [[[pred_scaled]]], axis=1)

    print(f"   🔮 forecast 7 วัน: 🟢low={day_forecasts['low']} 🟡medium={day_forecasts['medium']} 🔴high={day_forecasts['high']}")
    print(f"   ✅ เสร็จแล้ว\n")

# ----------------------------
# Bulk insert
# ----------------------------
DemandForecast.objects.bulk_create(forecast_objects, batch_size=500)
print(f"✅ เขียน Forecast {len(forecast_objects)} records\n")

# ----------------------------
# สรุปผลทุกห้อง
# ----------------------------
print("=" * 55)
print("📊 สรุปผลการเทรนรายห้อง")
print("=" * 55)

if trained_rooms:
    for r in sorted(trained_rooms, key=lambda x: x['mae']):
        bar = '█' * int(r['mae'] * 10)
        print(f"  {r['name'][:25]:<25} MAE={r['mae']:.3f} {bar}")

    print("-" * 55)
    print(f"  MAE  เฉลี่ย = {np.mean(all_mae):.4f}")
    print(f"  RMSE เฉลี่ย = {np.mean(all_rmse):.4f}")
    print(f"  เทรนสำเร็จ  = {len(trained_rooms)}/{len(rooms)} ห้อง")

if skipped_rooms:
    print(f"\n  ⚠️  ข้ามเพราะข้อมูลน้อย ({len(skipped_rooms)} ห้อง):")
    for name in skipped_rooms:
        print(f"     - {name}")

print("=" * 55)
print("\n🎉 เสร็จสมบูรณ์!")