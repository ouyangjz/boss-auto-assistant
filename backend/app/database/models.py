from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def local_now() -> datetime:
    return datetime.now()


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_job_name", "job_name"),
        Index("ix_jobs_company_name", "company_name"),
        Index("ix_jobs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    job_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    salary: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    location: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    experience: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    education: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    hr_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    hr_title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    job_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=local_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=local_now, onupdate=local_now
    )

    tags: Mapped[List[JobTag]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    evaluations: Mapped[List[JobEvaluation]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    applications: Mapped[List[Application]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobTag(Base):
    __tablename__ = "job_tags"
    __table_args__ = (UniqueConstraint("job_id", "tag", name="uq_job_tags_job_tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=local_now)

    job: Mapped[Job] = relationship(back_populates="tags")


class JobEvaluation(Base):
    __tablename__ = "job_evaluations"
    __table_args__ = (
        CheckConstraint(
            "match_score IS NULL OR (match_score >= 0 AND match_score <= 100)",
            name="ck_job_evaluations_match_score",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    job_category: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    output_list: Mapped[Any] = mapped_column(JSON, nullable=True)
    self_intro_context: Mapped[Any] = mapped_column(JSON, nullable=True)
    raw_ai_output: Mapped[Any] = mapped_column(JSON, nullable=False)
    source_file: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    migration_key: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=local_now)

    job: Mapped[Job] = relationship(back_populates="evaluations")
    requirements: Mapped[List[EvaluationRequirement]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    applications: Mapped[List[Application]] = relationship(back_populates="evaluation")


class EvaluationRequirement(Base):
    __tablename__ = "evaluation_requirements"
    __table_args__ = (
        Index(
            "ix_evaluation_requirements_type_content",
            "requirement_type",
            "content",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("job_evaluations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requirement_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    logic: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    alternatives: Mapped[Any] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=local_now)

    evaluation: Mapped[JobEvaluation] = relationship(back_populates="requirements")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('未投递', '沟通', '投递简历', '面试阶段', '入职阶段')",
            name="ck_applications_status",
        ),
        Index("ix_applications_status", "status"),
        Index("ix_applications_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    evaluation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("job_evaluations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="未投递")
    contacted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=local_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=local_now, onupdate=local_now
    )

    job: Mapped[Job] = relationship(back_populates="applications")
    evaluation: Mapped[Optional[JobEvaluation]] = relationship(back_populates="applications")
    communication: Mapped[Optional[Communication]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Communication(Base):
    __tablename__ = "communications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=local_now)

    application: Mapped[Application] = relationship(back_populates="communication")
