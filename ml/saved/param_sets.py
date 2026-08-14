# ══════════════════════════════════════════════════════════════════════════════
#  Single source of truth for hyperparameter set configuration (A/B/C/D/E).
#  forecast.py and plotting.py both import PARAM_SETS from here so the two
#  never drift out of sync (they previously did — plotting.py kept its own
#  hand-copied duplicate that went stale after every edit to forecast.py).
# ══════════════════════════════════════════════════════════════════════════════

PARAM_SETS = {
    # Round counts (epochs/estimators) set to 20/40/60/70/90 across A-E.
    # depth/leaves/lr per set were chosen alongside those round counts.
    'A': {
        'name': 'A - Fast (Baseline)',
        'lstm_epochs': 20, 'lstm_batch': 16,
        'lstm_lookback': 20,
        'lgb_estimators': 20, 'lgb_depth': 6, 'lgb_leaves': 31, 'lgb_lr': 0.15,
        'xgb_estimators': 20, 'xgb_depth': 5, 'xgb_lr': 0.15,
    },
    'B': {
        'name': 'B - Balanced',
        'lstm_epochs': 40, 'lstm_batch': 8,
        'lstm_lookback': 40,
        'lgb_estimators': 40, 'lgb_depth': 8, 'lgb_leaves': 63, 'lgb_lr': 0.06,
        'xgb_estimators': 40, 'xgb_depth': 6, 'xgb_lr': 0.06,
    },
    'C': {
        'name': 'C - High Quality',
        'lstm_epochs': 60, 'lstm_batch': 8,
        'lstm_lookback': 60,
        'lgb_estimators': 60, 'lgb_depth': 10, 'lgb_leaves': 127, 'lgb_lr': 0.04,
        'xgb_estimators': 60, 'xgb_depth': 8, 'xgb_lr': 0.04,
    },
    # Experimental — trains harder than C to test whether more training keeps
    # helping or plateaus/hurts. Not the production default; used only for
    # the one-off A/B/C/D(/E) comparison experiment (see saved_meta_D_new/
    # saved_meta_E_new archives).
    'D': {
        'name': 'D - Extra Deep (Experimental)',
        'lstm_epochs': 70, 'lstm_batch': 8,
        'lstm_lookback': 70,
        'lgb_estimators': 70, 'lgb_depth': 12, 'lgb_leaves': 255, 'lgb_lr': 0.03,
        'xgb_estimators': 70, 'xgb_depth': 10, 'xgb_lr': 0.03,
    },
    # Deeper still than D — the control for the "does more depth keep
    # helping" question. If E measures worse than C/D despite training the
    # hardest, that confirms C (or D) is the right pick, not a plateau we
    # just haven't trained past yet.
    'E': {
        'name': 'E - Maximum Depth (Experimental)',
        'lstm_epochs': 90, 'lstm_batch': 8,
        'lstm_lookback': 90,
        'lgb_estimators': 90, 'lgb_depth': 14, 'lgb_leaves': 511, 'lgb_lr': 0.02,
        'xgb_estimators': 90, 'xgb_depth': 12, 'xgb_lr': 0.02,
    },
}
