import os
import sys
import django
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from tensorflow.keras.callbacks import EarlyStopping
from datetime import timedelta

# ----------------------------
# 1. Setup Django
# ----------------------------
sys.path.append('/Users/macthanakorn/room_booking')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'room_booking.settings')
django.setup()

from booking.models import Booking, Room, DemandForecast
from django.utils import timezone

# ⚡ FAST CONFIG
LOOKBACK = 24
EPOCHS = 50
BATCH_SIZE = 512
DOWNSAMPLE = 1   # ไม่ตัดข้อมูลออก เพื่อความแม่นยำ

# ----------------------------
# 2. Helper Functions
# ----------------------------
def create_sequences(data, lookback=24):
    X, y = [], []
    for i in range(len(data) - lookback):
        X.append(data[i:i+lookback])
        y.append(data[i+lookback][0])
    return np.array(X), np.array(y)

def build_model(lookback, n_features):
    model = Sequential([
        Input(shape=(lookback, n_features)),
        LSTM(32, return_sequences=True),
        Dropout(0.2),
        LSTM(16),
        Dense(1)
    ])
    model.compile(optimizer='adam', loss='mse')
    return model

# ----------------------------
# 3. Load & Process Data
# ----------------------------
print("📦 กำลังโหลดข้อมูลการจอง...")
bookings = Booking.objects.exclude(status='cancelled').values('start_time', 'room_id')
df = pd.DataFrame(list(bookings))

if df.empty:
    print("❌ ไม่พบข้อมูลการจองในระบบ")
    sys.exit(1)

df['start_time'] = pd.to_datetime(df['start_time']).dt.tz_convert(timezone.get_current_timezone_name())
today = timezone.now().date()

print("🧹 ล้างข้อมูลพยากรณ์เดิมเพื่อเตรียม Update...")
DemandForecast.objects.filter(forecast_date__gte=today).delete()

rooms = list(Room.objects.all())
forecast_objects = []

print(f"🏢 พบทั้งหมด {len(rooms)} ห้อง")

# ----------------------------
# 4. Train & Forecast Loop
# ----------------------------
for room in rooms:
    room_df = df[df['room_id'] == room.id].copy()

    if len(room_df) < 20:
        continue

    print(f"🏠 กำลังประมวลผล: {room.name}...", end=' ', flush=True)

    room_df = room_df.set_index('start_time')
    hourly = room_df.resample('1h').size().to_frame(name='booking_count')
    hourly = hourly.fillna(0)

    # Feature Engineering
    hourly['h_sin'] = np.sin(2 * np.pi * hourly.index.hour / 24)
    hourly['h_cos'] = np.cos(2 * np.pi * hourly.index.hour / 24)
    hourly['d_sin'] = np.sin(2 * np.pi * hourly.index.dayofweek / 7)
    hourly['d_cos'] = np.cos(2 * np.pi * hourly.index.dayofweek / 7)

    features = ['booking_count', 'h_sin', 'h_cos', 'd_sin', 'd_cos']
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(hourly[features])

    X, y = create_sequences(scaled, LOOKBACK)
    if len(X) < 10:
        print("⚠️ ข้อมูล Sequence ไม่พอ -> ข้าม")
        continue

    # แบ่ง Train / Validation 80:20 เพื่อวัด loss จริง
    split = int(len(X) * 0.8)
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    model = build_model(LOOKBACK, len(features))
    early_stop = EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True)
    model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=[early_stop],
        verbose=0
    )

    last_seq = scaled[-LOOKBACK:]
    max_history_val = float(hourly['booking_count'].max()) if hourly['booking_count'].max() > 0 else 1.0

    # พยากรณ์ล่วงหน้า 7 วัน (Recursive)
    for day_offset in range(7):
        f_date = today + timedelta(days=day_offset)
        for hr in range(8, 21):
            pred_scaled = model.predict(last_seq.reshape(1, LOOKBACK, -1), verbose=0)[0][0]
            pred_scaled = max(0.0, float(pred_scaled))

            actual_booking_pred = pred_scaled * max_history_val

            if pred_scaled < 0.35:
                d_level, d_status = "ต่ำ", "ว่าง"
            elif pred_scaled < 0.75:
                d_level, d_status = "ปานกลาง", "เริ่มหนาแน่น"
            else:
                d_level, d_status = "สูง", "หนาแน่นมาก"

            forecast_objects.append(DemandForecast(
                room=room,
                forecast_date=f_date,
                hour=hr,
                predicted_demand=round(actual_booking_pred, 2),
                demand_level=d_level,
                availability=d_status,
            ))

            # Update Sequence สำหรับก้าวถัดไป
            h_s = np.sin(2 * np.pi * hr / 24)
            h_c = np.cos(2 * np.pi * hr / 24)
            d_s = np.sin(2 * np.pi * f_date.weekday() / 7)
            d_c = np.cos(2 * np.pi * f_date.weekday() / 7)
            new_row = np.array([pred_scaled, h_s, h_c, d_s, d_c])
            last_seq = np.vstack([last_seq[1:], new_row])

    print("✅ เสร็จสิ้น")

# ----------------------------
# 5. Bulk Push To Database
# ----------------------------
if forecast_objects:
    print(f"\n🚀 กำลัง Push ข้อมูลพยากรณ์ {len(forecast_objects)} รายการลง Database...")
    DemandForecast.objects.bulk_create(forecast_objects, batch_size=2000)
    print("\n" + "✨" * 15)
    print("🎉 พยากรณ์สำเร็จ!")
    print("✨" * 15)
else:
    print("❌ พยากรณ์ล้มเหลว: ไม่มีข้อมูลห้องที่เข้าเงื่อนไข")