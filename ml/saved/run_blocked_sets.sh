#!/usr/bin/env bash
# Blocked-calibration variant of run_direct_sets.sh: train A-D, test, and
# build every direct figure again as *_direct_blocked.*, plus the
# contiguous-vs-blocked comparison. Writes only to ml/saved/blocked_calib/,
# *_direct_blocked.* / blocked_* files in metrics_plots/, and logs/blocked_<id>/.
# The original run's models, metas, CSVs and figures are never touched.
#
# Usage (from anywhere):
#   bash ml/saved/run_blocked_sets.sh               # train A-D, then everything
#   bash ml/saved/run_blocked_sets.sh C             # train only set C
#   bash ml/saved/run_blocked_sets.sh --skip-train  # models already trained
set -euo pipefail
cd "$(dirname "$0")"
PY="${PY:-../../tf-env/bin/python}"
ARG="${1:-}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="logs/blocked_${RUN_ID}"
mkdir -p "$LOG_DIR"
echo "logging to $LOG_DIR"
{
  echo "run_id      : $RUN_ID"
  echo "variant     : BLOCKED calibration"
  echo "started     : $(date)"
  echo "arg         : ${ARG:-all sets}"
  echo "git HEAD    : $(git rev-parse --short HEAD 2>/dev/null || echo 'n/a')"
  echo "git dirty   : $(git status --porcelain 2>/dev/null | wc -l | tr -d ' ') file(s) modified"
} | tee "$LOG_DIR/run_info.txt"

step() {           # step <logname> <command...>
  local name="$1"; shift
  echo
  echo "=== $name ==="
  "$@" 2>&1 | tee "$LOG_DIR/${name}.log"
}

if [ "$ARG" = "--skip-train" ]; then
  echo "skipping training (using blocked_calib/saved_direct_sets as is)"
elif [ -n "$ARG" ]; then
  step 01_train "$PY" blocked_calibration_direct.py --sets "$ARG"
else
  step 01_train "$PY" blocked_calibration_direct.py
fi
step 02_test          "$PY" blocked_calibration_direct.py --test
step 03_table         "$PY" build_adaptive_vs_fixed_current.py --blocked
step 04_config        "$PY" plot_direct_config.py --blocked
step 05_test_curves   "$PY" plot_test_curves_by_set.py --blocked
step 06_gap           "$PY" plot_train_vs_test_gap.py --blocked
step 07_train_curves  "$PY" plot_training_curves_by_set.py --blocked
step 08_train_loss    "$PY" plot_training_loss_by_set.py --blocked
step 09_compare       "$PY" plot_blocked_vs_contiguous.py

for f in adaptive_vs_fixed_by_set_current_direct_blocked.csv test_only_results_direct_blocked.csv \
         blocked_calibration_blocks.csv blocked_vs_contiguous_calibration.csv; do
  cp "metrics_plots/$f" "$LOG_DIR/" 2>/dev/null || true
done

echo
echo "=== DONE — contiguous vs blocked ===" | tee "$LOG_DIR/99_summary.log"
cat metrics_plots/blocked_vs_contiguous_calibration.csv | tee -a "$LOG_DIR/99_summary.log"
echo "finished: $(date)" | tee -a "$LOG_DIR/run_info.txt"
echo
echo "figures -> metrics_plots/*_direct_blocked.png, blocked_vs_contiguous_calibration.png"
echo "logs + data snapshot -> $LOG_DIR"
