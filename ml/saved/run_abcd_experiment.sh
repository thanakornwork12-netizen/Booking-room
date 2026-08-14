#!/bin/bash
# Sequential A -> B -> D -> E -> C retrain experiment, with archiving after each set.
# C is trained LAST so the live saved_models/saved_meta directories end up
# holding C (the production default) with no manual restore step needed.
#
# Safety: saved_models_backup_pretrain4_<date>/ and saved_meta_backup_pretrain4_<date>/
# were already taken before this script runs, as a rollback point if anything
# goes wrong mid-sequence.

set -e  # stop immediately on any error, don't silently continue to the next set
set -o pipefail  # keep set -e working correctly through the tee pipe below

cd /Users/macthanakorn/room_booking
LOG=ml/saved/metrics_plots/abcd_experiment_progress.log
MARKER=ml/saved/metrics_plots/abcd_experiment_start.txt

# Record the exact UTC start time BEFORE any training runs. training_history.jsonl
# is append-only and already has A/B/C entries from earlier sessions (since
# 2026-07-12) — those must NOT be mixed with this run's fresh entries when
# plotting. Anything downstream must filter training_history.jsonl to
# `timestamp >= this marker` before aggregating per param_set, so old and new
# runs of the same letter (e.g. old C from July vs new C from today) never
# get averaged together into one distorted curve.
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$MARKER"
echo "=== ABCDE experiment started at $(date) (marker: $(cat $MARKER)) ===" > "$LOG"

run_set () {
    local SET=$1
    echo "--- [$(date +%H:%M:%S)] Training Set $SET ---" | tee -a "$LOG"
    tf-env/bin/python3 -u ml/saved/forecast.py --retrain --param-set "$SET" 2>&1 | tee -a "$LOG"
    echo "--- [$(date +%H:%M:%S)] Set $SET training finished, archiving ---" | tee -a "$LOG"
    rm -rf "ml/saved/saved_models_${SET}_new" "ml/saved/saved_meta_${SET}_new"
    cp -r ml/saved/saved_models "ml/saved/saved_models_${SET}_new"
    cp -r ml/saved/saved_meta "ml/saved/saved_meta_${SET}_new"
    echo "--- [$(date +%H:%M:%S)] Set $SET archived to saved_models_${SET}_new / saved_meta_${SET}_new ---" | tee -a "$LOG"
}

run_set A
run_set B
run_set D
run_set E
run_set C

echo "=== ABCDE experiment finished at $(date) ===" | tee -a "$LOG"
echo "Live saved_models/ and saved_meta/ now hold Set C (trained last, current data)." | tee -a "$LOG"
echo "Fresh archives (current data, same room population across all 5 sets):" | tee -a "$LOG"
echo "  saved_models_A_new / saved_meta_A_new" | tee -a "$LOG"
echo "  saved_models_B_new / saved_meta_B_new" | tee -a "$LOG"
echo "  saved_models_D_new / saved_meta_D_new" | tee -a "$LOG"
echo "  saved_models_E_new / saved_meta_E_new" | tee -a "$LOG"
echo "  saved_models_C_new / saved_meta_C_new" | tee -a "$LOG"
