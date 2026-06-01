# Smart Waste Bin — IoT System

> *A waste bin that doesn't just sit there. It senses, thinks, and tells you when it needs attention.*

An end-to-end IoT pipeline that turns a **Raspberry Pi 5** with an **HC‑SR501 PIR motion sensor** and an **MQ‑3 gas sensor** into a **Smart Waste Bin**. The system detects usage and gas events, ships them over MQTT, persists and serves them via a REST API, derives higher‑level insight with rule‑based and ML **virtual sensors**, and visualises everything in a **Home Assistant** dashboard and a custom **live desktop dashboard** — all from a single `docker compose up`.

> **Course:** Advanced Programming Techniques  
> **Team 10:** Vasileios Banakos · Charalampos Papadopoulos · Ioanna Trochatou  
> **License:** MIT

---

## What makes this interesting?

| Capability | Detail |
|---|---|
| **Real hardware sensing** | HC‑SR501 PIR on BCM 17, MQ‑3 gas sensor on BCM 23, running on Raspberry Pi 5 |
| **Loose coupling** | Every component talks only through MQTT topics — swap or kill any service without touching the others |
| **Semantic data** | Events are JSON‑LD using `schema.org` + `SOSA/SSN` — machine‑readable out of the box |
| **Two virtual sensors** | A rule engine classifies usage intensity; a RandomForest predicts whether the next hour will be busy or quiet |
| **Demo mode** | Both visual tools simulate live traffic without any hardware attached |
| **One‑command deployment** | `docker compose up` starts everything: edge node, backend, ML trainer, Home Assistant |

---

## 1. Architecture

```
         RASPBERRY PI (edge)              MQTT BROKER                 BACKEND (Docker)
       +---------------------+      (public broker.hivemq.com)     +----------------------+
       | HC-SR501 PIR sensor |   smartbin/<bin>/<dev>/motion  ---> | mqtt_consumer.py     |
       | MQ-3 gas sensor     |   smartbin/<bin>/<dev>/gas          |   -> motion_events   |
       |        |            |   smartbin/<bin>/<dev>/events       +----------------------+
       | motion_sensor_lib   |   smartbin/<bin>/<dev>/event_count  | api.py (Flask-RESTx) |
       |  sampler+interpreter|   smartbin/<bin>/<dev>/last_motion  |   REST + Swagger     |
       |        |            |   smartbin/<bin>/<dev>/online  <--- +----------------------+
       | pir_mqtt_producer --+-> smartbin/<bin>/usage      <------ | virtual_sensor_rules |
       +---------------------+   smartbin/<bin>/prediction <------ | virtual_sensor_ml    |
                                 smartbin/<bin>/alert       <------ | Node-RED (flows)     |
                                       |          |               +----------------------+
                              +--------v---+  +----v------------------+
                              | Home       |  | laptop_dashboard      |
                              | Assistant  |  |  mqtt_gui_consumer.py |
                              | dashboard  |  |  analyze.py (Seaborn) |
                              +------------+  +-----------------------+
```

The default bin identity across the whole system is **`bin-01` / `pir-01`** — the edge node, the virtual sensors, the Home Assistant entities, and the JSON‑LD models all share this identity so data flows without any translation layer.

---

## 2. Repository Layout

```
Smart_Waste_Bin_Project/
├── docs/
│   ├── ontology.md             # JSON-LD data model documentation (M5)
│   └── asyncapi.yaml           # AsyncAPI spec for the MQTT interface (M8)
├── laptop_dashboard/
│   ├── analyze.py              # Seaborn analytical charts (M11)
│   └── mqtt_gui_consumer.py    # Live Tkinter + Matplotlib dashboard (M11)
├── models/                     # JSON-LD data model (M5)
│   ├── context.jsonld          # Shared @context
│   ├── wastebin.jsonld         # Bin entities
│   ├── sensor.jsonld           # Sensor entities
│   └── environment.jsonld      # Deployment environment
├── pi_edge_node/               # Raspberry Pi tier (reads real GPIO)
│   ├── motion_sensor_lib/      # Modular sense/interpret library (M3)
│   │   ├── __init__.py
│   │   ├── sampler.py          # PirSampler — raw GPIO reads
│   │   └── interpreter.py      # PirInterpreter — debounce/cooldown logic
│   ├── pir_event_logger.py     # Local JSONL logger, pre-MQTT (M2)
│   ├── pir_mqtt_producer.py    # MQTT publisher + HA discovery (PIR & MQ-3) (M6/M7)
│   ├── pir_smoke_test.py       # Lowest-level GPIO wiring check
│   ├── debug_print_events.py   # Library sanity check
│   ├── Dockerfile
│   └── requirements.txt
├── src/                        # Backend tier
│   ├── api.py                  # Flask-RESTx REST API + Swagger (M8)
│   ├── mqtt_consumer.py        # Persists events to JSONL (M6/M7)
│   ├── virtual_sensor_rules.py # Rule-based usage intensity (M9)
│   ├── virtual_sensor_ml.py    # ML busy/quiet prediction (M9)
│   ├── train_model.py          # Trains the RandomForest model (M9)
│   ├── Dockerfile
│   └── requirements.txt
├── node_red/flows.json         # Low-code processing + alerting (M10)
├── home_assistant/
│   ├── configuration.yaml      # MQTT discovery + manual fallback entities (M9)
│   └── dashboard.yaml          # Status dashboard (M11)
├── docker-compose.yml          # One-command stack (M4)
└── README.md
```

---

## 3. Milestone Checklist

| # | Milestone | Where it lives | Status |
|---|---|---|---|
| M1 | Project foundation & structure | whole repo + this README | ✅ done |
| M2 | PIR integration + JSONL logging | `pi_edge_node/pir_event_logger.py` | ✅ done |
| M3 | Modular pipeline components | `pi_edge_node/motion_sensor_lib/` | ✅ done |
| M4 | Containerisation (single `up`) | `docker-compose.yml`, Dockerfiles | ✅ done |
| M5 | JSON-LD data modelling | `models/`, `docs/ontology.md` | ✅ done |
| M6 | MQTT broker + producer/consumer | broker.hivemq.com, `pir_mqtt_producer.py`, `mqtt_consumer.py` | ✅ done |
| M7 | HA discovery + LWT online status | `pir_mqtt_producer.py` | ✅ done |
| M8 | REST API + AsyncAPI spec | `src/api.py`, `docs/asyncapi.yaml` | ✅ done |
| M9 | Rule + ML virtual sensors | `virtual_sensor_rules.py`, `virtual_sensor_ml.py` | ✅ done |
| M10 | Node-RED low-code layer | `node_red/flows.json` | ✅ done |
| M11 | HA dashboard + Seaborn analytics | `home_assistant/`, `analyze.py`, live GUI | ✅ done |

---

## 4. Quick Start (Docker — recommended)

> **Requirements:** Docker + Docker Compose on a Raspberry Pi with HC‑SR501 PIR on **BCM 17** and MQ‑3 gas sensor on **BCM 23**.

```bash
cd Smart_Waste_Bin_Project
docker compose up -d --build
```

This single command:
- Trains the RandomForest ML model (`train` job, runs once)
- Starts the edge producer (reads real PIR + gas over GPIO)
- Starts the MQTT consumer (persists events to JSONL)
- Starts the REST API at **http://localhost:5000** (Swagger UI at `/`)
- Starts rule + ML virtual sensors
- Starts Home Assistant at **http://localhost:8123**

```bash
docker compose logs -f producer     # watch real motion/gas events
docker compose ps                   # check service health
docker compose down                 # stop everything (-v also wipes the volume)
```

---

## 5. Running Without Docker (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Verify wiring first
python pi_edge_node/pir_smoke_test.py --pin 17        # raw voltage changes on the pin
python pi_edge_node/debug_print_events.py --pin 17    # clean, debounced events

# Start the edge node
python pi_edge_node/pir_mqtt_producer.py \
    --broker broker.hivemq.com --pin 17 --gas-pin 23 \
    --bin-id bin-01 --device-id pir-01
```

The backend services (`consumer`, `api`, virtual sensors) have no GPIO dependency and run on any host that can reach the broker.

---

## 6. REST API

Swagger UI: `http://localhost:5000/`

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health/` | Liveness + broker connectivity |
| GET | `/bins/` | List all known bins |
| GET | `/bins/<id>` | Single bin detail |
| GET | `/bins/<id>/events` | Recent events for a bin |
| POST | `/bins/<id>/emptied` | Record an "emptied" action + publish to MQTT |
| GET | `/sensors/` | List all sensors |
| GET | `/virtual/` | Latest usage intensity + ML prediction |
| POST | `/mqtt/publish` | Publish an arbitrary MQTT message |
| GET | `/mqtt/topics` | Last known payload per topic |

---

## 7. MQTT Topic Scheme

| Topic | Payload | Producer |
|---|---|---|
| `smartbin/<bin>/<dev>/motion` | `detected` / `clear` | edge node |
| `smartbin/<bin>/<dev>/gas` | `detected` / `clear` | edge node |
| `smartbin/<bin>/<dev>/events` | rich JSON‑LD event | edge node |
| `smartbin/<bin>/<dev>/event_count` | integer (retained) | edge node |
| `smartbin/<bin>/<dev>/last_motion` | ISO timestamp | edge node |
| `smartbin/<bin>/<dev>/online` | `true` / `false` (LWT) | edge node |
| `smartbin/<bin>/usage` | JSON usage level | rule sensor |
| `smartbin/<bin>/prediction` | JSON busy/quiet + confidence | ML sensor |
| `smartbin/<bin>/alert` | JSON alert message | Node-RED |

---

## 8. Home Assistant Setup

Home Assistant runs as the `homeassistant` service and is accessible at **http://\<host\>:8123** (dashboard at `/smart-waste-bin/overview`).

On first run: **Settings → Devices & Services → Add Integration → MQTT**, point it at `broker.hivemq.com:1883`. MQTT auto-discovery then creates the *Smart Bin bin-01* device with all entities (motion, gas, online, event count, last motion, usage intensity, ML prediction) — no manual YAML needed.

---

## 9. Demo Mode (no hardware required)

Both visual tools can run entirely without a Raspberry Pi:

```bash
python laptop_dashboard/analyze.py --demo            # generates synthetic data + 6 Seaborn charts
python laptop_dashboard/mqtt_gui_consumer.py --demo  # animates the live Tkinter dashboard
```

---

## 10. Team (Group 10)

| Name | Main Contributions |
|---|---|
| **Vasileios Banakos** | Everything |
| **Charalampos Papadopoulos** | Everything |
| **Ioanna Trochatou** | Everything |

---
## 11. Generative AIs used

| **Claude AI** | 
| **Perplexity AI** |
| **Gemini AI** | 

## License

MIT — see [LICENSE](LICENSE).
