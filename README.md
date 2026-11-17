# GTA VI launch-day Twitch viewers — hour-by-hour forecaster

Forecasts how many people watch Grand Theft Auto VI live on Twitch in each
hour (2–24) of its release day, 2026-11-19 (UTC), as five quantiles per hour
(5%, 25%, 50%, 75%, 95%), given everything recorded up to the end of hour 1.

## Method

Past big launches publish one viewer count per hour. For a launch, write its
release-day curve as log-ratios to its own hour-1 print,
`L_h = ln(viewers_h / viewers_1)`. Two facts show up in every comparable set
the case ships:

1. **The curve has a shape.** It dips in hours 2–5 (only New Zealand and
   the UK have unlocked), then rises as Europe and the Americas unlock,
   peaking around hours 19–21 (US prime time).
2. **The size of hour 1 predicts the shape.** A launch whose hour 1 is
   already huge grows much less through the day than one whose hour 1 is
   small (correlation between `ln(p1)` and late-hour `L_h` is about −0.6
   to −0.9 across the comparables).

So for each hour `h` the program fits, over the comparable launches, the
line `L_h = a_h + b_h * ln(p1)` and predicts this case's `L_h` from its own
hour-1 print (clamped to the comparables' `ln(p1)` range, so a
record-breaking hour 1 never extrapolates the line). The per-hour slopes
are then smoothed over neighbouring hours (an 11-hour centred moving
average, each hour's intercept refitted): one hour's slope is estimated
from only ~19 curves, so it is noisy, while the true slope changes
slowly with the hour. The five quantiles are the prediction plus the
empirical quantiles of that hour's regression residuals — the spread the
comparables actually showed around the line.

**Pool.** Comparables with a complete 24-hour release-day curve whose
hour-1 print is at least 5,000 viewers, excluding launches the case marks
early-access-contaminated or weak (their hour 1 is not a launch hour).
Small categories are sampled sparsely, so their tiny hour-1 prints make
wild log-ratios; the 5,000 floor keeps the fit honest. If the pool is too
small the floor relaxes; with fewer than three curves the forecast falls
back to the house persistence shape. The final case's comparables include
the four practice launches, which join the pool the same way.

## Scores (local reproduction, pinball loss on the log scale)

Practice cases, answers re-fetched from SullyGnome (hour-1 prints match the
cases exactly) and scored with the rules' own formula:

| case | loss | typical miss | 90% coverage |
| ---- | ---: | ---: | ---: |
| p00 Marvel's Wolverine | 0.248 | 50.4% | 0.70 |
| p01 Red Dead Redemption 2 | 0.171 | 31.6% | 0.96 |
| p02 God of War Ragnarök | 0.112 | 16.9% | 1.00 |
| p03 Marvel's Spider-Man 2 | 0.183 | 29.3% | 0.83 |
| **mean** | **0.178** | | |

House baseline on the same cases: **0.387**. Leave-one-out over the 18
big comparable launches: **0.266** vs the baseline's 0.392.

## Run

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Python 3.13, standard library only, no network. Reads every `<id>.in` in
the input directory and writes one `<id>.out` per case. Deterministic:
same case in, same forecast out, byte for byte. Runs in ~0.4 s per case,
far inside the 8 s cap.

## License

MIT — see `LICENSE`.
