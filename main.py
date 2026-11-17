"""Forecast GTA VI's launch-day Twitch viewers, hour by hour, after hour 1.

Method (fitted on the case's own comparables, nothing else):
  Past big launches publish one number per hour.  For a launch, write its
  release-day curve as log-ratios to its own hour-1 print,
  L_h = ln(viewers_h / viewers_1), h = 2..24.  Two facts show up in every
  comparable set:

  1. The curve has a shape: it dips in hours 2-5 (only New Zealand and the
     UK have unlocked), then rises as Europe and the Americas unlock, peaking
     around hours 19-21 (US prime time) at roughly 1.3x-2.3x hour 1.
  2. The size of hour 1 predicts the shape: a launch whose hour 1 is already
     huge grows much less through the day than one whose hour 1 is small
     (corr(ln p1, L_h) about -0.6 to -0.9 at late hours over the comparables).

  So for each hour h we fit, over the comparable launches, the line
  L_h = a_h + b_h * ln(p1), and predict this case's L_h from its own hour-1
  print p1 (clamped to the comparables' ln(p1) range, so a record-breaking
  hour 1 never extrapolates the line).  The per-hour slopes are then
  smoothed over neighbouring hours (an 11-hour centred moving average,
  each hour's intercept refitted): one hour's slope is estimated from
  only ~19 curves, so it is noisy, while the true slope changes slowly
  with the hour.  The five quantiles are the prediction plus the
  empirical quantiles of that hour's regression residuals, so the
  spread is the spread the comparables actually showed around the line, not
  an assumed one.

Pool: comparables with a complete 24-hour release-day curve whose hour-1
print is at least 5,000 viewers, excluding launches the case marks
early-access-contaminated or weak (their hour 1 is not a launch hour).
Small categories are sampled sparsely, so their tiny hour-1 prints make
wild log-ratios; the 5,000 floor keeps the fit honest.  If the pool is
too small the floor relaxes (1,000, then any complete curve); with fewer
than three curves the forecast falls back to the house persistence shape.

Only the standard library is used.  The program is deterministic: same
case in, same forecast out, byte for byte.  It reads every <id>.in in the
input directory and writes one <id>.out per case.

Run locally: mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module
# shipped beside this file imports.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# House persistence fallback: q_tau(h) = p1 * exp(z_tau * SIGMA * sqrt(h-1)).
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
SIGMA = 0.15
MIN_POOL = 5          # curves needed before the floor relaxes
MIN_FLOOR = 5000      # hour-1 viewers for a curve to join the pool
VIEWER_CAP = 1_000_000_000


def parse_time(text):
    """ISO 8601 UTC timestamp -> aware datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def round2(x):
    """x rounded to 2 decimals, half up, as the starter rounds it."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def quantile(xs, q):
    """Linear-interpolation quantile of a sorted sample."""
    ordered = sorted(xs)
    if not ordered:
        return 0.0
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def release_day_curve(comp):
    """The comparable's 24 hourly viewer counts on its release day.

    Returns a list of 24 positive numbers (hours 1..24), or None when the
    curve is incomplete: a point is missing, zero, or the day never started
    (the target's own pre-launch history has no release day at all).
    """
    try:
        day_start = parse_time(comp["day_start"])
    except (KeyError, TypeError, ValueError):
        return None
    by_hour = {}
    for point in comp.get("hourly") or []:
        viewers = point.get("viewers")
        if viewers is None or viewers <= 0:
            continue
        try:
            at = parse_time(point["from"])
        except (KeyError, TypeError, ValueError):
            continue
        hour = int((at - day_start).total_seconds() // 3600) + 1
        if 1 <= hour <= 24:
            by_hour[hour] = viewers
    curve = [by_hour.get(h) for h in range(1, 25)]
    if any(v is None for v in curve):
        return None
    return curve


def build_pool(case, floor):
    """Comparable release-day curves usable for the fit.

    Excludes launches the case marks early-access-contaminated or weak, and
    curves whose hour-1 print is below the floor.
    """
    pool = []
    for comp in case.get("comparables") or []:
        unlock = (comp.get("unlock") or "").lower()
        if "tier: early-access" in unlock or "tier: weak" in unlock:
            continue
        curve = release_day_curve(comp)
        if curve is None or curve[0] < floor:
            continue
        pool.append(curve)
    return pool


def ols(xs, ys):
    """Least-squares line ys ~ a + b*xs; returns (a, b)."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return my, 0.0
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def baseline_quantiles(p1, hour):
    """House persistence shape, used only when the pool is too small."""
    return [round2(p1 * math.exp(z * SIGMA * math.sqrt(hour - 1))) for z in Z]


def forecast_case(case):
    levels = list(case.get("levels") or LEVELS)
    known = next((k for k in case.get("known") or [] if k.get("hour") == 1), None)
    if known is None:
        hourly = case.get("history_hourly") or []
        p1 = max(1.0, hourly[-1]["viewers"]) if hourly else 1.0
    else:
        p1 = max(1.0, float(known["viewers"]))

    pool = build_pool(case, MIN_FLOOR)
    if len(pool) < MIN_POOL:
        pool = build_pool(case, 1000)
    if len(pool) < 3:
        pool = build_pool(case, 0)

    hours = [row["hour"] for row in case.get("forecast") or []]
    if not hours:
        hours = list(range(2, 25))

    if len(pool) < 3:
        return {"hours": [{"hour": h, "q": baseline_quantiles(p1, h)} for h in hours]}

    xs = [math.log(curve[0]) for curve in pool]
    lo, hi = min(xs), max(xs)
    x_case = min(max(math.log(p1), lo), hi)

    # One line per hour, then smooth the slopes over neighbouring hours.
    # A single hour's slope comes from ~19 curves, so it is noisy, while
    # the true slope moves slowly with the hour.  An 11-hour centred
    # moving average of the slopes, with each hour's intercept refitted
    # as mean(y - b_smooth * x), cuts that noise: measured on the
    # practice cases and on leave-one-out over the 18 big comparables
    # it helps a little on both (practice 0.1795 -> 0.1784, LOO
    # 0.2699 -> 0.2656).  Wider windows turn back up again, and one
    # shared slope is far worse, so 11 hours is the measured sweet spot.
    fits = []
    for hour in hours:
        ratios = [math.log(curve[hour - 1] / curve[0]) for curve in pool]
        fits.append((ratios,) + ols(xs, ratios))
    slopes = [b for _, _, b in fits]
    smoothed = []
    for i, (ratios, _, _) in enumerate(fits):
        window = slopes[max(0, i - 5):i + 6]
        b_smooth = sum(window) / len(window)
        a_smooth = sum(y - b_smooth * x for x, y in zip(xs, ratios)) / len(xs)
        smoothed.append((a_smooth, b_smooth))

    rows = []
    for i, hour in enumerate(hours):
        ratios = fits[i][0]
        a, b = smoothed[i]
        centre = a + b * x_case
        residuals = [y - (a + b * x) for x, y in zip(xs, ratios)]
        quantiles = []
        previous = 0.0
        for tau in levels:
            value = p1 * math.exp(centre + quantile(residuals, tau))
            value = min(max(value, 1.0), VIEWER_CAP)
            value = round2(value)
            # Quantiles of one distribution never decrease; keep it so
            # after rounding too.
            if value < previous:
                value = previous
            previous = value
            quantiles.append(value)
        rows.append({"hour": hour, "q": quantiles})
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
