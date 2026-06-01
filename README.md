# Smart Waste Bin — IoT System

An end-to-end IoT pipeline that turns a **Raspberry Pi 5** with an **HC‑SR501 PIR
motion sensor** and an **MQ‑3 gas sensor** into a **Smart Waste Bin**. It senses
usage and gas levels, ships events over MQTT, persists and serves them through a
REST API, derives insight with rule‑based and ML **virtual sensors**, and
visualises everything in a **Home Assistant** dashboard and a custom **live
desktop dashboard**.

The edge node reads the sensors over GPIO, so it runs on a Raspberry Pi. The
rest of the stack comes up with a single `docker compose up`.

> **Course:** Advanced Programming Techniques
> **Team 10:** Vasileios Banakos · Charalampos Papadopoulos · Ioanna Trochatou

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

Every tier communicates only through the broker, so any component can be
replaced, restarted, or moved to another host independently. The default bin
identity across the whole system is **`bin-01` / `pir-01`** — the edge node, the
virtual sensors, the Home Assistant entities and the JSON‑LD models all agree.

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

| #   | Milestone                          | Where it lives                                                | Done |
|-----|------------------------------------|---------------------------------------------------------------|------|
| M1  | Project foundation & structure     | whole repo + this README                                      | done |
| M2  | PIR integration + JSONL logging    | `pi_edge_node/pir_event_logger.py`                            | done |
| M3  | Modular pipeline components        | `pi_edge_node/motion_sensor_lib/`                             | done |
| M4  | Containerisation (single `up`)     | `docker-compose.yml`, Dockerfiles                             | done |
| M5  | JSON-LD data modelling             | `models/`, `docs/ontology.md`                                 | done |
| M6  | MQTT broker + producer/consumer    | broker.hivemq.com, `pir_mqtt_producer.py`, `mqtt_consumer.py` | done |
| M7  | HA discovery + LWT online status   | `pir_mqtt_producer.py`                                         | done |
| M8  | REST API + AsyncAPI spec           | `src/api.py`, `docs/asyncapi.yaml`                            | done |
| M9  | Rule + ML virtual sensors          | `virtual_sensor_rules.py`, `virtual_sensor_ml.py`            | done |
| M10 | Node-RED low-code layer            | `node_red/flows.json`                                         | done |
| M11 | HA dashboard + Seaborn analytics   | `home_assistant/`, `analyze.py`, live GUI                     | done |

---

## 4. Quick Start (Docker, on the Raspberry Pi)

> **Requirements:** Docker + Docker Compose on a Raspberry Pi with the HC‑SR501
> PIR on **BCM 17** and the MQ‑3 gas sensor on **BCM 23**.

```bash
cd Smart_Waste_Bin_Project
docker compose up -d --build
```

This connects every service to `broker.hivemq.com:1883`, runs the one-shot
`train` job, starts the rule + ML virtual sensors, starts the edge-node producer
(reading real GPIO via `privileged` + `/dev`), the consumer, the REST API
(`http://localhost:5000`, Swagger at `/`), and Home Assistant.

```bash
docker compose logs -f producer     # watch real motion/gas events
docker compose ps                   # service status
docker compose down                 # stop everything (add -v to wipe the volume)
```

---

## 5. Running Without Docker (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# wiring sanity checks first
python pi_edge_node/pir_smoke_test.py --pin 17        # raw voltage changes
python pi_edge_node/debug_print_events.py --pin 17    # clean, debounced events

# the real edge node
python pi_edge_node/pir_mqtt_producer.py \
    --broker broker.hivemq.com --pin 17 --gas-pin 23 \
    --bin-id bin-01 --device-id pir-01
```

The backend services (`consumer`, `api`, virtual sensors) have no GPIO
dependency and run on any host that can reach the broker.

---

## 6. REST API

Swagger UI: `http://localhost:5000/`

| Method | Endpoint                  | Description                              |
|--------|---------------------------|------------------------------------------|
| GET    | `/health/`                | Liveness + broker status                 |
| GET    | `/bins/`                  | List all bins                            |
| GET    | `/bins/<id>`              | One bin                                  |
| GET    | `/bins/<id>/events`       | Recent events for a bin (by `bin_id`)    |
| POST   | `/bins/<id>/emptied`      | Record an "emptied" action + publish     |
| GET    | `/sensors/`               | List sensors                             |
| GET    | `/virtual/`               | Latest usage intensity + ML prediction   |
| POST   | `/mqtt/publish`           | Publish an arbitrary MQTT message        |
| GET    | `/mqtt/topics`            | Last message per known topic             |

---

## 7. Home Assistant

Home Assistant runs as the `homeassistant` service in `docker-compose.yml`
(`up` starts it, `down` stops it). It mounts `home_assistant/` as `/config`, so
it uses the project `configuration.yaml` and `dashboard.yaml`. UI at
`http://<host>:8123` (dashboard at `/smart-waste-bin/overview`).

On first run, add the MQTT integration via **Settings → Devices & Services →
Add Integration → MQTT**, pointing at `broker.hivemq.com:1883`. After that,
**auto-discovery** creates the *Smart Bin bin-01* device with motion, gas,
online, event-count, last-motion, usage-intensity and busy-prediction entities.

---

## 8. Demo / Showcase Without Hardware

Both visual tools have a built-in demo mode so they can be shown without a Pi or
a live broker:

```bash
python laptop_dashboard/analyze.py --demo            # generate synthetic data + 6 charts
python laptop_dashboard/mqtt_gui_consumer.py --demo  # animate the live dashboard
```

---

## 9. MQTT Topic Scheme

| Topic                                  | Payload                | Producer    | Consumers              |
|----------------------------------------|------------------------|-------------|------------------------|
| `smartbin/<bin>/<dev>/motion`          | `detected` / `clear`   | edge node   | HA, rules, GUI         |
| `smartbin/<bin>/<dev>/gas`             | `detected` / `clear`   | edge node   | HA, GUI                |
| `smartbin/<bin>/<dev>/events`          | rich JSON‑LD event     | edge node   | consumer, API, analyze |
| `smartbin/<bin>/<dev>/event_count`     | integer (retained)     | edge node   | HA                     |
| `smartbin/<bin>/<dev>/last_motion`     | ISO timestamp          | edge node   | HA                     |
| `smartbin/<bin>/<dev>/online`          | `true` / `false` (LWT) | edge node   | HA, GUI                |
| `smartbin/<bin>/usage`                 | JSON usage level       | rule sensor | HA, API, GUI           |
| `smartbin/<bin>/prediction`            | JSON busy/quiet        | ML sensor   | HA, API, GUI           |

---

## 10. Team (Group 10)

| Name                     | Contributions                                                  |
|--------------------------|----------------------------------------------------------------|
| Vasileios Banakos        | Edge node & sensor library (PIR/Gas), MQTT producer            |
| Charalampos Papadopoulos | Backend: REST API, consumer, virtual sensors, Docker Compose   |
| Ioanna Trochatou         | Data modelling & visualisation: HA, Seaborn, GUI, Node‑RED     |

## License

MIT — see [LICENSE](LICENSE).
