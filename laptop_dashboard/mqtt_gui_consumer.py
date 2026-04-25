import tkinter as tk
from tkinter import filedialog, messagebox
import paho.mqtt.client as mqtt
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import time
import queue
import csv
import json
import threading
import argparse
from collections import deque
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
MQTT_BROKER   = "broker.hivemq.com"
MQTT_PORT     = 1883
MQTT_TOPIC    = "wastebin/motion"
LOG_FILE      = "events_log.json"
ALERT_THRESH  = 10   # events/hour before "needs checking" alert

# ── Palette ───────────────────────────────────────────────────────────────────
BG       = "#0d1117"
SURFACE  = "#161b22"
SURFACE2 = "#1c2128"
BORDER   = "#30363d"
ACCENT   = "#00d084"
ACCENT2  = "#58a6ff"
PURPLE   = "#d2a8ff"
TEXT     = "#e6edf3"
MUTED    = "#8b949e"
WARN     = "#f0883e"
ERROR    = "#ff7b72"

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor":   SURFACE,
    "axes.edgecolor":   BORDER,
    "axes.labelcolor":  MUTED,
    "xtick.color":      MUTED,
    "ytick.color":      MUTED,
    "text.color":       TEXT,
    "grid.color":       BORDER,
    "grid.linestyle":   "--",
    "grid.alpha":       0.4,
})


class Dashboard:
    def __init__(self, root, broker=MQTT_BROKER, port=MQTT_PORT, topic=MQTT_TOPIC):
        self.root   = root
        self.broker = broker
        self.port   = port
        self.topic  = topic

        self.root.title("Smart Waste Bin  ·  Live Dashboard")
        self.root.geometry("1100x780")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        # ── Data stores ───────────────────────────────────────────────────────
        self.q              = queue.Queue()
        self.saved_data     = []
        self.last_time      = None
        self.counter        = 0
        self.session_start  = time.time()

        self.delays         = deque(maxlen=60)   # inter-event delays
        self.x_events       = deque(maxlen=60)   # event indices for line chart
        self.bucket_counts  = deque(maxlen=20)   # events per 10-s bucket
        self._bucket_t      = time.time()
        self._bucket_n      = 0

        self.hourly         = [0] * 24            # events per hour of day
        self.events_this_hour = 0
        self._hour_mark     = datetime.now().hour

        self._build_ui()
        self._setup_mqtt()
        self._poll()
        self._tick()   # 1-s uptime/alert ticker

    # ══════════════════════════════════════════════════════════════════════════
    # UI
    # ══════════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        # ── Top bar ───────────────────────────────────────────────────────────
        topbar = tk.Frame(self.root, bg=SURFACE, height=54)
        topbar.pack(fill=tk.X)
        topbar.pack_propagate(False)

        tk.Label(topbar, text="🗑", font=("Arial", 20), bg=SURFACE, fg=ACCENT
                 ).pack(side=tk.LEFT, padx=(16, 6))
        tk.Label(topbar, text="Smart Waste Bin", font=("Arial", 14, "bold"),
                 bg=SURFACE, fg=TEXT).pack(side=tk.LEFT)
        tk.Label(topbar, text="Live Dashboard", font=("Arial", 10),
                 bg=SURFACE, fg=MUTED).pack(side=tk.LEFT, padx=(6, 0))

        # Status pill
        pill = tk.Frame(topbar, bg=SURFACE)
        pill.pack(side=tk.RIGHT, padx=16)
        self.dot        = tk.Label(pill, text="●", font=("Arial", 13), bg=SURFACE, fg=WARN)
        self.dot.pack(side=tk.LEFT)
        self.status_lbl = tk.Label(pill, text="Connecting…", font=("Arial", 10),
                                   bg=SURFACE, fg=WARN)
        self.status_lbl.pack(side=tk.LEFT, padx=(4, 0))

        # Alert badge
        self.alert_lbl = tk.Label(topbar, text="", font=("Arial", 10, "bold"),
                                  bg=WARN, fg="#0d1117", padx=10, pady=3)

        # Export button
        tk.Button(topbar, text="↓  Export CSV", font=("Arial", 10, "bold"),
                  bg=ACCENT2, fg="#0d1117", relief="flat", padx=12, pady=3,
                  cursor="hand2", command=self._save_csv,
                  activebackground="#79c0ff"
                  ).pack(side=tk.RIGHT, padx=(0, 10), pady=10)

        # ── KPI strip ─────────────────────────────────────────────────────────
        kpi_row = tk.Frame(self.root, bg=BG)
        kpi_row.pack(fill=tk.X, padx=14, pady=(12, 0))

        self.kpi_total   = self._kpi(kpi_row, "TOTAL EVENTS",      "0",  ACCENT)
        self.kpi_last    = self._kpi(kpi_row, "LAST DELAY",         "—",  ACCENT2)
        self.kpi_avg     = self._kpi(kpi_row, "AVG DELAY",          "—",  PURPLE)
        self.kpi_peak    = self._kpi(kpi_row, "PEAK HOUR",          "—",  WARN)
        self.kpi_uptime  = self._kpi(kpi_row, "UPTIME",             "0s", MUTED)
        self.kpi_device  = self._kpi(kpi_row, "LAST DEVICE",        "—",  ACCENT)

        # ── Main area ─────────────────────────────────────────────────────────
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)

        # ── Left: feed + last-seen ─────────────────────────────────────────
        left = tk.Frame(main, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(0, weight=3)
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        feed_frame = tk.Frame(left, bg=SURFACE)
        feed_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        tk.Label(feed_frame, text="LIVE FEED", font=("Courier", 8, "bold"),
                 bg=SURFACE, fg=MUTED, anchor="w").pack(fill=tk.X, padx=12, pady=(10, 2))
        self.feed = tk.Text(feed_frame, bg=SURFACE, fg=TEXT,
                            font=("Courier", 10), bd=0, wrap=tk.WORD,
                            state="disabled", relief="flat", padx=10, pady=4,
                            selectbackground=ACCENT2)
        self.feed.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 8))
        for tag, color in [("ts", MUTED), ("ok", ACCENT), ("warn", WARN),
                           ("error", ERROR), ("info", ACCENT2), ("dev", PURPLE)]:
            self.feed.tag_config(tag, foreground=color)

        # Last-seen card
        ls_frame = tk.Frame(left, bg=SURFACE2, padx=14, pady=10)
        ls_frame.grid(row=1, column=0, sticky="nsew")
        tk.Label(ls_frame, text="LAST ACTIVITY", font=("Courier", 8, "bold"),
                 bg=SURFACE2, fg=MUTED, anchor="w").pack(anchor="w")
        self.last_seen_lbl = tk.Label(ls_frame, text="No events yet",
                                      font=("Arial", 13, "bold"),
                                      bg=SURFACE2, fg=TEXT)
        self.last_seen_lbl.pack(anchor="w")
        self.last_seen_ago = tk.Label(ls_frame, text="",
                                      font=("Arial", 10), bg=SURFACE2, fg=MUTED)
        self.last_seen_ago.pack(anchor="w")

        # ── Right: 3 charts ────────────────────────────────────────────────
        right = tk.Frame(main, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=3)
        right.rowconfigure(1, weight=2)
        right.rowconfigure(2, weight=2)
        right.columnconfigure(0, weight=1)

        # Chart 1 — delay line
        self.fig1, self.ax1 = self._chart_frame(right, 0, "DELAY BETWEEN EVENTS  (s)", 5.6, 2.4)
        self.canvas1 = self._embed_chart(self.fig1, right, 0)

        # Chart 2 — bucket bar
        self.fig2, self.ax2 = self._chart_frame(right, 1, "EVENTS / 10s BUCKET", 5.6, 1.8)
        self.canvas2 = self._embed_chart(self.fig2, right, 1)

        # Chart 3 — hourly heatmap bar
        self.fig3, self.ax3 = self._chart_frame(right, 2, "USAGE BY HOUR OF DAY  (today)", 5.6, 1.8)
        self.canvas3 = self._embed_chart(self.fig3, right, 2)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _kpi(self, parent, label, value, color):
        f = tk.Frame(parent, bg=SURFACE2, padx=12, pady=8)
        f.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=(0, 8))
        tk.Label(f, text=label, font=("Courier", 7, "bold"),
                 bg=SURFACE2, fg=MUTED).pack(anchor="w")
        lbl = tk.Label(f, text=value, font=("Arial", 20, "bold"),
                       bg=SURFACE2, fg=color)
        lbl.pack(anchor="w")
        return lbl

    def _chart_frame(self, parent, row, title, w, h):
        frame = tk.Frame(parent, bg=SURFACE)
        frame.grid(row=row, column=0, sticky="nsew",
                   pady=(0, 6) if row < 2 else 0)
        tk.Label(frame, text=title, font=("Courier", 8, "bold"),
                 bg=SURFACE, fg=MUTED, anchor="w").pack(fill=tk.X, padx=12, pady=(8, 0))
        fig, ax = plt.subplots(figsize=(w, h))
        fig.patch.set_facecolor(BG)
        ax.set_facecolor(SURFACE)
        ax.grid(True)
        fig.tight_layout(pad=1.1)
        frame._fig_ref = (fig, ax, frame)
        return fig, ax

    def _embed_chart(self, fig, parent, row):
        frame = parent.grid_slaves(row=row, column=0)[0]
        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        w = canvas.get_tk_widget()
        w.configure(bg=BG, highlightthickness=0)
        w.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 6))
        return canvas

    # ══════════════════════════════════════════════════════════════════════════
    # Feed
    # ══════════════════════════════════════════════════════════════════════════
    def _log(self, text, tag="info"):
        ts = time.strftime("%H:%M:%S")
        self.feed.config(state="normal")
        self.feed.insert(tk.END, f"[{ts}] ", "ts")
        self.feed.insert(tk.END, text + "\n", tag)
        self.feed.see(tk.END)
        self.feed.config(state="disabled")

    # ══════════════════════════════════════════════════════════════════════════
    # MQTT
    # ══════════════════════════════════════════════════════════════════════════
    def _setup_mqtt(self):
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:
            self.client = mqtt.Client()
        self.client.on_connect    = self._on_connect
        self.client.on_message    = self._on_message
        self.client.on_disconnect = self._on_disconnect

        def _connect():
            for attempt in range(1, 6):
                try:
                    self.q.put({"t": "log", "v": f"Connecting to {self.broker}:{self.port}  (attempt {attempt}/5)…", "s": "warn"})
                    self.client.connect(self.broker, self.port, keepalive=60)
                    self.client.loop_start()
                    return
                except Exception as e:
                    self.q.put({"t": "log", "v": f"Failed: {e}. Retry in 5s…", "s": "error"})
                    time.sleep(5)
            self.q.put({"t": "log", "v": "Could not connect after 5 attempts.", "s": "error"})
            self.q.put({"t": "conn", "v": "failed"})

        threading.Thread(target=_connect, daemon=True).start()

    def _on_connect(self, client, ud, flags, rc, props=None):
        if rc == 0:
            self.q.put({"t": "conn", "v": "ok"})
            client.subscribe(self.topic)
        else:
            self.q.put({"t": "log", "v": f"Refused (rc={rc})", "s": "error"})

    def _on_disconnect(self, client, ud, flags, rc, props=None):
        self.q.put({"t": "conn", "v": "lost"})

    def _on_message(self, client, ud, msg):
        try:
            payload = msg.payload.decode("utf-8", errors="replace")
        except Exception:
            payload = str(msg.payload)
        self.q.put({"t": "data", "v": payload})

    # ══════════════════════════════════════════════════════════════════════════
    # Polling loop
    # ══════════════════════════════════════════════════════════════════════════
    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                tt = item["t"]
                if tt == "log":
                    self._log(item["v"], item.get("s", "info"))
                elif tt == "conn":
                    v = item["v"]
                    if v == "ok":
                        self._set_status("● Connected", ACCENT)
                        self._log(f"✓ Connected — subscribed to: {self.topic}", "ok")
                    else:
                        self._set_status("● Disconnected", ERROR)
                        self._log("Connection lost.", "error")
                elif tt == "data":
                    self._handle(item["v"])
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _set_status(self, text, color):
        self.dot.config(fg=color)
        self.status_lbl.config(text=text, fg=color)

    # ══════════════════════════════════════════════════════════════════════════
    # 1-second ticker — uptime, last-seen ago, hourly bucket reset
    # ══════════════════════════════════════════════════════════════════════════
    def _tick(self):
        # Uptime
        elapsed = int(time.time() - self.session_start)
        h, r = divmod(elapsed, 3600)
        m, s = divmod(r, 60)
        uptime_str = f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")
        self.kpi_uptime.config(text=uptime_str)

        # Last seen ago
        if self.last_time:
            ago = int(time.time() - self.last_time)
            self.last_seen_ago.config(text=f"{ago}s ago")

        # Hourly bucket reset
        now_hour = datetime.now().hour
        if now_hour != self._hour_mark:
            self.events_this_hour = 0
            self._hour_mark = now_hour

        # Alert check
        if self.events_this_hour >= ALERT_THRESH:
            self.alert_lbl.config(text=f"⚠  {self.events_this_hour} events this hour — bin needs checking")
            self.alert_lbl.pack(side=tk.LEFT, padx=10)
        else:
            self.alert_lbl.pack_forget()

        self.root.after(1000, self._tick)

    # ══════════════════════════════════════════════════════════════════════════
    # Data handler
    # ══════════════════════════════════════════════════════════════════════════
    def _handle(self, payload):
        now = time.time()
        self.counter += 1
        self.kpi_total.config(text=str(self.counter))

        # ── Parse JSON ────────────────────────────────────────────────────────
        device   = "unknown"
        seq      = self.counter
        location = ""
        uptime_s = None
        cpu_temp = None

        try:
            d        = json.loads(payload)
            device   = d.get("device_id", "unknown")
            seq      = d.get("seq", self.counter)
            location = d.get("location", "")
            uptime_s = d.get("uptime_s")
            cpu_temp = d.get("cpu_temp_c")

            loc_str  = f"  loc={location}" if location else ""
            temp_str = f"  cpu={cpu_temp}°C" if cpu_temp is not None else ""
            self._log(f"device={device}  seq={seq}{loc_str}{temp_str}", "dev")
        except json.JSONDecodeError:
            self._log(payload, "ok")

        self.kpi_device.config(text=str(device)[:14])

        # ── Hourly stats ──────────────────────────────────────────────────────
        hr = datetime.now().hour
        self.hourly[hr] += 1
        self.events_this_hour += 1
        peak_hr = self.hourly.index(max(self.hourly))
        self.kpi_peak.config(text=f"{peak_hr:02d}:00")

        # ── Inter-event delay ─────────────────────────────────────────────────
        delay = 0.0
        if self.last_time is not None:
            delay = now - self.last_time
        self.last_time = now

        self.last_seen_lbl.config(text=time.strftime("%H:%M:%S"))

        if self.counter > 1:
            self.delays.append(delay)
            self.x_events.append(self.counter)
            self.kpi_last.config(text=f"{delay:.1f}s")
            avg = sum(self.delays) / len(self.delays)
            self.kpi_avg.config(text=f"{avg:.1f}s")
            self._update_line()

        # ── 10-s bucket ───────────────────────────────────────────────────────
        self._bucket_n += 1
        if now - self._bucket_t >= 10:
            self.bucket_counts.append(self._bucket_n)
            self._bucket_n = 0
            self._bucket_t = now
            self._update_bar()

        # ── Hourly chart ──────────────────────────────────────────────────────
        self._update_hourly()

        # ── Pulse ─────────────────────────────────────────────────────────────
        self.dot.config(fg="#ffffff")
        self.root.after(150, lambda: self.dot.config(fg=ACCENT))

        # ── Persist to CSV + JSONL ────────────────────────────────────────────
        ts_str = time.strftime("%H:%M:%S")
        self.saved_data.append([ts_str, self.counter, round(delay, 3), payload])

        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                json.dump({
                    "time":        time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "seq":         self.counter,
                    "device_id":   device,
                    "location":    location,
                    "delay_s":     round(delay, 3),
                    "uptime_s":    uptime_s,
                    "cpu_temp_c":  cpu_temp,
                    "raw":         payload
                }, f)
                f.write("\n")
        except Exception as e:
            self._log(f"JSON log error: {e}", "error")

    # ══════════════════════════════════════════════════════════════════════════
    # Charts
    # ══════════════════════════════════════════════════════════════════════════
    def _update_line(self):
        xs = list(self.x_events)
        ys = list(self.delays)
        self.ax1.cla()
        self.ax1.set_facecolor(SURFACE)
        self.ax1.set_xlabel("Event #", fontsize=8)
        self.ax1.set_ylabel("Delay (s)", fontsize=8)
        self.ax1.grid(True)
        if xs:
            self.ax1.plot(xs, ys, color=ACCENT, lw=2)
            self.ax1.fill_between(xs, ys, alpha=0.12, color=ACCENT)
            self.ax1.plot(xs[-1], ys[-1], "o", color=ACCENT, ms=5)
            pad = max(ys) * 0.15 if max(ys) > 0 else 1
            self.ax1.set_xlim(min(xs) - 0.5, max(xs) + 0.5)
            self.ax1.set_ylim(0, max(ys) + pad)
        self.fig1.tight_layout(pad=1.1)
        self.canvas1.draw_idle()

    def _update_bar(self):
        bd = list(self.bucket_counts)
        if not bd:
            return
        self.ax2.cla()
        self.ax2.set_facecolor(SURFACE)
        self.ax2.set_xlabel("Bucket (oldest → newest)", fontsize=8)
        self.ax2.set_ylabel("Count", fontsize=8)
        self.ax2.grid(True, axis="y")
        colors = [ACCENT if i == len(bd) - 1 else ACCENT2 for i in range(len(bd))]
        self.ax2.bar(range(len(bd)), bd, color=colors, width=0.6)
        self.ax2.set_xlim(-0.5, max(len(bd), 5) - 0.5)
        self.ax2.set_ylim(0, max(bd) * 1.3 + 1)
        self.fig2.tight_layout(pad=1.1)
        self.canvas2.draw_idle()

    def _update_hourly(self):
        self.ax3.cla()
        self.ax3.set_facecolor(SURFACE)
        self.ax3.set_xlabel("Hour of day", fontsize=8)
        self.ax3.set_ylabel("Events", fontsize=8)
        self.ax3.grid(True, axis="y")
        current_hr = datetime.now().hour
        colors = [ACCENT if i == current_hr else ACCENT2 for i in range(24)]
        self.ax3.bar(range(24), self.hourly, color=colors, width=0.7)
        self.ax3.set_xlim(-0.5, 23.5)
        self.ax3.set_xticks(range(0, 24, 2))
        self.ax3.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)], fontsize=7)
        peak = max(self.hourly) if max(self.hourly) > 0 else 1
        self.ax3.set_ylim(0, peak * 1.3 + 1)
        self.fig3.tight_layout(pad=1.1)
        self.canvas3.draw_idle()

    # ══════════════════════════════════════════════════════════════════════════
    # Save CSV
    # ══════════════════════════════════════════════════════════════════════════
    def _save_csv(self):
        if not self.saved_data:
            messagebox.showinfo("No Data", "No events recorded yet.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All", "*.*")],
            title="Export sensor data"
        )
        if path:
            try:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["Time", "Seq", "Delay_s", "Raw_JSON"])
                    w.writerows(self.saved_data)
                messagebox.showinfo("Saved", f"Exported to:\n{path}")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    # ══════════════════════════════════════════════════════════════════════════
    # Close
    # ══════════════════════════════════════════════════════════════════════════
    def on_close(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
        self.root.quit()
        self.root.destroy()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Smart Waste Bin Dashboard v2")
    p.add_argument("--broker", default=MQTT_BROKER)
    p.add_argument("--port",   type=int, default=MQTT_PORT)
    p.add_argument("--topic",  default=MQTT_TOPIC)
    args = p.parse_args()

    root = tk.Tk()
    app  = Dashboard(root, broker=args.broker, port=args.port, topic=args.topic)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
