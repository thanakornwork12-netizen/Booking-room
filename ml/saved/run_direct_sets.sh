#!/usr/bin/env bash
# Train the direct sets and refresh every artifact that reports them.
#
#   ./run_direct_sets.sh          train every set (A B C D)
#   ./run_direct_sets.sh D        train only D, then re-test and re-plot everything
#
# Testing ALWAYS covers every set even when training only one: test_direct_sets.py
# rewrites test_only_results_direct.csv from just the sets it was given, so
# running it with --sets D would leave a file holding D alone and silently drop
# A/B/C from every table built afterwards.
#
# Every step writes its own log under logs/<timestamp>/ as well as to the
# screen. The round each set is served at is chosen from numbers that scroll
# past during training, so a run whose output was not kept cannot be explained
# afterwards -- the figures alone do not say why a round was picked.
set -euo pipefail
cd "$(dirname "$0")"

TRAIN_SETS="${1:-}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="logs/${RUN_ID}"
mkdir -p "$LOG_DIR"

echo "logging to $LOG_DIR"
{
  echo "run_id      : $RUN_ID"
  echo "started     : $(date)"
  echo "train sets  : ${TRAIN_SETS:-all}"
  echo "git HEAD    : $(git rev-parse --short HEAD 2>/dev/null || echo 'n/a')"
  echo "git dirty   : $(git status --porcelain 2>/dev/null | wc -l | tr -d ' ') file(s) modified"
} | tee "$LOG_DIR/run_info.txt"

step() {           # step <logname> <command...>
  local name="$1"; shift
  echo
  echo "=== $name ==="
  "$@" 2>&1 | tee "$LOG_DIR/${name}.log"
}

if [ -n "$TRAIN_SETS" ]; then
  step 01_train python3 train_direct_sets.py --sets "$TRAIN_SETS"
else
  step 01_train python3 train_direct_sets.py
fi

step 02_test          python3 test_direct_sets.py
step 03_table         python3 build_adaptive_vs_fixed_current.py --direct
step 04_config        python3 plot_direct_config.py
step 05_test_curves   python3 plot_test_curves_by_set.py --direct
step 06_gap           python3 plot_train_vs_test_gap.py --direct
step 07_train_curves  python3 plot_training_curves_by_set.py --direct
step 08_train_loss    python3 plot_training_loss_by_set.py --direct
step 09_consolidate   python3 consolidate_results.py --direct
step 10_baseline      python3 baseline_from_excel.py --direct

# Snapshot the numbers the figures were drawn from, so a figure can always be
# traced back to its data even after the next run overwrites metrics_plots/.
cp metrics_plots/adaptive_vs_fixed_by_set_current_direct.csv "$LOG_DIR/" 2>/dev/null || true
cp metrics_plots/test_only_results_direct.csv "$LOG_DIR/" 2>/dev/null || true
cp metrics_plots/consolidated_results_direct.csv "$LOG_DIR/" 2>/dev/null || true

echo
echo "=== DONE — train vs test per set ===" | tee "$LOG_DIR/99_summary.log"
python3 - <<'PY' 2>&1 | tee -a "$LOG_DIR/99_summary.log"
import pandas as pd
print(pd.read_csv('metrics_plots/adaptive_vs_fixed_by_set_current_direct.csv').to_string(index=False))
PY
echo "finished: $(date)" | tee -a "$LOG_DIR/run_info.txt"
echo
echo "logs + data snapshot -> $LOG_DIR"
