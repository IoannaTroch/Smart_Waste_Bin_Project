# Smart Waste Bin — IoT System

An end-to-end IoT pipeline that turns a Raspberry Pi 5 with an HC‑SR501 PIR
motion sensor and a MQ‑3 gas sensor into a **Smart Waste Bin**. It senses
usage and gas levels, ships events over MQTT, persists and serves them through a
REST API, derives insight with rule‑based and ML virtual sensors and
visualises everything in a Home Assistant dashboard and a custom live
desktop dashboard.

The edge node reads the sensors over GPIO, so it runs on a Raspberry Pi. The
rest of the backend comes up with a single `docker compose up`.

> **Course:** Advanced Programming Techniques
> **Team 10:** Vasileios Banakos | Charalampos Papadopoulos | Ioanna Trochatou

---

## 1. Architecture

```text
                            ┌──────────────────────────────────────────────┐
                            │                MQTT BROKER                    │
   RASPBERRY PI (edge)      │           (public broker.hivemq.com)          │      BACKEND (Docker)
 ┌─────────────────────┐    │   smartbin/<bin>/<device>/motion              │   ┌──────────────────────┐
 │ HC-SR501 PIR sensor │    │   smartbin/<bin>/<device>/gas    ─────────────┼──▶│ mqtt_consumer.py     │
 │ MQ-3 Gas Sensor     │    │   smartbin/<bin>/<device>/events              │   │   └▶ motion_events.jsonl
 │        ▼            │    │   smartbin/<bin>/<device>/event_count         │   ├──────────────────────┤
 │ motion_sensor_lib   │    │   smartbin/<bin>/<device>/last_motion         │   │ api.py (Flask-RESTx) │
 │  sampler+interpreter│    │   smartbin/<bin>/<device>/online              │◀──│   REST + Swagger :5000│
 │        ▼            │    │   smartbin/<bin>/status                       │   ├──────────────────────┤
 │ pir_mqtt_producer  ─┼───▶│   smartbin/<bin>/usage      (rule sensor)     │◀──│ virtual_sensor_rules │
 └─────────────────────┘    │   smartbin/<bin>/prediction (ML sensor)       │◀──│ virtual_sensor_ml    │
                            │   smartbin/<bin>/alert      (Node-RED)        │◀──│ Node-RED (flows)     │
                            └───────────────┬───────────────┬───────────────┘   └──────────────────────┘
                                            │               │
                              ┌─────────────▼───┐   ┌───────▼───────────────┐
                              │ Home Assistant  │   │ laptop_dashboard      │
                              │  (auto-discovery│   │  mqtt_gui_consumer.py │
                              │   + dashboard)  │   │  analyze.py (Seaborn) │
                              └─────────────────┘   └───────────────────────┘
```

Every tier communicates only through the broker, so any component can be
replaced, restarted or moved to another host independently. The default bin
identity across the whole system is **`bin-01` / `pir-01`** — the edge node, the
virtual sensors, the Home Assistant entities and the JSON‑LD models all agree on
it.

---

## 2. Repository Layout

```text
Smart_Waste_Bin_Project/
├── docs/
│   ├── ontology.md             # JSON-LD data model documentation 
│   └── asyncapi.yaml           # AsyncAPI spec for the MQTT interface 
├── laptop_dashboard/
│   ├── analyze.py              # Seaborn analytical charts (
│   ├── mqtt_gui_consumer.py    # Live Tkinter + Matplotlib dashboard (
│   └── events_log.json         # Sample events for the demo
├── models/                     # JSON-LD data model 
│   ├── context.jsonld          # Shared @context
│   ├── wastebin.jsonld         # Bin entities
│   ├── sensor.jsonld           # Sensor entities
│   └── environment.jsonld      # Deployment environment
├── pi_edge_node/               # Raspberry Pi tier 
│   ├── motion_sensor_lib/      # Modular sense/interpret library 
│   │   ├── __init__.py
│   │   ├── sampler.py          # PirSampler — raw GPIO reads
│   │   └── interpreter.py      # PirInterpreter — debounce/cooldown logic
│   ├── pir_event_logger.py     # Local JSONL logger
│   ├── pir_mqtt_producer.py    # MQTT publisher + HA discovery (PIR & MQ-3) 
│   ├── pir_smoke_test.py       # Low-level GPIO wiring check
│   ├── debug_print_events.py   # Library sanity check (sampler -> interpreter)
│   ├── Dockerfile
│   └── requirements.txt
├── src/                        # Backend tier
│   ├── api.py                  # Flask-RESTx REST API + Swagger 
│   ├── mqtt_consumer.py        # Persists events to JSONL 
│   ├── virtual_sensor_rules.py # Rule-based usage intensity 
│   ├── virtual_sensor_ml.py    # ML busy/quiet prediction 
│   ├── train_model.py          # Trains the model 
│   ├── Dockerfile
│   └── requirements.txt
├── node_red/
│   └── flows.json              # Low-code processing + alerting 
├── home_assistant/
│   ├── configuration.yaml      # MQTT discovery + manual fallback entities 
│   └── dashboard.yaml          # RUSTIC status dashboard (
├── mosquitto/
│   └── mosquitto.conf          # Optional local broker config (
├── docker-compose.yml          # One-command backend stack 
└── README.md
```

> **Note:** `src/main.py` and `src/sensors/` are a standalone threaded
> producer/consumer demo kept from an earlier milestone. The shipped pipeline
> uses `pir_mqtt_producer.py` + `motion_sensor_lib/` instead; you can delete the
> `src/main.py` / `src/sensors/` pair if you want a single source of truth.

---

## 3. Milestone Checklist

| #   | Milestone                          | Where it lives                                          | Done |
|-----|------------------------------------|---------------------------------------------------------|------|
| M1  | Project foundation & structure     | whole repo + this README                                | ✅   |
| M2  | PIR integration + JSONL logging    | `pi_edge_node/pir_event_logger.py`                      | ✅   |
| M3  | Modular pipeline components        | `pi_edge_node/motion_sensor_lib/`                       | ✅   |
| M4  | Containerisation (single `up`)     | `docker-compose.yml`, Dockerfiles                       | ✅   |
| M5  | JSON-LD data modelling             | `models/`, `docs/ontology.md`                           | ✅   |
| M6  | MQTT broker + producer/consumer    | broker.hivemq.com, `pir_mqtt_producer.py`, `mqtt_consumer.py` | ✅ |
| M7  | HA discovery + LWT online status   | `pir_mqtt_producer.py`           | ✅   |
| M8  | REST API + AsyncAPI spec           | `src/api.py`, `docs/asyncapi.yaml`                      | ✅   |
| M9  | Rule + ML virtual sensors          | `virtual_sensor_rules.py`, `virtual_sensor_ml.py`       | ✅   |
| M10 | Node-RED low-code layer            | `node_red/flows.json`                                   | ✅   |
| M11 | HA dashboard + Seaborn analytics   | `home_assistant/`, `analyze.py`, live GUI               | ✅   |

---

## 4. Quick Start (Docker, on the Raspberry Pi)

> **Requirements:** Docker + Docker Compose running on a Raspberry Pi with the
> HC‑SR501 PIR on **BCM 17** and the MQ‑3 gas sensor on **BCM 23**.

```bash
cd Smart_Waste_Bin_Project
docker compose up -d --build
```

This will:

- Connect every service to the public broker `broker.hivemq.com:1883`.
- Run the one-shot train job, then start the rule and ML virtual sensors.
- Start the edge-node producer, which reads the real GPIO sensors (the
  service runs `privileged` with `/dev` mounted) and publishes as `bin-01` / `pir-01`.
- Start the consumer (writes `motion_events.jsonl` into the shared volume).
- Start the REST API at `http://localhost:5000` (Swagger UI at `/`).

Useful commands:

```bash
docker compose logs -f producer     # watch real motion/gas events
docker compose ps                   # service status
docker compose down                 # stop everything (add -v to wipe the volume)
```

Home Assistant also starts as part of the stack — on first run, do the
one-time MQTT integration setup in its UI.

---

## 5. Running Without Docker (Manual)

On the Raspberry Pi, create a virtual environment and install everything:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then run the edge node against the wired sensors:

```bash
python pi_edge_node/pir_mqtt_producer.py \
    --broker broker.hivemq.com \
    --pin 17 --gas-pin 23 \
    --bin-id bin-01 --device-id pir-01
```

Before running the full producer it's worth checking the wiring:

```bash
python pi_edge_node/pir_smoke_test.py --pin 17        # raw voltage changes
python pi_edge_node/debug_print_events.py --pin 17    # clean, debounced events
```

The backend services (`consumer`, `api`, virtual sensors) have no GPIO
dependency and can run on any host that can reach the broker.

---

## 6. REST API Reference

Interactive Swagger UI: `http://localhost:5000/`

| Method | Endpoint                  | Description                                  |
|--------|---------------------------|----------------------------------------------|
| GET    | `/health/`                | Liveness + broker connection status          |
| GET    | `/bins/`                  | List all bins (from `wastebin.jsonld`)       |
| GET    | `/bins/<bin_id>`          | One bin                                      |
| GET    | `/bins/<bin_id>/events`   | Recent events for a bin (filtered by `bin_id`) |
| POST   | `/bins/<bin_id>/emptied`  | Record an "emptied" action + publish to MQTT |
| GET    | `/sensors/`               | List sensors (from `sensor.jsonld`)          |
| GET    | `/virtual/`               | Latest usage intensity + ML prediction       |
| POST   | `/mqtt/publish`           | Publish an arbitrary MQTT message            |
| GET    | `/mqtt/topics`            | Last message seen on every known topic       |

---

## 7. Home Assistant Setup

Home Assistant runs as the `homeassistant` service in `docker-compose.yml`, so
`docker compose up` starts it and `docker compose down` stops it. It mounts
`home_assistant/` as its `/config`, so it uses your `configuration.yaml` and
`dashboard.yaml` directly. With host networking the UI is at
`http://<host>:8123` (your dashboard: `http://<host>:8123/smart-waste-bin/overview`).

On first start, do the one-time MQTT setup:

1. Open the HA UI and create an account.
2. **Settings → Devices & Services → Add Integration → MQTT**, pointing it at
   `broker.hivemq.com` (port 1883, no auth). The broker connection itself is set
   up here, in the UI — it can't be pre-seeded from YAML.

After that, MQTT auto‑discovery takes over: the edge-node producer and both
virtual sensors announce their entities on `homeassistant/.../config`, so a
"Smart Bin bin-01" device appears automatically with:
   - `binary_sensor`: PIR Motion, Gas Alert, Edge Node Online
   - `sensor`: Motion Event Count, Last Motion
   - `sensor`: Usage Intensity (rule sensor) and Busy Prediction (ML sensor)

`home_assistant/configuration.yaml` also defines the same entities as a manual
fallback for demos where discovery hasn't fired yet, plus the dashboard in
`home_assistant/dashboard.yaml`.

---

## 8. The Live Desktop Dashboard

A dark‑themed, real‑time console built with Tkinter + Matplotlib:

```bash
python laptop_dashboard/mqtt_gui_consumer.py --broker broker.hivemq.com
```

Shows a virtual-sensor strip (usage intensity, ML prediction, live motion), three
live charts (pipeline delay, events per 10‑second bucket, hourly histogram), and a
live event feed for both `[motion] DETECTED` and `[gas] ALERT`.

---

## 9. Analytical Charts (Seaborn)

```bash
python laptop_dashboard/analyze.py        # reads data/motion_events.jsonl
```

---

## 10. Node-RED (Low-Code Layer)

Import `node_red/flows.json`. The flow subscribes to `smartbin/+/+/motion`,
filters detections, counts events in a sliding window, classifies usage and
raises an alert on `smartbin/<bin>/alert` when usage is high. Because it uses a
wildcard subscription it works regardless of the bin/device id.

---

## 11. MQTT Topic Scheme

| Topic                                  | Payload                | Producer        | Consumers                |
|----------------------------------------|------------------------|-----------------|--------------------------|
| `smartbin/<bin>/<device>/motion`       | `detected` / `clear`   | edge node       | HA, rule sensor, GUI     |
| `smartbin/<bin>/<device>/gas`          | `detected` / `clear`   | edge node       | HA, GUI                  |
| `smartbin/<bin>/<device>/events`       | rich JSON‑LD event     | edge node       | consumer, API, analyze   |
| `smartbin/<bin>/<device>/event_count`  | integer (retained)     | edge node       | HA                       |
| `smartbin/<bin>/<device>/last_motion`  | ISO timestamp          | edge node       | HA                       |
| `smartbin/<bin>/<device>/online`       | `true` / `false` (LWT) | edge node       | HA, GUI                  |
| `smartbin/<bin>/usage`                 | JSON usage level       | rule sensor     | HA, API, GUI             |
| `smartbin/<bin>/prediction`            | JSON busy/quiet        | ML sensor       | HA, API, GUI             |

---


## License

MIT — see [LICENSE](LICENSE).
