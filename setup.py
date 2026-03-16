#!/usr/bin/env python3
"""Interactive onboarding CLI — generates config.yaml."""
from __future__ import annotations

import sys

import yaml


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def main() -> None:
    print("=== mine29-scraper-worker setup ===\n")
    print("This scraper finds visa-sponsored jobs on LinkedIn.\n")

    categories = []
    while True:
        print(f"--- Category {len(categories) + 1} ---")
        name = ask("Category name (e.g. IT, Marketing)", "")
        if not name:
            if categories:
                break
            print("At least one category is required.")
            continue

        keywords = ask("LinkedIn search keywords", "software engineer")
        location = ask("Location", "Singapore")
        topic = ask("ntfy topic (unique random name)", f"mine29-{name.lower().replace(' ', '-')}-jobs")
        experience = ask("Experience level filter (empty=all, options: internship,entry,associate,mid-senior,director,executive)", "")

        categories.append({
            "name": name,
            "keywords": keywords,
            "ntfy_topic": topic,
            "location": location,
            "experience_level": experience,
        })

        if not ask("Add another category? (y/n)", "n").lower().startswith("y"):
            break

    print("\n--- Notifications ---")
    ntfy_server = ask("ntfy server URL", "https://ntfy.sh")
    ntfy_token = ask("ntfy access token (leave empty for public topics)", "")
    batch_size = int(ask("Max notifications per category per run", "10"))

    print("\n--- Database ---")
    db_path = ask("SQLite database path", "/data/jobs.db")
    retention = int(ask("Job retention days", "90"))

    config = {
        "scraper": {
            "page_size": 25,
            "max_pages": 4,
            "request_timeout": 30,
            "delay_between_requests": 3.0,
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
        "ai": {
            "enabled": False,
            "api_key": "",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
            "request_timeout": 30,
        },
        "logging": {
            "level": "INFO",
        },
    }

    output_path = "config.yaml"
    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"\nConfig written to {output_path}")
    print("Run: python3 -m src.main")


if __name__ == "__main__":
    main()
