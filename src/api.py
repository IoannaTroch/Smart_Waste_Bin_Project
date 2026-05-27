#!/usr/bin/env python3
"""
api.py  —  Smart Waste Bin REST API (Milestone 8 / Lab 08).

A pull-based OpenAPI interface (Flask + Flask-RESTx, auto Swagger UI at /) that
sits next to the push-based MQTT/AsyncAPI interface. It exposes:

    GET  /bins                       list registered bins (from wastebin.jsonld)
    GET  /bins/<id>                  one bin
    GET  /bins/<id>/events           motion events for that bin (from JSONL log)
    POST /bins/<id>/emptied          record an "emptied" action + publish to MQTT
    GET  /sensors                    list sensors (from sensor.jsonld)
    GET  /sensors/<id>               one sensor
    GET  /virtual                    latest virtual-sensor readings (usage + prediction)
    POST /mqtt/publish               publish an arbitrary message to the broker
    GET  /mqtt/topics                last message seen on every known topic
    GET  /mqtt/topics/<topic>        last message on one topic
    GET  /health                     liveness + broker status

Paths resolve relative to the project root, and the MQTT bridge degrades
gracefully: if no broker is reachable the API still starts and serves models.

Run:   python api.py        (then open http://localhost:5000/)
Env:   MODELS_DIR, DATA_DIR, MQTT_BROKER, MQTT_PORT, API_PORT
"""

import os
import json
import threading
from datetime import datetime, timezone

from flask import Flask, request
from flask_restx import Api, Resource, fields, reqparse
import paho.mqtt.client as mqtt


# ── Paths (project-root aware, override with env vars) ────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

MODELS_DIR = os.getenv("MODELS_DIR", os.path.join(PROJECT_ROOT, "models"))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

WASTEBIN_MODEL_FILE = os.path.join(MODELS_DIR, "wastebin.jsonld")
SENSOR_MODEL_FILE = os.path.join(MODELS_DIR, "sensor.jsonld")
EVENTS_FILE = os.path.join(DATA_DIR, "motion_events.jsonl")

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))


# ── Data loading helpers ──────────────────────────────────────────────────────
def load_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_load_list(filepath, key):
    try:
        return load_json(filepath).get(key, [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def load_events(filepath, limit=None, sensor_id=None):
    events = []
    if not os.path.exists(filepath):
        return events
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if sensor_id is not None and record.get("madeBySensor") != sensor_id:
                continue
            events.append(record)
    events.reverse()  # newest first
    if limit is not None:
        events = events[:limit]
    return events


bins_registry = safe_load_list(WASTEBIN_MODEL_FILE, "bins")
sensors_registry = safe_load_list(SENSOR_MODEL_FILE, "sensors")


def find_bin(bin_id):
    return next((b for b in bins_registry if b.get("id") == bin_id), None)


def find_sensor(sensor_id):
    return next((s for s in sensors_registry if s.get("id") == sensor_id), None)


def get_sensor_for_bin(bin_id):
    for s in sensors_registry:
        if s.get("mounted_on") == bin_id and str(s.get("model", "")).startswith("HC-SR501"):
            return s.get("id")
    # fall back to any sensor mounted on the bin
    for s in sensors_registry:
        if s.get("mounted_on") == bin_id:
            return s.get("id")
    return None


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── Flask / Flask-RESTx ───────────────────────────────────────────────────────
app = Flask(__name__)
api = Api(
    app,
    version="1.0",
    title="Smart Waste Bin API",
    description="Pull-based REST API for Smart Waste Bin data, sensors and MQTT bridge.",
    doc="/",
)

bins_ns = api.namespace("bins", description="Wastebin operations", path="/bins")
sensors_ns = api.namespace("sensors", description="Sensor operations", path="/sensors")
virtual_ns = api.namespace("virtual", description="Virtual sensors", path="/virtual")
mqtt_ns = api.namespace("mqtt", description="MQTT broker bridge", path="/mqtt")
health_ns = api.namespace("health", description="Health check", path="/health")


# ── Swagger models ────────────────────────────────────────────────────────────
bin_model = api.model("Bin", {
    "id": fields.String(required=True),
    "name": fields.String,
    "location": fields.String,
    "status": fields.String,
    "model": fields.String,
    "capacity_liters": fields.Integer,
    "monitors": fields.String,
})
sensor_model = api.model("Sensor", {
    "id": fields.String(required=True),
    "type": fields.String,
    "model": fields.String,
    "mounted_on": fields.String,
    "status": fields.String,
})
event_model = api.model("Event", {
    "startDate": fields.String(description="Event time (ISO)"),
    "resultTime": fields.String,
    "madeBySensor": fields.String,
    "hasSimpleResult": fields.String,
    "eventNumber": fields.Integer,
    "_topic": fields.String,
    "_received_at": fields.String,
})
emptied_model = api.model("EmptiedRecord", {
    "emptied_at": fields.String,
    "emptied_by": fields.String,
})
publish_model = api.model("MQTTPublish", {
    "topic": fields.String(required=True),
    "payload": fields.String(required=True),
    "qos": fields.Integer(default=1),
    "retain": fields.Boolean(default=False),
})

events_parser = reqparse.RequestParser()
events_parser.add_argument("limit", type=int, default=50, help="Max events to return")


# ── MQTT bridge (degrades gracefully) ─────────────────────────────────────────
topic_store = {}
topic_lock = threading.Lock()
mqtt_connected = {"ok": False}


def make_client():
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="wastebin-api")
    except (AttributeError, TypeError):
        return mqtt.Client(client_id="wastebin-api")


def on_connect(client, userdata, flags, rc, properties=None):
    mqtt_connected["ok"] = (rc == 0)
    if rc == 0:
        client.subscribe("smartbin/#", qos=1)
        print("[api] MQTT connected, subscribed to smartbin/#")


def on_disconnect(client, userdata, *a):
    mqtt_connected["ok"] = False


def on_message(client, userdata, msg):
    record = {
        "topic": msg.topic,
        "payload": msg.payload.decode("utf-8", errors="replace"),
        "qos": msg.qos,
        "retain": msg.retain,
        "timestamp": now_iso(),
    }
    with topic_lock:
        topic_store[msg.topic] = record


mqtt_client = make_client()
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message
try:
    mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
    mqtt_client.loop_start()
    print(f"[api] MQTT bridge -> {MQTT_BROKER}:{MQTT_PORT} (async)")
except Exception as exc:  # pragma: no cover
    print(f"[api] MQTT bridge unavailable ({exc}); REST endpoints still work.")


# ── Bins ──────────────────────────────────────────────────────────────────────
@bins_ns.route("/")
class BinList(Resource):
    @bins_ns.marshal_list_with(bin_model)
    def get(self):
        """List all registered bins."""
        return bins_registry


@bins_ns.route("/<string:bin_id>")
@bins_ns.response(404, "Bin not found")
class Bin(Resource):
    @bins_ns.marshal_with(bin_model)
    def get(self, bin_id):
        """Get one bin."""
        b = find_bin(bin_id)
        if not b:
            api.abort(404, f"Bin {bin_id} not found")
        return b


@bins_ns.route("/<string:bin_id>/events")
class BinEvents(Resource):
    @bins_ns.expect(events_parser)
    @bins_ns.marshal_list_with(event_model)
    def get(self, bin_id):
        """Get motion events for a bin (newest first)."""
        args = events_parser.parse_args()
        sensor_id = get_sensor_for_bin(bin_id)
        if sensor_id is None:
            api.abort(404, f"No sensor found for bin {bin_id}")
        return load_events(EVENTS_FILE, limit=args.get("limit"), sensor_id=sensor_id)


@bins_ns.route("/<string:bin_id>/emptied")
@bins_ns.response(201, "Bin marked as emptied")
@bins_ns.response(404, "Bin not found")
class BinEmptied(Resource):
    @bins_ns.expect(emptied_model)
    def post(self, bin_id):
        """Record that a bin was emptied and publish status to MQTT."""
        if not find_bin(bin_id):
            api.abort(404, f"Bin {bin_id} not found")
        data = request.json or {}
        record = {
            "bin_id": bin_id,
            "emptied_at": data.get("emptied_at", now_iso()),
            "emptied_by": data.get("emptied_by", "unknown"),
        }
        with open(os.path.join(DATA_DIR, "emptied_events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        mqtt_client.publish(
            f"smartbin/{bin_id}/status",
            json.dumps({"state": "emptied", "emptied_at": record["emptied_at"]}),
            qos=1, retain=True,
        )
        return record, 201


# ── Sensors ─────────────────────────────────────────────────────────────────
@sensors_ns.route("/")
class SensorList(Resource):
    @sensors_ns.marshal_list_with(sensor_model)
    def get(self):
        """List all registered sensors (physical + virtual)."""
        return sensors_registry


@sensors_ns.route("/<string:sensor_id>")
@sensors_ns.response(404, "Sensor not found")
class Sensor(Resource):
    @sensors_ns.marshal_with(sensor_model)
    def get(self, sensor_id):
        """Get one sensor."""
        s = find_sensor(sensor_id)
        if not s:
            api.abort(404, f"Sensor {sensor_id} not found")
        return s


# ── Virtual sensors (Milestone 9) ─────────────────────────────────────────────
@virtual_ns.route("/")
class VirtualSensors(Resource):
    def get(self):
        """Latest readings from the rule-based and ML virtual sensors."""
        with topic_lock:
            usage = next((v for k, v in topic_store.items() if k.endswith("/usage")), None)
            prediction = next((v for k, v in topic_store.items() if k.endswith("/prediction")), None)

        def parse(rec):
            if not rec:
                return None
            try:
                return json.loads(rec["payload"])
            except (json.JSONDecodeError, TypeError):
                return rec["payload"]

        return {"usage_intensity": parse(usage), "busy_prediction": parse(prediction)}, 200


# ── MQTT bridge endpoints ─────────────────────────────────────────────────────
@mqtt_ns.route("/publish")
class MQTTPublish(Resource):
    @mqtt_ns.expect(publish_model)
    def post(self):
        """Publish a message to an MQTT topic."""
        data = request.json or {}
        topic, payload = data.get("topic"), data.get("payload")
        qos, retain = data.get("qos", 1), data.get("retain", False)
        if not topic or payload is None:
            api.abort(400, "Both 'topic' and 'payload' are required")
        if qos not in (0, 1, 2):
            api.abort(400, "QoS must be 0, 1, or 2")
        result = mqtt_client.publish(topic, payload, qos=qos, retain=retain)
        return {"status": "published", "topic": topic, "qos": qos,
                "retain": retain, "mqtt_rc": result.rc}, 200


@mqtt_ns.route("/topics")
class MQTTTopics(Resource):
    def get(self):
        """List every known topic and its last received message."""
        with topic_lock:
            topics = list(topic_store.values())
        return {"topic_count": len(topics), "topics": topics}, 200


@mqtt_ns.route("/topics/<path:topic>")
@mqtt_ns.response(404, "No message received on that topic yet")
class MQTTTopicDetail(Resource):
    def get(self, topic):
        """Last message for one topic."""
        with topic_lock:
            if topic not in topic_store:
                api.abort(404, f"No message on topic '{topic}'")
            return topic_store[topic], 200


# ── Health ──────────────────────────────────────────────────────────────────
@health_ns.route("/")
class Health(Resource):
    def get(self):
        """Liveness + dependency status."""
        return {
            "status": "ok",
            "time": now_iso(),
            "mqtt_connected": mqtt_connected["ok"],
            "bins_loaded": len(bins_registry),
            "sensors_loaded": len(sensors_registry),
            "events_log_exists": os.path.exists(EVENTS_FILE),
        }, 200


if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "5000"))
    app.run(debug=False, host="0.0.0.0", port=port)
