"""
Train hyperparameter sets sequentially with optimized speed
Default: Train only Set B (fast + good quality)
"""
import os
import sys
import subprocess
import time
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
METRICS_DIR = CURRENT_DIR / "metrics_plots"


def run_training(param_set, use_import_excel=False):
    """Run training for a specific parameter set. forecast.py always trains full rounds by default."""
    cmd = ['python', str(CURRENT_DIR / 'forecast.py')]

    if use_import_excel:
        cmd.append('--import-excel')
    else:
        cmd.append('--retrain')

    cmd.extend(['--param-set', param_set])

    print(f"\n{'=' * 80}")
    print(f"🚀 Training: Parameter Set {param_set}")
    print(f"{'=' * 80}\n")
    
    start_time = time.time()
    try:
        result = subprocess.run(cmd, cwd=str(CURRENT_DIR.parent.parent))
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            print(f"\n✅ Set {param_set} completed in {elapsed/60:.1f} minutes")
            return True
        else:
            print(f"\n❌ Set {param_set} failed with exit code {result.returncode}")
            return False
    except Exception as e:
        print(f"\n❌ Error running Set {param_set}: {e}")
        return False


def run_comparison():
    """Generate comparison report."""
    cmd = ['python', str(CURRENT_DIR / 'compare_hyperparams.py')]
    
    print(f"\n{'=' * 80}")
    print(f"📊 Generating Comparison Report")
    print(f"{'=' * 80}\n")
    
    try:
        result = subprocess.run(cmd, cwd=str(CURRENT_DIR.parent.parent))
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error generating comparison: {e}")
        return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Train hyperparameter sets with optimized speed'
    )
    parser.add_argument('--sets', type=str, default='B', 
                        help='Which sets to train: A, B, C, or ABC (default: B)')
    parser.add_argument('--import-excel', action='store_true',
                        help='Import real data and train (instead of --retrain)')
    parser.add_argument('--skip-comparison', action='store_true',
                        help='Skip final comparison report')
    args = parser.parse_args()
    
    # Parse which sets to train
    sets_to_train = list(args.sets.upper())
    valid_sets = {'A', 'B', 'C'}
    sets_to_train = [s for s in sets_to_train if s in valid_sets]
    
    if not sets_to_train:
        sets_to_train = ['B']
    
    print("\n" + "=" * 80)
    print(f"🔄 TRAIN HYPERPARAMETER SETS: {', '.join(sets_to_train)}")
    print("=" * 80)
    print(f"Mode: {'Import + Train' if args.import_excel else 'Retrain'}")
    print(f"Estimated time: {2 * len(sets_to_train):.0f} hours\n")
    
    results = {}
    
    overall_start = time.time()
    
    for i, param_set in enumerate(sets_to_train, 1):
        print(f"\n[{i}/{len(sets_to_train)}] Training Set {param_set}...")
        success = run_training(param_set, use_import_excel=args.import_excel)
        results[param_set] = success
        
        if not success:
            print(f"⚠️  Set {param_set} failed, continuing with next set...")
        
        # Add small delay between sets
        if i < len(sets_to_train):
            time.sleep(2)
    
    overall_elapsed = time.time() - overall_start
    
    # Summary
    print(f"\n{'=' * 80}")
    print(f"📋 TRAINING SUMMARY")
    print(f"{'=' * 80}")
    print(f"Total time: {overall_elapsed/3600:.1f} hours\n")
    
    for param_set in sets_to_train:
        status = "✅ SUCCESS" if results[param_set] else "❌ FAILED"
        print(f"  Set {param_set}: {status}")
    
    success_count = sum(1 for v in results.values() if v)
    print(f"\n  Total: {success_count}/{len(sets_to_train)} sets completed\n")
    
    # Generate comparison if multiple sets
    if not args.skip_comparison and success_count > 0 and len(sets_to_train) > 1:
        ok = run_comparison()
        if ok:
            print(f"\n🎯 Comparison report generated in: {METRICS_DIR}")
            print(f"   Files:")
            print(f"   - hyperparam_comparison.csv")
            print(f"   - hyperparam_comparison.png")

    # Regenerate centralized plot outputs from training logs
    if success_count > 0:
        print('\n📌 Regenerating centralized plot outputs using ml/saved/generate_plots.py')
        try:
            plot_script = CURRENT_DIR / 'generate_plots.py'
            result = subprocess.run([sys.executable, str(plot_script)], cwd=str(CURRENT_DIR), check=False)
            print('generate_plots.py exit code:', result.returncode)
            if result.returncode != 0:
                print('Warning: generate_plots.py did not complete successfully')
        except Exception as e:
            print(f'Warning: failed to run generate_plots.py: {e}')

    print(f"\n{'=' * 80}\n")


if __name__ == '__main__':
    main()
