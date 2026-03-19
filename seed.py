import os
import sys
import django
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
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
EPOCHS   = 100
MIN_ROWS = 5   # เทรนทุกห้อง ห้ามข้าม ต่ำสุด 5 rows

def create_sequences(data, lookback):
    X, y = [], []
    for i in range(len(data) - lookback):
        X.append(data[i:i+lookback])
        y.append(data[i+lookback])
    return np.array(X), np.array(y)

def build_model(lookback):
    model = Sequential([
        Input(shape=(lookback, 1)),
        LSTM(64, return_sequences=True),
        Dropout(0.2),
        LSTM(32),
        Dropout(0.2),
        Dense(1)
    ])
    model.compile(optimizer='adam', loss='mse')
    return model

def build_simple_model(lookback):
    """โมเดลเล็กสำหรับห้องที่ข้อมูลน้อย"""
    model = Sequential([
        Input(shape=(lookback, 1)),
        LSTM(16),
        Dense(1)
    ])
    model.compile(optimizer='adam', loss='mse')
    return model

def map_demand(ratio):
    ratio = min(ratio, 1.0)
    if ratio < 0.35:
        return 'low',    'low',    round((1 - ratio) * 100, 1)
    elif ratio < 0.65:
        return 'medium', 'medium', 70.0
    else:
        return 'high',   'high',   round(ratio * 100, 1)

def accuracy_pct(mae, max_val):
    """คำนวณ accuracy % จาก MAE"""
    if max_val == 0:
        return 100.0
    return round(max(0, (1 - mae / max_val) * 100), 2)

# ----------------------------
# โหลดข้อมูล
# ----------------------------
print("📦 โหลดข้อมูลจาก DB...")

bookings = Booking.objects.exclude(status='cancelled').values('start_time', 'room_id')
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

DemandForecast.objects.filter(forecast_date__gte=today).delete()
print("🗑️  ลบ forecast เก่าเรียบร้อย\n")

forecast_objects = []
all_mae, all_rmse, all_r2, all_acc = [], [], [], []
trained_rooms = []
default_rooms = []

# ----------------------------
# เทรน + พยากรณ์ แยกรายห้อง
# ----------------------------
for idx, room in enumerate(rooms):
    print(f"[{idx+1}/{len(rooms)}] 🏠 {room.name}")

    room_df = df[df['room_id'] == room.id].copy()
    hourly  = room_df.groupby(['date','hour']).size().reset_index(name='booking_count')
    hourly  = hourly.sort_values(['date','hour']).reset_index(drop=True)

    total_bookings = len(room_df)
    print(f"   📋 {total_bookings} ครั้ง | hourly rows = {len(hourly)}")

    MAX_BOOKING = max(float(hourly['booking_count'].max()) if len(hourly) > 0 else 1.0, 1.0)

    # ถ้าข้อมูลน้อยมากๆ ใช้ค่า default
    if len(hourly) < MIN_ROWS:
        print(f"   ⚠️  ข้อมูลน้อยมาก ({len(hourly)} rows) → ใช้ค่า default low")
        default_rooms.append(room.name)
        for day_offset in range(7):
            forecast_date = today + timedelta(days=day_offset)
            for hour in range(8, 21):
                forecast_objects.append(DemandForecast(
                    room=room, forecast_date=forecast_date, hour=hour,
                    predicted_demand=0.0, demand_level='low',
                    availability='low', confidence=90.0
                ))
        print()
        continue

    print(f"   📊 MAX_BOOKING = {MAX_BOOKING}")

    # กำหนด lookback ตามข้อมูลที่มี
    effective_lookback = min(LOOKBACK, max(2, len(hourly) - 2))

    scaler = MinMaxScaler()
    hourly['scaled'] = scaler.fit_transform(hourly[['booking_count']])
    values = hourly['scaled'].values

    X, y = create_sequences(values, effective_lookback)

    # ถ้าสร้าง sequence ไม่ได้เลย ใช้ข้อมูลโดยตรง
    if len(X) == 0:
        print(f"   ⚠️  sequence = 0 → ใช้ค่า default")
        default_rooms.append(room.name)
        avg_ratio = float(hourly['booking_count'].mean()) / MAX_BOOKING
        demand_level, availability, confidence = map_demand(avg_ratio)
        for day_offset in range(7):
            forecast_date = today + timedelta(days=day_offset)
            for hour in range(8, 21):
                forecast_objects.append(DemandForecast(
                    room=room, forecast_date=forecast_date, hour=hour,
                    predicted_demand=round(float(hourly['booking_count'].mean()), 4),
                    demand_level=demand_level, availability=availability,
                    confidence=confidence
                ))
        print()
        continue

    X = X.reshape((X.shape[0], X.shape[1], 1))

    split   = max(1, int(len(X) * 0.8))
    X_train = X[:split]; X_test = X[split:]
    y_train = y[:split]; y_test = y[split:]

    print(f"   🧠 lookback={effective_lookback} train={len(X_train)} test={len(X_test)}")

    # เลือก model ตามขนาดข้อมูล
    if len(X_train) < 20:
        model = build_simple_model(effective_lookback)
        epochs = 50
    else:
        model = build_model(effective_lookback)
        epochs = EPOCHS

    early_stop = EarlyStopping(patience=5, restore_best_weights=True, verbose=0)

    model.fit(
        X_train, y_train,
        epochs=epochs,
        batch_size=min(16, len(X_train)),
        validation_split=0.2 if len(X_train) >= 5 else 0.0,
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
        acc  = accuracy_pct(mae, MAX_BOOKING)

        # R2 score
        try:
            r2 = r2_score(y_test_inv, y_pred_inv)
        except:
            r2 = 0.0

        all_mae.append(mae)
        all_rmse.append(rmse)
        all_r2.append(r2)
        all_acc.append(acc)
        trained_rooms.append({
            'name': room.name, 'mae': mae, 'rmse': rmse,
            'r2': r2, 'acc': acc, 'bookings': total_bookings,
            'max_booking': MAX_BOOKING
        })
        print(f"   📈 MAE={mae:.4f}  RMSE={rmse:.4f}  R²={r2:.4f}  Acc={acc:.1f}%")

    # บันทึกโมเดล
    room_dir = f'ml/saved/room_{room.id}'
    os.makedirs(room_dir, exist_ok=True)
    model.save(f'{room_dir}/model.keras')
    joblib.dump(scaler, f'{room_dir}/scaler.pkl')
    joblib.dump(MAX_BOOKING, f'{room_dir}/max_booking.pkl')

    # พยากรณ์ 7 วัน
    last_seq = values[-effective_lookback:].reshape(1, effective_lookback, 1)
    day_forecasts = {'low': 0, 'medium': 0, 'high': 0}

    for day_offset in range(7):
        forecast_date = today + timedelta(days=day_offset)
        for hour in range(8, 21):
            pred_scaled = model.predict(last_seq, verbose=0)[0][0]
            pred_value  = max(0.0, float(scaler.inverse_transform([[pred_scaled]])[0][0]))
            ratio       = pred_value / MAX_BOOKING if MAX_BOOKING > 0 else 0
            demand_level, availability, confidence = map_demand(ratio)
            day_forecasts[demand_level] += 1

            forecast_objects.append(DemandForecast(
                room=room, forecast_date=forecast_date, hour=hour,
                predicted_demand=round(pred_value, 4),
                demand_level=demand_level, availability=availability,
                confidence=confidence
            ))
            last_seq = np.append(last_seq[:, 1:, :], [[[pred_scaled]]], axis=1)

    print(f"   🔮 low={day_forecasts['low']} medium={day_forecasts['medium']} high={day_forecasts['high']}")
    print()

# ----------------------------
# Bulk insert
# ----------------------------
DemandForecast.objects.bulk_create(forecast_objects, batch_size=500)
print(f"✅ เขียน Forecast {len(forecast_objects)} records\n")

# ----------------------------
# สรุปผล
# ----------------------------
print("=" * 62)
print("📊 สรุปผลการเทรนรายห้อง")
print("=" * 62)
print(f"  {'ห้อง':<20} {'MAE':>7} {'RMSE':>7} {'R²':>7} {'Acc%':>7} {'จอง':>6}")
print("-" * 62)

if trained_rooms:
    for r in sorted(trained_rooms, key=lambda x: x['acc'], reverse=True):
        bar = '●' if r['acc'] >= 95 else '○'
        print(f"  {bar} {r['name'][:18]:<18} {r['mae']:>7.4f} {r['rmse']:>7.4f} {r['r2']:>7.4f} {r['acc']:>6.1f}% {r['bookings']:>5}")

    print("=" * 62)
    print(f"\n  📌 ผลรวมทุกห้องที่เทรนสำเร็จ ({len(trained_rooms)} ห้อง)")
    print(f"  ├─ MAE  เฉลี่ย  = {np.mean(all_mae):.4f}")
    print(f"  ├─ RMSE เฉลี่ย  = {np.mean(all_rmse):.4f}")
    print(f"  ├─ R²   เฉลี่ย  = {np.mean(all_r2):.4f}")
    print(f"  └─ Acc  เฉลี่ย  = {np.mean(all_acc):.2f}%")

    # แบ่งกลุ่ม accuracy
    high_acc   = [r for r in trained_rooms if r['acc'] >= 95]
    medium_acc = [r for r in trained_rooms if 80 <= r['acc'] < 95]
    low_acc    = [r for r in trained_rooms if r['acc'] < 80]

    print(f"\n  🟢 Acc ≥ 95% : {len(high_acc)} ห้อง")
    print(f"  🟡 Acc 80-95%: {len(medium_acc)} ห้อง")
    print(f"  🔴 Acc < 80% : {len(low_acc)} ห้อง")

    # forecast distribution
    all_forecasts = DemandForecast.objects.filter(forecast_date__gte=today)
    low_c    = all_forecasts.filter(demand_level='low').count()
    medium_c = all_forecasts.filter(demand_level='medium').count()
    high_c   = all_forecasts.filter(demand_level='high').count()

    print(f"\n  🔮 Forecast Distribution (7 วัน)")
    print(f"  ├─ 🟢 low    = {low_c} slots ({low_c/(low_c+medium_c+high_c)*100:.1f}%)")
    print(f"  ├─ 🟡 medium = {medium_c} slots ({medium_c/(low_c+medium_c+high_c)*100:.1f}%)")
    print(f"  └─ 🔴 high   = {high_c} slots ({high_c/(low_c+medium_c+high_c)*100:.1f}%)")

if default_rooms:
    print(f"\n  ⚠️  ใช้ค่า default ({len(default_rooms)} ห้อง): {', '.join(default_rooms)}")

print(f"\n  เทรนสำเร็จ  = {len(trained_rooms)}/{len(rooms)} ห้อง")
print("=" * 62)
print("\n🎉 เสร็จสมบูรณ์!")