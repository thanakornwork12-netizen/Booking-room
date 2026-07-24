#!/bin/bash
# รัน LSTM training ทั้ง 3 param sets (A, B, C)

set -e
cd /Users/macthanakorn/room_booking
source tf-env/bin/activate

echo "════════════════════════════════════════════════════════════════════"
echo "🚀 Running LSTM Training - All Param Sets"
echo "════════════════════════════════════════════════════════════════════"

echo ""
echo "📦 Param Set A - Fast (Baseline)"
echo "   epochs=20, batch=16, lookback=21"
echo "────────────────────────────────────────────────────────────────────"
python ml/saved/train_lstm_only.py --param-set A

echo ""
echo "📦 Param Set B - Balanced"
echo "   epochs=50, batch=8, lookback=30"
echo "────────────────────────────────────────────────────────────────────"
python ml/saved/train_lstm_only.py --param-set B

echo ""
echo "📦 Param Set C - High Quality"
echo "   epochs=100, batch=4, lookback=42"
echo "────────────────────────────────────────────────────────────────────"
python ml/saved/train_lstm_only.py --param-set C

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "✅ All LSTM training complete!"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo "📊 View results:"
echo "   tail -100 ml/saved/metrics_plots/training_history.jsonl | grep 'param_set'"
echo ""
