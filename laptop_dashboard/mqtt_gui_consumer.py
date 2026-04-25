import tkinter as tk
from tkinter import filedialog, messagebox
import paho.mqtt.client as mqtt
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
import time
import queue
import csv
import json
import threading
import argparse
from collections import deque

# ── Config ────────────────────────────────────────────────────────────────────
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT   = 1883
MQTT_TOPIC  = "wastebin/motion"

# ── Palette ───────────────────────────────────────────────────────────────────
BG        = "#0d1117"
SURFACE   = "#161b22"
SURFACE2  = "#1c2128"
BORDER    = "#30363d"
ACCENT    = "#00d084"
ACCENT2   = "#58a6ff"
TEXT      = "#e6edf3"
MUTED     = "#8b949e"
WARN      = "#f0883e"
ERROR     = "#ff7b72"
CHART_BG  = "#0d1117"

plt.rcParams.update({
    "figure.facecolor": CHART_BG,
    "axes.facecolor":   SURFACE,
    "axes.edgecolor":   BORDER,
    "axes.labelcolor":  MUTED,
    "xtick.color":      MUTED,
    "ytick.color":      MUTED,
    "text.color":       TEXT,
    "grid.color":       BORDER,
    "grid.linestyle":   "--",
    "grid.alpha":       0.5,
    "lines.linewidth":  2,
})

class Dashboard:
    def __init__(self, root, broker=MQTT_BROKER, port=MQTT_PORT, topic=MQTT_TOPIC):
        self.root   = root
        self.broker = broker
        self.port   = port
        self.topic  = topic

        self.root.title("Smart Waste Bin  ·  Live Dashboard")
        self.root.geometry("1000x720")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        # Data
        self.q           = queue.Queue()
        self.saved_data  = []
        self.last_time   = None
        self.counter     = 0
        self.pulse_on    = False
        self.x_data      = deque(maxlen=60)
        self.y_data      = deque(maxlen=60)
        self.bar_data    = deque(maxlen=20)   # events per 10-s bucket
        self._bucket_start = time.time()
        self._bucket_count = 0

        self._build_ui()
        self._setup_mqtt()
        self._poll()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Top bar ────────────────────────────────────────────────────────
        topbar = tk.Frame(self.root, bg=SURFACE, height=56)
        topbar.pack(fill=tk.X, side=tk.TOP)
        topbar.pack_propagate(False)

        # Logo / title
        tk.Label(topbar, text="🗑", font=("SF Pro", 22), bg=SURFACE, fg=ACCENT
                 ).pack(side=tk.LEFT, padx=(18, 6), pady=8)
        tk.Label(topbar, text="Smart Waste Bin", font=("SF Pro", 15, "bold"),
                 bg=SURFACE, fg=TEXT).pack(side=tk.LEFT)
        tk.Label(topbar, text="Live Dashboard", font=("SF Pro", 11),
                 bg=SURFACE, fg=MUTED).pack(side=tk.LEFT, padx=(6, 0), pady=2)

        # Status pill
        self.pill_frame = tk.Frame(topbar, bg=SURFACE)
        self.pill_frame.pack(side=tk.RIGHT, padx=18)
        self.dot   = tk.Label(self.pill_frame, text="●", font=("SF Pro", 12),
                              bg=SURFACE, fg=WARN)
        self.dot.pack(side=tk.LEFT)
        self.status_lbl = tk.Label(self.pill_frame, text="Connecting…",
                                   font=("SF Pro", 10), bg=SURFACE, fg=WARN)
        self.status_lbl.pack(side=tk.LEFT, padx=(4, 0))

        # Save button
        save_btn = tk.Button(topbar, text="↓  Export CSV",
                             font=("SF Pro", 10, "bold"),
                             bg=ACCENT2, fg="#0d1117", relief="flat",
                             padx=12, pady=4, cursor="hand2",
                             command=self._save_csv,
                             activebackground="#79c0ff", activeforeground="#0d1117")
        save_btn.pack(side=tk.RIGHT, padx=(0, 12), pady=10)

        # ── KPI strip ──────────────────────────────────────────────────────
        kpi_row = tk.Frame(self.root, bg=BG)
        kpi_row.pack(fill=tk.X, padx=16, pady=(14, 0))

        self.kpi_total   = self._kpi_card(kpi_row, "TOTAL EVENTS",   "0",   ACCENT)
        self.kpi_last    = self._kpi_card(kpi_row, "LAST DELAY",      "—",   ACCENT2)
        self.kpi_avg     = self._kpi_card(kpi_row, "AVG DELAY",       "—",   "#d2a8ff")
        self.kpi_device  = self._kpi_card(kpi_row, "LAST DEVICE",     "—",   WARN)

        # ── Main area: feed + charts ────────────────────────────────────────
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)

        # Left: feed
        feed_frame = tk.Frame(main, bg=SURFACE, bd=0)
        feed_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        tk.Label(feed_frame, text="LIVE FEED",
                 font=("SF Pro Mono", 9, "bold"), bg=SURFACE, fg=MUTED,
                 anchor="w").pack(fill=tk.X, padx=14, pady=(12, 4))

        self.feed = tk.Text(feed_frame, bg=SURFACE, fg=TEXT,
                            font=("SF Pro Mono", 10), bd=0, wrap=tk.WORD,
                            insertbackground=TEXT, state="disabled",
                            relief="flat", padx=10, pady=6,
                            selectbackground=ACCENT2)
        self.feed.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 8))
        self.feed.tag_config("ts",     foreground=MUTED)
        self.feed.tag_config("ok",     foreground=ACCENT)
        self.feed.tag_config("warn",   foreground=WARN)
        self.feed.tag_config("error",  foreground=ERROR)
        self.feed.tag_config("info",   foreground=ACCENT2)
        self.feed.tag_config("device", foreground="#d2a8ff")

        # Right: charts stacked
        chart_col = tk.Frame(main, bg=BG)
        chart_col.grid(row=0, column=1, sticky="nsew")
        chart_col.rowconfigure(0, weight=3)
        chart_col.rowconfigure(1, weight=2)
        chart_col.columnconfigure(0, weight=1)

        line_frame = tk.Frame(chart_col, bg=SURFACE)
        line_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        tk.Label(line_frame, text="DELAY BETWEEN EVENTS  (s)",
                 font=("SF Pro Mono", 9, "bold"), bg=SURFACE, fg=MUTED,
                 anchor="w").pack(fill=tk.X, padx=14, pady=(10, 0))

        self.fig1, self.ax1 = plt.subplots(figsize=(5.6, 2.6))
        self.fig1.patch.set_facecolor(CHART_BG)
        self.ax1.set_facecolor(SURFACE)
        self.line_plot, = self.ax1.plot([], [], color=ACCENT, lw=2, zorder=3)
        self.ax1.fill_between([], [], alpha=0.15, color=ACCENT)
        self.ax1.set_xlim(0, 10)
        self.ax1.set_ylim(0, 30)
        self.ax1.set_xlabel("Event #", fontsize=8)
        self.ax1.set_ylabel("Delay (s)", fontsize=8)
        self.ax1.grid(True)
        self.fig1.tight_layout(pad=1.2)

        canvas1 = FigureCanvasTkAgg(self.fig1, master=line_frame)
        canvas1.draw()
        canvas1.get_tk_widget().configure(bg=CHART_BG, highlightthickness=0)
        canvas1.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 8))
        self.canvas1 = canvas1

        bar_frame = tk.Frame(chart_col, bg=SURFACE)
        bar_frame.grid(row=1, column=0, sticky="nsew")
        tk.Label(bar_frame, text="EVENTS / 10s BUCKET",
                 font=("SF Pro Mono", 9, "bold"), bg=SURFACE, fg=MUTED,
                 anchor="w").pack(fill=tk.X, padx=14, pady=(10, 0))

        self.fig2, self.ax2 = plt.subplots(figsize=(5.6, 1.8))
        self.fig2.patch.set_facecolor(CHART_BG)
        self.ax2.set_facecolor(SURFACE)
        self.bar_container = self.ax2.bar(range(1), [0], color=ACCENT2,
                                          width=0.6, zorder=3)
        self.ax2.set_xlim(-0.5, 20)
        self.ax2.set_ylim(0, 10)
        self.ax2.set_xlabel("Bucket (oldest → newest)", fontsize=8)
        self.ax2.set_ylabel("Count", fontsize=8)
        self.ax2.grid(True, axis="y")
        self.fig2.tight_layout(pad=1.2)

        canvas2 = FigureCanvasTkAgg(self.fig2, master=bar_frame)
        canvas2.draw()
        canvas2.get_tk_widget().configure(bg=CHART_BG, highlightthickness=0)
        canvas2.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 8))
        self.canvas2 = canvas2

    def _kpi_card(self, parent, label, value, color):
        frame = tk.Frame(parent, bg=SURFACE2, padx=16, pady=10)
        frame.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=(0, 8))
        tk.Label(frame, text=label, font=("SF Pro Mono", 8, "bold"),
                 bg=SURFACE2, fg=MUTED).pack(anchor="w")
        val_lbl = tk.Label(frame, text=value, font=("SF Pro", 22, "bold"),
                           bg=SURFACE2, fg=color)
        val_lbl.pack(anchor="w")
        return val_lbl

    # ── Feed helpers ──────────────────────────────────────────────────────────
    def _log(self, text, tag="info"):
        ts = time.strftime("%H:%M:%S")
        self.feed.config(state="normal")
        self.feed.insert(tk.END, f"[{ts}] ", "ts")
        self.feed.insert(tk.END, text + "\n", tag)
        self.feed.see(tk.END)
        self.feed.config(state="disabled")

    # ── MQTT ──────────────────────────────────────────────────────────────────
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
                    self.q.put({"t": "status", "v": f"Connecting to {self.broker}:{self.port}  (attempt {attempt}/5)…", "s": "warn"})
                    self.client.connect(self.broker, self.port, keepalive=60)
                    self.client.loop_start()
                    return
                except Exception as e:
                    self.q.put({"t": "status", "v": f"Failed: {e}. Retrying in 5 s…", "s": "error"})
                    time.sleep(5)
            self.q.put({"t": "status", "v": "Could not connect after 5 attempts.", "s": "error"})
            self.q.put({"t": "conn", "v": "failed"})

        threading.Thread(target=_connect, daemon=True).start()

    def _on_connect(self, client, ud, flags, rc, props=None):
        if rc == 0:
            self.q.put({"t": "conn", "v": "ok"})
            client.subscribe(self.topic)
        else:
            self.q.put({"t": "status", "v": f"Connection refused  (rc={rc})", "s": "error"})

    def _on_disconnect(self, client, ud, flags, rc, props=None):
        self.q.put({"t": "conn", "v": "lost"})

    def _on_message(self, client, ud, msg):
        try:
            payload = msg.payload.decode("utf-8", errors="replace")
        except Exception:
            payload = str(msg.payload)
        self.q.put({"t": "data", "v": payload})

    # ── Polling loop (Tk-safe) ────────────────────────────────────────────────
    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                tt = item["t"]

                if tt == "status":
                    self._log(item["v"], item.get("s", "info"))

                elif tt == "conn":
                    v = item["v"]
                    if v == "ok":
                        self._set_status("● Connected", ACCENT)
                        self._log(f"✓ Connected — subscribed to: {self.topic}", "ok")
                    elif v in ("lost", "failed"):
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

    # ── Data processing ───────────────────────────────────────────────────────
    def _handle(self, payload):
        now = time.time()

        # ── Counter
        self.counter += 1
        self.kpi_total.config(text=str(self.counter))

        # ── Parse JSON
        device, seq = "unknown", self.counter
        try:
            d = json.loads(payload)
            device = d.get("device_id", "unknown")
            seq    = d.get("seq", self.counter)
            self._log(f"device={device}  seq={seq}  time={d.get('event_time','')}", "device")
        except json.JSONDecodeError:
            self._log(payload, "ok")

        self.kpi_device.config(text=str(device)[:14])

        # ── Delay
        delay = 0.0
        if self.last_time is not None:
            delay = now - self.last_time
        self.last_time = now

        if self.counter > 1:
            self.x_data.append(self.counter)
            self.y_data.append(delay)
            self.kpi_last.config(text=f"{delay:.1f} s")
            if len(self.y_data) > 1:
                avg = sum(self.y_data) / len(self.y_data)
                self.kpi_avg.config(text=f"{avg:.1f} s")
            self._update_line_chart()

        # ── 10-s bucket bar chart
        self._bucket_count += 1
        if now - self._bucket_start >= 10:
            self.bar_data.append(self._bucket_count)
            self._bucket_count  = 0
            self._bucket_start  = now
            self._update_bar_chart()

        # ── Pulse the dot
        self._pulse()

        # ── Store
        self.saved_data.append([
            time.strftime("%H:%M:%S"), self.counter, delay, payload
        ])

    def _pulse(self):
        self.dot.config(fg="#ffffff")
        self.root.after(150, lambda: self.dot.config(fg=ACCENT))

    # ── Chart updates ─────────────────────────────────────────────────────────
    def _update_line_chart(self):
        xs = list(self.x_data)
        ys = list(self.y_data)
        self.ax1.cla()
        self.ax1.set_facecolor(SURFACE)
        self.ax1.set_xlabel("Event #", fontsize=8)
        self.ax1.set_ylabel("Delay (s)", fontsize=8)
        self.ax1.grid(True)
        if xs:
            self.ax1.plot(xs, ys, color=ACCENT, lw=2, zorder=3)
            self.ax1.fill_between(xs, ys, alpha=0.12, color=ACCENT)
            # Mark latest point
            self.ax1.plot(xs[-1], ys[-1], "o", color=ACCENT, ms=6, zorder=4)
            pad = max(ys) * 0.15 if max(ys) > 0 else 1
            self.ax1.set_xlim(min(xs) - 0.5, max(xs) + 0.5)
            self.ax1.set_ylim(0, max(ys) + pad)
        self.fig1.tight_layout(pad=1.2)
        self.canvas1.draw_idle()

    def _update_bar_chart(self):
        bd = list(self.bar_data)
        if not bd:
            return
        self.ax2.cla()
        self.ax2.set_facecolor(SURFACE)
        self.ax2.set_xlabel("Bucket (oldest → newest)", fontsize=8)
        self.ax2.set_ylabel("Count", fontsize=8)
        self.ax2.grid(True, axis="y")
        colors = [ACCENT if i == len(bd) - 1 else ACCENT2 for i in range(len(bd))]
        self.ax2.bar(range(len(bd)), bd, color=colors, width=0.6, zorder=3)
        self.ax2.set_xlim(-0.5, max(len(bd), 5) - 0.5)
        self.ax2.set_ylim(0, max(bd) * 1.3 + 1)
        self.fig2.tight_layout(pad=1.2)
        self.canvas2.draw_idle()

    # ── Save ──────────────────────────────────────────────────────────────────
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
                messagebox.showinfo("Saved", f"Data exported to:\n{path}")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    # ── Close ─────────────────────────────────────────────────────────────────
    def on_close(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
        self.root.quit()
        self.root.destroy()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Smart Waste Bin Dashboard")
    p.add_argument("--broker", default=MQTT_BROKER)
    p.add_argument("--port",   type=int, default=MQTT_PORT)
    p.add_argument("--topic",  default=MQTT_TOPIC)
    args = p.parse_args()

    root = tk.Tk()
    app  = Dashboard(root, broker=args.broker, port=args.port, topic=args.topic)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
