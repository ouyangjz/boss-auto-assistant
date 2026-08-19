import json

import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Application,
    Base,
    Communication,
    EvaluationRequirement,
    Job,
    JobEvaluation,
    JobTag,
)
from app.database.services import job_exists, save_first_communication, save_job_result
from scripts.import_json_to_db import import_file


@pytest.fixture()
def database(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def sample_payload(job_id="job-1", score=88):
    return {
        "job_id": job_id,
        "job_name": "Python engineer",
        "company_name": "Example",
        "job_tags": ["Python", "SQL", "Python"],
        "coze_output": {
            "match_score": score,
            "job_category": "backend",
            "summary": "good match",
            "query": "Python SQL",
            "outputList": [{"documentId": 1}],
            "self_intro_context": [{"matched_skills": ["Python"]}],
            "top_requirements": [
                {
                    "requirement": "Python development",
                    "importance": 10,
                    "logic": "must",
                    "alternatives": [],
                }
            ],
            "required_skills": ["Python", "SQL"],
            "preferred_skills": ["FastAPI"],
        },
    }


def test_database_initializes_six_required_tables(database):
    engine, _ = database
    tables = set(inspect(engine).get_table_names())
    assert {
        "jobs",
        "job_tags",
        "job_evaluations",
        "evaluation_requirements",
        "applications",
        "communications",
    }.issubset(tables)
    application_columns = {column["name"] for column in inspect(engine).get_columns("applications")}
    communication_columns = {
        column["name"] for column in inspect(engine).get_columns("communications")
    }
    assert "applied_at" not in application_columns
    assert "direction" not in communication_columns
    assert "message_type" not in communication_columns


def test_save_job_result_maps_structured_data(database):
    _, sessions = database
    result = save_job_result(
        sample_payload(), application_status="沟通", session_factory=sessions
    )

    assert result.job_created is True
    assert result.evaluation_created is True
    assert result.application_database_id is not None
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        assert session.scalar(select(func.count()).select_from(JobTag)) == 2
        evaluation = session.scalar(select(JobEvaluation))
        assert evaluation.match_score == 88
        assert evaluation.output_list == [{"documentId": 1}]
        assert evaluation.raw_ai_output["summary"] == "good match"
        requirements = session.scalars(select(EvaluationRequirement)).all()
        assert {item.requirement_type for item in requirements} == {
            "top_requirement",
            "required_skill",
            "preferred_skill",
        }
        assert len(requirements) == 4
        application = session.scalar(select(Application))
        assert application.status == "沟通"
        assert application.evaluation_id == evaluation.id


def test_job_exists_checks_non_empty_business_id(database):
    _, sessions = database
    assert job_exists("job-1", session_factory=sessions) is False
    assert job_exists("", session_factory=sessions) is False

    save_job_result(sample_payload(), session_factory=sessions)

    assert job_exists("job-1", session_factory=sessions) is True
    assert job_exists("  job-1  ", session_factory=sessions) is True


def test_duplicate_job_creates_new_evaluation_only(database):
    _, sessions = database
    save_job_result(
        sample_payload(score=70),
        application_status="沟通",
        session_factory=sessions,
    )
    save_job_result(
        sample_payload(score=90),
        application_status="沟通",
        session_factory=sessions,
    )

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        assert session.scalar(select(func.count()).select_from(JobEvaluation)) == 2
        assert session.scalar(select(func.count()).select_from(Application)) == 1
        assert session.scalars(
            select(JobEvaluation.match_score).order_by(JobEvaluation.id)
        ).all() == [70, 90]


def test_reanalysis_does_not_regress_manually_confirmed_status(database):
    _, sessions = database
    first = save_job_result(
        sample_payload(), application_status="沟通", session_factory=sessions
    )
    with sessions.begin() as session:
        application = session.get(Application, first.application_database_id)
        application.status = "面试阶段"

    save_job_result(
        sample_payload(score=20),
        application_status="未投递",
        session_factory=sessions,
    )
    with sessions() as session:
        application = session.get(Application, first.application_database_id)
        assert application.status == "面试阶段"


def test_only_first_generated_communication_is_saved(database):
    _, sessions = database
    saved_job = save_job_result(
        sample_payload(), application_status="沟通", session_factory=sessions
    )

    first = save_first_communication(
        saved_job.application_database_id,
        "第一次沟通语",
        session_factory=sessions,
    )
    second = save_first_communication(
        saved_job.application_database_id,
        "不应覆盖的第二次沟通语",
        session_factory=sessions,
    )

    assert first.created is True
    assert second.created is False
    assert second.communication_database_id == first.communication_database_id
    with sessions() as session:
        communications = session.scalars(select(Communication)).all()
        assert len(communications) == 1
        assert communications[0].content == "第一次沟通语"


def test_transaction_rolls_back_invalid_evaluation(database):
    _, sessions = database
    payload = sample_payload(job_id="rollback-job")
    payload["coze_output"]["top_requirements"][0]["importance"] = "invalid"

    with pytest.raises(ValueError):
        save_job_result(payload, session_factory=sessions)

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0
        assert session.scalar(select(func.count()).select_from(JobEvaluation)) == 0


def test_import_file_is_idempotent(database, tmp_path, monkeypatch):
    _, sessions = database
    data_root = tmp_path / "data"
    data_root.mkdir()
    path = data_root / "20260818_104341_000001_job.json"
    path.write_text(json.dumps(sample_payload(), ensure_ascii=False), encoding="utf-8")

    def save_with_test_session(payload, **kwargs):
        return save_job_result(payload, session_factory=sessions, **kwargs)

    monkeypatch.setattr(
        "scripts.import_json_to_db.save_job_result", save_with_test_session
    )
    assert import_file(path, data_root) == "success"
    assert import_file(path, data_root) == "skipped"

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        assert session.scalar(select(func.count()).select_from(JobEvaluation)) == 1


def test_import_does_not_create_application_or_communication(database):
    _, sessions = database
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Application)) == 0
        assert session.scalar(select(func.count()).select_from(Communication)) == 0
