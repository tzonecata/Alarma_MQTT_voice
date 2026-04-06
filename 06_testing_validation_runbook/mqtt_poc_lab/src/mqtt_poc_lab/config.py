from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not data:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must contain a top-level mapping")
    return data


def deep_get(mapping: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    node: Any = mapping
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node
