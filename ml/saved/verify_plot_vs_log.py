import argparse
import os
import random
from pathlib import Path

from ml.saved import plotting


def _load_log(log_path):
    records = plotting._load_training_history_log(log_path)
    if not records:
        raise ValueError(f'No valid records found in {log_path}')
    return records


def _sample_points(records, sample_count=5):
    points = []
    for param_set in plotting.PARAM_SET_ORDER:
        for model in ['lstm', 'lightgbm', 'xgboost']:
            for metric in ['train_acc', 'val_acc', 'train_loss', 'val_loss']:
                x, y = plotting._partial_mean_curve(records, model, metric, param_set)
                if x.size > 0:
                    for xi, yi in zip(x, y):
                        points.append((param_set, model, metric, int(xi), float(yi)))
    if not points:
        raise ValueError('No curve points available to sample from log')
    random.shuffle(points)
    return points[:min(sample_count, len(points))]


def _compute_expected_value(records, param_set, model, metric, epoch):
    values = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if str(rec.get('param_set', '')).strip().upper() != param_set:
            continue
        if str(rec.get('model', '')).strip().lower() != model:
            continue
        if str(rec.get('epoch', '')).strip() != str(epoch):
            continue
        if metric not in rec:
            continue
        try:
            value = float(rec[metric])
        except Exception:
            continue
        if not plotting.np.isfinite(value):
            continue
        values.append(value)
    if not values:
        return None
    return sum(values) / len(values)


def verify(log_path, sample_count=5):
    records = _load_log(log_path)
    plotting.validate_training_history_log(records)
    samples = _sample_points(records, sample_count)
    passed = 0
    failures = []
    for param_set, model, metric, epoch, plotted_value in samples:
        expected = _compute_expected_value(records, param_set, model, metric, epoch)
        if expected is None:
            failures.append((param_set, model, metric, epoch, plotted_value, 'no raw values'))
            continue
        if abs(expected - plotted_value) > 1e-6:
            failures.append((param_set, model, metric, epoch, plotted_value, expected))
        else:
            passed += 1
    return samples, passed, failures


def main():
    parser = argparse.ArgumentParser(description='Verify plot values against centralized training history log')
    parser.add_argument('--log', default='ml/saved/metrics_plots/training_history.jsonl', help='Path to training history log JSONL')
    parser.add_argument('--samples', type=int, default=5, help='Number of random points to verify')
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        raise FileNotFoundError(f'Log file not found: {log_path}')

    samples, passed, failures = verify(str(log_path), sample_count=args.samples)
    print(f'Verification samples: {len(samples)}')
    for param_set, model, metric, epoch, plotted_value in samples:
        print(f'  {param_set}/{model}/{metric}/epoch={epoch}: plotted={plotted_value:.6f}')
    if failures:
        print('\nFailures:')
        for failure in failures:
            if failure[-1] == 'no raw values':
                print(f'  {failure[0]}/{failure[1]}/{failure[2]}/epoch={failure[3]}: plotted={failure[4]} raw missing')
            else:
                print(f'  {failure[0]}/{failure[1]}/{failure[2]}/epoch={failure[3]}: plotted={failure[4]:.6f} expected={failure[5]:.6f}')
    else:
        print('\nAll sampled points match the raw log mean values exactly.')
    print(f'Passed: {passed}, Failed: {len(failures)}')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
