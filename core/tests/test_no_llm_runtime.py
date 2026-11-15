import re
from pathlib import Path

import pytest

from core.models import Dam
from core.services.indices.registry import INDEX_REGISTRY

RUNTIME_PATHS = [
    Path("core/services/indices"),
    Path("core/services/hri.py"),
    Path("core/services/buffer.py"),
    Path("core/services/analog.py"),
    Path("core/services/scenario.py"),
]
FORBIDDEN = re.compile(
    r"\b(openai|anthropic|langchain|llama_index|mistralai|google\.generativeai|"
    r"google\.genai|cohere|ollama)\b",
    re.IGNORECASE,
)


def test_no_ai_sdk_import_in_runtime_path():
    offenders = []
    for path in RUNTIME_PATHS:
        files = [path] if path.is_file() else list(path.rglob("*.py"))
        for file in files:
            if FORBIDDEN.search(file.read_text(encoding="utf-8")):
                offenders.append(str(file))
    assert offenders == []


def test_every_registered_provider_has_an_inactive_agent_slot():
    assert INDEX_REGISTRY
    for provider in INDEX_REGISTRY.values():
        assert provider.agent_hook is None
