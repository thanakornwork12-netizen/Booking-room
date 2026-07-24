import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / 'ml' / 'saved' / 'generate_plots.py'

if __name__ == '__main__':
    if not SCRIPT.exists():
        print('Missing generate_plots.py at', SCRIPT)
        sys.exit(1)

    print('Running centralized plot generation via ml/saved/generate_plots.py')
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=str(ROOT))
    print('Completed with exit code', result.returncode)
    sys.exit(result.returncode)
