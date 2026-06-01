#!/usr/bin/env python3
"""
mqtt_gui_consumer.py  —  advanced live dashboard (Milestone 11 + Dashboard).

A dark-themed Tkinter operations console for the Smart Waste Bin. It subscribes
to the whole `smartbin/#` tree on the broker and routes messages by topic:

    .../events       rich JSON motion event    -> KPIs, charts, live feed, JSONL log
    .../motion       "detected"/"clear"        -> live status indicator
    .../gas          "detected"/"clear"        -> gas alert banner + KPI
    .../online       "true"/"false" (LWT)      -> online/offline tracking
    .../usage        rule-based virtual sensor -> Usage Intensity card (color-coded)
    .../prediction   ML virtual sensor         -> Next-Hour Prediction card
    .../status       retained bin status       -> system overview

Information design follows RUSTIC: a clear hierarchy (status banner -> KPIs ->
detail), color-coded states (idle/low/medium/high, busy/quiet, online/offline),
conditional alerts, and a system-overview footer.

Run:
    python mqtt_gui_consumer.py --broker broker.hivemq.com
    python mqtt_gui_consumer.py --demo        # no broker needed: animated showcase
"""

import argparse
import csv
import json
import queue
import random
import threading
import time
from collections import deque, defaultdict
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import paho.mqtt.client as mqtt


# ── Config ────────────────────────────────────────────────────────────────────
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "smartbin/#"
LOG_FILE = "events_log.json"
ALERT_THRESH = 10  # events/hour before a "needs checking" alert

# ── Palette (RUSTIC-friendly, high contrast) ──────────────────────────────────
BG, SURFACE, SURFACE2, BORDER = "#0d1117", "#161b22", "#1c2128", "#30363d"
ACCENT, ACCENT2, PURPLE = "#00d084", "#58a6ff", "#d2a8ff"
TEXT, MUTED, WARN, ERROR = "#e6edf3", "#8b949e", "#f0883e", "#ff7b72"
GOLD = "#e3b341"

LEVEL_COLORS = {"idle": MUTED, "low": ACCENT, "medium": WARN, "high": ERROR}
PREDICT_COLORS = {"busy": WARN, "quiet": ACCENT}

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": SURFACE, "axes.edgecolor": BORDER,
    "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "text.color": TEXT, "grid.color": BORDER, "grid.linestyle": "--", "grid.alpha": 0.4,
})


class Dashboard:
    def __init__(self, root, broker, port, topic, demo=False):
        self.root, self.broker, self.port, self.topic = root, broker, port, topic
        self.demo = demo
        root.title("Smart Waste Bin  -  Live Operations Dashboard" + ("  [DEMO]" if demo else ""))
        root.geometry("1320x920")
        root.configure(bg=BG)
        root.minsize(1100, 780)

        # data stores
        self.q = queue.Queue()
        self.saved_data = []
        self.last_time = None
        self.counter = 0
        self.msg_count = 0
        self.session_start = time.time()
        self.delays = deque(maxlen=60)
        self.x_events = deque(maxlen=60)
        self.bucket_counts = deque(maxlen=20)
        self._bucket_t = time.time()
        self._bucket_n = 0
        self.hourly = [0] * 24
        self.events_this_hour = 0
        self._hour_mark = datetime.now().hour
        self.per_bin = defaultdict(int)
        self.online = {}
        self.gas_active = set()
        self.usage_level = "—"
        self.prediction = "—"
        self.motion_state = "idle"
        self._stop = False

        self._build_ui()
        self._setup_source()
        self._poll()
        self._tick()

    # ══════════════════════════════════════════════ UI ═══════════════════════
    def _build_ui(self):
        # Top bar
        top = tk.Frame(self.root, bg=SURFACE, height=58); top.pack(fill=tk.X); top.pack_propagate(False)
        tk.Label(top, text="🗑", font=("Arial", 22), bg=SURFACE, fg=ACCENT).pack(side=tk.LEFT, padx=(16, 6))
        tk.Label(top, text="Smart Waste Bin", font=("Arial", 15, "bold"), bg=SURFACE, fg=TEXT).pack(side=tk.LEFT)
        tk.Label(top, text="Live Operations Dashboard", font=("Arial", 10), bg=SURFACE, fg=MUTED).pack(side=tk.LEFT, padx=(6, 0))

        tk.Button(top, text="↓  Export CSV", font=("Arial", 10, "bold"), bg=ACCENT2, fg=BG,
                  relief="flat", padx=12, pady=3, cursor="hand2", command=self._save_csv,
                  activebackground="#79c0ff").pack(side=tk.RIGHT, padx=(0, 14), pady=12)

        pill = tk.Frame(top, bg=SURFACE); pill.pack(side=tk.RIGHT, padx=10)
        self.dot = tk.Label(pill, text="●", font=("Arial", 13), bg=SURFACE, fg=WARN); self.dot.pack(side=tk.LEFT)
        self.status_lbl = tk.Label(pill, text="Connecting…", font=("Arial", 10), bg=SURFACE, fg=WARN); self.status_lbl.pack(side=tk.LEFT, padx=(4, 0))

        self.clock_lbl = tk.Label(top, text="--:--:--", font=("Courier", 12, "bold"), bg=SURFACE, fg=MUTED)
        self.clock_lbl.pack(side=tk.RIGHT, padx=14)
        self.msgs_lbl = tk.Label(top, text="0 msgs", font=("Courier", 9), bg=SURFACE, fg=MUTED)
        self.msgs_lbl.pack(side=tk.RIGHT, padx=4)

        # KPI strip
        kpis = tk.Frame(self.root, bg=BG); kpis.pack(fill=tk.X, padx=14, pady=(12, 0))
        self.kpi_total = self._kpi(kpis, "TOTAL EVENTS", "0", ACCENT)
        self.kpi_last = self._kpi(kpis, "LAST DELAY", "—", ACCENT2)
        self.kpi_avg = self._kpi(kpis, "AVG DELAY", "—", PURPLE)
        self.kpi_peak = self._kpi(kpis, "PEAK HOUR", "—", WARN)
        self.kpi_uptime = self._kpi(kpis, "UPTIME", "0s", MUTED)
        self.kpi_device = self._kpi(kpis, "LAST DEVICE", "—", ACCENT)

        # Virtual-sensor strip
        vs = tk.Frame(self.root, bg=BG); vs.pack(fill=tk.X, padx=14, pady=(8, 0))
        self.kpi_usage = self._kpi(vs, "USAGE INTENSITY  (rule sensor)", "—", MUTED)
        self.kpi_predict = self._kpi(vs, "NEXT-HOUR PREDICTION  (ML sensor)", "—", MUTED)
        self.kpi_motion = self._kpi(vs, "LIVE MOTION", "idle", MUTED)
        self.kpi_gas = self._kpi(vs, "GAS  (MQ-3)", "—", MUTED)

        # Gas alert banner (hidden until a gas alert fires)
        self.gas_banner = tk.Label(self.root, text="", font=("Arial", 12, "bold"),
                                   bg=ERROR, fg="#ffffff", pady=9)

        # Main area
        main = tk.Frame(self.root, bg=BG); main.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)
        self.main = main
        main.columnconfigure(0, weight=1); main.columnconfigure(1, weight=2); main.rowconfigure(0, weight=1)

        left = tk.Frame(main, bg=BG); left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(0, weight=3); left.rowconfigure(1, weight=1); left.columnconfigure(0, weight=1)

        feed_frame = tk.Frame(left, bg=SURFACE); feed_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        tk.Label(feed_frame, text="LIVE FEED", font=("Courier", 8, "bold"), bg=SURFACE, fg=MUTED, anchor="w").pack(fill=tk.X, padx=12, pady=(10, 2))
        self.feed = tk.Text(feed_frame, bg=SURFACE, fg=TEXT, font=("Courier", 10), bd=0, wrap=tk.WORD,
                            state="disabled", relief="flat", padx=10, pady=4, selectbackground=ACCENT2)
        self.feed.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 8))
        for tag, color in [("ts", MUTED), ("ok", ACCENT), ("warn", WARN), ("error", ERROR),
                           ("info", ACCENT2), ("dev", PURPLE), ("gold", GOLD)]:
            self.feed.tag_config(tag, foreground=color)

        ov = tk.Frame(left, bg=SURFACE2, padx=14, pady=10); ov.grid(row=1, column=0, sticky="nsew")
        tk.Label(ov, text="SYSTEM OVERVIEW", font=("Courier", 8, "bold"), bg=SURFACE2, fg=MUTED, anchor="w").pack(anchor="w")
        self.last_seen_lbl = tk.Label(ov, text="No events yet", font=("Arial", 13, "bold"), bg=SURFACE2, fg=TEXT); self.last_seen_lbl.pack(anchor="w")
        self.last_seen_ago = tk.Label(ov, text="", font=("Arial", 10), bg=SURFACE2, fg=MUTED); self.last_seen_ago.pack(anchor="w")
        self.overview_lbl = tk.Label(ov, text="Bins seen: —", font=("Courier", 9), bg=SURFACE2, fg=MUTED, justify="left", anchor="w"); self.overview_lbl.pack(anchor="w", pady=(6, 0))

        right = tk.Frame(main, bg=BG); right.grid(row=0, column=1, sticky="nsew")
        for i, w in enumerate((3, 2, 2, 2)):
            right.rowconfigure(i, weight=w)
        right.columnconfigure(0, weight=1)
        self.fig1, self.ax1 = self._chart_frame(right, 0, "DELAY BETWEEN EVENTS  (s)", 5.6, 2.1)
        self.canvas1 = self._embed(self.fig1, right, 0)
        self.fig2, self.ax2 = self._chart_frame(right, 1, "EVENTS / 10s BUCKET", 5.6, 1.5)
        self.canvas2 = self._embed(self.fig2, right, 1)
        self.fig3, self.ax3 = self._chart_frame(right, 2, "USAGE BY HOUR OF DAY  (today)", 5.6, 1.5)
        self.canvas3 = self._embed(self.fig3, right, 2)
        self.fig4, self.ax4 = self._chart_frame(right, 3, "TOTAL EVENTS PER BIN", 5.6, 1.5)
        self.canvas4 = self._embed(self.fig4, right, 3)

    def _kpi(self, parent, label, value, color):
        f = tk.Frame(parent, bg=SURFACE2, padx=12, pady=8)
        f.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=(0, 8))
        tk.Label(f, text=label, font=("Courier", 7, "bold"), bg=SURFACE2, fg=MUTED).pack(anchor="w")
        lbl = tk.Label(f, text=value, font=("Arial", 20, "bold"), bg=SURFACE2, fg=color); lbl.pack(anchor="w")
        return lbl

    def _chart_frame(self, parent, row, title, w, h):
        frame = tk.Frame(parent, bg=SURFACE)
        frame.grid(row=row, column=0, sticky="nsew", pady=(0, 6) if row < 3 else 0)
        tk.Label(frame, text=title, font=("Courier", 8, "bold"), bg=SURFACE, fg=MUTED, anchor="w").pack(fill=tk.X, padx=12, pady=(8, 0))
        fig, ax = plt.subplots(figsize=(w, h)); fig.patch.set_facecolor(BG); ax.set_facecolor(SURFACE); ax.grid(True)
        fig.tight_layout(pad=1.1)
        return fig, ax

    def _embed(self, fig, parent, row):
        frame = parent.grid_slaves(row=row, column=0)[0]
        canvas = FigureCanvasTkAgg(fig, master=frame); canvas.draw()
        w = canvas.get_tk_widget(); w.configure(bg=BG, highlightthickness=0)
        w.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 6))
        return canvas

    # ══════════════════════════════════════════════ feed ═════════════════════
    def _log(self, text, tag="info"):
        ts = time.strftime("%H:%M:%S")
        self.feed.config(state="normal")
        self.feed.insert(tk.END, f"[{ts}] ", "ts")
        self.feed.insert(tk.END, text + "\n", tag)
        # cap feed length to keep it snappy
        if int(self.feed.index("end-1c").split(".")[0]) > 500:
            self.feed.delete("1.0", "200.0")
        self.feed.see(tk.END)
        self.feed.config(state="disabled")

    # ══════════════════════════════════════════════ source ══════════════════
    def _setup_source(self):
        if self.demo:
            self._start_demo()
            return
        self._setup_mqtt()

    def _setup_mqtt(self):
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except (AttributeError, TypeError):
            self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        def connect():
            for attempt in range(1, 6):
                try:
                    self.q.put({"t": "log", "v": f"Connecting to {self.broker}:{self.port} (attempt {attempt}/5)…", "s": "warn"})
                    self.client.connect(self.broker, self.port, keepalive=60)
                    self.client.loop_start()
                    return
                except Exception as e:
                    self.q.put({"t": "log", "v": f"Failed: {e}. Retry in 5s…", "s": "error"})
                    time.sleep(5)
            self.q.put({"t": "conn", "v": "failed"})

        threading.Thread(target=connect, daemon=True).start()

    def _on_connect(self, client, ud, flags, rc, props=None):
        if rc == 0:
            self.q.put({"t": "conn", "v": "ok"})
            client.subscribe(self.topic, qos=1)
        else:
            self.q.put({"t": "log", "v": f"Refused (rc={rc})", "s": "error"})

    def _on_disconnect(self, client, ud, *a):
        self.q.put({"t": "conn", "v": "lost"})

    def _on_message(self, client, ud, msg):
        try:
            payload = msg.payload.decode("utf-8", errors="replace")
        except Exception:
            payload = str(msg.payload)
        self.q.put({"t": "data", "topic": msg.topic, "v": payload})

    # ── Demo feeder: synthesises a realistic stream with no broker ────────────
    def _start_demo(self):
        self.q.put({"t": "conn", "v": "demo"})

        def feed():
            rng = random.Random()
            bins = [("bin-01", "pir-01", "Kitchen Corner", 1.0),
                    ("bin-02", "pir-02", "Entrance", 0.55)]
            seq = {b[0]: 0 for b in bins}
            for b in bins:
                self.q.put({"t": "data", "topic": f"smartbin/{b[0]}/{b[1]}/online", "v": "true"})
            n = 0
            while not self._stop:
                hour = datetime.now().hour
                base = 6 if 11 <= hour <= 14 else 4 if 8 <= hour <= 18 else 2 if 19 <= hour <= 21 else 1
                b = rng.choices(bins, weights=[bb[3] for bb in bins])[0]
                bin_id, dev, locname, _ = b
                seq[bin_id] += 1; n += 1

                self.q.put({"t": "data", "topic": f"smartbin/{bin_id}/{dev}/motion", "v": "detected"})
                ev = {"name": "MotionDetected", "bin_id": bin_id, "device_id": dev,
                      "eventNumber": seq[bin_id], "madeBySensor": dev,
                      "location": {"@type": "Place", "name": locname},
                      "cpu_temp_c": round(rng.uniform(45, 60), 1)}
                self.q.put({"t": "data", "topic": f"smartbin/{bin_id}/{dev}/events", "v": json.dumps(ev)})
                time.sleep(rng.uniform(0.15, 0.5))
                self.q.put({"t": "data", "topic": f"smartbin/{bin_id}/{dev}/motion", "v": "clear"})

                if n % 4 == 0:
                    lvl = rng.choices(["idle", "low", "medium", "high"], weights=[1, 3, 3, 2])[0]
                    self.q.put({"t": "data", "topic": f"smartbin/{bin_id}/usage",
                                "v": json.dumps({"usage_level": lvl, "event_count": rng.randint(0, 25), "window_minutes": 10})})
                if n % 6 == 0:
                    pred = rng.choice(["busy", "quiet"])
                    self.q.put({"t": "data", "topic": f"smartbin/{bin_id}/prediction",
                                "v": json.dumps({"prediction": pred, "confidence": round(rng.uniform(0.62, 0.98), 2)})})
                if n % 19 == 0:
                    self.q.put({"t": "data", "topic": f"smartbin/{bin_id}/{dev}/gas", "v": "detected"})
                    time.sleep(rng.uniform(1.2, 2.4))
                    self.q.put({"t": "data", "topic": f"smartbin/{bin_id}/{dev}/gas", "v": "clear"})

                time.sleep(max(0.25, rng.expovariate(base / 3.0)))

        threading.Thread(target=feed, daemon=True).start()

    # ══════════════════════════════════════════════ poll ═════════════════════
    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item["t"] == "log":
                    self._log(item["v"], item.get("s", "info"))
                elif item["t"] == "conn":
                    if item["v"] == "ok":
                        self._set_status("● Connected", ACCENT)
                        self._log(f"✓ Connected — subscribed to {self.topic}", "ok")
                    elif item["v"] == "demo":
                        self._set_status("● Demo Mode", PURPLE)
                        self._log("Demo mode — synthesising live traffic (no broker)", "dev")
                    else:
                        self._set_status("● Disconnected", ERROR)
                        self._log("Connection lost.", "error")
                elif item["t"] == "data":
                    self.msg_count += 1
                    self._route(item["topic"], item["v"])
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _set_status(self, text, color):
        self.dot.config(fg=color); self.status_lbl.config(text=text, fg=color)

    # ══════════════════════════════════════════════ routing ══════════════════
    def _route(self, topic, payload):
        if topic.endswith("/events"):
            self._handle_event(topic, payload)
        elif topic.endswith("/motion"):
            self._handle_motion(payload)
        elif topic.endswith("/gas"):
            self._handle_gas(topic, payload)
        elif topic.endswith("/online"):
            self._handle_online(topic, payload)
        elif topic.endswith("/usage"):
            self._handle_usage(payload)
        elif topic.endswith("/prediction"):
            self._handle_prediction(payload)
        elif topic.endswith("/status"):
            pass  # status reflected via events/motion already

    def _handle_motion(self, payload):
        state = payload.strip().strip('"')
        if state in ("detected", "clear"):
            self.motion_state = "ACTIVE" if state == "detected" else "idle"
            color = ERROR if state == "detected" else MUTED
            self.kpi_motion.config(text=self.motion_state, fg=color)

    def _handle_gas(self, topic, payload):
        state = payload.strip().strip('"')
        parts = topic.split("/")
        bin_id = parts[1] if len(parts) > 1 else "?"
        dev = parts[2] if len(parts) > 2 else "?"
        if state == "detected":
            if topic not in self.gas_active:
                self._log(f"⚠ GAS ALERT  bin={bin_id} device={dev}", "error")
            self.gas_active.add(topic)
        else:
            if topic in self.gas_active:
                self._log(f"gas cleared  bin={bin_id}", "ok")
            self.gas_active.discard(topic)
        self._refresh_gas()

    def _refresh_gas(self):
        if self.gas_active:
            devs = ", ".join(sorted({t.split("/")[1] for t in self.gas_active}))
            self.gas_banner.config(text=f"⚠   GAS DETECTED — {devs}   —   ventilate and check the bin")
            if not self.gas_banner.winfo_ismapped():
                self.gas_banner.pack(fill=tk.X, padx=14, pady=(8, 0), before=self.main)
            self.kpi_gas.config(text="ALERT", fg=ERROR)
        else:
            if self.gas_banner.winfo_ismapped():
                self.gas_banner.pack_forget()
            self.kpi_gas.config(text="CLEAR", fg=ACCENT)

    def _handle_online(self, topic, payload):
        state = payload.strip().strip('"').lower()
        parts = topic.split("/")
        dev = parts[2] if len(parts) > 2 else parts[-1]
        was = self.online.get(dev)
        self.online[dev] = (state == "true")
        if was != self.online[dev]:
            self._log(f"{dev} is {'ONLINE' if self.online[dev] else 'OFFLINE'}",
                      "ok" if self.online[dev] else "error")
        self._refresh_overview()

    def _handle_usage(self, payload):
        try:
            d = json.loads(payload)
            level = d.get("usage_level", "—")
            self.usage_level = level
            self.kpi_usage.config(text=level.upper(), fg=LEVEL_COLORS.get(level, MUTED))
            self._log(f"usage intensity → {level} ({d.get('event_count', '?')} in {d.get('window_minutes', '?')}min)", "info")
        except json.JSONDecodeError:
            pass

    def _handle_prediction(self, payload):
        try:
            d = json.loads(payload)
            pred = d.get("prediction", "—")
            conf = d.get("confidence")
            self.prediction = pred
            txt = f"{pred.upper()}" + (f"  {conf*100:.0f}%" if isinstance(conf, (int, float)) else "")
            self.kpi_predict.config(text=txt, fg=PREDICT_COLORS.get(pred, MUTED))
            self._log(f"ML prediction → next hour {pred} (conf {conf})", "dev")
        except (json.JSONDecodeError, AttributeError):
            pass

    def _handle_event(self, topic, payload):
        now = time.time()
        self.counter += 1
        self.kpi_total.config(text=str(self.counter))

        device, location, bin_id = "unknown", "", topic.split("/")[1] if "/" in topic else "?"
        cpu_temp = None
        try:
            d = json.loads(payload)
            device = d.get("device_id") or d.get("madeBySensor", "unknown")
            bin_id = d.get("bin_id", bin_id)
            loc = d.get("location")
            location = loc.get("name") if isinstance(loc, dict) else (loc or "")
            cpu_temp = d.get("cpu_temp_c")
            loc_str = f"  loc={location}" if location else ""
            temp_str = f"  cpu={cpu_temp}°C" if cpu_temp is not None else ""
            self._log(f"bin={bin_id}  device={device}  #{d.get('eventNumber', self.counter)}{loc_str}{temp_str}", "dev")
        except json.JSONDecodeError:
            self._log(payload, "ok")

        self.kpi_device.config(text=str(device)[:14])
        self.per_bin[bin_id] += 1
        self._refresh_overview()

        hr = datetime.now().hour
        self.hourly[hr] += 1
        self.events_this_hour += 1
        self.kpi_peak.config(text=f"{self.hourly.index(max(self.hourly)):02d}:00")

        delay = (now - self.last_time) if self.last_time is not None else 0.0
        self.last_time = now
        self.last_seen_lbl.config(text=time.strftime("%H:%M:%S"))

        if self.counter > 1:
            self.delays.append(delay); self.x_events.append(self.counter)
            self.kpi_last.config(text=f"{delay:.1f}s")
            self.kpi_avg.config(text=f"{sum(self.delays)/len(self.delays):.1f}s")
            self._update_line()

        self._bucket_n += 1
        if now - self._bucket_t >= 10:
            self.bucket_counts.append(self._bucket_n); self._bucket_n = 0; self._bucket_t = now
            self._update_bar()
        self._update_hourly()
        self._update_perbin()

        self.dot.config(fg="#ffffff"); self.root.after(150, lambda: self.dot.config(fg=PURPLE if self.demo else ACCENT))

        self.saved_data.append([time.strftime("%H:%M:%S"), self.counter, round(delay, 3), bin_id, device, payload])
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                json.dump({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "seq": self.counter,
                           "bin_id": bin_id, "device_id": device, "location": location,
                           "delay_s": round(delay, 3), "cpu_temp_c": cpu_temp, "raw": payload}, f)
                f.write("\n")
        except Exception as e:
            self._log(f"JSON log error: {e}", "error")

    def _refresh_overview(self):
        bins = "  ".join(f"{b}={n}" for b, n in sorted(self.per_bin.items())) or "—"
        on = sorted(d for d, o in self.online.items() if o)
        off = sorted(d for d, o in self.online.items() if not o)
        line = f"Bins seen: {bins}\nOnline: {', '.join(on) or '—'}"
        if off:
            line += f"\nOffline: {', '.join(off)}"
        self.overview_lbl.config(text=line)

    # ══════════════════════════════════════════════ ticker ═══════════════════
    def _tick(self):
        self.clock_lbl.config(text=time.strftime("%H:%M:%S"))
        self.msgs_lbl.config(text=f"{self.msg_count} msgs")
        elapsed = int(time.time() - self.session_start)
        h, r = divmod(elapsed, 3600); m, s = divmod(r, 60)
        self.kpi_uptime.config(text=f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s"))
        if self.last_time:
            self.last_seen_ago.config(text=f"{int(time.time() - self.last_time)}s ago")
        if datetime.now().hour != self._hour_mark:
            self.events_this_hour = 0; self._hour_mark = datetime.now().hour
        if self.events_this_hour >= ALERT_THRESH and not self.gas_active:
            self.gas_banner.config(text=f"⚠   {self.events_this_hour} events this hour — bin may need checking",
                                   bg=WARN)
            if not self.gas_banner.winfo_ismapped():
                self.gas_banner.pack(fill=tk.X, padx=14, pady=(8, 0), before=self.main)
        elif not self.gas_active and self.gas_banner.cget("bg") == WARN and self.gas_banner.winfo_ismapped():
            self.gas_banner.pack_forget()
        # keep gas banner red when a real gas alert is active
        if self.gas_active:
            self.gas_banner.config(bg=ERROR)
        self.root.after(1000, self._tick)

    # ══════════════════════════════════════════════ charts ═══════════════════
    def _update_line(self):
        xs, ys = list(self.x_events), list(self.delays)
        self.ax1.cla(); self.ax1.set_facecolor(SURFACE); self.ax1.grid(True)
        self.ax1.set_xlabel("Event #", fontsize=8); self.ax1.set_ylabel("Delay (s)", fontsize=8)
        if xs:
            self.ax1.plot(xs, ys, color=ACCENT, lw=2)
            self.ax1.fill_between(xs, ys, alpha=0.12, color=ACCENT)
            self.ax1.plot(xs[-1], ys[-1], "o", color=ACCENT, ms=5)
            self.ax1.set_xlim(min(xs) - 0.5, max(xs) + 0.5)
            self.ax1.set_ylim(0, (max(ys) or 1) * 1.15 + 0.5)
        self.fig1.tight_layout(pad=1.1); self.canvas1.draw_idle()

    def _update_bar(self):
        bd = list(self.bucket_counts)
        if not bd:
            return
        self.ax2.cla(); self.ax2.set_facecolor(SURFACE); self.ax2.grid(True, axis="y")
        self.ax2.set_xlabel("Bucket (old → new)", fontsize=8); self.ax2.set_ylabel("Count", fontsize=8)
        colors = [ACCENT if i == len(bd) - 1 else ACCENT2 for i in range(len(bd))]
        self.ax2.bar(range(len(bd)), bd, color=colors, width=0.6)
        self.ax2.set_xlim(-0.5, max(len(bd), 5) - 0.5); self.ax2.set_ylim(0, max(bd) * 1.3 + 1)
        self.fig2.tight_layout(pad=1.1); self.canvas2.draw_idle()

    def _update_hourly(self):
        self.ax3.cla(); self.ax3.set_facecolor(SURFACE); self.ax3.grid(True, axis="y")
        self.ax3.set_xlabel("Hour of day", fontsize=8); self.ax3.set_ylabel("Events", fontsize=8)
        cur = datetime.now().hour
        colors = [ACCENT if i == cur else ACCENT2 for i in range(24)]
        self.ax3.bar(range(24), self.hourly, color=colors, width=0.7)
        self.ax3.set_xlim(-0.5, 23.5); self.ax3.set_xticks(range(0, 24, 2))
        self.ax3.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)], fontsize=7)
        self.ax3.set_ylim(0, (max(self.hourly) or 1) * 1.3 + 1)
        self.fig3.tight_layout(pad=1.1); self.canvas3.draw_idle()

    def _update_perbin(self):
        items = sorted(self.per_bin.items())
        if not items:
            return
        labels = [b for b, _ in items]
        vals = [n for _, n in items]
        palette = [ACCENT2, PURPLE, ACCENT, WARN, GOLD]
        colors = [palette[i % len(palette)] for i in range(len(vals))]
        self.ax4.cla(); self.ax4.set_facecolor(SURFACE); self.ax4.grid(True, axis="x")
        self.ax4.barh(range(len(vals)), vals, color=colors, height=0.55)
        self.ax4.set_yticks(range(len(labels)))
        self.ax4.set_yticklabels(labels, fontsize=8)
        self.ax4.set_xlabel("Total events", fontsize=8)
        self.ax4.set_xlim(0, (max(vals) or 1) * 1.18 + 1)
        for i, v in enumerate(vals):
            self.ax4.text(v + max(vals) * 0.02 + 0.1, i, str(v), va="center", fontsize=8, color=TEXT)
        self.fig4.tight_layout(pad=1.1); self.canvas4.draw_idle()

    # ══════════════════════════════════════════════ export ═══════════════════
    def _save_csv(self):
        if not self.saved_data:
            messagebox.showinfo("No Data", "No events recorded yet."); return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv"), ("All", "*.*")],
                                            title="Export sensor data")
        if path:
            try:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["Time", "Seq", "Delay_s", "Bin", "Device", "Raw_JSON"])
                    w.writerows(self.saved_data)
                messagebox.showinfo("Saved", f"Exported to:\n{path}")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def on_close(self):
        self._stop = True
        try:
            if not self.demo:
                self.client.loop_stop(); self.client.disconnect()
        except Exception:
            pass
        self.root.quit(); self.root.destroy()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Smart Waste Bin live dashboard")
    p.add_argument("--broker", default=MQTT_BROKER)
    p.add_argument("--port", type=int, default=MQTT_PORT)
    p.add_argument("--topic", default=MQTT_TOPIC)
    p.add_argument("--demo", action="store_true",
                   help="Animate the dashboard from synthetic data (no broker needed)")
    args = p.parse_args()

    root = tk.Tk()
    app = Dashboard(root, args.broker, args.port, args.topic, demo=args.demo)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
