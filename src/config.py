from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from src.models import (
    AIConfig,
    AppConfig,
    CategoryConfig,
    DatabaseConfig,
    LoggingConfig,
    NotificationConfig,
    ScraperConfig,
)

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("config.yaml")


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError("Config file must be a YAML mapping")

    config = _parse_config(raw)
    _apply_env_overrides(config)
    _validate(config)
    return config


def _parse_config(raw: dict) -> AppConfig:
    scraper_raw = raw.get("scraper", {})
    scraper = ScraperConfig(
        page_size=scraper_raw.get("page_size", ScraperConfig.page_size),
        max_pages=scraper_raw.get("max_pages", ScraperConfig.max_pages),
        request_timeout=scraper_raw.get("request_timeout", ScraperConfig.request_timeout),
        delay_between_requests=scraper_raw.get(
            "delay_between_requests", ScraperConfig.delay_between_requests
        ),
    )

    categories = []
    for cat_raw in raw.get("categories", []):
        categories.append(
            CategoryConfig(
                name=cat_raw["name"],
                keywords=cat_raw["keywords"],
                ntfy_topic=cat_raw["ntfy_topic"],
                location=cat_raw.get("location", "Singapore"),
                experience_level=cat_raw.get("experience_level", ""),
                highlight_keywords=cat_raw.get("highlight_keywords", []),
            )
        )

    notif_raw = raw.get("notifications", {})
    notifications = NotificationConfig(
        ntfy_server=notif_raw.get("ntfy_server", NotificationConfig.ntfy_server),
        ntfy_token=notif_raw.get("ntfy_token", ""),
        priority=notif_raw.get("priority", NotificationConfig.priority),
        batch_size=notif_raw.get("batch_size", NotificationConfig.batch_size),
    )

    db_raw = raw.get("database", {})
    database = DatabaseConfig(
        path=db_raw.get("path", DatabaseConfig.path),
        retention_days=db_raw.get("retention_days", DatabaseConfig.retention_days),
    )

    log_raw = raw.get("logging", {})
    logging_cfg = LoggingConfig(level=log_raw.get("level", LoggingConfig.level))

    ai_raw = raw.get("ai", {})
    ai = AIConfig(
        enabled=ai_raw.get("enabled", False),
        api_key=ai_raw.get("api_key", ""),
        base_url=ai_raw.get("base_url", AIConfig.base_url),
        model=ai_raw.get("model", AIConfig.model),
        request_timeout=ai_raw.get("request_timeout", AIConfig.request_timeout),
    )

    return AppConfig(
        scraper=scraper,
        categories=categories,
        notifications=notifications,
        database=database,
        logging=logging_cfg,
        ai=ai,
    )


def _apply_env_overrides(config: AppConfig) -> None:
    if token := os.environ.get("NTFY_TOKEN"):
        config.notifications.ntfy_token = token
    if server := os.environ.get("NTFY_SERVER"):
        config.notifications.ntfy_server = server
    if level := os.environ.get("LOG_LEVEL"):
        config.logging.level = level.upper()
    if db_path := os.environ.get("DB_PATH"):
        config.database.path = db_path
    if ai_key := os.environ.get("AI_API_KEY"):
        config.ai.api_key = ai_key
    if ai_enabled := os.environ.get("AI_ENABLED"):
        config.ai.enabled = ai_enabled.lower() in ("true", "1", "yes")


def _validate(config: AppConfig) -> None:
    if not config.categories:
        raise ValueError("At least one category must be configured")

    for cat in config.categories:
        if not cat.name:
            raise ValueError("Category name is required")
        if not cat.keywords:
            raise ValueError(f"Category '{cat.name}' missing keywords")
        if not cat.ntfy_topic:
            raise ValueError(f"Category '{cat.name}' missing ntfy_topic")

    if config.scraper.page_size < 1 or config.scraper.page_size > 25:
        raise ValueError("page_size must be between 1 and 25")
    if config.scraper.max_pages < 1:
        raise ValueError("max_pages must be at least 1")
    if config.database.retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    if config.ai.enabled and not config.ai.api_key:
        raise ValueError("AI is enabled but ai.api_key is not set (config or AI_API_KEY env var)")
