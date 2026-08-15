"""
Core evidence-aggregation pipeline. This is where a validated sensor event
turns into a RoadIssue creation/update: spatial matching -> AI interpretation
-> aggregation -> confidence/severity/status/classification -> persistence.
"""

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import (
    ISSUE_ID_PREFIX,
    ISSUE_ID_PAD,
    STATUS_REPEATING_MIN_REPORTS,
    STATUS_HIGH_CONFIDENCE_MIN_REPORTS,
    STATUS_HIGH_CONFIDENCE_MIN_UNIQUE_DEVICES,
    STATUS_HIGH_CONFIDENCE_MIN_CONFIDENCE,
    STATUS_CONFIRMED_MIN_REPORTS,
    STATUS_CONFIRMED_MIN_UNIQUE_DEVICES,
    STATUS_CONFIRMED_MIN_CONFIDENCE,
)
from app.database.models import RoadIssue, SensorReport, Device
from app.intelligence.classifier import analyze_sensor_event
from app.issues.clustering import find_nearby_issue
from app.issues.confidence import calculate_final_confidence, calculate_final_severity

logger = logging.getLogger("urban_pulse.issues")


def _next_issue_id(db: Session) -> str:
    count = db.query(func.count(RoadIssue.id)).scalar() or 0
    return f"{ISSUE_ID_PREFIX}{str(count + 1).zfill(ISSUE_ID_PAD)}"


def _calculate_status(report_count: int, unique_device_count: int, confidence: float) -> str:
    """
    Backend-owned status thresholds. Hackathon defaults, all named constants
    in app/core/config.py — nothing scattered inline.
    """
    if (
        report_count >= STATUS_CONFIRMED_MIN_REPORTS
        and unique_device_count >= STATUS_CONFIRMED_MIN_UNIQUE_DEVICES
        and confidence >= STATUS_CONFIRMED_MIN_CONFIDENCE
    ):
        return "confirmed"

    if (
        report_count >= STATUS_HIGH_CONFIDENCE_MIN_REPORTS
        and unique_device_count >= STATUS_HIGH_CONFIDENCE_MIN_UNIQUE_DEVICES
        and confidence >= STATUS_HIGH_CONFIDENCE_MIN_CONFIDENCE
    ):
        return "high_confidence"

    if report_count >= STATUS_REPEATING_MIN_REPORTS:
        return "repeating"

    return "likely"


def _resolve_classification(current: str, ai_classification: str, status: str) -> str:
    """
    The AI proposes a classification per-event; the issue's overall
    classification only strengthens toward a specific type (e.g.
    pothole_likely) when the accumulated status actually supports it.
    A single ambiguous read should not overwrite a previously well-evidenced
    classification with "unknown".
    """
    if ai_classification == "unknown":
        return current if current != "unknown" else "unknown"

    if status in ("likely",):
        # Not enough accumulated evidence yet — keep it generic unless we
        # have nothing better.
        return ai_classification if current == "unknown" else current or ai_classification

    return ai_classification


def ingest_sensor_event(
    db: Session,
    device: Device,
    timestamp: datetime,
    latitude: float,
    longitude: float,
    speed: float | None,
    heading: float | None,
    event_type: str,
    phone_confidence: float | None,
    phone_severity: float | None,
    sensor_source: str | None,
    features: dict[str, Any] | None,
    vision_evidence: list[dict[str, Any]] | None = None,
) -> tuple[SensorReport, RoadIssue]:
    """
    Full pipeline for one incoming sensor_event message. Returns the
    persisted SensorReport and the RoadIssue it was attributed to.
    """

    # 1. Spatial matching against existing (non-resolved) issues.
    matched_issue = find_nearby_issue(db, latitude, longitude)

    prior_report_count = matched_issue.report_count if matched_issue else 0
    prior_unique_device_count = matched_issue.unique_device_count if matched_issue else 0

    # 2. AI / rule-based interpretation of this specific event.
    interpretation = analyze_sensor_event(
        event_type=event_type,
        phone_confidence=phone_confidence,
        phone_severity=phone_severity,
        sensor_source=sensor_source,
        features=features,
        speed=speed,
        heading=heading,
        prior_report_count=prior_report_count,
        prior_unique_device_count=prior_unique_device_count,
        vision_evidence=vision_evidence,
    )

    # 3. Persist the raw sensor report (evidence), linked once we know the issue id.
    report = SensorReport(
        device_id=device.id,
        timestamp=timestamp,
        latitude=latitude,
        longitude=longitude,
        speed=speed,
        heading=heading,
        event_type=event_type,
        phone_confidence=phone_confidence,
        phone_severity=phone_severity,
        sensor_source=sensor_source,
        features_json=json.dumps(features) if features else None,
        ai_classification=interpretation.classification,
        ai_confidence=interpretation.confidence,
    )

    # 4. Find-or-create the RoadIssue.
    if matched_issue is None:
        issue = RoadIssue(
            id=_next_issue_id(db),
            latitude=latitude,
            longitude=longitude,
            status="likely",
            classification="unknown",
            confidence=0.0,
            severity=0.0,
            report_count=0,
            unique_device_count=0,
            first_seen=timestamp,
            last_seen=timestamp,
        )
        db.add(issue)
        db.flush()  # assign id before linking report
    else:
        issue = matched_issue

    report.issue_id = issue.id
    db.add(report)
    db.flush()

    # 5. Aggregate evidence: report_count and unique_device_count from actual rows,
    #    so counts never drift from reality even under concurrent writes.
    report_count = db.query(func.count(SensorReport.id)).filter(SensorReport.issue_id == issue.id).scalar() or 0
    unique_device_count = (
        db.query(func.count(func.distinct(SensorReport.device_id)))
        .filter(SensorReport.issue_id == issue.id)
        .scalar()
        or 0
    )

    matched_within_radius = matched_issue is not None or report_count == 1

    final_confidence = calculate_final_confidence(
        phone_confidence=phone_confidence,
        ai_confidence=interpretation.confidence,
        report_count=report_count,
        unique_device_count=unique_device_count,
        matched_within_radius=matched_within_radius,
        vision_evidence_present=bool(vision_evidence),
    )
    final_severity = calculate_final_severity(
        ai_severity=interpretation.severity,
        phone_severity=phone_severity,
        report_count=report_count,
    )
    final_status = _calculate_status(report_count, unique_device_count, final_confidence)
    final_classification = _resolve_classification(issue.classification, interpretation.classification, final_status)

    issue.report_count = report_count
    issue.unique_device_count = unique_device_count
    issue.confidence = final_confidence
    issue.severity = final_severity
    issue.status = final_status
    issue.classification = final_classification
    issue.last_seen = timestamp

    db.commit()
    db.refresh(issue)
    db.refresh(report)

    logger.info(
        "sensor event ingested: device=%s issue=%s status=%s confidence=%.2f",
        device.id,
        issue.id,
        issue.status,
        issue.confidence,
    )

    return report, issue


def list_issues_for_user(db: Session, user_id: str) -> list[RoadIssue]:
    """
    Issues relevant to the authenticated user's own devices (not the global
    map — that's served over WS /api/v1/ws/map).
    """
    return (
        db.query(RoadIssue)
        .join(SensorReport, SensorReport.issue_id == RoadIssue.id)
        .join(Device, Device.id == SensorReport.device_id)
        .filter(Device.user_id == user_id)
        .distinct()
        .order_by(RoadIssue.last_seen.desc())
        .all()
    )
