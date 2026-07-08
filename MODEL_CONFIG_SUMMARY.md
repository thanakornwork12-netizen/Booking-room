# Model Configuration and Hyperparameters Summary

## Overview
Our forecasting system uses an **Ensemble approach** with 3 base models and a weighted blend strategy:
- **LSTM (Primary)** - 60% weight - Captures temporal/seasonal patterns
- **LightGBM** - 22% weight - Gradient boosting for feature interactions  
- **XGBoost** - 18% weight - Additional gradient boosting ensemble

---

## 1. LSTM (Primary Model)

### Architecture
| Parameter | Specification |
|-----------|--------------|
| **Input Shape** | (lookback=14, n_features) - Multivariate sequences |
| **Layer 1** | LSTM(64 units, return_sequences=True) |
| **Dropout 1** | 0.2 |
| **Layer 2** | LSTM(32 units, return_sequences=False) |
| **Dropout 2** | 0.2 |
| **Dense Layer** | 16 units, activation='relu' |
| **Output Layer** | Dense(1) - Regression output |

### Training Configuration
| Parameter | Value |
|-----------|-------|
| **Input Sequence Length** | 14 days (lookback) |
| **Epochs** | 60 |
| **Batch Size** | 32 |
| **Optimizer** | Adam (default learning rate) |
| **Loss Function** | Mean Absolute Error (MAE) |
| **Early Stopping** | Yes (patience=10, monitor='val_loss') |
| **Scaling** | MinMaxScaler (per-column for features, separate for target) |

### Data Requirements
- **Minimum Training Samples**: lookback + 10 = 24 data points
- **Sequence Type**: Multivariate LSTM (uses both historical demand + feature data) |

---

## 2. LightGBM (Base Model)

### Hyperparameters
| Parameter | Value |
|-----------|-------|
| **n_estimators** | 180 |
| **learning_rate** | 0.06 |
| **max_depth** | 3 |
| **num_leaves** | 8 |
| **objective** | regression (MAE) |
| **metric** | mae |
| **early_stopping_rounds** | 50 |

### Training
- Train/val split: 80/20
- Evaluation metric: MAE
- Early stopping on validation MAE

---

## 3. XGBoost (Base Model)

### Hyperparameters (Variant 1)
| Parameter | Value |
|-----------|-------|
| **n_estimators** | 140 |
| **learning_rate** | 0.04 |
| **max_depth** | 4 |
| **subsample** | 0.7 |
| **objective** | reg:squarederror |
| **early_stopping_rounds** | 50 |

### Hyperparameters (Variant 2)
| Parameter | Value |
|-----------|-------|
| **n_estimators** | 140 |
| **learning_rate** | 0.05 |
| **max_depth** | 5 |
| **subsample** | 0.8 |
| **colsample_bytree** | 0.8 |
| **early_stopping_rounds** | 50 |

### Training
- Train/val split: 80/20
- Evaluation metric: MAE
- Early stopping on validation MAE
- n_jobs: -1 (parallel processing)

---

## 4. Ensemble Configuration

### Weighting Strategy (Primary)
| Model | Weight | Purpose |
|-------|--------|---------|
| **LSTM** | 60% | Primary forecaster - captures temporal patterns |
| **LightGBM** | 22% | Secondary - feature interactions |
| **XGBoost** | 18% | Tertiary - additional ensemble diversity |

### Fallback Models
| Model | Purpose |
|-------|---------|
| **Seasonal Median Model** | When ensemble R² < threshold |
| **Cold Start Model** | First 30 days of room booking history |

---

## 5. Data & Feature Engineering

### Input Features
- Historical demand (time series)
- Seasonal components
- Trend indicators
- Day-of-week patterns
- Holiday indicators (if available)

### Data Requirements Per Room
| Requirement | Value |
|------------|-------|
| **Minimum Days** | 30 |
| **Minimum Unique Booking Days** | 14 |
| **Forecast Horizon** | 14 days |
| **Training/Validation Split** | 80/20 |

---

## 6. Classification Metrics (for performance tracking)

### Metrics Computed
- **Accuracy**: Percentage of correct high/med/low demand predictions
- **F1 Score**: Harmonic mean of precision and recall
- **Recall**: True positive rate
- **Precision**: Positive predictive value
- **Loss**: MAE or categorical cross-entropy

### Demand Thresholds
- **High Demand**: Adaptive threshold (~95th percentile)
- **Medium Demand**: Adaptive threshold (~50th percentile)
- **Low Demand**: Below medium threshold

---

## 7. Output & Evaluation

### Generated Plots (5 Total Images)
1. **LSTM Accuracy & Loss Curve** - Shows training progression across rooms
2. **LightGBM Accuracy & Loss Curve** - Shows training progression across rooms
3. **XGBoost Accuracy & Loss Curve** - Shows training progression across rooms
4. **Ensemble Accuracy & Loss Curve** - Shows training progression across rooms
5. **Model Overview Summary** - Comparison across all models

### Metrics Summary File
- **CSV Output**: `metrics_summary.csv` with per-room and aggregate metrics
- **Fields**: Room ID, Model Accuracy, Loss, Per-model accuracies, Status

---

## 8. Key Differences from Example (Table 2)

| Aspect | Example Table | Our Implementation |
|--------|---------------|-------------------|
| **Input Size** | 224×224 (images) | Time series sequences (14 days) |
| **Base Architecture** | DenseNet-121, EfficientNet-B3, MobileNetV2 | LSTM, LightGBM, XGBoost |
| **Task** | Image classification (10 classes) | Demand forecasting (regression) |
| **Output Layer** | Dense(10) + Softmax | Dense(1) for regression |
| **Loss Function** | Categorical Cross-entropy | MAE (Mean Absolute Error) |
| **Learning Rate** | 1×10⁻⁴ | LSTM: Adam default, LGB: 0.06, XGB: 0.04-0.05 |
| **Batch Size** | 16 (EfficientNet) / 32 (others) | 32 (LSTM), varies for tree models |
| **Epochs** | 30 | 60 (LSTM), 140-180 (boosting rounds) |
| **Primary Task** | Computer Vision | Time Series Forecasting |
| **Ensemble Method** | Likely concatenation + dense | Weighted averaging (60/22/18) |
