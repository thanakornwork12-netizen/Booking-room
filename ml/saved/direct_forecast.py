"""Direct multi-horizon demand forecaster, built for THIS dataset.

Why this exists
───────────────
The original pipeline trains a one-step-ahead regressor and then applies it
recursively for 14 days.  At training time `lag_1` is the true previous day; at
serving time, on day 14, `lag_1` is the model's own 13-step-old guess.  The
model therefore learns to lean on a feature that is real in training and
fabricated in production, and the error compounds across the horizon.  Measured
on the held-out Excel split that costs roughly four accuracy points.

Here every row is (origin t, horizon h) and predicts y[t+h] directly, using
only what is knowable at t.  Nothing is fed back into itself, so h=14 is as
honest as h=1, and training matches serving exactly.

What this dataset actually offers (each checked, not assumed)
────────────────────────────────────────────────────────────
* The 8 rooms move together — weekly correlation .68-.93 — because one academic
  calendar drives them all.  A single pooled model over all rooms sees ~8x the
  data, with room identity and each room's share of campus load as features.
* `load_term_schedule()` returns nothing for any of the 8 rooms, so the 18
  `term_*` columns the old feature set carried were constant zeros.  Dropped.
* `created_at` in the database is the bulk-import timestamp (7,251 rows share
  one instant), so there is no booking-lead-time signal to mine.
* 1.9% of bookings span more than one day but carry 16-61% of every room's
  hours.  Once such a block has started it is committed fact, and on the test
  split every single day covered by an already-running block was 'urgent'.
  Trees ignore it as a feature (too rare to split on), so it is applied as a
  floor on the prediction instead.

The reported metric is 3-class accuracy (low / medium / urgent) obtained by
thresholding predicted hours, so the point estimate is chosen to land in the
most probable class rather than at the conditional median — a quantile ensemble
gives the distribution, `_argmax_class` picks from it.
"""
import os

import numpy as np
import pandas as pd

import forecast as F

HORIZON = 14

# Origin spacing for the TEST split only (train always steps by 1).
#
# HORIZON reproduces the live job exactly: it runs once a fortnight and
# forecasts the next 14 days. But as an evaluation it leaves only ~16
# independent origins per room (~228 rows), and each target day is then scored
# at whichever single horizon it happens to land on. Train origins step by 1,
# so train and test accuracy were being measured over differently sampled row
# sets — measured on the same saved models, moving test to step 1 shrank set
# A's negative train-test gap from -1.21pp to -0.46pp and changed 3C16-17 by
# -3.2pp on its own, purely because the fortnightly grid had landed on easy
# days for it.
#
# 1 matches the train sampling (every day an origin, every day scored at all
# 14 horizons) and raises test rows per room from ~228 to ~3100. Set this back
# to HORIZON to reproduce the live-job cadence.
TEST_ORIGIN_STEP = 1
MIN_HISTORY = 400          # days of history before a room starts producing origins
QUANTILES = (0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95)
CALIB_FRACTION = 0.125     # of the training span, matching the old pipeline

ROOM_IDS = {
    '2C05-06': 443, '2C09': 445, '2C10-11': 446, '2C16-17': 447,
    '3C05-06': 448, '1C-MEETING': 487, '3C16-17': 505, '4C05': 506,
}

FEATURES = [
    # this room's observed state at the origin
    'lag0', 'lag1', 'lag2', 'lag6', 'lag13', 'lag20', 'lag27',
    'rm7', 'rm14', 'rm28', 'rm56', 'rs7', 'rs28', 'rx7', 'rx28', 'nz28',
    'rm7_rm28', 'rm28_rm56',
    # the other rooms at the origin
    'peer_rm7', 'peer_rm28', 'rel_level',
    # deterministic calendar of the target day
    'h', 'dow', 'is_wknd', 'month', 'dom', 'woy',
    'sin_dow', 'cos_dow', 'sin_doy', 'cos_doy', 'sin_doy2', 'cos_doy2', 'holiday',
    # the target weekday's own history as known at the origin
    'sdow4', 'sdow8', 'sdow12', 'prev_dow1', 'prev_dow2', 'prev_dow3', 'prev_dow4',
    # the same calendar position a year earlier
    'year_ago', 'year_ago_win',
    'peer_sdow8', 'peer_prev_dow',
    # identity / scale
    'room_ix', 'room_scale', 'room_active',
    # already-committed multi-day blocks
    'blk_hours', 'blk_active', 'blk_days_in', 'blk_days_left',
]
# Term features were tried as extra columns here and removed: mining a
# schedule under a train cutoff left every calibration/test date outside every
# term run, so the columns became sentinels exactly where the model is scored.
# See forecast.resolve_term_schedule for the measurement that rejected them.
CATEGORICAL = ['dow', 'room_ix', 'month']


def _daily_series(rows, room_id):
    if len(rows) == 0:
        return pd.Series(dtype=float)
    x = rows.copy()
    x['room_id'] = room_id
    x['duration'] = x['duration_hours']
    x['date'] = pd.to_datetime(x['date']).dt.date
    return F._prepare_daily_series(x, None, None)


class Dataset:
    """Every room aligned onto one shared calendar, with the split boundaries
    and thresholds the existing evaluation uses."""

    def __init__(self, train_xlsx, test_xlsx):
        tr = pd.read_excel(train_xlsx)
        te = pd.read_excel(test_xlsx)
        for d in (tr, te):
            d['date'] = pd.to_datetime(d['date'])
            # match load_raw_bookings(): a room cannot deliver more than ~12h/day
            d['duration_hours'] = d['duration_hours'].clip(lower=0.25, upper=12.0)
        self.train_rows, self.test_rows = tr, te

        raw = {}
        for code, rid in ROOM_IDS.items():
            s_tr = _daily_series(tr[tr.room_code == code], rid)
            both = pd.concat([tr[tr.room_code == code], te[te.room_code == code]])
            full = _daily_series(both, rid)
            if full is None or len(full) == 0:
                continue
            n_train = len(s_tr)
            calib_len = max(1, int(round(n_train * CALIB_FRACTION)))
            train_end = max(n_train - calib_len, F.MIN_TRAIN_ROWS)
            calib_end = min(n_train, len(full) - 1)
            cap95 = float(full.iloc[:train_end].quantile(0.95)) or 1.0
            s = full.clip(upper=cap95)
            peak = float(s.iloc[:train_end].quantile(0.95)) or 1.0
            thr_high, thr_med = F.compute_adaptive_thresholds(s.iloc[:train_end], peak)
            raw[code] = dict(s=s, rid=rid, peak=peak, thr_high=thr_high, thr_med=thr_med,
                             scale=max(peak, 1e-6),
                             d_train_end=s.index[train_end],
                             d_calib_end=s.index[calib_end], d_last=s.index[-1])

        self.calendar = pd.date_range(min(d['s'].index[0] for d in raw.values()),
                                      max(d['s'].index[-1] for d in raw.values()), freq='D')
        pos = {d: i for i, d in enumerate(self.calendar)}
        self.pos = pos
        self.codes = list(raw)
        self.code_ix = {c: i for i, c in enumerate(self.codes)}

        self.rooms = {}
        for code, d in raw.items():
            s = d['s'].reindex(self.calendar, fill_value=0.0)
            self.rooms[code] = dict(
                v=s.to_numpy(float), rid=d['rid'], peak=d['peak'], scale=d['scale'],
                thr_high=d['thr_high'], thr_med=d['thr_med'],
                start=pos[d['s'].index[0]], train_end=pos[d['d_train_end']],
                calib_end=pos[d['d_calib_end']], last=pos[d['d_last']],
            )

        cal = self.calendar
        self.dow = cal.dayofweek.to_numpy()
        self.doy = cal.dayofyear.to_numpy()
        self.woy = cal.isocalendar().week.to_numpy()
        self.month = cal.month.to_numpy()
        self.dom = cal.day.to_numpy()
        self.holiday = np.array([float(F._is_fixed_th_public_holiday(d)) for d in cal])

        self._precompute_rollups()
        self._precompute_blocks(pd.concat([tr, te], ignore_index=True))


    def _precompute_rollups(self):
        self.pre = {}
        for code, r in self.rooms.items():
            s = pd.Series(r['v'])
            p = {f'rm{w}': s.rolling(w, min_periods=1).mean().to_numpy() for w in (7, 14, 28, 56)}
            p['rs7'] = s.rolling(7, min_periods=1).std().fillna(0).to_numpy()
            p['rs28'] = s.rolling(28, min_periods=1).std().fillna(0).to_numpy()
            p['rx7'] = s.rolling(7, min_periods=1).max().to_numpy()
            p['rx28'] = s.rolling(28, min_periods=1).max().to_numpy()
            p['nz28'] = (s > 0).rolling(28, min_periods=1).mean().to_numpy()
            # trailing mean over the last k occurrences of each weekday
            for k in (4, 8, 12):
                out = np.zeros(len(s))
                for dw in range(7):
                    sel = np.where(self.dow == dw)[0]
                    out[sel] = pd.Series(r['v'][sel]).rolling(k, min_periods=1).mean().to_numpy()
                p[f'sdow{k}'] = out
            self.pre[code] = p

    def _precompute_blocks(self, all_rows):
        """Per-day committed hours, tagged with the day the booking began, so a
        forecast origin can be asked what it already knows."""
        all_rows = all_rows.copy()
        all_rows['start_time'] = pd.to_datetime(all_rows['start_time'])
        all_rows['end_time'] = pd.to_datetime(all_rows['end_time'])
        self.contrib = {c: {} for c in self.codes}
        for code in self.codes:
            b = all_rows[all_rows.room_code == code]
            for start, end in zip(b['start_time'], b['end_time']):
                start, end = pd.Timestamp(start), pd.Timestamp(end)
                if end <= start:
                    continue
                sp = self.pos.get(start.normalize())
                if sp is None:
                    continue
                ep = self.pos.get(end.normalize(), sp)
                cur = start.normalize()
                while cur <= end.normalize():
                    jp = self.pos.get(cur)
                    if jp is not None:
                        ov_s, ov_e = max(start, cur), min(end, cur + pd.Timedelta(days=1))
                        hrs = (ov_e - ov_s).total_seconds() / 3600.0
                        if hrs > 0:
                            self.contrib[code].setdefault(jp, []).append(
                                (sp, min(hrs, 12.0), ep))
                    cur += pd.Timedelta(days=1)

    def known_block(self, code, origin, target):
        """Hours on `target` already committed by blocks begun at or before
        `origin`.  A same-day booking has sp == target > origin, so only genuine
        multi-day blocks that are already running ever contribute."""
        hours, end_max, start_min = 0.0, -1, 10 ** 9
        for sp, h, ep in self.contrib[code].get(target, ()):
            if sp <= origin:
                hours += h
                end_max = max(end_max, ep)
                start_min = min(start_min, sp)
        if hours <= 0:
            return 0.0, 0.0, 0.0, 0.0
        return hours, 1.0, float(target - start_min), float(max(0, end_max - target))

    def peers(self, code):
        return [c for c in self.codes if c != code]

    def cuts(self, code):
        """Class boundaries in normalised (hours / peak_ref) space."""
        r = self.rooms[code]
        med_buf = max(F.LABEL_MED_BUFFER, max(F.LABEL_BUFFER, 0.01))
        return (r['thr_med'] * (1.0 - med_buf),
                r['thr_high'] * (1.0 - max(F.LABEL_BUFFER, 0.01)))

    # ── feature construction ────────────────────────────────────────────────
    def build_rows(self, code, origins):
        r = self.rooms[code]
        v, last, scale = r['v'], r['last'], r['scale']
        pre, peers = self.pre[code], self.peers(code)
        rows, ys, meta = [], [], []

        for t in origins:
            rm7, rm14 = pre['rm7'][t], pre['rm14'][t]
            rm28, rm56 = pre['rm28'][t], pre['rm56'][t]
            origin_state = [
                v[t], v[t - 1] if t >= 1 else 0.0, v[t - 2] if t >= 2 else 0.0,
                v[t - 6] if t >= 6 else 0.0, v[t - 13] if t >= 13 else 0.0,
                v[t - 20] if t >= 20 else 0.0, v[t - 27] if t >= 27 else 0.0,
                rm7, rm14, rm28, rm56, pre['rs7'][t], pre['rs28'][t],
                pre['rx7'][t], pre['rx28'][t], pre['nz28'][t],
                rm7 / (rm28 + 1e-6), rm28 / (rm56 + 1e-6),
            ]
            peer_rm7 = float(np.mean([self.pre[p]['rm7'][t] / self.rooms[p]['scale']
                                      for p in peers]))
            peer_rm28 = float(np.mean([self.pre[p]['rm28'][t] / self.rooms[p]['scale']
                                       for p in peers]))
            peer_state = [peer_rm7, peer_rm28, (rm28 / scale) / (peer_rm28 + 1e-6)]

            for h in range(1, HORIZON + 1):
                j = t + h
                if j > last:
                    break
                dow = int(self.dow[j])
                doy = float(self.doy[j])
                calendar = [
                    h, dow, 1.0 if dow >= 5 else 0.0, self.month[j], self.dom[j],
                    int(self.woy[j]),
                    np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7),
                    np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25),
                    np.sin(4 * np.pi * doy / 365.25), np.cos(4 * np.pi * doy / 365.25),
                    self.holiday[j],
                ]
                # step back to the last occurrence of the target weekday that
                # the origin can actually see
                anchor = j - 7 * ((j - t + 6) // 7)
                same_dow = [pre[f'sdow{k}'][anchor] if anchor >= 0 else 0.0
                            for k in (4, 8, 12)]
                prev_dow = [v[j - 7 * k] if 0 <= j - 7 * k <= t else np.nan
                            for k in range(1, 5)]
                ya = j - 364          # 52 weeks keeps the weekday aligned
                year_ago = v[ya] if 0 <= ya <= t else np.nan
                year_ago_win = (float(v[max(0, ya - 3): ya + 4].mean())
                                if ya - 3 >= 0 and ya + 3 <= t else np.nan)
                peer_sdow = float(np.mean([self.pre[p]['sdow8'][anchor] / self.rooms[p]['scale']
                                           for p in peers]) if anchor >= 0 else 0.0)
                peer_prev = float(np.nanmean(
                    [(self.rooms[p]['v'][j - 7] / self.rooms[p]['scale'])
                     if j - 7 <= t else np.nan for p in peers]))
                blk = self.known_block(code, t, j)

                rows.append(origin_state + peer_state + calendar + same_dow + prev_dow +
                            [year_ago, year_ago_win, peer_sdow, peer_prev,
                             self.code_ix[code], scale, pre['nz28'][t] * scale] +
                            list(blk))
                ys.append(v[j])
                meta.append((code, t, h, j))
        return np.asarray(rows, float), np.asarray(ys, float), meta

    def origins(self, code, split):
        r = self.rooms[code]
        if split == 'train':
            return list(range(r['start'] + MIN_HISTORY, r['train_end'] - 1))
        if split == 'calib':
            return list(range(r['train_end'] - HORIZON, r['calib_end'] - 1))
        return list(range(r['calib_end'], r['last'], TEST_ORIGIN_STEP))

    def matrix(self, split, codes=None):
        """Feature matrix for one split; targets are normalised by peak_ref so
        rooms of different sizes can share a model."""
        X, Y, M = [], [], []
        for code in (codes or self.codes):
            r = self.rooms[code]
            if split == 'train':
                lo, hi = 0, r['train_end']
            elif split == 'calib':
                lo, hi = r['train_end'], r['calib_end']
            else:
                lo, hi = r['calib_end'], 10 ** 9
            x, y, m = self.build_rows(code, self.origins(code, split))
            if len(x) == 0:
                continue
            keep = np.array([lo <= q[3] < hi for q in m])
            if not keep.any():
                continue
            X.append(x[keep])
            Y.append(y[keep] / r['scale'])
            M += [m[i] for i in np.where(keep)[0]]
        return np.vstack(X), np.concatenate(Y), M


# ── turning a predicted distribution into a served number ───────────────────
_MASS = np.diff([0.0] + list(QUANTILES) + [1.0])
_MASS = (_MASS[:-1] + _MASS[1:]) / 2.0


def argmax_class(quantile_preds, meta, data):
    """Emit the centre of the most probable demand band.

    The metric is 3-class accuracy after thresholding, so the best point
    estimate is the one most likely to land in the right band — not the
    conditional median, which on a right-skewed series sits below the peaks and
    reported half of all 'urgent' days as 'low' or 'medium'.
    """
    out = np.zeros(len(quantile_preds))
    for i, m in enumerate(meta):
        lo, hi = data.cuts(m[0])
        q = np.sort(quantile_preds[i])
        mass = [_MASS[q < lo].sum(), _MASS[(q >= lo) & (q < hi)].sum(), _MASS[q >= hi].sum()]
        band = int(np.argmax(mass))
        if band == 0:
            sel = q[q < lo]
            out[i] = np.median(sel) if sel.size else lo * 0.5
        elif band == 1:
            sel = q[(q >= lo) & (q < hi)]
            out[i] = np.median(sel) if sel.size else (lo + hi) / 2
        else:
            sel = q[q >= hi]
            out[i] = np.median(sel) if sel.size else hi * 1.05
    return out


def median_forecast(quantile_preds):
    """The conditional median — the point estimate that minimises MAE.

    Kept separate from the class decision on purpose: the two are answers to
    different questions under different losses, and forcing one number to serve
    both makes each worse.  Hours shown to a user come from here; the demand
    band comes from `argmax_class`.
    """
    qs = list(QUANTILES)
    lo = max(i for i, q in enumerate(qs) if q <= 0.5)
    hi = min(i for i, q in enumerate(qs) if q >= 0.5)
    if lo == hi:
        return quantile_preds[:, lo]
    span = qs[hi] - qs[lo]
    w = (0.5 - qs[lo]) / span
    return (1 - w) * quantile_preds[:, lo] + w * quantile_preds[:, hi]


def selection_margin(n_days):
    """How much better an alternative must score before it is believed.

    A calibration window of ~109 days carries a standard error near
    sqrt(0.25/109) = 0.048 on an accuracy estimate, so a strategy winning by a
    couple of thousandths has won nothing.  Choosing on such a margin actively
    hurt: on the first production run 2C16-17 switched to a day-of-week profile
    on a 0.002 calibration edge and lost 8 points of test accuracy, dragging
    the fleet mean from 0.800 to 0.764.  Two standard errors is the price of
    leaving the default.
    """
    return 2.0 * np.sqrt(0.25 / max(n_days, 1))


def choose_strategy(scores, n_days, default='argmax_class'):
    """Pick a room's strategy, defaulting unless another wins by real margin."""
    if default not in scores:
        return max(scores, key=scores.get), 0.0
    margin = selection_margin(n_days)
    best = max(scores, key=scores.get)
    if best == default:
        return default, 0.0
    lead = scores[best] - scores[default]
    return (best, lead) if lead > margin else (default, lead)


def apply_block_floor(pred, X, meta, data):
    """Committed hours are a fact, so no forecast may sit below them."""
    ix = FEATURES.index('blk_hours')
    known = X[:, ix] / np.array([data.rooms[m[0]]['scale'] for m in meta])
    return np.maximum(pred, known)


def strategies(data, code, quantile_preds, X, meta):
    """Candidate predictors for one room.

    The 8 rooms are not one problem: 1C-MEETING books once a fortnight and a
    flat 'low' beats any model on it, while 3C16-17 runs near capacity and
    needs the whole distribution.  Each room picks its own winner on the
    calibration window (see train_direct.py), so a room is never forced onto a
    predictor that demonstrably does not suit it.
    """
    r = data.rooms[code]
    lo, hi = data.cuts(code)
    n = len(meta)

    band_centre = [lo * 0.5, (lo + hi) / 2, hi * 1.05]
    train_norm = r['v'][:r['train_end']] / r['scale']
    labels = np.where(train_norm >= hi, 2, np.where(train_norm >= lo, 1, 0))
    constant = band_centre[int(np.bincount(labels, minlength=3).argmax())]

    sdow8 = data.pre[code]['sdow8']
    dow_profile = np.zeros(n)
    for i, (_, t, _h, j) in enumerate(meta):
        anchor = j - 7 * ((j - t + 6) // 7)
        dow_profile[i] = (sdow8[anchor] / r['scale']) if anchor >= 0 else 0.0

    amc = argmax_class(quantile_preds, meta, data)
    median = quantile_preds[:, len(QUANTILES) // 2]
    return {
        'argmax_class': amc,
        'median': median,
        'dow_profile': dow_profile,
        'constant': np.full(n, constant),
        'blend_amc_dow': 0.5 * amc + 0.5 * dow_profile,
    }


def accuracy_by_room(data, meta, y_norm, pred_norm):
    out = {}
    codes = np.array([m[0] for m in meta])
    for code in data.codes:
        k = codes == code
        if not k.any():
            continue
        r = data.rooms[code]
        cls = F.compute_classification_metrics(
            y_norm[k] * r['scale'], np.maximum(0.0, pred_norm[k]) * r['scale'],
            r['thr_high'], r['thr_med'], r['peak'])
        out[code] = cls
    return out
