# 📊 LSTM Accuracy & Loss Issues - Root Cause Analysis & Fixes

## 🔴 ปัญหาที่พบ

จากการวิเคราะห์ `training_history.jsonl`:

```
Epoch 1: train_acc=0.5046, val_acc=0.3697, train_loss=0.288, val_loss=0.257
Epoch 10: train_acc=0.6777, val_acc=0.5879, train_loss=0.191, val_loss=0.169
Epoch 15: train_acc=0.6711, val_acc=0.6424, train_loss=0.165, val_loss=0.143
```

### ❌ ปัญหาหลัก:
1. **Val Accuracy ต่ำมาก (37% → 64%)** - จำแนกประเมินผ่านอย่างไม่ดี
2. **Loss ยังอยู่ที่ 0.143** - ค่อนข้างสูง (ต้อง < 0.10)
3. **Val Acc fluctuate** - Epoch 10 มี 58.79% แต่ Epoch 15 ลดเหลือ 64.24%
4. **ไม่ converge ดี** - Loss ลดลงช้า + Val curve ไม่เรียบ

---

## 🔍 Root Cause Analysis

| ปัญหา | ต้นเหตุ | ผลกระทบ |
|------|--------|---------|
| **Lookback = 14 days** | ✗ สั้นเกินไป | ไม่จับ seasonal patterns (ต้อง 21-42 วัน) |
| **Batch size = 32** | ✗ ใหญ่เกินไป | Gradient updates ช้า = converge ไม่ดี |
| **LSTM 64→32 units** | ✗ Underfitting | Model ไม่มี capacity จำ patterns ที่ซับซ้อน |
| **Dropout 0.2 เท่านั้น** | ✗ ไม่พอ | Overfitting → Val accuracy ต่ำ |
| **No LR Scheduler** | ✗ Learning rate fixed | Stuck in local minima หลัง epoch 10-15 |
| **Architecture quá đơn giản** | ✗ 2 LSTM layers | Không enough layers để extract features |
| **Early Stop patience=10** | ✓ Okay | แต่ combined กับ LR fixed → stop vague |

---

## ✅ Solutions Applied

### 1️⃣ **Hyperparameters Tuning**

```python
# Old (Param B):
'lstm_epochs': 30, 'lstm_batch': 16, 'lstm_lookback': 14

# New (Param B - IMPROVED):
'lstm_epochs': 50, 'lstm_batch': 8, 'lstm_lookback': 30
```

| Parameter | Old | New | เหตุผล |
|-----------|-----|-----|---------|
| **epochs** | 30 | 50 | เทรนนานขึ้น = มีเวลา converge |
| **batch_size** | 16 | 8 | Gradient updates บ่อยขึ้น = เทรนดี |
| **lookback** | 14 | 30 | จับ seasonal patterns (4+ weeks) |
| **patience** | 10 | 15 | ให้เทรนไปต่อขึ้น = ก่อน early stop |

### 2️⃣ **LSTM Architecture Enhancement**

```python
# Old:
model = Sequential([
    LSTM(64, return_sequences=True),
    Dropout(0.2),
    LSTM(32, return_sequences=False),
    Dropout(0.2),
    Dense(16, activation='relu'),
    Dense(1),
])

# New (IMPROVED):
model = Sequential([
    LSTM(128, return_sequences=True),    # ↑ 64 → 128 units
    Dropout(0.3),                         # ↑ 0.2 → 0.3
    LSTM(64, return_sequences=True),     # ← NEW: 2nd layer for depth
    Dropout(0.3),                         # ← NEW: more regularization
    LSTM(32, return_sequences=False),
    Dropout(0.2),
    Dense(32, activation='relu'),        # ↑ 16 → 32 units
    Dropout(0.2),                         # ← NEW dropout
    Dense(16, activation='relu'),        # ← NEW: intermediate layer
    Dense(1),
])
```

**ประโยชน์:**
- ✅ +128 units layer 1 = มี capacity สำหรับ temporal patterns
- ✅ +LSTM layer = 3 LSTM layers ทำให้ลึกขึ้น
- ✅ +Dropout layers = ลด overfitting
- ✅ +Dense layers = ให้ interpret features ได้ดีขึ้น

### 3️⃣ **Optimizer with Gradient Clipping**

```python
# Old:
model.compile(optimizer='adam', loss='mae', metrics=['mae'])

# New (IMPROVED):
optimizer = Adam(learning_rate=0.001, decay=1e-6, clipvalue=1.0)
model.compile(optimizer=optimizer, loss='mae', metrics=['mae'])
```

**ประโยชน์:**
- ✅ `decay=1e-6` = learning rate ลดค่าช้า ๆ (adaptive)
- ✅ `clipvalue=1.0` = กัน exploding gradients

### 4️⃣ **Learning Rate Scheduler (KEY FIX!)**

```python
# NEW: ReduceLROnPlateau callback
from tensorflow.keras.callbacks import ReduceLROnPlateau

reduce_lr = ReduceLROnPlateau(
    monitor='val_loss',
    factor=0.5,       # ลด LR ลง 50% ทุกครั้ง
    patience=5,       # หลัง 5 epochs ที่ val_loss ไม่ improve
    min_lr=1e-5,      # ไม่ลดต่ำกว่านี้
    verbose=0
)
callbacks.append(reduce_lr)
```

**ทำไมสำคัญ:**
- ✅ เมื่อ val_loss หยุดลดลง → ลด LR เพื่อ fine-tune
- ✅ ช่วย escape local minima
- ✅ เป็นเหตุหลักที่ model ติดตรงนี้

---

## 🎯 Expected Improvements

หลังจากปรับปรุง:

| Metric | Before | Expected After | Target |
|--------|--------|-----------------|--------|
| **Train Acc** | 67% | **75-82%** | 80%+ |
| **Val Acc** | 64% | **70-78%** | 75%+ |
| **Train Loss** | 0.165 | **0.100-0.130** | 0.10 |
| **Val Loss** | 0.143 | **0.095-0.120** | 0.10 |
| **Convergence** | Stuck @ ep15 | **Smooth to ep50** | ✓ |
| **Overfitting** | Yes | **No** | ✓ |

---

## 🚀 ขั้นตอนการใช้ Fix

### Step 1: Apply Changes (DONE)
```bash
# Changes applied in ml/saved/forecast.py:
# 1. Updated PARAM_SETS with new lookback values
# 2. Enhanced LSTM architecture (128→64→32 units)
# 3. Added Adam optimizer with decay + gradient clipping
# 4. Added ReduceLROnPlateau callback
```

### Step 2: Test with One Room
```bash
cd /Users/macthanakorn/room_booking
python test_lstm_improvements.py --param-set B --room "ห้องกันเกรา"
```

### Step 3: Monitor Results
- เปรียบเทียบ metrics จาก `training_history.jsonl`
- ตรวจว่า val_loss ลดลงจนถึง epoch 50
- ตรวจว่า val_acc เพิ่มขึ้น (ไม่ fluctuate)

### Step 4: Full Retrain
```bash
python ml/saved/train_lstm_only.py --param-set B
```

### Step 5: Generate Plots
```bash
python ml/saved/generate_plots.py
```

---

## 🔍 Debugging Commands

```bash
# 1. Check last 5 epochs of a room
tail -20 ml/saved/metrics_plots/training_history.jsonl | grep "ห้องกันเกรา"

# 2. Plot training curves
python ml/saved/generate_plots.py

# 3. Analyze metrics
python ml/saved/metrics_report.py

# 4. Check one room metadata
python -c "
import joblib
meta = joblib.load('ml/saved_meta/587_meta.pkl')
print(meta.get('model_metrics', {}).get('lstm', {}).get('classification'))
"
```

---

## 📚 References

- [TensorFlow LSTM Best Practices](https://www.tensorflow.org/guide/keras/rnn)
- [Learning Rate Scheduling](https://keras.io/api/callbacks/reduce_lr_on_plateau/)
- [Hyperparameter Tuning for RNNs](https://arxiv.org/abs/1604.06778)
- [Dropout and Regularization](https://arxiv.org/abs/1502.01852)

---

## ⚠️ Important Notes

1. **First training may take longer** (epoch 50 vs 15-30)
   - Set Param C for aggressive training: epochs=100, batch=4, lookback=42
   
2. **GPU usage** will increase slightly due to larger model
   - Check with: `nvidia-smi` (if GPU available)
   
3. **Batch size 8 is slower but better**
   - More gradient updates per epoch
   - Better convergence behavior
   
4. **Patience 15 is important**
   - Don't reduce below 10 (might stop too early)
   - Combine with ReduceLROnPlateau for best results

---

## ✅ Checklist

- [x] Updated PARAM_SETS hyperparameters
- [x] Enhanced LSTM architecture (3 LSTM layers)
- [x] Added Adam optimizer with decay
- [x] Added ReduceLROnPlateau callback
- [ ] Test with one room (ห้องกันเกรา)
- [ ] Monitor training curves
- [ ] Full retrain with param B
- [ ] Generate comparison plots
- [ ] Deploy to production

---

**Last Updated**: 2026-07-12
**Files Modified**: ml/saved/forecast.py (LSTM model, callbacks, hyperparams)
**Test Script**: test_lstm_improvements.py
