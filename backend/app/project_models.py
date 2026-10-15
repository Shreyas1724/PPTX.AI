"""Additive models for Projects Studio, separate from presentation-folder records.

`projects` remains the canonical owner of decks.  A ProjectBlueprint is an
optional one-to-one extension of that existing record; older projects work as-is.
"""
import time
from sqlalchemy import Column, String, Integer, ForeignKey, Text, Boolean, UniqueConstraint, Index
from .core import Base, uid


def epoch(): return int(time.time())


class ProjectBlueprint(Base):
    __tablename__ = 'project_blueprints'
    project_id = Column(String, ForeignKey('projects.id'), primary_key=True)
    idea = Column(Text, nullable=False)
    domain = Column(String(120), nullable=False, default='')
    constraints_json = Column(Text, nullable=False, default='{}')
    content_json = Column(Text, nullable=False, default='{}')
    status = Column(String(24), nullable=False, default='draft', index=True)
    revision = Column(Integer, nullable=False, default=0)
    archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(Integer, nullable=False, default=epoch)
    updated_at = Column(Integer, nullable=False, default=epoch, index=True)


class ProjectBlueprintVersion(Base):
    __tablename__ = 'project_blueprint_versions'
    id = Column(String, primary_key=True, default=uid)
    project_id = Column(String, ForeignKey('project_blueprints.project_id'), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    snapshot = Column(Text, nullable=False)
    created_at = Column(Integer, nullable=False, default=epoch)
    __table_args__ = (UniqueConstraint('project_id', 'revision'),)


class ProjectAnalysisJob(Base):
    __tablename__ = 'project_analysis_jobs'
    id = Column(String, primary_key=True, default=uid)
    project_id = Column(String, ForeignKey('project_blueprints.project_id'), nullable=False, index=True)
    owner_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    request_key = Column(String(128), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    mode = Column(String(22), nullable=False, default='all')
    section = Column(String(36), nullable=True)
    status = Column(String(24), nullable=False, default='queued', index=True)
    base_revision = Column(Integer, nullable=False)
    cost = Column(Integer, nullable=False, default=0)
    error = Column(Text)
    result_json = Column(Text, nullable=False, default='{}')
    created_at = Column(Integer, nullable=False, default=epoch)
    updated_at = Column(Integer, nullable=False, default=epoch)
    lease_until = Column(Integer, nullable=False, default=0)
    __table_args__ = (UniqueConstraint('owner_id', 'request_key'), Index('ix_project_analysis_job_queue','status','created_at'))
