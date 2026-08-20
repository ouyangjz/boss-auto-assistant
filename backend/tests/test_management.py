import json

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.management import ManagementSettings, RuleCreate, RuleUpdate
from app.services.rule_service import RuleService


def _service(tmp_path, *, threshold=70):
    return RuleService(
        blacklist_path=tmp_path / "blacklist.json",
        whitelist_path=tmp_path / "whitelist.json",
        settings_path=tmp_path / "settings.json",
        default_threshold=threshold,
    )


def test_missing_config_loads_safe_defaults(tmp_path):
    service = _service(tmp_path)

    config = service.get_config()

    assert config.settings.match_threshold == 70
    assert config.blacklist == []
    assert config.whitelist == []


def test_settings_are_atomically_saved_and_reloaded(tmp_path):
    service = _service(tmp_path)
    service.update_settings(ManagementSettings(match_threshold=80))

    reloaded = _service(tmp_path)

    assert reloaded.get_settings().match_threshold == 80
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8")) == {
        "match_threshold": 80
    }
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_settings_keep_last_valid_value(tmp_path):
    service = _service(tmp_path)
    service.update_settings(ManagementSettings(match_threshold=76))
    assert service.get_settings().match_threshold == 76

    (tmp_path / "settings.json").write_text("{broken", encoding="utf-8")

    assert service.get_settings().match_threshold == 76


def test_rule_crud_and_disabled_rule_matching(tmp_path):
    service = _service(tmp_path)
    created = service.create_rule(
        "blacklist",
        RuleCreate(keyword="Java", target="job_name", enabled=True),
    )

    assert service.test_rules(
        {"job_name": "Java开发工程师", "company_name": "", "job_description": ""}
    ).result == "blacklist"

    service.update_rule("blacklist", created.id, RuleUpdate(enabled=False))
    assert service.test_rules(
        {"job_name": "Java开发工程师", "company_name": "", "job_description": ""}
    ).result == "unmatched"

    service.delete_rule("blacklist", created.id)
    assert service.get_rules("blacklist") == []


def test_blacklist_has_priority_over_whitelist(tmp_path):
    service = _service(tmp_path)
    service.create_rule(
        "blacklist",
        RuleCreate(keyword="风险公司", target="company_name"),
    )
    service.create_rule(
        "whitelist",
        RuleCreate(keyword="AI应用开发", target="job_name"),
    )

    result = service.test_rules(
        {
            "job_name": "AI应用开发工程师",
            "company_name": "风险公司（深圳）",
            "job_description": "",
        }
    )

    assert result.result == "blacklist"
    assert result.matched_rule.keyword == "风险公司"


def test_management_api_validates_threshold_and_rule(monkeypatch, tmp_path):
    service = _service(tmp_path)
    monkeypatch.setattr("app.api.management.rule_service", service)
    client = TestClient(app)

    assert client.patch(
        "/api/v1/management/settings", json={"match_threshold": 101}
    ).status_code == 422
    assert client.patch(
        "/api/v1/management/settings", json={"match_threshold": None}
    ).status_code == 422
    assert client.post(
        "/api/v1/management/blacklist",
        json={
            "keyword": "",
            "target": "job_name",
            "match_type": "contains",
            "enabled": True,
        },
    ).status_code == 422

    response = client.post(
        "/api/v1/management/whitelist",
        json={
            "keyword": "AI应用开发",
            "target": "job_name",
            "match_type": "contains",
            "enabled": True,
        },
    )
    assert response.status_code == 201
    assert client.get("/api/v1/management/config").json()["whitelist"][0][
        "keyword"
    ] == "AI应用开发"
