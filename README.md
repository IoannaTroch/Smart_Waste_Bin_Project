Here's the complete README.md file content in a single code block that you can copy and save as README.md:

text
# ♻️ Smart Waste Bin — IoT System

A complete, end-to-end IoT pipeline that turns a Raspberry Pi + HC‑SR501 PIR motion sensor into a **Smart Waste Bin**: it senses usage, ships events over MQTT, persists and serves them through a REST API, derives higher‑level insight with rule‑based and ML **virtual sensors**, and visualizes everything in both a **Home Assistant** dashboard and a custom **live desktop dashboard**. The whole backend comes up with a single `docker compose up`.

> **Course:** IoT / Middleware — Semester project  
> **Group 10:** ΜΠΑΝΑΚΟΣ ΒΑΣΙΛΕΙΟΣ · ΠΑΠΑΔΟΠΟΥΛΟΣ ΧΑΡΑΛΑΜΠΟΣ · ΤΡΟΧΑΤΟΥ ΙΩΑΝΝΑ

---

## 1. Architecture

```text
                            ┌──────────────────────────────────────────────┐
                            │                MQTT BROKER                   │
   RASPBERRY PI (edge)      │               (Mosquitto)                    │     BACKEND (Docker)
 ┌─────────────────────┐    │   smartbin/<bin>/<device>/motion             │   ┌──────────────────────┐
 │ HC-SR501 PIR sensor │    │   smartbin/<bin>/<device>/events  ────────────┼──▶│ mqtt_consumer.py     │
 │        │            │    │   smartbin/<bin>/<device>/event_count         │   │   └▶ motion_events.jsonl
 │        ▼            │    │   smartbin/<bin>/<device>/last_motion         │   ├──────────────────────┤
 │ motion_sensor_lib   │    │   smartbin/<bin>/<device>/online              │   │ api.py (Flask-RESTx) │
 │  sampler+interpreter│    │   smartbin/<bin>/status                       │◀──│   REST + Swagger :5000
 │        │            │    │   smartbin/<bin>/usage      (rule sensor)     │   ├──────────────────────┤
 │        ▼            │    │   smartbin/<bin>/prediction (ML sensor)       │◀──│ virtual_sensor_rules │
 │ pir_mqtt_producer ──┼───▶│   smartbin/<bin>/alert      (Node-RED)        │◀──│ virtual_sensor_ml    │
 └─────────────────────┘    └───────────────┬───────────────┬──────────────┘   └──────────────────────┘
                                            │               │
                              ┌─────────────▼───┐   ┌────────▼──────────────┐
                              │ Home Assistant  │   │ laptop_dashboard      │
                              │  (auto-discovery│   │  mqtt_gui_consumer.py │
                              │   + dashboard)  │   │  analyze.py (Seaborn) │
                              └─────────────────┘   └───────────────────────┘
                                            ▲
                              ┌─────────────┴───┐
                              │   Node-RED      │  low-code mirror of the
                              │   flows.json    │  usage logic + alerting
                              └─────────────────┘

Three tiers communicate only through the broker, so any component can be replaced, restarted, or moved to another host independently.
```

## 2. Repository layout
Smart_Waste_Bin_Project/
├── docs/
│ ├── ontology.md # JSON-LD data model documentation (M5)
│ └── asyncapi.yaml # AsyncAPI spec for the MQTT interface (M8)
├── laptop_dashboard/
│ ├── analyze.py # Seaborn analytical charts (M11)
│ ├── mqtt_gui_consumer.py # Advanced live Tkinter dashboard (M11)
│ ├── events_log.json # Sample events for the demo
│ └── requirements.txt
├── models/
│ ├── context.jsonld # Shared @context (M5)
│ ├── wastebin.jsonld # Bin entities
│ ├── sensor.jsonld # Sensor entities
│ └── environment.jsonld # Deployment environment
├── pi_edge_node/ # Raspberry Pi tier
│ ├── motion_sensor_lib/ # Modular sense/interpret library (M3)
│ │ ├── _init_.py
│ │ ├── sampler.py # PirSampler — raw GPIO reads (+ simulation)
│ │ └── interpreter.py # PirInterpreter — debounce/cooldown logic
│ ├── pir_smoke_test.py # Quick "is the sensor wired right?" check
│ ├── debug_print_events.py # Print clean events to the console
│ ├── pir_event_logger.py # JSONL event logger (M2)
│ ├── pir_mqtt_producer.py # MQTT publisher + HA discovery (M6/M7)
│ ├── Dockerfile
│ └── requirements.txt
├── src/ # Backend tier
│ ├── api.py # Flask-RESTx REST API + Swagger (M8)
│ ├── mqtt_consumer.py # Persists events to JSONL (M6)
│ ├── virtual_sensor_rules.py # Rule-based usage intensity (M9)
│ ├── virtual_sensor_ml.py # ML busy/quiet prediction (M9)
│ ├── train_model.py # Trains the RandomForest model (M9)
│ ├── Dockerfile
│ └── requirements.txt
├── node_red/
│ └── flows.json # Low-code processing + alerting (M10)
├── home_assistant/
│ ├── configuration.yaml # Broker + fallback entities (M9)
│ └── dashboard.yaml # RUSTIC status dashboard (M11)
├── mosquitto/
│ └── mosquitto.conf # Broker config (M6)
├── docker-compose.yml # One-command full stack (M4)
├── requirements.txt # All-in-one developer install
├── .gitignore
├── .dockerignore
├── LICENSE
└── README.md

text

## 3. Milestone checklist

| #   | Milestone                        | Where it lives                                | Done |
|-----|----------------------------------|-----------------------------------------------|------|
| M1  | Project foundation & structure   | whole repo + this README                        | ✅   |
| M2  | PIR integration + JSONL logging  | `pir_event_logger.py`                         | ✅   |
| M3  | Modular pipeline components      | `motion_sensor_lib/`                          | ✅   |
| M4  | Containerization (single up)     | `docker-compose.yml`, `Dockerfiles`, `mosquitto/` | ✅   |
| M5  | JSON-LD data modeling            | `models/`, `docs/ontology.md`                 | ✅   |
| M6  | MQTT broker + producer/consumer  | `mosquitto/`, `pir_mqtt_producer.py`, `mqtt_consumer.py` | ✅   |
| M8  | REST API + AsyncAPI spec         | `src/api.py`, `docs/asyncapi.yaml`            | ✅   |
| M9  | Rule + ML virtual sensors        | `virtual_sensor_rules.py`, `virtual_sensor_ml.py`, `train_model.py` | ✅   |
| M10 | Node-RED low-code layer          | `node_red/flows.json`                         | ✅   |
| M11 | HA dashboard + Seaborn analytics | `home_assistant/`, `analyze.py`, live GUI     | ✅   |

## 4. Quick start (full backend, one command)

**Requirements:** Docker + Docker Compose.

```bash
cd Smart_Waste_Bin_Project
docker compose up --build
```

That single command:
- starts the Mosquitto broker,
- runs the one‑shot train job (saves the ML model into the shared volume),
- starts the simulated producer (publishes motion events),
- starts the consumer (writes `data/motion_events.jsonl`),
- starts the REST API at http://localhost:5000 (Swagger UI at `/`),
- starts both virtual sensors (usage + prediction),
- starts Node-RED at http://localhost:1880.

Data persists in the `smartbin_data` and `node_red_data` Docker volumes, so it survives restarts.  
Stop with `Ctrl‑C`, then `docker compose down` (add `-v` to wipe the volumes).

**Check it's alive:**

```bash
curl http://localhost:5000/health/
curl http://localhost:5000/bins/
curl http://localhost:5000/virtual/
```

## 5. Running without Docker (manual / development)

Create one virtual environment and install everything:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
sudo apt install python3-tk        # GUI only (Debian/Ubuntu)
```

Then, in separate terminals, with a broker already running (`docker compose up mosquitto`, or a local mosquitto):

```bash
# 1) Edge node — publish simulated motion (no Raspberry Pi needed)
python pi_edge_node/pir_mqtt_producer.py --simulate

# 2) Consumer — persist rich events
python src/mqtt_consumer.py --broker localhost --out data/motion_events.jsonl

# 3) REST API
python src/api.py                           # http://localhost:5000

# 4) Virtual sensors
python src/virtual_sensor_rules.py --broker localhost --ha-discovery
python src/train_model.py                   # once, to create the model
python src/virtual_sensor_ml.py --broker localhost --ha-discovery
```

### On a real Raspberry Pi

Wire the HC‑SR501 to a GPIO pin (default BCM 4), then drop `--simulate`:

```bash
python pi_edge_node/pir_smoke_test.py --pin 4        # verify wiring
python pi_edge_node/pir_mqtt_producer.py \
    --broker <broker-ip> --pin 4 \
    --bin-id bin-01 --device-id pir-01 --location "Kitchen"
```

The library auto‑detects the absence of `gpiozero`/GPIO and falls back to simulation, so the exact same code runs on a laptop and on the Pi.

## 6. REST API reference

Interactive Swagger UI: http://localhost:5000/

| Method | Endpoint                    | Description                              |
|--------|-----------------------------|------------------------------------------|
| GET    | `/health/`                  | Liveness + broker connection status      |
| GET    | `/bins/`                    | List all bins (from `models/wastebin.jsonld`) |
| GET    | `/bins/<bin_id>`            | Single bin details                       |
| GET    | `/bins/<bin_id>/events`     | Recent motion events for a bin           |
| POST   | `/bins/<bin_id>/emptied`    | Mark a bin as emptied                    |
| GET    | `/sensors/`                 | List all sensors                         |
| GET    | `/sensors/<sensor_id>`      | Single sensor details                    |
| GET    | `/virtual/`                 | Latest usage‑intensity + ML prediction   |
| POST   | `/mqtt/publish`             | Publish a message to any topic via HTTP  |
| GET    | `/mqtt/topics`              | Snapshot of recently seen topics         |
| GET    | `/mqtt/topics/<topic>`      | Last retained value for a topic          |

The push‑based side of the system (MQTT) is formally documented in `docs/asyncapi.yaml`.

## 7. Home Assistant setup

The system uses MQTT auto‑discovery — every publisher announces its entities, so you barely configure anything by hand.

1. Install / run Home Assistant (Container, OS, or Core).
2. Add the MQTT integration: **Settings → Devices & Services → Add Integration → MQTT**, and point it at the broker:
   - Host: `localhost` (or `mosquitto` if HA runs in the same Compose network)
   - Port: `1883`, no username/password (anonymous, per `mosquitto.conf`).
3. Start the backend (`docker compose up`). Within seconds you'll see a new device "Smart Waste Bin bin‑01" with entities:
   - `binary_sensor`: PIR Motion, PIR Sensor Online
   - `sensor`: Wastebin Status, Motion Event Count, Last Motion Time
   - `sensor`: Usage Intensity (rule sensor) and Busy Prediction (ML sensor)
4. Install the dashboard: copy `home_assistant/dashboard.yaml` into your HA config directory and reference it from `configuration.yaml` (an example `configuration.yaml` with the broker block and a manual‑entity fallback is provided in `home_assistant/`). Reload, and open the Smart Waste Bin view in the sidebar.

The dashboard follows **RUSTIC**: a system overview at the top, a conditional alert banner that only appears when usage is high, per‑bin live status, gauges for derived intelligence, and 24‑hour history graphs.

If discovery hasn't fired yet during a demo, the manual `mqtt:` entities in `configuration.yaml` let the dashboard populate directly from the broker.

## 8. The live desktop dashboard (advanced GUI)

A dark‑themed, real‑time operations console built with Tkinter + Matplotlib:

```bash
python laptop_dashboard/mqtt_gui_consumer.py --broker localhost
# options: --port 1883  --topic 'smartbin/#'
```

**What it shows:**
- **KPI strip** — total events, last‑event delay, average delay, peak hour, uptime, active device.
- **Virtual‑sensor strip** — color‑coded usage intensity, the latest ML busy/quiet prediction, and a live motion indicator.
- **Three live charts** — pipeline delay over time, events in 10‑second buckets, and an hourly histogram.
- **Live event feed**, a per‑bin system‑overview footer, and an alert badge that lights up on high activity.
- **CSV export** of everything captured, plus a rolling `events_log.json`.

It subscribes to `smartbin/#` and routes each message by its topic suffix (events / motion / usage / prediction / status), so it stays in sync with the rest of the system automatically.

## 9. Analytical charts (Seaborn)

Generate static charts from the historical event log:

```bash
python laptop_dashboard/analyze.py        # reads data/motion_events.jsonl
```

Outputs PNGs into `charts/`:
- `events_per_hour.png` — activity pattern across the day
- `events_over_time.png` — volume trend
- `usage_heatmap.png` — day‑of‑week × hour intensity
- `latency_distribution.png` — pipeline latency, with outliers
- `latency_over_time.png` — latency trend
- `events_per_bin.png` — comparison across bins

## 10. Node-RED (low-code layer)

Import `node_red/flows.json` (Menu → Import). The flow mirrors the Python rule sensor entirely with visual nodes: it subscribes to the motion pipeline, filters genuine detections, counts events in a sliding 60‑second window, classifies usage (idle/low/medium/high), republishes the level to `smartbin/<bin>/usage`, and raises an alert on `smartbin/<bin>/alert` when usage is high. It demonstrates that the same processing logic can live as code or as low‑code flows over the shared broker.

## 11. MQTT topic scheme

| Topic                                      | Payload                  | Producer       | Consumers                        |
|--------------------------------------------|--------------------------|----------------|----------------------------------|
| `smartbin/<bin>/<device>/motion`           | `detected` / `clear`     | edge node      | HA, rule sensor, GUI             |
| `smartbin/<bin>/<device>/events`           | rich JSON‑LD event       | edge node      | consumer, API, analyze           |
| `smartbin/<bin>/<device>/event_count`      | integer (retained)       | edge node      | HA                               |
| `smartbin/<bin>/<device>/last_motion`      | ISO timestamp (retained) | edge node      | HA                               |
| `smartbin/<bin>/<device>/online`           | `true` / `false` (LWT)   | edge node      | HA, GUI                          |
| `smartbin/<bin>/status`                    | JSON status (retained)   | edge node      | HA, GUI                          |
| `smartbin/<bin>/usage`                     | JSON usage level         | rule sensor / Node‑RED | HA, API, GUI              |
| `smartbin/<bin>/prediction`                | JSON busy/quiet          | ML sensor      | HA, API, GUI                     |
| `smartbin/<bin>/alert`                     | JSON alert               | Node‑RED       | HA, GUI                          |

## 12. Work split (Group 10)

| Name                  | Contributions                                                |
|-----------------------|--------------------------------------------------------------|
| **ΜΠΑΝΑΚΟΣ ΒΑΣΙΛΕΙΟΣ**   | edge node & sensor library (M2, M3), MQTT producer (M6/M7)   |
| **ΠΑΠΑΔΟΠΟΥΛΟΣ ΧΑΡΑΛΑΜΠΟΣ** | backend: REST API, consumer, virtual sensors (M8, M9), containerization (M4) |
| **ΤΡΟΧΑΤΟΥ ΙΩΑΝΝΑ**      | data modeling (M5), visualization: Home Assistant + Seaborn + live GUI (M11), Node‑RED (M10) |

## License

MIT — see [LICENSE](LICENSE).