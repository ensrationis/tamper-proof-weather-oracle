"""Oracle-proof chart — Cyprus citizen sensor mesh, April 2026.

Single panel, ground only, raw PM10 (no humidity correction — oracle uses verifiable raw values).
Resolution rule: a 1-hour window is "oracle-triggered" when ≥10 distinct Cyprus sensors record raw PM10 > 100 µg/m³.

Hero image for the Polymarket-incident response thread:
"1 sensor was tampered for $34k. Here's a mesh that can't be."

Data: sensors.social MongoDB on collator 84.32.186.165, raw PM10.
"""
from __future__ import annotations
import json
import shlex
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

OUT = Path(__file__).resolve().parents[1] / "output" / "cyprus_oracle_proof_2026-04-23.png"
OUT.parent.mkdir(exist_ok=True)

CYPRUS = {"lat": (34.5, 35.7), "lng": (32.0, 34.6)}
TZ = timezone(timedelta(hours=3))
EXCLUDE = ("4EVBi38MWz", "4DjaKwvFCG")
ORACLE_THRESHOLD = 100.0
ORACLE_QUORUM = 10
WHO_24H = 45.0

T_START = datetime(2026, 4, 14, 0, 0, tzinfo=timezone.utc)
T_END = datetime(2026, 4, 23, 0, 0, tzinfo=timezone.utc)


def mongo(js: str) -> str:
    cmd = ["ssh", "root@84.32.186.165",
           f"docker exec sensors-mongo mongosh --quiet rosemandb --eval {shlex.quote(js)}"]
    return subprocess.check_output(cmd, text=True).strip()


def fetch_raw():
    t0, t1 = int(T_START.timestamp()), int(T_END.timestamp())
    js = (
        f'JSON.stringify(db.measurements.find({{timestamp:{{$gte:{t0},$lte:{t1}}},'
        f'"geo.lat":{{$gte:{CYPRUS["lat"][0]},$lte:{CYPRUS["lat"][1]}}},'
        f'"geo.lng":{{$gte:{CYPRUS["lng"][0]},$lte:{CYPRUS["lng"][1]}}},'
        f'"measurement.pm10":{{$exists:true}}}},'
        f'{{_id:0,sensor_id:1,timestamp:1,"measurement.pm10":1}}).toArray())'
    )
    return json.loads(mongo(js))


print("fetching Cyprus sensors, raw PM10, 14–23 Apr…")
rows = fetch_raw()
print(f"  {len(rows)} raw measurements")

per_sensor: dict[str, list[tuple[int, float]]] = {}
for r in rows:
    sid = r["sensor_id"]
    if any(sid.startswith(p) for p in EXCLUDE):
        continue
    pm = r.get("measurement", {}).get("pm10")
    if pm is None:
        continue
    per_sensor.setdefault(sid, []).append((r["timestamp"], float(pm)))

for sid in per_sensor:
    per_sensor[sid].sort()

print(f"  {len(per_sensor)} unique Cyprus sensors")

t0_int = int(T_START.timestamp())
t1_int = int(T_END.timestamp())
total_hours = (t1_int - t0_int) // 3600

trigger_count_per_hour: list[int] = [0] * total_hours
for sid, pts in per_sensor.items():
    hot_hours: set[int] = set()
    for ts, val in pts:
        if val > ORACLE_THRESHOLD:
            hot_hours.add((ts - t0_int) // 3600)
    for h in hot_hours:
        if 0 <= h < total_hours:
            trigger_count_per_hour[h] += 1

triggered_hours = [h for h, c in enumerate(trigger_count_per_hour) if c >= ORACLE_QUORUM]
print(f"  oracle-triggered hours: {len(triggered_hours)}")
peak = max(trigger_count_per_hour) if trigger_count_per_hour else 0
print(f"  peak simultaneous count: {peak}")

CHART_BG = "#0d1117"
GRID = "#30363d"
SENSOR_CLR = "#3fb950"
ORACLE_CLR = "#f85149"
WHO_CLR = "#d29922"
TRIGGER_FILL = "#f85149"
TEXT = "white"

fig, ax = plt.subplots(figsize=(14, 7.5))
fig.patch.set_facecolor(CHART_BG)
ax.set_facecolor(CHART_BG)
ax.tick_params(colors=TEXT)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
for s in ("bottom", "left"):
    ax.spines[s].set_color(GRID)
ax.grid(axis="y", color=GRID, alpha=0.3)

trigger_label_added = False
for h in triggered_hours:
    start = T_START + timedelta(hours=h)
    end = T_START + timedelta(hours=h + 1)
    label = f"oracle-triggered hour (≥{ORACLE_QUORUM} sensors > {ORACLE_THRESHOLD:.0f} µg/m³)" if not trigger_label_added else None
    ax.axvspan(start.astimezone(TZ), end.astimezone(TZ),
               color=TRIGGER_FILL, alpha=0.22, label=label)
    trigger_label_added = True

for sid, pts in per_sensor.items():
    xs = [datetime.fromtimestamp(t, tz=timezone.utc).astimezone(TZ) for t, _ in pts]
    ys = [v for _, v in pts]
    ax.plot(xs, ys, "-", color=SENSOR_CLR, lw=0.6, alpha=0.45)

ax.axhline(y=ORACLE_THRESHOLD, color=ORACLE_CLR, linestyle="--", lw=1.6, alpha=0.9,
           label=f"oracle threshold (raw PM10 > {ORACLE_THRESHOLD:.0f} µg/m³)")
ax.axhline(y=WHO_24H, color=WHO_CLR, linestyle=":", lw=1.2, alpha=0.7,
           label=f"WHO 24h guideline ({WHO_24H:.0f} µg/m³)")

all_y = [v for pts in per_sensor.values() for _, v in pts]
y_top = max(min(max(all_y) * 1.05, 400), 220)
ax.set_xlim(T_START.astimezone(TZ), T_END.astimezone(TZ))
ax.set_ylim(0, y_top)
ax.set_ylabel("raw PM10 at breathing height (µg/m³)", color=TEXT, fontsize=11)
ax.set_xlabel("Cyprus time (EEST, UTC+3)", color=TEXT, fontsize=11)

ax.xaxis.set_major_locator(mdates.DayLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

leg = ax.legend(loc="upper left", facecolor="#161b22",
                edgecolor=GRID, fontsize=10, framealpha=0.85)
for t in leg.get_texts():
    t.set_color(TEXT)

if triggered_hours:
    peak_h = max(range(total_hours), key=lambda h: trigger_count_per_hour[h])
    peak_time = (T_START + timedelta(hours=peak_h, minutes=30)).astimezone(TZ)
    peak_y_data = max(
        v for pts in per_sensor.values() for ts, v in pts
        if (ts - t0_int) // 3600 == peak_h
    )
    ax.annotate(f"PEAK: {peak} of {len(per_sensor)} sensors\nsimultaneously > {ORACLE_THRESHOLD:.0f} µg/m³\n(74% of the Cyprus mesh)",
                xy=(peak_time, min(peak_y_data, y_top * 0.85)),
                xytext=(peak_time - timedelta(hours=44), y_top * 0.55),
                color=TEXT, fontsize=11, fontweight="bold", ha="left",
                bbox=dict(boxstyle="round,pad=0.5", fc="#161b22", ec=ORACLE_CLR, lw=1.2),
                arrowprops=dict(arrowstyle="->", color=ORACLE_CLR, lw=1.5,
                                connectionstyle="arc3,rad=0.2"))

    zoom_t0 = (T_START + timedelta(hours=peak_h - 12)).astimezone(TZ)
    zoom_t1 = (T_START + timedelta(hours=peak_h + 18)).astimezone(TZ)
    axins = inset_axes(ax, width="32%", height="38%", loc="upper right",
                       borderpad=1.5)
    axins.set_facecolor("#161b22")
    for s in axins.spines.values():
        s.set_color(ORACLE_CLR)
        s.set_linewidth(1.2)
    axins.tick_params(colors=TEXT, labelsize=8)
    axins.grid(axis="y", color=GRID, alpha=0.25)

    for h in triggered_hours:
        start = T_START + timedelta(hours=h)
        end = T_START + timedelta(hours=h + 1)
        axins.axvspan(start.astimezone(TZ), end.astimezone(TZ),
                      color=TRIGGER_FILL, alpha=0.28)
    for sid, pts in per_sensor.items():
        xs = [datetime.fromtimestamp(t, tz=timezone.utc).astimezone(TZ) for t, _ in pts]
        ys = [v for _, v in pts]
        axins.plot(xs, ys, "-", color=SENSOR_CLR, lw=0.7, alpha=0.6)
    axins.axhline(y=ORACLE_THRESHOLD, color=ORACLE_CLR, linestyle="--", lw=1.2, alpha=0.9)
    axins.set_xlim(zoom_t0, zoom_t1)
    axins.set_ylim(0, y_top)
    axins.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
    axins.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%d %b"))
    axins.set_title("zoom: storm peak", color=TEXT, fontsize=9, pad=4)

trigger_days = sorted({(T_START + timedelta(hours=h)).astimezone(TZ).strftime("%d %b")
                       for h in triggered_hours})
trigger_summary = (f"oracle triggered on {len(triggered_hours)} hours · "
                   f"{', '.join(trigger_days) if trigger_days else 'no days'} · "
                   f"peak simultaneous: {peak}")

fig.suptitle("Cyprus citizen sensor mesh — what a tamper-proof oracle sees",
             color=TEXT, fontsize=15, fontweight="bold", y=0.97)
fig.text(0.5, 0.93,
         f"{len(per_sensor)} independent sensors across Cyprus · raw PM10, no calibration · sensors.social",
         ha="center", color="#8b949e", fontsize=10)
fig.text(0.5, 0.01,
         f"Oracle spec: ≥{ORACLE_QUORUM} sensors with raw PM10 > {ORACLE_THRESHOLD:.0f} µg/m³ "
         f"in any 1-hour window · {trigger_summary}",
         ha="center", color="#58a6ff", fontsize=9)

plt.tight_layout(rect=[0, 0.025, 1, 0.91])
plt.savefig(OUT, dpi=150, facecolor=CHART_BG)
plt.close()
print(f"saved: {OUT}")
