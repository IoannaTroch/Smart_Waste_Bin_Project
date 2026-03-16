import time
import argparse
import json
import sys
import uuid
import threading
from queue import Queue, Full, Empty
from datetime import datetime, timezone

from sensors.pir_sampler import PirSampler
from sensors.pir_interpreter import PirInterpreter

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def parse_iso_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def producer_loop(event_q, sampler, interp, args, metrics, stop_flag):
    run_id = str(uuid.uuid4())
    seq = 0

    while not stop_flag["stop"]:
        now = time.time()
        raw = sampler.read()

        for _ev in interp.update(raw, now):
            seq += 1
            rec = {
                "event_time": utc_now_iso(),
                "device_id": args.device_id,
                "event_type": "motion",
                "motion_state": "detected",
                "seq": seq,
                "run_id": run_id,
            }
            try:
                # Drop-newest policy: if full, it raises Full immediately
                event_q.put_nowait(rec)
                metrics["produced"] += 1
            except Full:
                metrics["dropped"] += 1

        time.sleep(args.sample_interval)

def consumer_loop(event_q, out_path, args, metrics, stop_flag):
    with open(out_path, "a", encoding="utf-8") as f:
        # Continue running if not stopped OR if there are still items to drain
        while (not stop_flag["stop"]) or (not event_q.empty()):
            try:
                rec = event_q.get(timeout=0.5)
            except Empty:
                continue

            # Enrichment step
            rec["ingest_time"] = utc_now_iso()
            event_dt = parse_iso_utc(rec["event_time"])
            ingest_dt = parse_iso_utc(rec["ingest_time"])
            rec["pipeline_latency_ms"] = int((ingest_dt - event_dt).total_seconds() * 1000)

            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()

            metrics["consumed"] += 1
            metrics["max_queue"] = max(metrics["max_queue"], event_q.qsize())
            event_q.task_done()

            # Simulate downstream slowdown
            if args.consumer_delay > 0:
                time.sleep(args.consumer_delay)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device-id", required=True)
    p.add_argument("--pin", type=int, required=True)
    p.add_argument("--sample-interval", type=float, default=0.1)
    p.add_argument("--cooldown", type=float, default=5.0)
    p.add_argument("--min-high", type=float, default=0.2)
    p.add_argument("--queue-size", type=int, default=100)
    p.add_argument("--consumer-delay", type=float, default=0.0)
    p.add_argument("--duration", type=float, default=60.0)
    p.add_argument("--out", required=True)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    sampler = PirSampler(args.pin)
    interp = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)
    
    event_q = Queue(maxsize=args.queue_size)
    metrics = {"produced": 0, "consumed": 0, "dropped": 0, "max_queue": 0}
    stop_flag = {"stop": False}

    producer_t = threading.Thread(target=producer_loop, args=(event_q, sampler, interp, args, metrics, stop_flag), daemon=True)
    consumer_t = threading.Thread(target=consumer_loop, args=(event_q, args.out, args, metrics, stop_flag), daemon=True)

    print(f"Starting pipeline (Duration: {args.duration}s)...")
    producer_t.start()
    consumer_t.start()

    start_t = time.time()
    try:
        while (time.time() - start_t) < args.duration:
            if args.verbose:
                print(f"[status] produced={metrics['produced']} consumed={metrics['consumed']} dropped={metrics['dropped']} queue={event_q.qsize()} max_queue={metrics['max_queue']}")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[main] Ctrl-C: stopping...")
    finally:
        stop_flag["stop"] = True
        producer_t.join()
        consumer_t.join()
        print("Clean shutdown complete. Data saved.")

if __name__ == "__main__":
    main()