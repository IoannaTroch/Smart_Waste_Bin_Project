import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import paho.mqtt.client as mqtt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import time
import queue
import csv
import json
import threading
import argparse

# --- Configuration ---
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883
MQTT_TOPIC = "wastebin/motion"

class MQTTViewerApp:
    def __init__(self, root, broker=MQTT_BROKER, port=MQTT_PORT, topic=MQTT_TOPIC):
        self.root = root
        self.root.title("Smart Waste Bin - Live Dashboard")
        self.root.geometry("850x650")

        self.broker = broker
        self.port = port
        self.topic = topic

        self.msg_queue = queue.Queue()
        self.saved_data = []
        self.last_msg_time = None
        self.counter = 0
        self.connected = False

        self.x_data = []
        self.y_delay_data = []

        self.setup_ui()
        self.setup_mqtt()     # Non-blocking now
        self.process_queue()  # Start Tk polling loop

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def setup_ui(self):
        top_frame = tk.Frame(self.root, pady=10)
        top_frame.pack(fill=tk.X)

        self.lbl_counter = tk.Label(
            top_frame, text="Motion Events Detected: 0",
            font=("Arial", 14, "bold")
        )
        self.lbl_counter.pack(side=tk.LEFT, padx=20)

        self.lbl_status = tk.Label(
            top_frame, text="⏳ Connecting...",
            font=("Arial", 10), fg="orange"
        )
        self.lbl_status.pack(side=tk.LEFT, padx=10)

        btn_save = tk.Button(
            top_frame, text="💾 Save Data to CSV",
            command=self.save_data,
            bg="#4CAF50", fg="white", font=("Arial", 12, "bold")
        )
        btn_save.pack(side=tk.RIGHT, padx=20)

        mid_frame = tk.LabelFrame(
            self.root, text=f"Live Feed (Topic: {self.topic})",
            padx=10, pady=10
        )
        mid_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self.txt_feed = scrolledtext.ScrolledText(
            mid_frame, height=8, state="disabled", bg="#f4f4f4"
        )
        self.txt_feed.pack(fill=tk.BOTH, expand=True)

        bot_frame = tk.LabelFrame(
            self.root,
            text="Time Delay Between Motion Events (Seconds)",
            padx=10, pady=10
        )
        bot_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self.fig, self.ax = plt.subplots(figsize=(6, 3), dpi=100)
        self.ax.set_xlabel("Event Sequence")
        self.ax.set_ylabel("Delay (s)")
        self.line, = self.ax.plot([], [], marker="o", color="orange")
        self.ax.grid(True, alpha=0.3)

        self.canvas = FigureCanvasTkAgg(self.fig, master=bot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------
    # MQTT — runs connect() in a background thread so Tk never freezes
    # ------------------------------------------------------------------
    def setup_mqtt(self):
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:
            self.client = mqtt.Client()

        self.client.on_connect    = self.on_connect
        self.client.on_message    = self.on_message
        self.client.on_disconnect = self.on_disconnect

        def _connect():
            retries = 0
            while retries < 5:
                try:
                    self.msg_queue.put({
                        "type": "status",
                        "payload": f"Connecting to {self.broker}:{self.port} "
                                   f"(attempt {retries + 1}/5)..."
                    })
                    self.client.connect(self.broker, self.port, keepalive=60)
                    self.client.loop_start()
                    return   # success — exit thread
                except Exception as e:
                    retries += 1
                    self.msg_queue.put({
                        "type": "status",
                        "payload": f"[WARN] Connect failed: {e}. Retrying in 5s..."
                    })
                    time.sleep(5)

            self.msg_queue.put({
                "type": "status",
                "payload": "[ERROR] Could not connect after 5 attempts. "
                           "Check broker address or try a different broker."
            })
            self.msg_queue.put({"type": "conn_failed"})

        threading.Thread(target=_connect, daemon=True).start()

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self.connected = True
            self.msg_queue.put({
                "type": "status",
                "payload": f"✅ Connected! Subscribed to: {self.topic}"
            })
            self.msg_queue.put({"type": "conn_ok"})
            client.subscribe(self.topic)
        else:
            self.msg_queue.put({
                "type": "status",
                "payload": f"[ERROR] Connection refused, code: {reason_code}"
            })

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        self.connected = False
        self.msg_queue.put({
            "type": "status",
            "payload": f"⚠️ Disconnected (code {reason_code}). Paho will auto-reconnect..."
        })
        self.msg_queue.put({"type": "conn_lost"})

    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode("utf-8", errors="replace")
        except Exception:
            payload = str(msg.payload)
        self.msg_queue.put({"type": "data", "topic": msg.topic, "payload": payload})

    # ------------------------------------------------------------------
    # Queue polling — only place we touch the GUI from MQTT callbacks
    # ------------------------------------------------------------------
    def process_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()

                if msg["type"] == "status":
                    self.append_to_feed(msg["payload"])

                elif msg["type"] == "conn_ok":
                    self.lbl_status.config(text="🟢 Connected", fg="green")

                elif msg["type"] in ("conn_lost", "conn_failed"):
                    self.lbl_status.config(text="🔴 Disconnected", fg="red")

                elif msg["type"] == "data":
                    self.handle_sensor_data(msg["payload"])

        except queue.Empty:
            pass

        self.root.after(100, self.process_queue)

    # ------------------------------------------------------------------
    # Data handling
    # ------------------------------------------------------------------
    def handle_sensor_data(self, payload):
        current_time = time.time()
        self.counter += 1
        self.lbl_counter.config(text=f"Motion Events Detected: {self.counter}")

        display_text = payload
        try:
            data_dict = json.loads(payload)
            display_text = (
                f"Device: {data_dict.get('device_id', 'N/A')} | "
                f"Seq: {data_dict.get('seq', 'N/A')} | "
                f"Time: {data_dict.get('event_time', 'N/A')}"
            )
        except json.JSONDecodeError:
            pass

        time_str = time.strftime("%H:%M:%S")
        self.append_to_feed(f"[{time_str}] {display_text}")

        delay = 0.0
        if self.last_msg_time is not None:
            delay = current_time - self.last_msg_time
        self.last_msg_time = current_time

        if self.counter > 1:
            self.x_data.append(self.counter)
            self.y_delay_data.append(delay)
            if len(self.x_data) > 50:
                self.x_data.pop(0)
                self.y_delay_data.pop(0)
            self.update_graph()

        self.saved_data.append([time_str, self.counter, delay, payload])

    def append_to_feed(self, text):
        self.txt_feed.config(state="normal")
        self.txt_feed.insert(tk.END, text + "\n")
        self.txt_feed.see(tk.END)
        self.txt_feed.config(state="disabled")

    def update_graph(self):
        self.line.set_data(self.x_data, self.y_delay_data)
        self.ax.relim()
        self.ax.autoscale_view()
        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def save_data(self):
        if not self.saved_data:
            messagebox.showinfo("No Data", "There is no data to save yet.")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Save Sensor Data"
        )
        if file_path:
            try:
                with open(file_path, mode="w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["Local_Time", "Event_Count", "Delay_Since_Last_Sec", "Raw_JSON_Payload"])
                    w.writerows(self.saved_data)
                messagebox.showinfo("Success", f"Saved to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------
    def on_closing(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
        self.root.quit()
        self.root.destroy()


# ------------------------------------------------------------------
# Entry point — accepts --broker / --port / --topic as CLI args
# ------------------------------------------------------------------
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Smart Waste Bin Dashboard")
    p.add_argument("--broker", default=MQTT_BROKER)
    p.add_argument("--port",   type=int, default=MQTT_PORT)
    p.add_argument("--topic",  default=MQTT_TOPIC)
    args = p.parse_args()

    root = tk.Tk()
    app = MQTTViewerApp(root, broker=args.broker, port=args.port, topic=args.topic)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
