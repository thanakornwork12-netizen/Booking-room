import os
import sys
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping, Callback
import joblib
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from booking.models import Booking, Room, DemandForecast

# Callback ส่ง progress ผ่าน WebSocket
class WSProgressCallback(Callback):
    def __init__(self, total_epochs, channel_layer):
        super().__init__()
        self.total_epochs = total_epochs
        self.channel_layer = channel_layer

    def on_epoch_end(self, epoch, logs=None):
        progress = round(((epoch + 1) / self.total_epochs) * 100)
        loss = round(logs.get('loss', 0), 4)
        val_loss = round(logs.get('val_loss', 0), 4)
        try:
            async_to_sync(self.channel_layer.group_send)(
                'retrain_progress',
                {
                    'type': 'retrain_update',
                    'epoch': epoch + 1,
                    'total': self.total_epochs,
                    'progress': progress,
                    'loss': loss,
                    'val_loss': val_loss,
                    'status': 'training',
                }
            )
        except Exception:
            pass

class Command(BaseCommand):
    help = 'Retrain LSTM model and update forecast'

    def handle(self, *args, **kwargs):
        channel_layer = get_channel_layer()

        def broadcast(data):
            try:
                async_to_sync(channel_layer.group_send)('retrain_progress', data)
            except Exception:
                pass

        broadcast({'type': 'retrain_update', 'status': 'loading', 'message': '📦 โหลดข้อมูล...'})

        bookings = Booking.objects.filter(
            status__in=['approved', 'completed']
        ).values('start_time', 'room_id', 'attendees')

        df = pd.DataFrame(list(bookings))

        if df.empty:
            broadcast({'type': 'retrain_update', 'status': 'error', 'message': '❌ ไม่มีข้อมูล'})
            return

        df['start_time'] = pd.to_datetime(df['start_time'], utc=True)
        df['date'] = df['start_time'].dt.date
        df['hour'] = df['start_time'].dt.hour

        hourly = df.groupby(['date', 'hour']).size().reset_index(name='booking_count')
        hourly = hourly.sort_values(['date', 'hour']).reset_index(drop=True)

        scaler = MinMaxScaler()
        hourly['scaled'] = scaler.fit_transform(hourly[['booking_count']])
        values = hourly['scaled'].values

        LOOKBACK = 24

        def create_sequences(data, lookback=24):
            X, y = [], []
            for i in range(len(data) - lookback):
                X.append(data[i:i+lookback])
                y.append(data[i+lookback])
            return np.array(X), np.array(y)

        X, y = create_sequences(values, LOOKBACK)
        X = X.reshape((X.shape[0], X.shape[1], 1))
        split = int(len(X) * 0.8)
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

        EPOCHS = 50

        model = Sequential([
            LSTM(64, return_sequences=True, input_shape=(LOOKBACK, 1)),
            Dropout(0.2),
            LSTM(32),
            Dropout(0.2),
            Dense(1)
        ])
        model.compile(optimizer='adam', loss='mse')

        broadcast({
            'type': 'retrain_update',
            'status': 'training',
            'message': f'🚀 เริ่ม training ({len(X_train)} samples)...',
            'progress': 0,
        })

        early_stop = EarlyStopping(patience=5, restore_best_weights=True)
        ws_callback = WSProgressCallback(EPOCHS, channel_layer)

        model.fit(
            X_train, y_train,
            epochs=EPOCHS,
            batch_size=32,
            validation_split=0.2,
            callbacks=[early_stop, ws_callback],
            verbose=0
        )

        y_pred = model.predict(X_test)
        y_pred_inv = scaler.inverse_transform(y_pred)
        y_test_inv = scaler.inverse_transform(y_test.reshape(-1, 1))
        mae = float(mean_absolute_error(y_test_inv, y_pred_inv))
        rmse = float(np.sqrt(mean_squared_error(y_test_inv, y_pred_inv)))

        os.makedirs('ml/saved', exist_ok=True)
        model.save('ml/saved/lstm_model.keras')
        joblib.dump(scaler, 'ml/saved/scaler.pkl')

        broadcast({
            'type': 'retrain_update',
            'status': 'forecasting',
            'message': '🔮 กำลังพยากรณ์...',
            'progress': 100,
            'mae': round(mae, 4),
            'rmse': round(rmse, 4),
        })

        rooms = list(Room.objects.filter(status='available'))
        today = timezone.now().date()
        DemandForecast.objects.filter(forecast_date__gte=today).delete()

        last_sequence = values[-LOOKBACK:].reshape(1, LOOKBACK, 1)
        forecast_objects = []

        for day_offset in range(7):
            forecast_date = today + timedelta(days=day_offset)
            for hour in range(8, 21):
                pred_scaled = model.predict(last_sequence, verbose=0)[0][0]
                pred_value = max(0, float(scaler.inverse_transform([[pred_scaled]])[0][0]))
                ratio = pred_value / len(rooms) if rooms else 0

                if ratio < 0.4:
                    demand_level, availability = 'low', 'low'
                    confidence = round((1 - ratio) * 100, 1)
                elif ratio < 0.7:
                    demand_level, availability = 'medium', 'medium'
                    confidence = 70.0
                else:
                    demand_level, availability = 'high', 'high'
                    confidence = round(ratio * 100, 1)

                for room in rooms:
                    forecast_objects.append(DemandForecast(
                        room=room,
                        forecast_date=forecast_date,
                        hour=hour,
                        predicted_demand=round(pred_value, 4),
                        demand_level=demand_level,
                        availability=availability,
                        confidence=confidence
                    ))

                new_val = np.array([[[pred_scaled]]])
                last_sequence = np.append(last_sequence[:, 1:, :], new_val, axis=1)

        DemandForecast.objects.bulk_create(forecast_objects, batch_size=500)

        broadcast({
            'type': 'retrain_update',
            'status': 'done',
            'message': f'🎉 เสร็จสมบูรณ์! MAE={round(mae,4)} RMSE={round(rmse,4)}',
            'mae': round(mae, 4),
            'rmse': round(rmse, 4),
            'forecast_count': len(forecast_objects),
            'progress': 100,
        })

        self.stdout.write(f'✅ Done MAE={mae:.4f} RMSE={rmse:.4f}')