"""Loads environment variables and the MCP server registry file."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SERVERS_PATH = Path("config/servers.json")
DEFAULT_ENV_PATH = Path(".env")


@dataclass
class ServerConfig:
    name: str
    transport: str  # "stdio" or "http"
    enabled: bool
    command: str | None = None
    args: list[str] | None = None
    url: str | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> "ServerConfig":
        return cls(
            name=raw["name"],
            transport=raw["transport"],
            enabled=raw.get("enabled", True),
            command=raw.get("command"),
            args=raw.get("args"),
            url=raw.get("url"),
        )


def load_env_file(path: Path = DEFAULT_ENV_PATH) -> None:
    """Populate os.environ from a simple KEY=VALUE file, without overwriting
    variables the shell already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_server_configs(path: Path = DEFAULT_SERVERS_PATH) -> list[ServerConfig]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [ServerConfig.from_dict(entry) for entry in raw["servers"]]


@dataclass
class AppConfig:
    anthropic_api_key: str
    anthropic_model: str
    servers: list[ServerConfig]

    @classmethod
    def load(
        cls,
        env_path: Path = DEFAULT_ENV_PATH,
        servers_path: Path = DEFAULT_SERVERS_PATH,
    ) -> "AppConfig":
        load_env_file(env_path)
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
        return cls(
            anthropic_api_key=api_key,
            anthropic_model=model,
            servers=load_server_configs(servers_path),
        )
