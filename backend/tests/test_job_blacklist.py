import json
import logging

from app.services.job_blacklist import check_job_blacklist


def _write_config(tmp_path, **overrides):
    config = {
        "enabled": True,
        "job_name_exact": [],
        "job_name_contains": [],
        "job_tag_contains": [],
        **overrides,
    }
    path = tmp_path / "job_blacklist.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


def test_matches_exact_name_after_basic_normalization(tmp_path):
    config_path = _write_config(
        tmp_path,
        job_name_exact=["亚马逊产品开发"],
    )

    result = check_job_blacklist(
        {"job_name": "  亚马逊产品开发  ", "job_tags": []},
        config_path,
    )

    assert result == {
        "matched": True,
        "rule_type": "job_name_exact",
        "rule": "亚马逊产品开发",
    }


def test_contains_matching_ignores_english_case(tmp_path):
    config_path = _write_config(
        tmp_path,
        job_name_contains=["WordPress前端开发"],
    )

    result = check_job_blacklist(
        {"job_name": "wordpress前端开发工程师", "job_tags": []},
        config_path,
    )

    assert result["matched"] is True
    assert result["rule_type"] == "job_name_contains"


def test_matches_rule_inside_individual_job_tag(tmp_path):
    config_path = _write_config(
        tmp_path,
        job_tag_contains=["售前客服"],
    )

    result = check_job_blacklist(
        {"job_name": "客户体验岗位", "job_tags": ["海外业务", "售前客服经验"]},
        config_path,
    )

    assert result == {
        "matched": True,
        "rule_type": "job_tag_contains",
        "rule": "售前客服",
    }


def test_protected_ai_job_is_not_blacklisted():
    result = check_job_blacklist(
        {
            "job_name": "AI应用开发工程师",
            "job_tags": ["Python", "Agent", "FastAPI"],
        }
    )

    assert result == {"matched": False}


def test_missing_config_warns_and_allows_job(tmp_path, caplog):
    missing_path = tmp_path / "missing.json"

    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        result = check_job_blacklist({"job_name": "电商客服专员"}, missing_path)

    assert result == {"matched": False}
    assert "config not found" in caplog.text


def test_invalid_json_warns_and_allows_job(tmp_path, caplog):
    config_path = tmp_path / "job_blacklist.json"
    config_path.write_text("{invalid", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        result = check_job_blacklist({"job_name": "电商客服专员"}, config_path)

    assert result == {"matched": False}
    assert "invalid config" in caplog.text


def test_disabled_config_allows_job(tmp_path):
    config_path = _write_config(
        tmp_path,
        enabled=False,
        job_name_contains=["电商客服"],
    )

    assert check_job_blacklist(
        {"job_name": "电商客服专员"}, config_path
    ) == {"matched": False}
