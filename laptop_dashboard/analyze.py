#!/usr/bin/env python3
"""
analyze.py  —  offline analytical visualizations (Milestone 11 / Lab 11).

Reads the historical event log (data/motion_events.jsonl, written by the MQTT
consumer) with pandas and produces a set of Seaborn charts answering concrete
questions about the Smart Waste Bin:

    * events_per_hour.png          When is the bin busiest during the day?
    * events_over_time.png         Is activity trending up or down?
    * usage_heatmap.png            Where are the busy windows across the week?
    * latency_distribution.png     How fast is the pipeline? Any outliers?
    * latency_over_time.png        Is the pipeline getting slower?
    * events_per_bin.png           Are all bins used equally?

DEMO / SMOKE-TEST MODE
----------------------
If no event log exists yet (or you pass --demo), analyze.py generates a
realistic synthetic backup dataset so every chart can be produced for a
showcase without needing a running pipeline:

    python analyze.py --demo            # force synthetic data
    python analyze.py --demo --days 21  # 3 weeks of synthetic data
    python analyze.py                   # real log, or auto-fallback to demo
    python analyze.py path/to/events.jsonl
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

import matplotlib
matplotlib.use("Agg")  # headless: write PNGs without a display
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sns.set_theme(style="whitegrid", context="notebook", font_scale=1.05)

CHARTS_DIR = os.getenv("CHARTS_DIR", "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)


# ── Synthetic backup data (demo / smoke test) ─────────────────────────────────
def generate_sample_events(path: str, days: int = 14, seed: int = 42) -> int:
    """Write a realistic synthetic event log to `path` (JSONL, same shape the
    MQTT consumer writes) so the charts can be showcased without a live system.

    The pattern is deliberately readable: weekday lunch + commute peaks, quiet
    weekends, two bins of differing popularity, and pipeline latency that mostly
    sits low with occasional spikes.
    """
    rng = random.Random(seed)
    bins = [
        ("bin-01", "pir-01", "Lab Room 101 - Kitchen Corner", 1.0),
        ("bin-02", "pir-02", "Lab Room 101 - Entrance", 0.55),
    ]
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=days)
    seq = {b[0]: 0 for b in bins}
    records = []

    t = start
    while t < now:
        hour, dow = t.hour, t.weekday()  # dow: 0=Mon .. 6=Sun
        if dow >= 5:                      # weekend
            base = 1
        elif 11 <= hour <= 14:            # lunch peak
            base = 7
        elif 8 <= hour <= 10:             # morning
            base = 4
        elif 15 <= hour <= 18:            # afternoon
            base = 5
        elif 19 <= hour <= 21:            # evening
            base = 2
        else:                             # night
            base = 0

        for bin_id, dev, locname, scale in bins:
            lam = max(0.0, rng.gauss(base * scale, base * 0.35 + 0.4))
            for _ in range(int(round(lam))):
                ev_t = t + timedelta(minutes=rng.uniform(0, 59), seconds=rng.uniform(0, 59))
                if ev_t >= now:
                    continue
                seq[bin_id] += 1
                # latency mostly ~15-40ms, with rare spikes
                latency_ms = rng.lognormvariate(3.1, 0.45)
                if rng.random() < 0.04:
                    latency_ms *= rng.uniform(3, 8)
                recv_t = ev_t + timedelta(milliseconds=latency_ms)
                iso = ev_t.isoformat().replace("+00:00", "Z")
                records.append({
                    "@context": "https://schema.org/",
                    "@type": "Event",
                    "name": "MotionDetected",
                    "startDate": iso,
                    "resultTime": iso,
                    "madeBySensor": dev,
                    "hasSimpleResult": "detected",
                    "location": {"@type": "Place", "name": locname},
                    "eventNumber": seq[bin_id],
                    "bin_id": bin_id,
                    "device_id": dev,
                    "cpu_temp_c": round(rng.uniform(45, 61), 1),
                    "gas_alert": "detected" if rng.random() < 0.02 else "clear",
                    "_received_at": recv_t.isoformat().replace("+00:00", "Z"),
                    "_topic": f"smartbin/{bin_id}/{dev}/events",
                })
        t += timedelta(hours=1)

    records.sort(key=lambda r: r["startDate"])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return len(records)


# ── Data loading ──────────────────────────────────────────────────────────────
def load_events(filepath: str) -> pd.DataFrame:
    """Load the JSONL event log written by mqtt_consumer.py / the producer."""
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # event time
    for col in ("startDate", "resultTime", "event_time"):
        if col in df.columns:
            df["timestamp"] = pd.to_datetime(df[col], utc=True, errors="coerce")
            break

    # pipeline latency = received - produced
    if "_received_at" in df.columns and "timestamp" in df.columns:
        received = pd.to_datetime(df["_received_at"], utc=True, errors="coerce")
        df["pipeline_latency_ms"] = ((received - df["timestamp"]).dt.total_seconds() * 1000).round(2)
        df.loc[df["pipeline_latency_ms"] < 0, "pipeline_latency_ms"] = float("nan")

    # bin/device id from topic smartbin/<bin>/<device>/events
    if "_topic" in df.columns:
        df["bin_id"] = df["_topic"].str.split("/").str[1]
        df["device_id"] = df["_topic"].str.split("/").str[2]
    elif "bin_id" not in df.columns and "madeBySensor" in df.columns:
        df["device_id"] = df["madeBySensor"]

    if "timestamp" in df.columns:
        df["hour"] = df["timestamp"].dt.hour
        df["day_of_week"] = df["timestamp"].dt.day_name()
        df["date"] = df["timestamp"].dt.date
    return df


def _save(name: str) -> None:
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, name), dpi=150)
    plt.close()
    print(f"Saved {name}")


# ── Charts ────────────────────────────────────────────────────────────────────
def plot_events_per_hour(df):
    hourly = df.groupby("hour").size().reset_index(name="event_count")
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=hourly, x="hour", y="event_count", color="#2196a8", ax=ax, width=0.7)
    ax.set_xlabel("Hour of Day"); ax.set_ylabel("Number of Events")
    ax.set_title("Motion Events by Hour of Day", fontsize=14, fontweight="bold", pad=12)
    sns.despine(); _save("events_per_hour.png")


def plot_events_over_time(df):
    d = df.copy(); d["date"] = pd.to_datetime(d["date"])
    daily = d.groupby("date").size().reset_index(name="event_count")
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.lineplot(data=daily, x="date", y="event_count", marker="o",
                 color="#e8630a", linewidth=2.5, markersize=7, ax=ax)
    ax.set_xlabel("Date"); ax.set_ylabel("Number of Events")
    ax.set_title("Daily Motion Events Over Time", fontsize=14, fontweight="bold", pad=12)
    plt.xticks(rotation=45); sns.despine(); _save("events_over_time.png")


def plot_usage_heatmap(df):
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = (df.groupby(["day_of_week", "hour"]).size().reset_index(name="count")
             .pivot(index="day_of_week", columns="hour", values="count").fillna(0))
    pivot = pivot.reindex([d for d in order if d in pivot.index])
    fig, ax = plt.subplots(figsize=(14, 5))
    sns.heatmap(pivot, cmap="YlOrRd", annot=True, fmt=".0f", linewidths=0.5,
                ax=ax, cbar_kws={"shrink": 0.7})
    ax.set_xlabel("Hour of Day"); ax.set_ylabel("")
    ax.set_title("Usage Heatmap: Hour x Day of Week", fontsize=14, fontweight="bold", pad=12)
    _save("usage_heatmap.png")


def plot_latency_distribution(df):
    if "pipeline_latency_ms" not in df.columns or df["pipeline_latency_ms"].isna().all():
        print("Skipping latency_distribution: no latency data"); return
    data = df["pipeline_latency_ms"].dropna()
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.histplot(x=data, kde=True, color="#437a22", bins=30, ax=ax, alpha=0.75)
    ax.axvline(data.median(), color="#a12c7b", ls="--", lw=1.5,
               label=f"Median: {data.median():.1f} ms")
    ax.set_xlabel("Pipeline Latency (ms)"); ax.set_ylabel("Frequency")
    ax.set_title("Distribution of Pipeline Latency", fontsize=14, fontweight="bold", pad=12)
    ax.legend(); sns.despine(); _save("latency_distribution.png")


def plot_latency_over_time(df):
    if "pipeline_latency_ms" not in df.columns or "timestamp" not in df.columns:
        print("Skipping latency_over_time: missing columns"); return
    if df["pipeline_latency_ms"].isna().all():
        print("Skipping latency_over_time: no latency data"); return
    d = df.sort_values("timestamp")
    rolling = d["pipeline_latency_ms"].rolling(30, min_periods=5).mean()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.scatter(d["timestamp"], d["pipeline_latency_ms"], alpha=0.4, s=15,
               color="#7a39bb", label="Individual events")
    ax.plot(d["timestamp"], rolling, color="#da7101", lw=2, label="30-event rolling mean")
    ax.set_xlabel("Time"); ax.set_ylabel("Pipeline Latency (ms)")
    ax.set_title("Pipeline Latency Over Time", fontsize=14, fontweight="bold", pad=12)
    ax.legend(); plt.xticks(rotation=45); sns.despine(); _save("latency_over_time.png")


def plot_events_per_bin(df):
    if "bin_id" not in df.columns:
        print("Skipping events_per_bin: no bin_id"); return
    counts = df.groupby("bin_id").size().reset_index(name="count")
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(data=counts, x="bin_id", y="count",
                palette=sns.color_palette("tab10", len(counts)), hue="bin_id",
                legend=False, ax=ax, width=0.5)
    ax.set_xlabel("Bin ID"); ax.set_ylabel("Total Events")
    ax.set_title("Total Events per Bin", fontsize=14, fontweight="bold", pad=12)
    sns.despine(); _save("events_per_bin.png")


def main() -> None:
    ap = argparse.ArgumentParser(description="Smart Waste Bin analytical charts")
    ap.add_argument("path", nargs="?", default=None,
                    help="Path to a JSONL event log (default: ../data/motion_events.jsonl)")
    ap.add_argument("--demo", action="store_true",
                    help="Generate synthetic backup data and chart it (no pipeline needed)")
    ap.add_argument("--days", type=int, default=14,
                    help="Days of synthetic data to generate in demo mode")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filepath = args.path or os.path.join(root, "data", "motion_events.jsonl")

    # Demo / smoke-test: forced, or auto-fallback when there is no real data.
    if args.demo or not os.path.exists(filepath):
        reason = "forced by --demo" if args.demo else f"no log at {filepath}"
        backup = os.path.join(root, "data", "motion_events_sample.jsonl")
        n = generate_sample_events(backup, days=args.days)
        print(f"[demo] {reason}: generated {n} synthetic events -> {backup}")
        filepath = backup

    print(f"Loading events from: {filepath}")
    df = load_events(filepath)
    print(f"Loaded {len(df)} events")
    if df.empty:
        print("Event log is empty.")
        sys.exit(1)

    plot_events_per_hour(df)
    plot_events_over_time(df)
    plot_usage_heatmap(df)
    plot_latency_distribution(df)
    plot_latency_over_time(df)
    plot_events_per_bin(df)
    print(f"\nAll charts saved to {CHARTS_DIR}/")


if __name__ == "__main__":
    main()
