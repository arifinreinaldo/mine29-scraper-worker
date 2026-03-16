#!/usr/bin/env python3
"""Interactive onboarding CLI — generates config.yaml."""
from __future__ import annotations

import sys

import yaml

DEFAULT_VISA_KEYWORDS = [
    "Employment Pass",
    "EP",
    "S Pass",
    "work visa",
    "visa sponsorship",
    "foreigner",
]

CATEGORIES = {
    "1": ("Information Technology", "Information Technology"),
    "2": ("Marketing", "Marketing / Public Relations"),
}


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def ask_yes(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    value = input(f"{prompt}{suffix}: ").strip().lower()
    if not value:
        return default
    return value in ("y", "yes")


def main() -> None:
    print("=== mine29-scraper-worker setup ===\n")

    print("Which categories do you want to track?")
    for key, (name, _) in CATEGORIES.items():
        print(f"  {key}. {name}")

    selected_input = ask("Enter numbers separated by comma", "1,2")
    selected_keys = [k.strip() for k in selected_input.split(",")]

    categories = []
    for key in selected_keys:
        if key not in CATEGORIES:
            print(f"Unknown category: {key}, skipping")
            continue

        name, api_category = CATEGORIES[key]
        print(f"\n--- {name} ---")
        topic = ask(f"ntfy topic for {name}", f"mine29-{name.lower().replace(' ', '-')}-jobs")
        min_salary = int(ask("Minimum salary (SGD/month)", "5000"))

        categories.append({
            "name": name,
            "api_category": api_category,
            "ntfy_topic": topic,
            "filters": {
                "employment_types": ["Full Time", "Contract"],
                "position_levels": [],
                "min_salary": min_salary,
                "visa_keywords": DEFAULT_VISA_KEYWORDS,
            },
        })

    if not categories:
        print("No categories selected. Exiting.")
        sys.exit(1)

    print("\n--- Notifications ---")
    ntfy_server = ask("ntfy server URL", "https://ntfy.sh")
    ntfy_token = ask("ntfy access token (leave empty for public topics)", "")
    batch_size = int(ask("Max notifications per category per run", "10"))

    print("\n--- Database ---")
    db_path = ask("SQLite database path", "/data/jobs.db")
    retention = int(ask("Job retention days", "90"))

    config = {
        "scraper": {
            "base_url": "https://api.mycareersfuture.gov.sg",
            "page_size": 100,
            "max_pages": 5,
            "request_timeout": 30,
            "delay_between_requests": 2.0,
        },
        "categories": categories,
        "notifications": {
            "ntfy_server": ntfy_server,
            "ntfy_token": ntfy_token,
            "priority": "default",
            "batch_size": batch_size,
        },
        "database": {
            "path": db_path,
            "retention_days": retention,
        },
        "logging": {
            "level": "INFO",
        },
    }

    output_path = "config.yaml"
    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"\nConfig written to {output_path}")
    print("You can now run: python -m src.main")


if __name__ == "__main__":
    main()
