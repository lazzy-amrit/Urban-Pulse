"""
Handling for vision_event messages. Vision detections are treated as
supplementary evidence for an existing (or newly matched) RoadIssue — they
do not independently create report_count/unique_device_count growth the way
a sensor_event does, since Ultra Vision is user-activated and intermittent.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import RoadIssue
from app.issues.clustering import find_nearby_issue
from app.issues.confidence import calculate_final_confidence

logger = logging.getLogger("urban_pulse.issues")


def apply_vision_evidence(
    db: Session,
    latitude: float,
    longitude: float,
    detections: list[dict[str, Any]],
) -> RoadIssue | None:
    issue = find_nearby_issue(db, latitude, longitude)
    if issue is None:
        # No existing evidence at this location yet — vision alone does not
        # create a RoadIssue.
        logger.info("vision_event received with no nearby issue; ignoring")
        return None

    if not detections:
        return issue

    best_detection_confidence = max((d.get("confidence", 0.0) for d in detections), default=0.0)

    updated_confidence = calculate_final_confidence(
        phone_confidence=issue.confidence,
        ai_confidence=best_detection_confidence,
        report_count=issue.report_count,
        unique_device_count=issue.unique_device_count,
        matched_within_radius=True,
        vision_evidence_present=True,
    )

    # Vision evidence can only reinforce, never lower, existing confidence.
    issue.confidence = max(issue.confidence, updated_confidence)
    db.commit()
    db.refresh(issue)
    return issue
