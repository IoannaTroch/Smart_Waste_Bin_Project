# Smart Waste Bin Project 

## Team Members
* **Member 1:** Vasileios Banakos - up1100950
* **Member 2:** Charalampos Papadopoulos - up1104662
* **Member 3:** Ioanna Trochatou - up1101103

## Project Overview
This project implements an intelligent waste management system utilizing **Edge Computing** and the **Producer-Consumer** pattern. Using a **Raspberry Pi** and **PIR Motion Sensors**, the system detects disposal activities, processes the data locally to filter noise, and transmits real-time telemetry to a cloud-based or local **MQTT Broker** for visualization on a live dashboard.

## Key Features
- **Smart Edge Logic:** Custom Python library to handle sensor "de-bouncing" and cooldown periods (5s) to prevent redundant data.
- **Real-time Telemetry:** Transmission of event sequences, unique Run IDs, Uptime, and CPU temperature via MQTT.
- **Dual-Logging:** Simultaneous local JSONL logging on the Pi and remote streaming to the dashboard.
- **Interactive Dashboard:** A Tkinter-based GUI featuring live Matplotlib charts for frequency analysis and inter-event delays.
- **Network Resilience:** Simulation mode for testing without hardware and auto-reconnect logic for MQTT.



## Semantic Data Model
The physical system and its deployment environment have been modeled as structured entities using **JSON-LD**. This creates a semantic "Digital Twin" of the project, allowing it to interoperate with broader Smart Building and IoT ecosystems.

The model utilizes industry-standard Web Ontologies:
* **Schema.org:** For physical dimensions, capacities, and general product definitions.
* **SOSA / SSN (W3C):** For describing the HC-SR501 PIR sensor, its mounting, and the specific observations it makes.
* **BOT (Building Topology Ontology):** To accurately map the bin's physical deployment location (KYPES IoT Lab -> HMTY Building).
* **Custom Pipeline Context:** For project-specific hardware variables (e.g., `gpioPin`, `cooldownSeconds`).

## Technologies Used
- **Hardware:** Raspberry Pi 4/5, HC-SR501 PIR Sensor.
- **Languages:** Python 3.13+.
- **Protocols:** MQTT (Paho-MQTT), TCP/IP.
- **Libraries:** `gpiozero`, `paho-mqtt`, `matplotlib`, `tkinter`, `rpi-lgpio`.
- **DevOps:** GitHub, Virtual Environments (venv).

## Project Structure
- `pi_edge_node/`: Contains the PIR logic, local logger, and MQTT producer.
- `laptop_dashboard/`: Contains the MQTT consumer and the graphical user interface.
- `motion_sensor_lib/`: Shared logic for sampling and interpreting sensor data.

## Project Milestones
More detailed project milestones/goals and required functionalities will be announced progressively, in alignment with the lab sequence.

- [x] **Milestone 1 (Lab 01):** Establish your team’s project foundation (GitHub repository, project structure, initial documentation, and reproducible development workflow).
- [x] **Milestone 2 (Lab 02):** Add real sensor input to your project by integrating the HC-SR501 PIR motion sensor on the Raspberry Pi and producing clean motion events (using your mini library + JSONL logger).
- [x] **Milestone 3 (Lab 03):** Start restructuring your Smart Waste Bin project into a set of modular data pipeline components. Your team should separate sensing, buffering, downstream processing/output and other functionalities so that parts of the system can be reused, replaced, and extended more easily.
- [ ] **Milestone 4 (Lab 04):** Containerize your Smart Waste Bin project into a Docker image/(or multiple images) and define its deployment with Docker Compose, so that by the end your system starts, runs, and persists data with a single `docker compose up`.
- [ ] **Milestone 5 (Lab 05):** Model your Smart Waste Bin system using JSON-LD. Describe your sensors, the wastebin, and the deployment environment as structured entities with explicit relationships between them.
- [x] **Milestone 6 (Lab 06):** Replace your in-process producers–consumers (publisher/subscribers) with MQTT-based communication. Set up a Mosquitto broker, split your pipeline into a standalone components, and define a topic structure for your Smart Waste Bin system. Your publishers and subscribers should run as separate processes that communicate only through the broker.

---

---

## How to run

### 1. Prerequisites
Ensure both the Raspberry Pi and your Laptop are connected to the same network.
* **Mac/Laptop:** `pip install paho-mqtt matplotlib`
* **Raspberry Pi:** `pip install paho-mqtt gpiozero rpi-lgpio`

### 2. Running the System

#### **Step A: Start the Dashboard (Consumer)**
On your **Laptop**, navigate to the dashboard folder and run:
```bash
python mqtt_gui_consumer.py --broker broker.hivemq.com
```

#### **Step B: Start the Sensor Node (Producer)**
On your **Raspberry Pi**, navigate to the edge node folder and run:

```bash
python pir_mqtt_producer.py --device-id bin-kitchen --pin 18 \
  --location kitchen --broker broker.hivemq.com
  ```
