import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SERVER_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(SERVER_ROOT / ".env")


def _bounded_score(value: str, setting_name: str = "MATCH_THRESHOLD") -> int:
    score = int(value)
    if not 0 <= score <= 100:
        raise ValueError(f"{setting_name} 必须在 0 到 100 之间")
    return score


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "BOSS Job Evaluator")
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    match_threshold: int = _bounded_score(os.getenv("MATCH_THRESHOLD", "70"))
    data_dir: Path = SERVER_ROOT / os.getenv("DATA_DIR", "data")
    database_url: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{(data_dir / 'jobs.db').as_posix()}"
    )
    job_blacklist_config: Path = SERVER_ROOT / os.getenv(
        "JOB_BLACKLIST_CONFIG", "config/job_blacklist.json"
    )
    job_whitelist_config: Path = SERVER_ROOT / os.getenv(
        "JOB_WHITELIST_CONFIG", "config/job_whitelist.json"
    )
    coze_base_url: str = os.getenv("COZE_BASE_URL", "").strip()
    coze_workflow_id: str = os.getenv("COZE_WORKFLOW_ID", "").strip()
    coze_introduction_workflow_id: str = os.getenv(
        "COZE_INTRODUCTION_WORKFLOW_ID", ""
    ).strip()
    coze_token: str = os.getenv("COZE_TOKEN", "").strip()
    coze_timeout_seconds: float = float(os.getenv("COZE_TIMEOUT_SECONDS", "90"))
    coze_introduction_timeout_seconds: float = float(
        os.getenv(
            "COZE_INTRODUCTION_TIMEOUT_SECONDS",
            os.getenv("COZE_TIMEOUT_SECONDS", "90"),
        )
    )
    coze_timeout_fallback_score: int = _bounded_score(
        os.getenv("COZE_TIMEOUT_FALLBACK_SCORE", "50"),
        "COZE_TIMEOUT_FALLBACK_SCORE",
    )


settings = Settings()
