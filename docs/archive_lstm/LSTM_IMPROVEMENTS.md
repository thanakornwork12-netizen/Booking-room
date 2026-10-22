# 🔧 LSTM Accuracy & Loss Issues - Analysis & Fixes

## 🔴 ปัญหาที่พบ

### 1. **Classification Accuracy ต่ำ (50-60%) + Loss สูง**
```
Epoch 1: train_acc=0.5046, val_acc=0.3697, train_loss=0.288, val_loss=0.257
Epoch 15: train_acc=0.6711, val_acc=0.6424, train_loss=0.165, val_loss=0.143
```
- ❌ Validation accuracy ยังต่ำ (~64%) แม้เทรนเสร็จ
- ❌ Loss ก็ค่อนข้างสูง (0.143)

### 2. **Root Causes**

| ปัญหา | สาเหตุ | ผลกระทบ |
|------|--------|---------|
| **Lookback = 14 days** | สั้นเกินไป | ไม่จับ seasonal patterns (ต้อง 30+ วัน) |
| **Batch size = 32** | ใหญ่เกินไป | Gradient updates ช้า, ระบบไม่ converge ดี |
| **LSTM Architecture** | Simple 64→32 units | Underfitting - capacity ไม่พอ |
| **Dropout = 0.2** | เยิ่ว | Regularization ตัดข้อมูลไป 20% |
| **No Learning Rate Decay** | Fixed learning rate | ไม่ fine-tune ใน later epochs |
| **Early Stopping Patience=10** | หยุด vague | บางครั้ง stop เร็ว |
| **Data Imbalance** | Low/Medium/High demand ไม่สมดุล | Model bias ไปทาง majority class |

---

## ✅ Solutions

### **1. ปรับ Hyperparameters (Quick Fix)**

```python
# ในไฟล์ forecast.py ที่ PARAM_SETS:

'B': {
    'name': 'B - Balanced',
    'lstm_epochs': 50,      # ↑ ขยายจาก 30 → 50 (เทรนยาวขึ้น)
    'lstm_batch': 8,        # ↓ ลดจาก 16 → 8 (gradient updates บ่อยขึ้น)
    'lstm_lookback': 30,    # ↑ ขยายจาก 14 → 30 (จับ seasonal)
    'lstm_patience': 15,    # ↑ ขยายจาก 10 → 15 (ให้เทรนนานขึ้น)
    'lgb_estimators': 30, ...
},
```

### **2. ปรับ LSTM Architecture (Medium Fix)**

```python
# ค้นหา "model = Sequential" ในฟังก์ชัน train_lstm()

# ❌ OLD:
model = Sequential([
    LSTM(64, return_sequences=True, input_shape=(lookback, input_cols)),
    Dropout(0.2),
    LSTM(32, return_sequences=False),
    Dropout(0.2),
    Dense(16, activation='relu'),
    Dense(1),
])

# ✅ NEW:
model = Sequential([
    # Layer 1: เพิ่มความจำไป 128 units
    LSTM(128, return_sequences=True, input_shape=(lookback, input_cols)),
    Dropout(0.3),          # เพิ่ม dropout ไปลดทำให้ overfit
    
    # Layer 2: ยังคง 64 units
    LSTM(64, return_sequences=True),
    Dropout(0.3),
    
    # Layer 3: Output layer สำหรับ LSTM
    LSTM(32, return_sequences=False),
    Dropout(0.2),
    
    # Dense layers
    Dense(32, activation='relu'),  # ↑ ขยายจาก 16 → 32
    Dropout(0.2),
    Dense(16, activation='relu'),
    Dense(1),
])
```

### **3. ปรับ Optimizer & Learning Rate (Advanced)**

```python
# ❌ OLD:
model.compile(optimizer='adam', loss='mae', metrics=['mae'])

# ✅ NEW:
from tensorflow.keras.optimizers import Adam

# สร้าง optimizer ที่มี learning rate decay
optimizer = Adam(
    learning_rate=0.001,
    decay=1e-6,           # Learning rate decay
    clipvalue=1.0         # Gradient clipping
)

model.compile(
    optimizer=optimizer,
    loss='mae',
    metrics=['mae']
)
```

### **4. เพิ่ม Learning Rate Scheduler (Best Practice)**

```python
# เพิ่มใน callbacks:
from tensorflow.keras.callbacks import ReduceLROnPlateau

callbacks = []
if not DISABLE_EARLY_STOPPING:
    es = EarlyStopping(
        monitor='val_loss',
        mode='min',
        patience=patience,
        restore_best_weights=True,
        verbose=0
    )
    callbacks.append(es)

# ✅ NEW: Reduce learning rate when val_loss plateaus
reduce_lr = ReduceLROnPlateau(
    monitor='val_loss',
    factor=0.5,           # ลด LR ลง 50%
    patience=5,           # หลัง 5 epochs ที่ val_loss ไม่ improve
    min_lr=1e-5,
    verbose=0
)
callbacks.append(reduce_lr)

cls_cb = LSTMClassificationHistoryCallback(...)
callbacks.append(cls_cb)
```

### **5. ข้อมูล Normalization (Critical)**

```python
# ตรวจสอบว่า scaling ถูกต้อง:
# ใน train_lstm() ที่ฟังก์ชัน MinMaxScaler:

scaler_y = MinMaxScaler()
scaler_y.fit(y_train_raw.reshape(-1, 1))

# ❓ เช็ค: ข้อมูลที่ scale แล้วควรมีค่า 0-1
y_scaled = scaler_y.transform(y_train_raw.reshape(-1, 1))
print(f"Scaled data range: [{y_scaled.min():.3f}, {y_scaled.max():.3f}]")
# ต้องใกล้ 0-1 ไม่ใช่ 0-100 หรือ negative
```

---

## 📋 Implementation Checklist

- [ ] 1. อัปเดต PARAM_SETS (batch=8, epochs=50, lookback=30)
- [ ] 2. แก้ LSTM architecture (+128 units layer 1)
- [ ] 3. เพิ่ม Learning Rate Scheduler (ReduceLROnPlateau)
- [ ] 4. ทดสอบเทรนอีกครั้ง:
  ```bash
  python ml/saved/train_lstm_only.py --param-set B
  ```
- [ ] 5. เปรียบเทียบ metrics ก่อน/หลัง ใน training_history.jsonl
- [ ] 6. ถ้ายังไม่ดี → ลองเพิ่ม class weights (สำหรับ imbalanced data)

---

## 🎯 Expected Results

หลังจากปรับปรุง:
- ✅ **train_acc**: 60% → **75-80%**
- ✅ **val_acc**: 64% → **70-75%**  
- ✅ **val_loss**: 0.143 → **0.10-0.12**
- ✅ Loss curve ลดลงเรื่อยๆ ไม่ fluctuate

---

## 🔍 Debugging Commands

```bash
# 1. ดูสถิติข้อมูล
python ml/saved/forecast.py --show-data-stats

# 2. เทรน 1 ห้องด้วย verbose
python -c "
import sys
sys.path.append('/Users/macthanakorn/room_booking')
# ... ดูรายละเอียดการเทรนแต่ละ epoch
"

# 3. วาดกราฟ training history
python ml/saved/generate_plots.py
```

---

## 📚 References

- [TensorFlow LSTM Guide](https://www.tensorflow.org/guide/keras/rnn)
- [Learning Rate Decay vs Scheduler](https://keras.io/api/callbacks/reduce_lr_on_plateau/)
- [LSTM for Time Series](https://github.com/chuacheowhuan/ResearchNotes/blob/main/LSTM_forecasting.md)
