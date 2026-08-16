"""
Evidence-aggregation pipeline. ingest_sensor_event() is the fast synchronous
path (spatial match, persist, aggregate) driven by a locally-computed
interpretation — no network calls, so it's safe to run inline in the
WebSocket loop. apply_ai_refinement() is called later, from a background
task, once/if Gemini finishes; it recomputes the same issue with the
better classification.
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
from app.intelligence.ai_provider import AIInterpretation
from app.issues.clustering import find_nearby_issue
from app.issues.confidence import calculate_final_confidence, calculate_final_severity

logger = logging.getLogger("urban_pulse.issues")


def _next_issue_id(db: Session) -> str:
    count = db.query(func.count(RoadIssue.id)).scalar() or 0
    return f"{ISSUE_ID_PREFIX}{str(count + 1).zfill(ISSUE_ID_PAD)}"


def get_prior_counts(db: Session, latitude: float, longitude: float) -> tuple[int, int]:
    """
    Report/unique-device counts for whatever issue already sits at this
    location, if any. Used to build the *first-pass* fallback interpretation
    with real evidence instead of always assuming a brand-new location —
    otherwise repeat/independent-device signal never reaches the classifier
    when Gemini is unavailable.
    """
    issue = find_nearby_issue(db, latitude, longitude)
    if issue is None:
        return 0, 0
    return issue.report_count, issue.unique_device_count


def calculate_status(report_count: int, unique_device_count: int, confidence: float) -> str:
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
    if ai_classification == "unknown":
        return current if current != "unknown" else "unknown"
    if status == "likely" and current != "unknown":
        return current
    return ai_classification


def _recompute_issue(
    db: Session,
    issue: RoadIssue,
    phone_confidence: float | None,
    phone_severity: float | None,
    interpretation: AIInterpretation,
    matched_within_radius: bool,
    vision_evidence_present: bool,
    timestamp: datetime,
) -> None:
    report_count = db.query(func.count(SensorReport.id)).filter(SensorReport.issue_id == issue.id).scalar() or 0
    unique_device_count = (
        db.query(func.count(func.distinct(SensorReport.device_id)))
        .filter(SensorReport.issue_id == issue.id)
        .scalar()
        or 0
    )

    confidence = calculate_final_confidence(
        phone_confidence=phone_confidence,
        ai_confidence=interpretation.confidence,
        report_count=report_count,
        unique_device_count=unique_device_count,
        matched_within_radius=matched_within_radius,
        vision_evidence_present=vision_evidence_present,
    )
    severity = calculate_final_severity(
        ai_severity=interpretation.severity,
        phone_severity=phone_severity,
        report_count=report_count,
    )
    status = calculate_status(report_count, unique_device_count, confidence)
    classification = _resolve_classification(issue.classification, interpretation.classification, status)

    issue.report_count = report_count
    issue.unique_device_count = unique_device_count
    issue.confidence = confidence
    issue.severity = severity
    issue.status = status
    issue.classification = classification
    issue.last_seen = timestamp
    db.commit()
    db.refresh(issue)


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
    interpretation: AIInterpretation,
) -> tuple[SensorReport, RoadIssue]:
    matched_issue = find_nearby_issue(db, latitude, longitude)

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
        db.flush()
    else:
        issue = matched_issue

    report.issue_id = issue.id
    db.add(report)
    db.flush()

    _recompute_issue(
        db,
        issue,
        phone_confidence=phone_confidence,
        phone_severity=phone_severity,
        interpretation=interpretation,
        matched_within_radius=True,
        vision_evidence_present=False,
        timestamp=timestamp,
    )
    db.refresh(report)

    logger.info(
        "event ingested: device=%s issue=%s status=%s confidence=%.2f",
        device.id, issue.id, issue.status, issue.confidence,
    )
    return report, issue


def apply_ai_refinement(db: Session, report_id: str, interpretation: AIInterpretation) -> tuple[SensorReport, RoadIssue] | None:
    report = db.query(SensorReport).filter(SensorReport.id == report_id).first()
    if report is None or report.issue_id is None:
        return None

    issue = db.query(RoadIssue).filter(RoadIssue.id == report.issue_id).first()
    if issue is None:
        return None

    report.ai_classification = interpretation.classification
    report.ai_confidence = interpretation.confidence
    db.commit()

    _recompute_issue(
        db,
        issue,
        phone_confidence=report.phone_confidence,
        phone_severity=report.phone_severity,
        interpretation=interpretation,
        matched_within_radius=True,
        vision_evidence_present=False,
        timestamp=report.timestamp,
    )
    db.refresh(report)
    logger.info("AI refinement applied: issue=%s status=%s confidence=%.2f", issue.id, issue.status, issue.confidence)
    return report, issue


def list_issues_for_user(db: Session, user_id: str) -> list[RoadIssue]:
    return (
        db.query(RoadIssue)
        .join(SensorReport, SensorReport.issue_id == RoadIssue.id)
        .join(Device, Device.id == SensorReport.device_id)
        .filter(Device.user_id == user_id)
        .distinct()
        .order_by(RoadIssue.last_seen.desc())
        .all()
    )
