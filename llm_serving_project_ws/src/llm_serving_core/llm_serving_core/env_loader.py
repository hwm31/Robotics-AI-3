"""프로젝트 .env 파일 탐색 및 로드."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_env_file() -> str | None:
    """워크스페이스 루트 등에서 .env 파일 경로를 찾습니다."""
    explicit = os.environ.get('LLM_SERVING_ENV_FILE')
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return str(path)

    for start in (Path.cwd(), Path(__file__).resolve()):
        for directory in (start, *start.parents):
            candidate = directory / '.env'
            if candidate.is_file():
                return str(candidate)

    return None


def load_project_env() -> str | None:
    """.env를 로드하고 사용한 파일 경로를 반환합니다."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None

    env_file = resolve_env_file()
    if env_file is None:
        return None

    load_dotenv(env_file, override=False)
    return env_file
