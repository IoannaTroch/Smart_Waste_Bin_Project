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

Run:
    python analyze.py                              # uses ../data/motion_events.jsonl
    python analyze.py path/to/events.jsonl
"""

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")  # headless: write PNGs without a display
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sns.set_theme(style="whitegrid", context="notebook", font_scale=1.05)

CHARTS_DIR = os.getenv("CHARTS_DIR", "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)


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
                palette=sns.color_palette("tab10", len(counts)), ax=ax, width=0.5)
    ax.set_xlabel("Bin ID"); ax.set_ylabel("Total Events")
    ax.set_title("Total Events per Bin", fontsize=14, fontweight="bold", pad=12)
    sns.despine(); _save("events_per_bin.png")


def main() -> None:
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filepath = os.path.join(root, "data", "motion_events.jsonl")

    print(f"Loading events from: {filepath}")
    if not os.path.exists(filepath):
        print("No event log found. Run the producer + consumer first "
              "(or `docker compose up`) to generate data.")
        sys.exit(1)

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
