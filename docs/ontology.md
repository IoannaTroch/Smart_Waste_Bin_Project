# Smart Wastebin — Custom Ontology Terms

Base namespace: `https://github.com/IoannaTroch/Smart_Waste_Bin_Project/blob/main/docs/ontology.md#`

Prefix used in JSON-LD: `pipeline`

## Pipeline Terms

### sequenceNumber
- **Type:** `xsd:integer`
- **Description:** Monotonically increasing counter assigned by the producer to each event record within a single pipeline run. Used to detect gaps or reordering in the stream.

### runId
- **Type:** `xsd:string`
- **Description:** Unique identifier for a single execution of the pipeline. All records sharing the same runId were produced in the same run session.

### pipelineLatencyMs
- **Type:** `xsd:float`
- **Description:** Time in milliseconds between the moment the producer created the event (event_time) and the moment the consumer ingested it (ingest_time). Measures end-to-end queue transit time.

### ingestTime
- **Type:** `xsd:dateTime`
- **Description:** ISO 8601 timestamp recording the moment the pipeline consumer received and processed the event record.

### motionState
- **Type:** `xsd:string`
- **Allowed values:** `detected`, `cleared`
- **Description:** The discrete outcome of the PIR observation. `detected` means at least one warm body crossed the detection cone during the observation window. `cleared` means no motion was detected during the cooldown period following a prior detection.

## Sensor Terms

### gpioPin
- **Type:** `xsd:integer`
- **Description:** BCM-numbered GPIO pin on the Raspberry Pi to which the sensor's signal output line is connected.

### detectionRangeMeters
- **Type:** `xsd:float`
- **Description:** Maximum radial distance in metres at which the sensor can reliably detect a moving warm body, as adjusted via the sensitivity potentiometer.

### detectionAngleDegrees
- **Type:** `xsd:float`
- **Description:** Full cone angle in degrees of the sensor's detection field, determined by the Fresnel lens geometry.

### cooldownSeconds
- **Type:** `xsd:float`
- **Description:** Minimum wait time in seconds enforced by the pipeline after a detection event before a new detection can be registered. Corresponds to the software debounce period implemented in Lab 02.

### triggerMode
- **Type:** `xsd:string`
- **Allowed values:** `H`, `L`
- **Description:** Hardware jumper setting on the HC-SR501 module. `H` enables repeatable triggering (output stays high while motion persists); `L` disables repeat triggering (single pulse per crossing).

## Wastebin Terms

### fillLevelPercent
- **Type:** `xsd:float`
- **Description:** Current fill level of the wastebin expressed as a percentage of total capacity (0.0 = empty, 100.0 = full). Updated by sensor readings in the full project.