"""
Simple spatial matching: find an existing RoadIssue within a fixed radius
of a new sensor report's coordinates. Deliberately not a full GIS solution —
a haversine distance check is enough for a hackathon-scale dataset.
"""

import math

from sqlalchemy.orm import Session

from app.core.config import SPATIAL_MATCH_RADIUS_METERS
from app.database.models import RoadIssue

EARTH_RADIUS_METERS = 6_371_000


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_METERS * c


def find_nearby_issue(
    db: Session,
    latitude: float,
    longitude: float,
    radius_meters: float = SPATIAL_MATCH_RADIUS_METERS,
) -> RoadIssue | None:
    """
    Cheap pre-filter by a bounding lat/lon box, then exact haversine check on
    the (small) candidate set. Avoids pulling the whole table for every event.
    """
    lat_delta = radius_meters / 111_320  # ~meters per degree latitude
    lon_delta = radius_meters / (111_320 * max(math.cos(math.radians(latitude)), 0.01))

    candidates = (
        db.query(RoadIssue)
        .filter(
            RoadIssue.status != "resolved",
            RoadIssue.latitude.between(latitude - lat_delta, latitude + lat_delta),
            RoadIssue.longitude.between(longitude - lon_delta, longitude + lon_delta),
        )
        .all()
    )

    best_match: RoadIssue | None = None
    best_distance = radius_meters

    for candidate in candidates:
        distance = haversine_distance_meters(latitude, longitude, candidate.latitude, candidate.longitude)
        if distance <= radius_meters and distance <= best_distance:
            best_match = candidate
            best_distance = distance

    return best_match
