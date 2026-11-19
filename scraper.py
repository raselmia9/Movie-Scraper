#!/usr/bin/env python3
"""Collect every public movie card from the site's paginated movie catalog."""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SITE_URL = os.getenv("MOVIE_SITE_URL", "http://103.203.93.2/").rstrip("/") + "/"
MOVIES_URL = urljoin(SITE_URL, "movies")
OUTPUT_FILE = Path(os.getenv("OUTPUT_FILE", "movies.json"))
MAX_WORKERS = max(1, min(int(os.getenv("SCRAPER_WORKERS", "4")), 8))
DATE_PATTERN = re.compile(
    r"\b\d{1,2}-[A-Za-z]{3}-\d{4}\s+\d{1,2}:\d{2}:\d{2}\s*[AaPp][Mm]\b"
)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "Movie-Scraper/1.0 (public movie metadata)"})
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch_page(page_number: int) -> tuple[int, BeautifulSoup]:
    with make_session() as session:
        response = session.get(
            MOVIES_URL,
            params={"page": page_number},
            timeout=(20, 90),
        )
        response.raise_for_status()
    return page_number, BeautifulSoup(response.text, "html.parser")


def max_page_from(soup: BeautifulSoup) -> int:
    page_numbers = [1]
    for link in soup.select(".pagination a[href]"):
        label = link.get_text(" ", strip=True)
        if label.isdigit():
            page_numbers.append(int(label))
    return max(page_numbers)


def parse_movies(soup: BeautifulSoup) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for card in soup.select(".card"):
        title_link = card.select_one("h3.item-title a[href]")
        image = card.select_one("a[href] img[src]")
        if not title_link or not image:
            continue

        title = (title_link.get("title") or title_link.get_text(" ", strip=True)).strip()
        detail_url = urljoin(MOVIES_URL, title_link["href"].strip())
        thumbnail = urljoin(MOVIES_URL, image["src"].strip())
        if not title:
            continue

        published_date = ""
        date_element = card.select_one(".item-designation small")
        if date_element:
            match = DATE_PATTERN.search(date_element.get_text(" ", strip=True))
            if match:
                published_date = match.group(0)
                datetime.strptime(
                    published_date.lower().replace(" ", ""),
                    "%d-%b-%Y%I:%M:%S%p",
                )

        records.append(
            {
                "thumbnail": thumbnail,
                "title": title,
                "detail_url": detail_url,
                "published_date": published_date,
            }
        )
    return records


def scrape_all() -> tuple[list[dict[str, str]], int]:
    _, first_page = fetch_page(1)
    total_pages = max_page_from(first_page)
    movies_by_url: dict[str, dict[str, str]] = {}

    def save_page(soup: BeautifulSoup) -> None:
        for movie in parse_movies(soup):
            # Categories can repeat the same title; the all-movies catalog is unique by detail URL.
            movies_by_url[movie["detail_url"]] = movie

    save_page(first_page)
    if total_pages > 1:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(fetch_page, page): page for page in range(2, total_pages + 1)}
            completed = 1
            for future in as_completed(futures):
                page_number, soup = future.result()
                save_page(soup)
                completed += 1
                if completed % 25 == 0 or completed == total_pages:
                    print(f"Scanned {completed}/{total_pages} catalog pages", flush=True)

    movies = list(movies_by_url.values())
    if not movies:
        raise RuntimeError("No movie cards were found; output was not changed.")
    return movies, total_pages


def main() -> int:
    try:
        movies, pages_scanned = scrape_all()
        result = {
            "title": f"Complete Movie List | {len(movies)} items collected",
            "description": (
                f"Collected {len(movies)} unique movie items from all "
                f"{pages_scanned} pages of the site's movie catalog."
            ),
            "source_url": MOVIES_URL,
            "pages_scanned": pages_scanned,
            "total_items": len(movies),
            "collected_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fields": ["thumbnail", "title", "detail_url", "published_date"],
            "movies": movies,
        }
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Saved {len(movies)} unique items from {pages_scanned} pages to {OUTPUT_FILE}")
        return 0
    except Exception as exc:
        print(f"Scrape failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
