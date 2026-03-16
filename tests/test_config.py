import os

import pytest

from src.config import load_config


VALID_CONFIG = """\
scraper:
  base_url: "https://api.mycareersfuture.gov.sg"
  page_size: 50
  max_pages: 3

categories:
  - name: "IT"
    api_category: "Information Technology"
    ntfy_topic: "it-jobs"
    filters:
      min_salary: 6000
      employment_types: ["Full Time"]
      visa_keywords: ["EP"]

notifications:
  ntfy_server: "https://ntfy.sh"
  batch_size: 5

database:
  path: "/tmp/test.db"
  retention_days: 30

logging:
  level: "DEBUG"
"""


@pytest.fixture
def config_file(tmp_path):
    def _write(content: str = VALID_CONFIG):
        p = tmp_path / "config.yaml"
        p.write_text(content)
        return p
    return _write


class TestLoadConfig:
    def test_loads_valid_config(self, config_file):
        path = config_file()
        config = load_config(path)

        assert config.scraper.page_size == 50
        assert config.scraper.max_pages == 3
        assert len(config.categories) == 1
        assert config.categories[0].name == "IT"
        assert config.categories[0].filters.min_salary == 6000
        assert config.categories[0].filters.visa_keywords == ["EP"]
        assert config.notifications.batch_size == 5
        assert config.database.path == "/tmp/test.db"
        assert config.logging.level == "DEBUG"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_empty_categories_raises(self, config_file):
        path = config_file("scraper: {}\ncategories: []\n")
        with pytest.raises(ValueError, match="At least one category"):
            load_config(path)

    def test_missing_category_name_raises(self, config_file):
        path = config_file(
            'categories:\n  - name: ""\n    api_category: "IT"\n    ntfy_topic: "t"\n'
        )
        with pytest.raises(ValueError, match="name is required"):
            load_config(path)

    def test_missing_ntfy_topic_raises(self, config_file):
        path = config_file(
            'categories:\n  - name: "IT"\n    api_category: "IT"\n    ntfy_topic: ""\n'
        )
        with pytest.raises(ValueError, match="missing ntfy_topic"):
            load_config(path)

    def test_invalid_page_size_raises(self, config_file):
        path = config_file(
            'scraper:\n  page_size: 200\ncategories:\n  - name: "IT"\n    api_category: "IT"\n    ntfy_topic: "t"\n'
        )
        with pytest.raises(ValueError, match="page_size"):
            load_config(path)

    def test_env_overrides(self, config_file, monkeypatch):
        path = config_file()
        monkeypatch.setenv("NTFY_TOKEN", "secret-token")
        monkeypatch.setenv("NTFY_SERVER", "https://custom.ntfy.sh")
        monkeypatch.setenv("LOG_LEVEL", "warning")
        monkeypatch.setenv("DB_PATH", "/custom/path.db")

        config = load_config(path)

        assert config.notifications.ntfy_token == "secret-token"
        assert config.notifications.ntfy_server == "https://custom.ntfy.sh"
        assert config.logging.level == "WARNING"
        assert config.database.path == "/custom/path.db"

    def test_defaults_applied(self, config_file):
        minimal = (
            'categories:\n'
            '  - name: "IT"\n'
            '    api_category: "Information Technology"\n'
            '    ntfy_topic: "topic"\n'
        )
        path = config_file(minimal)
        config = load_config(path)

        assert config.scraper.page_size == 100
        assert config.scraper.delay_between_requests == 2.0
        assert config.notifications.ntfy_server == "https://ntfy.sh"
        assert config.database.retention_days == 90

    def test_non_dict_yaml_raises(self, config_file):
        path = config_file("- just a list\n")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(path)
