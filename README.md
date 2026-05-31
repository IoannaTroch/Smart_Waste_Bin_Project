# Smart Waste Bin — IoT System

An IoT pipeline that turns a Raspberry Pi + HC‑SR501 PIR motion sensor + **MQ-3 Gas Sensor** into a **Smart Waste Bin**: it senses usage and gas levels, ships events over MQTT, persists and serves them through a REST API, derives insight with rule‑based and ML **virtual sensors**, and visualizes everything in both a **Home Assistant** dashboard and a custom **live desktop dashboard**. The whole backend comes up with a single `docker compose up`.

> **Course:** Advanced programming technics
> **Group 10:** ΜΠΑΝΑΚΟΣ ΒΑΣΙΛΕΙΟΣ · ΠΑΠΑΔΟΠΟΥΛΟΣ ΧΑΡΑΛΑΜΠΟΣ · ΤΡΟΧΑΤΟΥ ΙΩΑΝΝΑ

***

## 1. Architecture

```text
                            ┌──────────────────────────────────────────────┐
                            │                MQTT BROKER                   │
   RASPBERRY PI (edge)      │               (HiveMQ Cloud)                 │      BACKEND (Docker)
 ┌─────────────────────┐    │   smartbin/<bin>/<device>/motion             │   ┌──────────────────────┐
 │ HC-SR501 PIR sensor │    │   smartbin/<bin>/<device>/gas   ─────────────┼──▶│ mqtt_consumer.py     │
 │ MQ-3 Gas Sensor     │    │   smartbin/<bin>/<device>/events             │   │   └▶ motion_events.jsonl
 │        ▼            │    │   smartbin/<bin>/<device>/event_count        │   ├──────────────────────┤
 │ motion_sensor_lib   │    │   smartbin/<bin>/<device>/last_motion        │   │ api.py (Flask-RESTx) │
 │  sampler+interpreter│    │   smartbin/<bin>/<device>/online             │◀──│   REST + Swagger :5000
 │        ▼            │    │   smartbin/<bin>/status                      │   ├──────────────────────┤
 │ pir_mqtt_producer  ─┼───▶│   smartbin/<bin>/usage      (rule sensor)    │◀──│ virtual_sensor_rules │
 └─────────────────────┘    │   smartbin/<bin>/prediction (ML sensor)      │◀──│ virtual_sensor_ml    │
                            │   smartbin/<bin>/alert      (Node-RED)       │◀──│ Node-RED (flows)     │
                            └───────────────┬───────────────┬──────────────┘   └──────────────────────┘
                                            │               │
                              ┌─────────────▼───┐   ┌───────▼───────────────┐
                              │ Home Assistant  │   │ laptop_dashboard      │
                              │  (auto-discovery│   │  mqtt_gui_consumer.py │
                              │   + dashboard)  │   │  analyze.py (Seaborn) │
                              └─────────────────┘   └───────────────────────┘
```

Three tiers communicate only through the broker, so any component can be replaced, restarted, or moved to another host independently.

***

## 2. Repository Layout

```text
Smart_Waste_Bin_Project/
├── docs/
│   ├── ontology.md             # JSON-LD data model documentation (M5)
│   └── asyncapi.yaml           # AsyncAPI spec for the MQTT interface (M8)
├── laptop_dashboard/
│   ├── analyze.py              # Seaborn analytical charts (M11)
│   ├── mqtt_gui_consumer.py    # Advanced live Tkinter dashboard (M11)
│   └── events_log.json         # Sample events for the demo
├── models/
│   ├── context.jsonld          # Shared @context (M5)
│   ├── wastebin.jsonld         # Bin entities
│   ├── sensor.jsonld           # Sensor entities
│   └── environment.jsonld      # Deployment environment
├── pi_edge_node/               # Raspberry Pi tier
│   ├── motion_sensor_lib/      # Modular sense/interpret library (M3)
│   │   ├── __init__.py
│   │   ├── sampler.py          # PirSampler — raw GPIO reads (+ simulation)
│   │   └── interpreter.py      # PirInterpreter — debounce/cooldown logic
│   ├── pir_mqtt_producer.py    # MQTT publisher + HA discovery (PIR & MQ-3) (M6/M7)
│   ├── Dockerfile
│   └── requirements.txt        # Uses rpi-lgpio for Bookworm hardware access
├── src/                        # Backend tier
│   ├── api.py                  # Flask-RESTx REST API + Swagger (M8)
│   ├── mqtt_consumer.py        # Persists events to JSONL (M6)
│   ├── virtual_sensor_rules.py # Rule-based usage intensity (M9)
│   ├── virtual_sensor_ml.py    # ML busy/quiet prediction (M9)
│   ├── train_model.py          # Trains the RandomForest model (M9)
│   ├── Dockerfile
│   └── requirements.txt
├── node_red/
│   └── flows.json              # Low-code processing + alerting (M10)
├── home_assistant/
│   ├── configuration.yaml      # Broker + fallback entities (M9)
│   └── dashboard.yaml          # RUSTIC status dashboard (M11)
├── docker-compose.yml          # One-command full stack (M4)
└── README.md
```

***

## 3. Milestone Checklist

| # | Milestone | Where it lives | Done |
|---|-----------|---------------|------|
| M1 | Project foundation & structure | whole repo + this README | ✅ |
| M2 | PIR integration + JSONL logging | `pir_event_logger.py` | ✅ |
| M3 | Modular pipeline components | `motion_sensor_lib/` | ✅ |
| M4 | Containerization (single up) | `docker-compose.yml`, Dockerfiles | ✅ |
| M5 | JSON-LD data modeling | `models/`, `docs/ontology.md` | ✅ |
| M6 | MQTT broker + producer/consumer | HiveMQ Cloud, `pir_mqtt_producer.py` | ✅ |
| M8 | REST API + AsyncAPI spec | `src/api.py`, `docs/asyncapi.yaml` | ✅ |
| M9 | Rule + ML virtual sensors | `virtual_sensor_rules.py`, `virtual_sensor_ml` | ✅ |
| M10 | Node-RED low-code layer | `node_red/flows.json` | ✅ |
| M11 | HA dashboard + Seaborn analytics | `home_assistant/`, `analyze.py`, live GUI | ✅ |

***

## 4. Quick Start (Docker Full Stack)

> **Requirements:** Docker + Docker Compose running on a Raspberry Pi.

```bash
cd Smart_Waste_Bin_Project/Smart_Waste_Bin_Project
docker compose up -d --build
docker compose start homeassistant
```

These commands:

- Connects to the public `broker.hivemq.com`
- Starts the Producer to read Hardware Pins (PIR on 17, MQ-3 on 23) natively via `/dev`
- Runs the one‑shot train job and starts ML/Rule virtual sensors
- Starts the consumer (writes `data/motion_events.jsonl`)
- Starts the REST API at `http://localhost:5000` (Swagger UI at `/`)

### Managing Home Assistant & Containers

If you want to stop/start specific containers without bringing down the whole stack:

```bash
docker compose stop homeassistant
docker compose start homeassistant
```

Stop the whole stack: `docker compose down` (add maybe `-v` to wipe the volumes).

***

## 5. Running Without Docker (Manual / Development)

Create one virtual environment and install everything:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r pi_edge_node/requirements.txt
```

### On the Raspberry Pi (Hardware Mode)

Wire the HC‑SR501 PIR to BCM 17 and the MQ-3 Gas Sensor to BCM 23. Then run:

```bash
python pi_edge_node/pir_mqtt_producer.py \
    --broker broker.hivemq.com \
    --pin 17 --gas-pin 23 \
    --bin-id bin-02 --device-id node-02 --location "Physical Bin"
```

> The system automatically avoids simulation mode as long as `rpi-lgpio` is installed.

***

## 6. REST API Reference

Interactive Swagger UI: `http://localhost:5000/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health/` | Liveness + broker connection status |
| GET | `/bins/` | List all bins (from `wastebin.jsonld`) |
| GET | `/bins/<bin_id>/events` | Recent motion/gas events for a bin |
| GET | `/virtual/` | Latest usage‑intensity + ML prediction |

***

## 7. Home Assistant Setup

The system uses **MQTT auto‑discovery** — every publisher announces its entities automatically to Home Assistant!

1. Install the MQTT integration in HA: **Settings → Devices & Services → Add Integration → MQTT**.
2. Point it at `broker.hivemq.com` (Port 1883, no auth).
3. Start the backend (`docker compose up -d`). Within seconds you'll see a new device **"Smart Waste Bin"** with entities:
   - `binary_sensor`: PIR Motion, Ethanol / Gas Alert, Edge Node Online
   - `sensor`: Wastebin Status, Motion Event Count, Last Motion Time
   - `sensor`: Usage Intensity (rule sensor) and Busy Prediction (ML sensor)

You can manage the Home Assistant container independently:

```bash
docker restart homeassistant   # to refresh configs
```

***

## 8. The Live Desktop Dashboard (Advanced GUI)

A dark‑themed, real‑time operations console built with **Tkinter + Matplotlib**:

```bash
python laptop_dashboard/mqtt_gui_consumer.py --broker broker.hivemq.com
```

What it shows:

- **Virtual‑sensor strip** — usage intensity, ML prediction, and live motion state
- **Three live charts** — pipeline delay over time, events in 10‑second buckets, and an hourly histogram
- **Live event feed**, capturing both `[motion] DETECTED` and `[gas] ALERT`

***

## 9. Analytical Charts (Seaborn)

Generate static charts from the historical event log:

```bash
python laptop_dashboard/analyze.py        # reads data/motion_events.jsonl
```

***

## 10. Node-RED (Low-Code Layer)

Import `node_red/flows.json`. The flow subscribes to the motion pipeline, filters detections, counts events in a sliding window, classifies usage, and raises an alert on `smartbin/<bin>/alert` when usage is high.

***

## 11. MQTT Topic Scheme

| Topic | Payload | Producer | Consumers |
|-------|---------|----------|-----------|
| `smartbin/<bin>/<device>/motion` | `detected` / `clear` | edge node | HA, rule sensor, GUI |
| `smartbin/<bin>/<device>/gas` | `detected` / `clear` | edge node | HA, GUI |
| `smartbin/<bin>/<device>/events` | rich JSON‑LD event | edge node | consumer, API, analyze |
| `smartbin/<bin>/<device>/event_count` | integer (retained) | edge node | HA |
| `smartbin/<bin>/<device>/last_motion` | ISO timestamp | edge node | HA |
| `smartbin/<bin>/<device>/online` | `true` / `false` (LWT) | edge node | HA, GUI |
| `smartbin/<bin>/usage` | JSON usage level | virtual sensor | HA, API, GUI |
| `smartbin/<bin>/prediction` | JSON busy/quiet | ML sensor | HA, API, GUI |

***

## 12. Work Split (Group 10)

| Name | Contributions |
|------|--------------|
| ΜΠΑΝΑΚΟΣ ΒΑΣΙΛΕΙΟΣ | Edge node & hardware sensor library (PIR/Gas), MQTT producer |
| ΠΑΠΑΔΟΠΟΥΛΟΣ ΧΑΡΑΛΑΜΠΟΣ | Backend: REST API, consumer, virtual sensors, Docker Compose |
| ΤΡΟΧΑΤΟΥ ΙΩΑΝΝΑ | Data modeling, visualization: HA + Seaborn + GUI, Node‑RED |

***

## License

MIT — see [LICENSE](LICENSE).
