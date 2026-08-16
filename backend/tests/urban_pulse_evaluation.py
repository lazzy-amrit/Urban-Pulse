"""
Realistic Urban Pulse evaluation. Talks to the real backend over real
WebSocket connections (via FastAPI's TestClient, which runs the actual
app) — no direct DB writes. Ground truth is fixed before any event is sent.

Usage:
    PYTHONPATH=. TURSO_DATABASE_URL=... TURSO_AUTH_TOKEN=... JWT_SECRET_KEY=... \
        python3 tests/urban_pulse_evaluation.py
"""

import os
import statistics
import time
import uuid

os.environ.setdefault("TURSO_DATABASE_URL", "libsql://local.db")
os.environ.setdefault("TURSO_AUTH_TOKEN", "dummy")
os.environ.setdefault("JWT_SECRET_KEY", "eval-secret")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database.database as dbmod
_engine = create_engine("sqlite:///./eval.db")
dbmod.engine = _engine
dbmod.LocalSession = sessionmaker(bind=_engine, autocommit=False, autoflush=False)

from fastapi.testclient import TestClient
import app.main as mainmod

DETECTION_THRESHOLD = 0.5
BASE_LAT, BASE_LON = 30.0000, 76.0000


def offset(lat, lon, meters_lat=0, meters_lon=0):
    return lat + meters_lat / 111_320, lon + meters_lon / 111_320


SCENARIOS = [
    {"name": "pothole_like", "is_anomaly": True,
     "features": {"accel_peak": 3.2, "gyro_peak": 1.8, "duration_ms": 300},
     "speed": 25, "phone_confidence": 0.75, "phone_severity": 0.6},
    {"name": "speed_bump", "is_anomaly": True,
     "features": {"accel_peak": 1.4, "gyro_peak": 0.5, "duration_ms": 900},
     "speed": 20, "phone_confidence": 0.6, "phone_severity": 0.4},
    {"name": "normal_smooth_road", "is_anomaly": False,
     "features": {"accel_peak": 0.15, "gyro_peak": 0.1, "duration_ms": 100},
     "speed": 30, "phone_confidence": 0.1, "phone_severity": 0.05},
    {"name": "random_movement", "is_anomaly": False,
     "features": {"accel_peak": 0.4, "gyro_peak": 0.3, "duration_ms": 150},
     "speed": 5, "phone_confidence": 0.2, "phone_severity": 0.15},
    {"name": "weak_anomaly", "is_anomaly": True,
     "features": {"accel_peak": 1.3, "gyro_peak": 0.7, "duration_ms": 400},
     "speed": 18, "phone_confidence": 0.55, "phone_severity": 0.35},
    {"name": "pothole_low_phone_confidence", "is_anomaly": True,
     "features": {"accel_peak": 3.0, "gyro_peak": 1.5, "duration_ms": 300},
     "speed": 25, "phone_confidence": 0.35, "phone_severity": 0.5},
    {"name": "normal_road_texture", "is_anomaly": False,
     "features": {"accel_peak": 0.7, "gyro_peak": 0.3, "duration_ms": 200},
     "speed": 40, "phone_confidence": 0.3, "phone_severity": 0.2},
    {"name": "aggressive_braking_false_trigger", "is_anomaly": False,
     "features": {"accel_peak": 1.6, "gyro_peak": 0.2, "duration_ms": 1200},
     "speed": 10, "phone_confidence": 0.4, "phone_severity": 0.3},
]


def make_client():
    client = TestClient(mainmod.app)
    client.__enter__()
    return client


def register(client):
    email = f"eval-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    return r.json()["access_token"]


def register_device(client, token, device_id):
    client.post("/api/v1/devices", headers={"Authorization": f"Bearer {token}"},
                json={"id": device_id, "name": "eval", "platform": "android", "app_version": "1.0"})


def send_event(dev_ws, device_id, lat, lon, scenario, ts):
    payload = {
        "device_id": device_id, "timestamp": ts, "latitude": lat, "longitude": lon,
        "speed": scenario["speed"], "heading": 90.0, "event_type": "road_anomaly",
        "confidence": scenario["phone_confidence"], "severity": scenario["phone_severity"],
        "sensor_source": "motion_fusion", "features": scenario["features"],
    }
    t0 = time.time()
    dev_ws.send_json({"type": "sensor_event", "payload": payload})
    ack = dev_ws.receive_json()
    latency = time.time() - t0
    return ack, latency


def run_detection_pass(client, label):
    print(f"\n--- PASS: {label} ---")
    token = register(client)
    headers = {"Authorization": f"Bearer {token}"}

    results = []
    for i, scenario in enumerate(SCENARIOS):
        device_id = f"dev-{uuid.uuid4().hex[:8]}"
        register_device(client, token, device_id)
        lat, lon = offset(BASE_LAT, BASE_LON, meters_lat=200 * (i + 1))  # keep issues separate
        ts = f"2026-08-16T10:{i:02d}:00Z"

        with client.websocket_connect(f"/api/v1/ws/device?token={token}&device_id={device_id}") as dev_ws:
            ack, latency = send_event(dev_ws, device_id, lat, lon, scenario, ts)

        issues = client.get("/api/v1/issues", headers=headers).json()
        issue = next((x for x in issues if x["id"] == ack["payload"]["issue_id"]), None)
        confidence = issue["confidence"] if issue else 0.0
        detected = confidence >= DETECTION_THRESHOLD

        results.append({
            "name": scenario["name"], "is_anomaly": scenario["is_anomaly"],
            "detected": detected, "confidence": confidence,
            "classification": issue["classification"] if issue else None,
            "ack_latency": latency,
        })

    tp = sum(1 for r in results if r["is_anomaly"] and r["detected"])
    fn = sum(1 for r in results if r["is_anomaly"] and not r["detected"])
    fp = sum(1 for r in results if not r["is_anomaly"] and r["detected"])
    tn = sum(1 for r in results if not r["is_anomaly"] and not r["detected"])

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    accuracy = (tp + tn) / len(results)
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    for r in results:
        mark = "TP" if r["is_anomaly"] and r["detected"] else \
               "FN" if r["is_anomaly"] and not r["detected"] else \
               "FP" if not r["is_anomaly"] and r["detected"] else "TN"
        print(f"  [{mark}] {r['name']:22s} conf={r['confidence']:.3f} class={r['classification']}")

    print(f"  accuracy={accuracy:.1%} precision={precision:.1%} recall={recall:.1%} fpr={fpr:.1%}")
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "accuracy": accuracy,
            "precision": precision, "recall": recall, "fpr": fpr, "results": results}


def run_aggregation_checks(client):
    print("\n--- AGGREGATION CHECKS ---")
    token = register(client)
    headers = {"Authorization": f"Bearer {token}"}
    strong = SCENARIOS[0]

    # same-device repeat: report_count grows, unique_device_count stays 1
    dev_id = f"dev-{uuid.uuid4().hex[:8]}"
    register_device(client, token, dev_id)
    lat, lon = offset(BASE_LAT, BASE_LON, meters_lat=5000)
    issue_id = None
    with client.websocket_connect(f"/api/v1/ws/device?token={token}&device_id={dev_id}") as ws:
        for i in range(3):
            ack, _ = send_event(ws, dev_id, lat, lon, strong, f"2026-08-16T11:{i:02d}:00Z")
            issue_id = ack["payload"]["issue_id"]
    issue = next(x for x in client.get("/api/v1/issues", headers=headers).json() if x["id"] == issue_id)
    same_device_ok = issue["unique_device_count"] == 1 and issue["report_count"] == 3 and issue["status"] != "confirmed"
    print(f"  same-device repeat: report_count={issue['report_count']} unique_device={issue['unique_device_count']} "
          f"status={issue['status']} -> {'OK' if same_device_ok else 'FAIL'}")

    # multi-device: 3 different devices, same spot -> unique_device_count should grow
    lat2, lon2 = offset(BASE_LAT, BASE_LON, meters_lat=6000)
    issue_id2 = None
    for i in range(3):
        dev = f"dev-{uuid.uuid4().hex[:8]}"
        register_device(client, token, dev)
        with client.websocket_connect(f"/api/v1/ws/device?token={token}&device_id={dev}") as ws:
            ack, _ = send_event(ws, dev, lat2, lon2, strong, f"2026-08-16T12:{i:02d}:00Z")
            issue_id2 = ack["payload"]["issue_id"]
    issue2 = next(x for x in client.get("/api/v1/issues", headers=headers).json() if x["id"] == issue_id2)
    multi_device_ok = issue2["unique_device_count"] == 3 and issue2["status"] in ("high_confidence", "confirmed")
    print(f"  multi-device: report_count={issue2['report_count']} unique_device={issue2['unique_device_count']} "
          f"status={issue2['status']} -> {'OK' if multi_device_ok else 'FAIL'}")

    # spatial separation: two strong events far apart -> two distinct issues
    dev_a = f"dev-{uuid.uuid4().hex[:8]}"
    register_device(client, token, dev_a)
    lat_a, lon_a = offset(BASE_LAT, BASE_LON, meters_lat=9000)
    lat_b, lon_b = offset(BASE_LAT, BASE_LON, meters_lat=9500)  # ~500m away, outside 15m radius
    with client.websocket_connect(f"/api/v1/ws/device?token={token}&device_id={dev_a}") as ws:
        ack_a, _ = send_event(ws, dev_a, lat_a, lon_a, strong, "2026-08-16T13:00:00Z")
        ack_b, _ = send_event(ws, dev_a, lat_b, lon_b, strong, "2026-08-16T13:01:00Z")
    separation_ok = ack_a["payload"]["issue_id"] != ack_b["payload"]["issue_id"]
    print(f"  spatial separation: {ack_a['payload']['issue_id']} vs {ack_b['payload']['issue_id']} "
          f"-> {'OK' if separation_ok else 'FAIL'}")

    # vision-supported: sensor event then vision_event nearby should not lower confidence
    dev_v = f"dev-{uuid.uuid4().hex[:8]}"
    register_device(client, token, dev_v)
    lat_v, lon_v = offset(BASE_LAT, BASE_LON, meters_lat=10000)
    with client.websocket_connect(f"/api/v1/ws/device?token={token}&device_id={dev_v}") as ws:
        ack_v, _ = send_event(ws, dev_v, lat_v, lon_v, SCENARIOS[4], "2026-08-16T14:00:00Z")
        before = next(x for x in client.get("/api/v1/issues", headers=headers).json() if x["id"] == ack_v["payload"]["issue_id"])
        ws.send_json({"type": "vision_event", "payload": {
            "device_id": dev_v, "timestamp": "2026-08-16T14:00:05Z",
            "latitude": lat_v, "longitude": lon_v,
            "detections": [{"class": "road_surface_anomaly", "confidence": 0.9, "bbox": [0, 0, 10, 10]}],
        }})
    time.sleep(0.2)
    after = next(x for x in client.get("/api/v1/issues", headers=headers).json() if x["id"] == ack_v["payload"]["issue_id"])
    vision_ok = after["confidence"] >= before["confidence"]
    print(f"  vision evidence: {before['confidence']:.3f} -> {after['confidence']:.3f} -> {'OK' if vision_ok else 'FAIL'}")

    return {"same_device_ok": same_device_ok, "multi_device_ok": multi_device_ok,
            "separation_ok": separation_ok, "vision_ok": vision_ok}


def run_burst_pass(client, n_events=30):
    print(f"\n--- PASS: burst/stress ({n_events} events) ---")
    token = register(client)
    dev_id = f"dev-{uuid.uuid4().hex[:8]}"
    register_device(client, token, dev_id)

    latencies = []
    failures = 0
    with client.websocket_connect(f"/api/v1/ws/device?token={token}&device_id={dev_id}") as ws:
        for i in range(n_events):
            lat, lon = offset(BASE_LAT, BASE_LON, meters_lat=20000 + i * 50)
            scenario = SCENARIOS[i % len(SCENARIOS)]
            try:
                _, latency = send_event(ws, dev_id, lat, lon, scenario, f"2026-08-16T15:{i%60:02d}:00Z")
                latencies.append(latency)
            except Exception:
                failures += 1

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)] if latencies else 0
    p95 = latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)] if latencies else 0
    print(f"  sent={n_events} ok={len(latencies)} failed={failures}")
    print(f"  ack latency: mean={statistics.mean(latencies):.3f}s p50={p50:.3f}s p95={p95:.3f}s")
    return {"sent": n_events, "ok": len(latencies), "failed": failures, "p50": p50, "p95": p95}


if __name__ == "__main__":
    import subprocess
    subprocess.run(["rm", "-f", "eval.db"])

    client = make_client()

    from app.intelligence import ai_provider
    print("Gemini configured for this run:", ai_provider.is_configured())

    pass1 = run_detection_pass(client, "AI enabled (Gemini configured)" if ai_provider.is_configured() else "AI not configured — fallback only")
    agg = run_aggregation_checks(client)
    burst = run_burst_pass(client)

    from app.intelligence.classifier import stats as gemini_stats
    print("\n--- GEMINI STATS ---")
    print(gemini_stats)

    subprocess.run(["rm", "-f", "eval.db"])
