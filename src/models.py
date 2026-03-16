from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Job:
    uuid: str
    title: str
    company: str
    category: str
    location: str
    posting_date: str
    url: str
    salary: str = ""
    description: str = ""

    @property
    def salary_display(self) -> str:
        return self.salary or "Not listed"


@dataclass
class CategoryConfig:
    name: str
    keywords: str
    ntfy_topic: str
    location: str = "Singapore"
    experience_level: str = ""


@dataclass
class ScraperConfig:
    page_size: int = 25
    max_pages: int = 4
    request_timeout: int = 30
    delay_between_requests: float = 3.0


@dataclass
class NotificationConfig:
    ntfy_server: str = "https://ntfy.sh"
    ntfy_token: str = ""
    priority: str = "default"
    batch_size: int = 10


@dataclass
class DatabaseConfig:
    path: str = "/data/jobs.db"
    retention_days: int = 90


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class AIConfig:
    enabled: bool = False
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-plus"
    request_timeout: int = 30


@dataclass
class AppConfig:
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    categories: list[CategoryConfig] = field(default_factory=list)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    ai: AIConfig = field(default_factory=AIConfig)
