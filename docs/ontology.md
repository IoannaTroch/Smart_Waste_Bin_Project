# Smart Waste Bin — Data Model & Ontology (Milestone 5)

This document describes how the Smart Waste Bin system is modelled with **JSON-LD**.
The goal is to describe the sensors, the bins, and the deployment environment as
structured entities with explicit, machine-readable relationships, reusing
established vocabularies instead of inventing everything from scratch.

## Vocabularies reused

| Prefix     | Namespace                              | Used for |
|------------|----------------------------------------|----------|
| `schema`   | https://schema.org/                    | Names, locations, generic things, events |
| `sosa`     | http://www.w3.org/ns/sosa/             | Sensors and observations (SOSA/SSN) |
| `geo`      | http://www.w3.org/2003/01/geo/wgs84_pos# | Latitude / longitude |
| `smartbin` | urn:smartbin:vocab#                    | Project-specific terms (bins, usage intensity) |

The shared `@context` lives in [`models/context.jsonld`](../models/context.jsonld)
and is referenced by every other model file, so terms are defined once.

## Entities

### Wastebin (`models/wastebin.jsonld`)
A physical container being monitored. Key properties: `id`, `name`, `location`,
`status`, `capacity_liters`, `fill_threshold_pct`. A bin is `deployedIn` an
Environment and `monitors`-ed by a Sensor.

### Sensor (`models/sensor.jsonld`)
A device (physical or virtual) producing observations. Key properties: `id`,
`type`, `model`, `status`, `observedProperty`. A sensor is `mounted_on` a bin.
The registry includes the physical PIR sensors **and** the two virtual sensors
from Milestone 9 (rule-based usage intensity, ML busy-period predictor).

### Environment (`models/environment.jsonld`)
The deployment context (the lab room): `id`, `name`, `location`, geo-coordinates,
and which bins it `contains`.

### Observation (runtime, on the wire)
Each motion event published to `smartbin/<bin>/<device>/events` is itself a small
JSON-LD document (`@type: Event`) carrying `startDate`, `madeBySensor`,
`hasSimpleResult`, and `location`, so the event stream is self-describing.

## Relationship graph

```
Environment(env-lab-101)
   └── contains ──> Wastebin(bin-01) ── monitors ──> Sensor(pir-01)  [HC-SR501]
                          ▲                                   │
                          │ mounted_on  ──────────────────────┘
                          ├── monitored by ──> Sensor(vs-usage-01)  [rule-based]
                          └── monitored by ──> Sensor(vs-predict-01) [ML]
```

## Why this matters
Because every entity carries a stable `@id` and typed relationships, the same
model drives the REST API (`/bins`, `/sensors`), labels Home Assistant entities,
and lets the analytics layer join events back to the bin and sensor that produced
them — all without hard-coding identifiers in the application logic.
