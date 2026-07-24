"""
Generate metric plots from unified training_history.jsonl file.

This script reads training history and generates summary plots.
All training data is centralized in a single append-only JSONL log.

Usage:
    python ml/saved/generate_plots.py
"""
import os
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
BASE_DIR = CURRENT_DIR.parents[1]
sys.path.append(str(BASE_DIR))

from ml.saved import plotting

METRICS_DIR = CURRENT_DIR / "metrics_plots"
TRAINING_HISTORY_LOG = METRICS_DIR / "training_history.jsonl"





def main():
    """Generate summary plots from training_history.jsonl."""

    log_file = str(TRAINING_HISTORY_LOG)
    if not Path(log_file).exists():
        print(f'Error: {log_file} not found')
        print('Run ml/saved/train_all_hyperparams.py first to generate training history')
        return

    print(f'Generating plots from {log_file}')
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        ok = plotting._plot_param_set_summary_table(
            log_file,
            str(METRICS_DIR / 'best_hyperparameters.png'),
        )
        print(f'best_hyperparameters.png ok={ok}')
    except Exception as e:
        print(f'best_hyperparameters.png failed: {e}')

    try:
        ok = plotting._plot_param_set_best_config_card(
            log_file,
            str(METRICS_DIR / 'best_hyperparameters_card.png'),
        )
        print(f'best_hyperparameters_card.png ok={ok}')
    except Exception as e:
        print(f'best_hyperparameters_card.png failed: {e}')

    try:
        ok = plotting._plot_model_accuracy_loss_comparison(
            log_file,
            str(METRICS_DIR / 'model_accuracy_loss_comparison.png'),
        )
        print(f'model_accuracy_loss_comparison.png ok={ok}')
    except Exception as e:
        print(f'model_accuracy_loss_comparison.png failed: {e}')

    try:
        ok = plotting._plot_param_set_val_acc_comparison(
            log_file,
            str(METRICS_DIR / 'param_set_val_acc_comparison.png'),
        )
        print(f'param_set_val_acc_comparison.png ok={ok}')
    except Exception as e:
        print(f'param_set_val_acc_comparison.png failed: {e}')

    try:
        ok = plotting.plot_model_configuration(
            str(METRICS_DIR / 'model_configuration.png'),
        )
        print(f'model_configuration.png ok={ok}')
    except Exception as e:
        print(f'model_configuration.png failed: {e}')


if __name__ == '__main__':
    main()
