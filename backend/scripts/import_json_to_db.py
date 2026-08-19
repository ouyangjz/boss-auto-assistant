import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.database.connection import init_database  # noqa: E402
from app.database.services import save_job_result  # noqa: E402


def historical_timestamp(path: Path) -> datetime:
    try:
        return datetime.strptime(path.name[:22], "%Y%m%d_%H%M%S_%f")
    except (ValueError, IndexError):
        return datetime.fromtimestamp(path.stat().st_mtime)


def import_file(path: Path, data_root: Path) -> str:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    if not str(payload.get("job_id") or "").strip():
        raise ValueError("missing job_id")

    source_file = path.relative_to(data_root).as_posix()
    migration_key = hashlib.sha256(raw).hexdigest()
    result = save_job_result(
        payload,
        source_file=source_file,
        migration_key=migration_key if payload.get("coze_output") is not None else None,
        created_at=historical_timestamp(path),
        application_status=None,
    )
    if not result.job_created and not result.evaluation_created:
        return "skipped"
    return "success"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Import historical job JSON files")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=SERVER_ROOT / "data",
        help="Directory to scan recursively (default: project data directory)",
    )
    args = parser.parse_args(argv)
    data_root = args.data_dir.resolve()
    files = sorted(data_root.rglob("*.json")) if data_root.exists() else []
    counts = {"success": 0, "skipped": 0, "failed": 0}
    failures = []

    init_database()
    for path in files:
        try:
            outcome = import_file(path, data_root)
            counts[outcome] += 1
        except Exception as exc:
            counts["failed"] += 1
            failures.append((path, str(exc)))

    print(f"扫描文件：{len(files)}")
    print(f"成功：{counts['success']}")
    print(f"跳过：{counts['skipped']}")
    print(f"失败：{counts['failed']}")
    for path, reason in failures:
        print(f"失败文件：{path}")
        print(f"错误原因：{reason}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
