import re

WINDOWS_INVALID_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_filename(value: str, fallback: str = "unknown-job") -> str:
    cleaned = WINDOWS_INVALID_FILENAME.sub("_", value).strip(" ._")
    return (cleaned or fallback)[:80]
