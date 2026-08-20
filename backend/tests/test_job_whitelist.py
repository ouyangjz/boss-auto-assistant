import json
import logging
from pathlib import Path

from app.services.job_whitelist import _config_cache, check_job_whitelist


def _write_config(tmp_path, **overrides):
    config = {
        "enabled": True,
        "job_name_exact": [],
        "job_name_contains": [],
        "job_tag_contains": [],
        **overrides,
    }
    path = tmp_path / "job_whitelist.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


def test_matches_exact_name_after_basic_normalization(tmp_path):
    config_path = _write_config(
        tmp_path,
        job_name_exact=["AI应用开发工程师"],
    )

    result = check_job_whitelist(
        {"job_name": "  AI应用开发工程师  ", "job_tags": []},
        config_path,
    )

    assert result == {
        "matched": True,
        "rule_type": "job_name_exact",
        "rule": "AI应用开发工程师",
    }


def test_contains_matching_ignores_english_case(tmp_path):
    config_path = _write_config(
        tmp_path,
        job_name_contains=["Python"],
    )

    result = check_job_whitelist(
        {"job_name": "python后端开发工程师", "job_tags": []},
        config_path,
    )

    assert result["matched"] is True
    assert result["rule_type"] == "job_name_contains"


def test_matches_rule_inside_individual_job_tag(tmp_path):
    config_path = _write_config(
        tmp_path,
        job_tag_contains=["FastAPI"],
    )

    result = check_job_whitelist(
        {"job_name": "后端工程师", "job_tags": ["Python", "fastapi框架"]},
        config_path,
    )

    assert result == {
        "matched": True,
        "rule_type": "job_tag_contains",
        "rule": "FastAPI",
    }


def test_unmatched_job_is_denied(tmp_path):
    config_path = _write_config(tmp_path, job_name_contains=["Python"])

    assert check_job_whitelist(
        {"job_name": "产品运营", "job_tags": []}, config_path
    ) == {"matched": False}


def test_missing_config_warns_and_denies_job(tmp_path, caplog):
    missing_path = tmp_path / "missing.json"

    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        result = check_job_whitelist({"job_name": "Python工程师"}, missing_path)

    assert result == {"matched": False}
    assert "config not found" in caplog.text


def test_invalid_or_disabled_config_denies_job(tmp_path):
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{invalid", encoding="utf-8")
    disabled_path = _write_config(
        tmp_path,
        enabled=False,
        job_name_contains=["Python"],
    )

    assert check_job_whitelist(
        {"job_name": "Python工程师"}, invalid_path
    ) == {"matched": False}
    assert check_job_whitelist(
        {"job_name": "Python工程师"}, disabled_path
    ) == {"matched": False}


def test_unchanged_config_uses_cached_content(tmp_path, monkeypatch):
    config_path = _write_config(tmp_path, job_name_contains=["Python"])
    _config_cache.clear(config_path)
    original_read_text = Path.read_text
    read_count = 0

    def counted_read_text(path, *args, **kwargs):
        nonlocal read_count
        if path == config_path.resolve():
            read_count += 1
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted_read_text)

    assert check_job_whitelist({"job_name": "Python工程师"}, config_path)["matched"]
    assert check_job_whitelist({"job_name": "Python工程师"}, config_path)["matched"]
    assert read_count == 1


def test_valid_config_change_reloads_cache(tmp_path):
    config_path = _write_config(tmp_path, job_name_contains=["Python"])
    assert check_job_whitelist({"job_name": "Python工程师"}, config_path)["matched"]

    config_path.write_text(
        json.dumps(
            {
                "enabled": True,
                "job_name_exact": [],
                "job_name_contains": ["Rust开发"],
                "job_tag_contains": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert check_job_whitelist(
        {"job_name": "Python工程师"}, config_path
    ) == {"matched": False}
    assert check_job_whitelist({"job_name": "Rust开发工程师"}, config_path)["matched"]


def test_invalid_reload_keeps_last_valid_config(tmp_path, caplog):
    config_path = _write_config(tmp_path, job_name_contains=["Python"])
    assert check_job_whitelist({"job_name": "Python工程师"}, config_path)["matched"]

    config_path.write_text("{invalid", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        result = check_job_whitelist({"job_name": "Python工程师"}, config_path)

    assert result["matched"] is True
    assert "keeping last valid config" in caplog.text
