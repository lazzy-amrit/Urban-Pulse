# Urban Pulse API Reference

Base URL (local dev): `http://localhost:8000`
All request/response bodies are JSON unless noted. All timestamps are ISO-8601 UTC.

---

## 1. Authentication

Urban Pulse uses JWT bearer tokens. There is no refresh token — tokens last **30 days**, after which the user must log in again.

Every protected endpoint requires this header:

```
Authorization: Bearer <access_token>
```

WebSockets can't send custom headers from a browser, so both WS endpoints take the token as a **query parameter** instead (see section 4).

### Error format

Every error response (any non-2xx) has this shape:

```json
{
  "detail": {
    "code": "ERROR_CODE",
    "message": "Human readable message"
  }
}
```

Common `code` values: `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `BAD_REQUEST`, `VALIDATION_ERROR`.

---

## 2. REST Endpoints

### 2.1 `POST /api/v1/auth/register`

Create a new account. Returns a token immediately (auto-login on register).

**Request**
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```
- `password`: 8–128 characters.

**Response `201`**
```json
{
  "user": {
    "id": "b0e4e1a6-2efa-4675-b289-fe03cea9b736",
    "email": "user@example.com",
    "created_at": "2026-08-15T15:33:01.381137"
  },
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer"
}
```

**Errors**: `409 CONFLICT` if the email is already registered.

---

### 2.2 `POST /api/v1/auth/login`

**Request**
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**Response `200`** — same shape as register.

**Errors**: `401 UNAUTHORIZED` on wrong email/password (message is generic, doesn't reveal which was wrong).

---

### 2.3 `GET /api/v1/auth/me` 🔒

**Response `200`**
```json
{
  "id": "b0e4e1a6-2efa-4675-b289-fe03cea9b736",
  "email": "user@example.com",
  "created_at": "2026-08-15T15:33:01.381137"
}
```

---

### 2.4 `PATCH /api/v1/auth/me` 🔒

Currently only supports changing email. Requires the current password as confirmation.

**Request**
```json
{
  "email": "newemail@example.com",
  "current_password": "password123"
}
```

**Response `200`** — updated `UserOut` object (same shape as `GET /me`).

**Errors**: `401` if `current_password` is wrong, `409` if the new email is already taken.

---

### 2.5 `POST /api/v1/auth/change-password` 🔒

**Request**
```json
{
  "current_password": "password123",
  "new_password": "newPassword456"
}
```

**Response**: `204 No Content` (empty body) on success.
**Errors**: `401` if `current_password` is wrong.

---

### 2.6 `POST /api/v1/auth/forgot-password`

No auth required. Always returns the same generic message regardless of whether the email exists — **don't** use this response to tell the user "email not found".

**Request**
```json
{ "email": "user@example.com" }
```

**Response `200`**
```json
{ "message": "If the account exists, a password reset code has been sent." }
```

A 6-digit OTP is emailed to the user (valid 10 minutes, single use, 5 attempts max). If no email provider is configured server-side (hackathon/dev mode), the OTP is generated but not actually delivered — check server logs.

---

### 2.7 `POST /api/v1/auth/reset-password`

**Request**
```json
{
  "email": "user@example.com",
  "otp": "123456",
  "new_password": "newPassword456"
}
```

**Response**: `204 No Content` on success.
**Errors**: `400 BAD_REQUEST` for any invalid/expired/already-used OTP, or too many attempts — the message is intentionally generic ("Invalid or expired code.") for all these cases.

---

### 2.8 `POST /api/v1/devices` 🔒

Registers a device, or updates it if the same `id` already exists **for this user**. The device ID is generated client-side by the app (a random UUID is fine) — never use a hardware identifier (IMEI, MAC, etc).

**Request**
```json
{
  "id": "a1b2c3d4-...-device-uuid",
  "name": "My Phone",
  "platform": "android",
  "app_version": "1.0.0"
}
```

**Response `201`**
```json
{
  "id": "a1b2c3d4-...-device-uuid",
  "name": "My Phone",
  "platform": "android",
  "app_version": "1.0.0",
  "created_at": "2026-08-15T15:33:02.962902",
  "last_seen": "2026-08-15T15:33:02.962905"
}
```

**Errors**: `403 FORBIDDEN` if that device `id` is already registered to a *different* account.

---

### 2.9 `GET /api/v1/devices` 🔒

Returns only the current user's devices.

**Response `200`**
```json
[
  {
    "id": "a1b2c3d4-...",
    "name": "My Phone",
    "platform": "android",
    "app_version": "1.0.0",
    "created_at": "2026-08-15T15:33:02.962902",
    "last_seen": "2026-08-15T15:33:02.962905"
  }
]
```

---

### 2.10 `GET /api/v1/issues` 🔒

Issues linked to reports from **the current user's own devices** — not the global map (that's the map WebSocket, section 4.2).

**Response `200`**
```json
[
  {
    "id": "UP-000001",
    "latitude": 30.12345,
    "longitude": 75.45678,
    "status": "repeating",
    "classification": "impact_event",
    "confidence": 0.4673,
    "severity": 0.628,
    "report_count": 3,
    "unique_device_count": 2,
    "first_seen": "2026-08-15T14:00:00",
    "last_seen": "2026-08-15T14:02:00"
  }
]
```

See section 5 for what `status`/`classification`/`confidence`/`severity` actually mean — this is the same shape used by the map WebSocket broadcasts.

---

### 2.11 `GET /api/v1/health`

No auth. Liveness check.

```json
{ "status": "ok" }
```

---

## 3. Field validation rules (apply everywhere)

| Field | Rule |
|---|---|
| `latitude` | -90 to 90 |
| `longitude` | -180 to 180 |
| `confidence` | 0.0 to 1.0 |
| `severity` | 0.0 to 1.0 |
| `speed` | >= 0 |
| `timestamp` | valid ISO-8601 |

---

## 4. WebSocket Endpoints

### 4.1 `WS /api/v1/ws/device` — phone → backend

**Connect:**
```
ws://localhost:8000/api/v1/ws/device?token=<JWT>&device_id=<your-device-id>
```
The device must already be registered via `POST /api/v1/devices` under the same account the token belongs to. Server closes with code `4401` (bad/missing token) or `4403` (device belongs to someone else / not registered) on auth failure.

**⚠️ Do not stream raw accelerometer samples.** The phone does its own local trigger + feature extraction, and only sends a `sensor_event` when something meaningful happened.

#### Outgoing message types (client → server)

**`sensor_event`** — the main event. Sent when the phone's local trigger fires.
```json
{
  "type": "sensor_event",
  "payload": {
    "device_id": "a1b2c3d4-...",
    "timestamp": "2026-08-15T14:00:00Z",
    "latitude": 30.12345,
    "longitude": 75.45678,
    "speed": 31.4,
    "heading": 181.2,
    "event_type": "road_anomaly",
    "confidence": 0.71,
    "severity": 0.42,
    "sensor_source": "motion_fusion",
    "features": {
      "accel_peak": 2.8,
      "gyro_peak": 1.4,
      "duration_ms": 380
    }
  }
}
```
> Everything under `payload` here is **evidence**, not a verdict. `event_type`, `confidence`, `severity` are what the phone *thinks* happened — the backend independently re-evaluates all of it (via AI + rule-based fallback) and computes its own numbers. Don't display the phone's own `confidence`/`severity` to the user as if it were final — wait for the server's `event_ack` / map broadcast.
>
> `features` is a free-form object — send whatever your local feature extraction produces (accel/gyro peaks, duration, etc). Not schema-locked.

**`heartbeat`** — periodic keepalive, updates `last_seen` on the device.
```json
{ "type": "heartbeat", "payload": { "device_id": "a1b2c3d4-..." } }
```

**`sensor_status`** — lightweight status ping (e.g. which sensors are currently active, battery level). Currently just updates `last_seen` server-side.
```json
{
  "type": "sensor_status",
  "payload": {
    "device_id": "a1b2c3d4-...",
    "sensors_active": ["accelerometer", "gyroscope"],
    "battery_level": 0.62
  }
}
```

**`vision_event`** — only sent when the user explicitly activates "Ultra Vision". Not continuous.
```json
{
  "type": "vision_event",
  "payload": {
    "device_id": "a1b2c3d4-...",
    "timestamp": "2026-08-15T14:00:00Z",
    "latitude": 30.12345,
    "longitude": 75.45678,
    "detections": [
      { "class": "road_surface_anomaly", "confidence": 0.91, "bbox": [120, 240, 400, 500] }
    ]
  }
}
```
Note: vision evidence only strengthens an issue that already exists nearby (from a prior `sensor_event`). It cannot create a new issue by itself.

#### Incoming message types (server → client)

**`event_ack`** — sent back after every `sensor_event`, tells you which issue it landed on and the issue's *current* status.
```json
{
  "type": "event_ack",
  "payload": {
    "event_id": "43a74a2f-239b-44c5-aab6-98618496a85b",
    "issue_id": "UP-000001",
    "status": "likely"
  }
}
```

---

### 4.2 `WS /api/v1/ws/map` — backend → frontend (live map)

**Connect:**
```
ws://localhost:8000/api/v1/ws/map?token=<JWT>
```

On connect, the server immediately sends one `issue_created` message per currently-active (non-resolved) issue, so you can populate the map on load. After that, it pushes live updates as they happen — no polling needed.

#### Incoming message types (server → client)

All three share the same payload shape:

```json
{
  "type": "issue_created",
  "payload": {
    "id": "UP-000001",
    "latitude": 30.12345,
    "longitude": 75.45678,
    "classification": "road_anomaly",
    "status": "likely",
    "confidence": 0.68,
    "severity": 0.42,
    "report_count": 1,
    "unique_device_count": 1,
    "created_at": "2026-08-15T15:33:01.381137",
    "updated_at": "2026-08-15T15:33:01.381137"
  }
}
```

- `issue_created` — a brand-new issue appeared (or, on connect, an existing active one).
- `issue_updated` — an existing issue got new evidence (confidence/status/classification may have changed).
- `issue_resolved` — issue marked resolved (e.g. road repaired) — remove/gray it out on your map.

**Do not calculate confidence, status, or classification on the frontend.** Just render what the server sends — it's already the fully-aggregated result.

---

## 5. Understanding the issue fields

### `status` — how much evidence exists (escalates only, never guessed by the phone)

| Value | Meaning |
|---|---|
| `likely` | Single report so far. |
| `repeating` | 2+ reports at this spot. |
| `high_confidence` | 3+ reports **from 2+ different devices**, confidence ≥ 0.60. |
| `confirmed` | 5+ reports from 2+ devices, confidence ≥ 0.82. |
| `resolved` | Manually/administratively marked fixed (not currently exposed via a public endpoint). |

A single device spamming reports from one phone can *not* reach `high_confidence` or `confirmed` alone — independent devices matter more than repeat count.

### `classification` — what kind of anomaly this probably is

`road_anomaly` · `surface_irregularity` · `impact_event` · `pothole_likely` · `speed_bump_likely` · `unknown`

This is always the backend's best current guess, not a phone-reported label. It only strengthens toward a specific type (e.g. `pothole_likely`) as more independent evidence accumulates — never trust a single low-evidence event to mean "confirmed pothole" in your UI copy. Suggested UI phrasing: use "likely road anomaly" / "repeating road anomaly" / "high-confidence road anomaly" / "confirmed road issue" rather than flatly saying "pothole" until `status` is `confirmed`.

### `confidence` / `severity` — both floats 0.0–1.0, and they mean different things

- **`confidence`** = how sure the backend is that this is a real, distinct road issue (driven by evidence quantity + independence + spatial tightness).
- **`severity`** = how bad the anomaly itself is (driven by sensor intensity — accel/gyro peaks). A single very sharp bump can have **high severity but low confidence** if it's only been reported once. Don't conflate the two in your UI (e.g. don't use severity color-coding to imply "this is definitely real").

---

## 6. Typical frontend flow

1. `POST /auth/register` or `/auth/login` → store `access_token`.
2. `POST /api/v1/devices` once per device (idempotent — safe to call every app launch).
3. Open `WS /api/v1/ws/map?token=...` on the map screen → render the initial batch of `issue_created` messages, then keep listening for `issue_updated`/`issue_resolved` to live-update markers.
4. On the phone-sensing side: open `WS /api/v1/ws/device?token=...&device_id=...`, send `sensor_event` when the local trigger fires, send periodic `heartbeat`, listen for `event_ack` to show local feedback ("reported!").
5. `GET /api/v1/issues` for a "my reports" screen — issues tied to the logged-in user's own devices specifically.
