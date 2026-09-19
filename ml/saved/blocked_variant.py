"""--blocked switch shared by the direct plotting scripts.

Call `apply(globals())` right after a script's `if DIRECT:` block. With
--blocked on the command line it re-points the script at the
blocked-calibration run (blocked_calib/, written by
blocked_calibration_direct.py), renames every output *_direct.* to
*_direct_blocked.* so the original figures are never overwritten, and stamps
each saved figure so the two variants cannot be confused.
"""
import os
import sys

SAVED = os.path.dirname(os.path.abspath(__file__))
BLOCKED_DIR = os.path.join(SAVED, 'blocked_calib')
PATH_KEYS = ('OUT_PNG', 'ACC_PNG', 'LOSS_PNG', 'BOTH_PNG', 'OUT_CSV', 'TEST_CSV')


def apply(g):
    if '--blocked' not in sys.argv:
        return False
    for k in PATH_KEYS:
        if isinstance(g.get(k), str):
            new = g[k].replace('_direct.', '_direct_blocked.')
            if new == g[k]:
                raise SystemExit(f'--blocked: {k}={g[k]} has no _direct suffix to rename')
            g[k] = new
    if 'SAVED_DIR' in g:
        g['SAVED_DIR'] = BLOCKED_DIR
    if 'MODEL_ROOT' in g:
        g['MODEL_ROOT'] = os.path.join(BLOCKED_DIR, 'saved_direct_sets')

    import matplotlib.figure as mf
    orig = mf.Figure.savefig

    def savefig(self, *a, **k):
        self.text(0.995, 0.995, 'BLOCKED calibration variant', ha='right', va='top',
                  fontsize=10, color='#c0392b', fontweight='bold')
        return orig(self, *a, **k)
    mf.Figure.savefig = savefig
    print(f'[--blocked] reading {BLOCKED_DIR}; outputs renamed *_direct_blocked.*', flush=True)
    return True
