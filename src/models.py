from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Job:
    uuid: str
    title: str
    company: str
    category: str
    min_salary: int
    max_salary: int
    position_level: str
    employment_type: str
    posting_date: str
    description: str = ""
    visa_matched: bool = False

    @property
    def url(self) -> str:
        return f"https://www.mycareersfuture.gov.sg/job/{self.uuid}"

    @property
    def salary_display(self) -> str:
        if self.min_salary == self.max_salary:
            return f"SGD {self.min_salary:,}/mo"
        return f"SGD {self.min_salary:,}–{self.max_salary:,}/mo"


@dataclass
class FilterConfig:
    employment_types: list[str] = field(default_factory=lambda: ["Full Time", "Contract"])
    position_levels: list[str] = field(default_factory=list)
    min_salary: int = 5000
    visa_keywords: list[str] = field(
        default_factory=lambda: [
            "Employment Pass",
            "EP",
            "S Pass",
            "work visa",
            "visa sponsorship",
            "foreigner",
        ]
    )


@dataclass
class CategoryConfig:
    name: str
    api_category: str
    ntfy_topic: str
    filters: FilterConfig = field(default_factory=FilterConfig)


@dataclass
class ScraperConfig:
    base_url: str = "https://api.mycareersfuture.gov.sg"
    page_size: int = 100
    max_pages: int = 5
    request_timeout: int = 30
    delay_between_requests: float = 2.0


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
class AppConfig:
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    categories: list[CategoryConfig] = field(default_factory=list)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
