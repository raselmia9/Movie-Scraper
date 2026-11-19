#!/usr/bin/env python3
"""Collect public movie-card metadata from the configured listing page."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = os.getenv("MOVIE_SITE_URL", "http://103.203.93.2/")
OUTPUT_FILE = Path(os.getenv("OUTPUT_FILE", "movies.json"))
DATE_PATTERN = re.compile(
    r"\b\d{1,2}-[A-Za-z]{3}-\d{4}\s+\d{1,2}:\d{2}:\d{2}\s*[AaPp][Mm]\b"
)


def scrape_movies() -> list[dict[str, str]]:
    response = requests.get(
        BASE_URL,
        headers={"User-Agent": "Movie-Scraper/1.0 (public metadata collection)"},
        timeout=30,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    movies: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for card in soup.select(".card"):
        title_link = card.select_one("h3.item-title a[href]")
        image = card.select_one("a[href] img[src]")
        if not title_link or not image:
            continue

        detail_url = urljoin(BASE_URL, title_link["href"].strip())
        title = (title_link.get("title") or title_link.get_text(" ", strip=True)).strip()
        thumbnail = urljoin(BASE_URL, image["src"].strip())
        if not title or detail_url in seen_urls:
            continue

        date_text = ""
        date_container = card.select_one(".item-designation small")
        if date_container:
            match = DATE_PATTERN.search(date_container.get_text(" ", strip=True))
            if match:
                date_text = match.group(0)
                # Validate the source format while keeping its displayed date unchanged.
                datetime.strptime(date_text.lower().replace(" ", ""), "%d-%b-%Y%I:%M:%S%p")

        movies.append(
            {
                "thumbnail": thumbnail,
                "title": title,
                "detail_url": detail_url,
                "published_date": date_text,
            }
        )
        seen_urls.add(detail_url)

    if not movies:
        raise RuntimeError("No movie cards found; refusing to overwrite the existing list.")
    return movies


def main() -> int:
    try:
        movies = scrape_movies()
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(
            json.dumps(movies, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Saved {len(movies)} unique movie records to {OUTPUT_FILE}")
        return 0
    except Exception as exc:
        print(f"Scrape failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
