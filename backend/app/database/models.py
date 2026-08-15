"""
All SQLAlchemy models live here. Routes must never define models inline.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship

from app.database.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
    otps = relationship("PasswordResetOTP", back_populates="user", cascade="all, delete-orphan")


class Device(Base):
    __tablename__ = "devices"

    # Device id is generated client-side by the app, not the server.
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    app_version = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="devices")
    sensor_reports = relationship("SensorReport", back_populates="device")


class RoadIssue(Base):
    __tablename__ = "road_issues"

    # Human-readable id, e.g. UP-000001. Generated in service layer.
    id = Column(String, primary_key=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="likely")
    classification = Column(String, nullable=False, default="unknown")
    confidence = Column(Float, nullable=False, default=0.0)
    severity = Column(Float, nullable=False, default=0.0)
    report_count = Column(Integer, nullable=False, default=0)
    unique_device_count = Column(Integer, nullable=False, default=0)
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    reports = relationship("SensorReport", back_populates="issue")


class SensorReport(Base):
    __tablename__ = "sensor_reports"

    id = Column(String, primary_key=True, default=gen_uuid)
    device_id = Column(String, ForeignKey("devices.id"), nullable=False, index=True)
    issue_id = Column(String, ForeignKey("road_issues.id"), nullable=True, index=True)

    timestamp = Column(DateTime, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    speed = Column(Float, nullable=True)
    heading = Column(Float, nullable=True)

    # Phone-reported evidence. NOT treated as ground truth.
    event_type = Column(String, nullable=False)
    phone_confidence = Column(Float, nullable=True)
    phone_severity = Column(Float, nullable=True)
    sensor_source = Column(String, nullable=True)
    features_json = Column(Text, nullable=True)  # JSON-encoded feature dict

    # Backend AI interpretation of this specific report.
    ai_classification = Column(String, nullable=True)
    ai_confidence = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    device = relationship("Device", back_populates="sensor_reports")
    issue = relationship("RoadIssue", back_populates="reports")


class PasswordResetOTP(Base):
    __tablename__ = "password_reset_otps"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    otp_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempt_count = Column(Integer, nullable=False, default=0)
    used = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="otps")
