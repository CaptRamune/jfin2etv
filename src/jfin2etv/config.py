"""Configuration loader for jfin2etv (DESIGN.md §12.1)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class JellyfinPathRemap(BaseModel):
    from_: str = Field(alias="from")
    to: str

    model_config = {"populate_by_name": True}


class JellyfinConfig(BaseModel):
    url: str = "http://jellyfin:8096"
    api_key_env: str = "JELLYFIN_API_KEY"
    request_timeout_s: float = 30.0
    path_remap: list[JellyfinPathRemap] = Field(default_factory=list)


class ErsatzTVServerConfig(BaseModel):
    bind_address: str = "0.0.0.0"
    port: int = 8409


class ErsatzTVConfig(BaseModel):
    config_dir: str = "/ersatztv-config"
    server: ErsatzTVServerConfig = Field(default_factory=ErsatzTVServerConfig)
    output_folder: str = "/tmp/hls"


class SchedulerConfig(BaseModel):
    run_time: str = "04:00"
    timezone: str | None = None
    window_hours_ahead: int = 72
    window_hours_behind: int = 48
    max_default_block_gap_hours: int = 1
    channels_in_parallel: int = 2

    @field_validator("run_time")
    @classmethod
    def _validate_run_time(cls, v: str) -> str:
        parts = v.split(":")
        if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
            raise ValueError(f"run_time must be HH:MM or HH:MM:SS, got {v!r}")
        return v


class LoggingConfig(BaseModel):
    level: str = "info"
    format: str = "json"


class EPGConfig(BaseModel):
    merged_output: str = "/epg/epg.xml"
    per_channel_output_dir: str = "/epg/per-channel"
    icon_base_url: str | None = None
    include_icons: bool = True


class HealthConfig(BaseModel):
    listen: str = "0.0.0.0:8080"

    @property
    def host_port(self) -> tuple[str, int]:
        host, _, port = self.listen.rpartition(":")
        return host or "0.0.0.0", int(port)


class Config(BaseModel):
    jellyfin: JellyfinConfig = Field(default_factory=JellyfinConfig)
    ersatztv: ErsatzTVConfig = Field(default_factory=ErsatzTVConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    epg: EPGConfig = Field(default_factory=EPGConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)

    config_dir: str = "/config"
    scripts_dir: str = "/scripts"
    state_dir: str = "/state"
    media_dir: str = "/media"

    def effective_timezone(self) -> str:
        return self.scheduler.timezone or os.environ.get("TZ", "UTC")

    def jellyfin_api_key(self) -> str:
        key = os.environ.get(self.jellyfin.api_key_env, "")
        if not key:
            raise RuntimeError(
                f"Jellyfin API key not set in env var {self.jellyfin.api_key_env!r}"
            )
        return key


def load_config(path: str | Path | None = None) -> Config:
    """Load configuration from YAML + env, applying defaults."""
    p = Path(path) if path else Path(os.environ.get("JFIN2ETV_CONFIG", "/config/jfin2etv.yml"))
    data: dict[str, Any]
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    if env_url := os.environ.get("JELLYFIN_URL"):
        data.setdefault("jellyfin", {})["url"] = env_url
    if env_level := os.environ.get("JFIN2ETV_LOG_LEVEL"):
        data.setdefault("logging", {})["level"] = env_level

    return Config.model_validate(data)


__all__ = [
    "Config",
    "EPGConfig",
    "ErsatzTVConfig",
    "ErsatzTVServerConfig",
    "HealthConfig",
    "JellyfinConfig",
    "JellyfinPathRemap",
    "LoggingConfig",
    "SchedulerConfig",
    "load_config",
]
