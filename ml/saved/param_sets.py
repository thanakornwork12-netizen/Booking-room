# ══════════════════════════════════════════════════════════════════════════════
#  Single source of truth for hyperparameter set configuration (A/B/C/D/E).
#  forecast.py and plotting.py both import PARAM_SETS from here so the two
#  never drift out of sync (they previously did — plotting.py kept its own
#  hand-copied duplicate that went stale after every edit to forecast.py).
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
#  CAPACITY NOTE (revised 2026-09-09)
#
#  The previous grids (80-240 trees) underfit: measured train R2 was 0.32-0.61
#  against test R2 0.26-0.48 — essentially no gap, meaning the models could not
#  even fit the data they were shown. Two things were capping them:
#
#    1. A fixed early_stopping patience of 10. LightGBM reported best_round
#       80/80 and XGBoost 76/80, i.e. training never reached its own limit.
#       Patience now scales with the budget (forecast._early_stopping_rounds).
#    2. Too few trees at too high a learning rate.
#
#  A/B/C below scale trees UP and learning rate DOWN, but deliberately keep
#  leaves/depth moderate: a room has ~863 daily rows (~755 after calibration),
#  so 127+ leaves would put a handful of rows in each leaf. Each set carries an
#  explicit 'patience' for early stopping on the calibration split, which still
#  decides where each run actually ends.
#
#  A/B/C are the three sets being reported. D/E/F are kept only so older
#  scripts that default to the full A-F list still import; they are not part
#  of the comparison and are not sized for it.
# ══════════════════════════════════════════════════════════════════════════════

PARAM_SETS = {
    # Conservative tree grids for per-room daily data (~500-800 effective
    # training rows). The previous high learning rates and very wide trees
    # memorized calendar noise and created large train/calibration gaps.
    'A': {
        'name': 'A - Fast (Baseline)',
        'lstm_epochs': 20, 'lstm_batch': 16,
        'lstm_lookback': 20,
        'lgb_estimators': 20, 'lgb_depth': 6, 'lgb_leaves': 31, 'lgb_lr': 0.15,
        'lgb_min_child_samples': 20, 'lgb_lambda_l1': 0.8, 'lgb_lambda_l2': 0.8,
        'lgb_feature_fraction': 0.80, 'lgb_bagging_fraction': 0.80,
        'xgb_estimators': 20, 'xgb_depth': 5, 'xgb_lr': 0.15,
        'xgb_min_child_weight': 5, 'xgb_subsample': 0.80, 'xgb_colsample_bytree': 0.80,
        'xgb_reg_alpha': 0.8, 'xgb_reg_lambda': 0.8,
        'patience': 50,
    },
    # Candidate evaluated alongside A by walk-forward CV. It is not a
    # standalone run: it exists to let rooms with a large train/calibration
    # gap select a shallower, more strongly regularized tree configuration.
    'A_REG': {
        'name': 'A - Anti-overfit candidate',
        'lstm_epochs': 10, 'lstm_batch': 16, 'lstm_lookback': 20,
        'lgb_estimators': 300, 'lgb_depth': 4, 'lgb_leaves': 15, 'lgb_lr': 0.05,
        'lgb_min_child_samples': 35, 'lgb_lambda_l1': 1.5, 'lgb_lambda_l2': 1.5,
        'lgb_feature_fraction': 0.70, 'lgb_bagging_fraction': 0.70,
        'patience': 50,
        'xgb_estimators': 300, 'xgb_depth': 3, 'xgb_lr': 0.05,
        'xgb_min_child_weight': 3, 'xgb_subsample': 0.70, 'xgb_colsample_bytree': 0.70,
        'xgb_reg_alpha': 1.5, 'xgb_reg_lambda': 1.5,
    },
    'B': {
        'name': 'B - Balanced',
        'lstm_epochs': 50, 'lstm_batch': 8,
        'lstm_lookback': 40,
        'lgb_estimators': 50, 'lgb_depth': 8, 'lgb_leaves': 63, 'lgb_lr': 0.06,
        'lgb_min_child_samples': 20, 'lgb_lambda_l1': 1.0, 'lgb_lambda_l2': 1.0,
        'lgb_feature_fraction': 0.80, 'lgb_bagging_fraction': 0.80,
        'xgb_estimators': 50, 'xgb_depth': 6, 'xgb_lr': 0.06,
        'xgb_min_child_weight': 5, 'xgb_subsample': 0.80, 'xgb_colsample_bytree': 0.80,
        'xgb_reg_alpha': 1.0, 'xgb_reg_lambda': 1.0,
        'patience': 75,
    },
    'C': {
        'name': 'C - High Quality',
        'lstm_epochs': 70, 'lstm_batch': 4,
        'lstm_lookback': 70,
        'lgb_estimators': 70, 'lgb_depth': 10, 'lgb_leaves': 127, 'lgb_lr': 0.04,
        'lgb_min_child_samples': 20, 'lgb_lambda_l1': 1.2, 'lgb_lambda_l2': 1.2,
        'lgb_feature_fraction': 0.75, 'lgb_bagging_fraction': 0.75,
        'xgb_estimators': 70, 'xgb_depth': 8, 'xgb_lr': 0.04,
        'xgb_min_child_weight': 5, 'xgb_subsample': 0.75, 'xgb_colsample_bytree': 0.75,
        'xgb_reg_alpha': 1.2, 'xgb_reg_lambda': 1.2,
        'patience': 100,
    },
    # Experimental — trains harder than C to test whether more training keeps
    # helping or plateaus/hurts. Not the production default; used only for
    # the one-off A/B/C/D(/E) comparison experiment (see saved_meta_D_new/
    # saved_meta_E_new archives).
    'D': {
        'name': 'D - Regularized medium trees',
        'lstm_epochs': 40, 'lstm_batch': 8,
        'lstm_lookback': 70,
        'lgb_estimators': 5000, 'lgb_depth': 8, 'lgb_leaves': 63, 'lgb_lr': 0.005,
        'lgb_min_child_samples': 25, 'lgb_lambda_l1': 1.0, 'lgb_lambda_l2': 1.0,
        'xgb_estimators': 5000, 'xgb_depth': 7, 'xgb_lr': 0.005,
        'xgb_reg_alpha': 1.0, 'xgb_reg_lambda': 1.0,
    },
    # Deeper still than D — the control for the "does more depth keep
    # helping" question. If E measures worse than C/D despite training the
    # hardest, that confirms C (or D) is the right pick, not a plateau we
    # just haven't trained past yet.
    'E': {
        'name': 'E - Regularized wide trees',
        'lstm_epochs': 50, 'lstm_batch': 8,
        'lstm_lookback': 90,
        'lgb_estimators': 10000, 'lgb_depth': 8, 'lgb_leaves': 63, 'lgb_lr': 0.002,
        'lgb_min_child_samples': 30, 'lgb_lambda_l1': 1.5, 'lgb_lambda_l2': 1.5,
        'lgb_feature_fraction': 0.65, 'lgb_bagging_fraction': 0.65,
        'xgb_estimators': 10000, 'xgb_depth': 7, 'xgb_lr': 0.002,
        'xgb_reg_alpha': 1.5, 'xgb_reg_lambda': 1.5,
        'xgb_subsample': 0.65, 'xgb_colsample_bytree': 0.65,
    },
    # Uses the same walk-forward top_k/model selection protocol as A-E while
    # keeping this set's own tree parameters.
    'F': {
        'name': 'F - Walk-forward tuned trees',
        'lstm_epochs': 10, 'lstm_batch': 16,
        'lstm_lookback': 20,
        'lgb_estimators': 1000, 'lgb_depth': 6, 'lgb_leaves': 31, 'lgb_lr': 0.02,
        'xgb_estimators': 1000, 'xgb_depth': 6, 'xgb_lr': 0.02,
    },
}
