#!/usr/bin/env python3
"""Collect catalog metadata and prefer homepage card timestamps by movie ID.

Detail-page URLs are stored as data; the scraper never requests them.
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SITE_URL = os.getenv("MOVIE_SITE_URL", "http://103.203.93.2/").rstrip("/") + "/"
MOVIES_URL = urljoin(SITE_URL, "movies")
HOME_URL = SITE_URL
OUTPUT_FILE = Path(os.getenv("OUTPUT_FILE", "movies.json"))
MAX_WORKERS = max(1, min(int(os.getenv("SCRAPER_WORKERS", "8")), 8))
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


def fetch_url(url: str, *, page_number: int | None = None) -> BeautifulSoup:
    # Only the homepage and catalog pages are requested. Movie detail URLs are never fetched.
    with make_session() as session:
        response = session.get(
            url,
            params={"page": page_number} if page_number is not None else None,
            timeout=(20, 90),
        )
        response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def movie_id_from_url(url: str) -> str:
    match = re.search(r"/video-details/(\d+)(?:[/?#]|$)", urlparse(url).path)
    return match.group(1) if match else ""


def homepage_publication_dates(soup: BeautifulSoup) -> dict[str, str]:
    """Map homepage card IDs to their displayed publication date/time."""
    dates: dict[str, str] = {}
    for card in soup.select(".card"):
        link = card.select_one("h3.item-title a[href]")
        if not link:
            continue
        movie_id = movie_id_from_url(urljoin(HOME_URL, link["href"].strip()))
        published_date = parse_card_published_date(card)
        if movie_id and published_date:
            dates[movie_id] = published_date
    if not dates:
        raise RuntimeError("No dated movie cards found on the homepage; output was not changed.")
    return dates


def fetch_page(page_number: int) -> tuple[int, BeautifulSoup]:
    return page_number, fetch_url(MOVIES_URL, page_number=page_number)


def max_page_from(soup: BeautifulSoup) -> int:
    page_numbers = [1]
    for link in soup.select(".pagination a[href]"):
        label = link.get_text(" ", strip=True)
        if label.isdigit():
            page_numbers.append(int(label))
    return max(page_numbers)


def parse_card_published_date(card: BeautifulSoup) -> str:
    """Read the displayed publish date/time directly from a card."""
    date_element = card.select_one(".item-designation small")
    if not date_element:
        return ""

    match = DATE_PATTERN.search(date_element.get_text(" ", strip=True))
    if not match:
        return ""

    published_date = match.group(0)
    datetime.strptime(
        published_date.lower().replace(" ", ""),
        "%d-%b-%Y%I:%M:%S%p",
    )
    return published_date


def load_previous_publication_dates() -> dict[str, str]:
    """Keep stored dates for items absent from the homepage's limited card set."""
    if not OUTPUT_FILE.is_file():
        return {}
    try:
        previous = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    dates: dict[str, str] = {}
    for movie in previous.get("movies", []):
        movie_id = movie_id_from_url(movie.get("detail_url", ""))
        value = movie.get("published_date", "")
        if movie_id and value:
            dates[movie_id] = value
    return dates


def parse_movies(
    soup: BeautifulSoup,
    home_dates: dict[str, str],
    previous_dates: dict[str, str],
) -> list[dict[str, str]]:
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

        # The all-catalog card supplies metadata only. Use the timestamp from the
        # homepage card with the same movie ID; do not trust the catalog timestamp.
        movie_id = movie_id_from_url(detail_url)
        # Preserve the previous saved value for IDs not present on the homepage.
        published_date = home_dates.get(movie_id) or previous_dates.get(movie_id, "")

        records.append(
            {
                "thumbnail": thumbnail,
                "title": title,
                "detail_url": detail_url,
                "published_date": published_date,
            }
        )
    return records


def scrape_all() -> tuple[list[dict[str, str]], int, int, int, int]:
    previous_dates = load_previous_publication_dates()
    home_dates = homepage_publication_dates(fetch_url(HOME_URL))
    _, first_page = fetch_page(1)
    total_pages = max_page_from(first_page)
    movies_by_url: dict[str, dict[str, str]] = {}

    def save_page(soup: BeautifulSoup) -> None:
        for movie in parse_movies(soup, home_dates, previous_dates):
            # Categories can repeat the same title; the all-movies catalog is unique by detail URL.
            movies_by_url[movie["detail_url"]] = movie

    save_page(first_page)
    if total_pages > 1:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            print(f"Fetching catalog pages with up to {MAX_WORKERS} parallel requests", flush=True)
            futures = {pool.submit(fetch_page, page): page for page in range(2, total_pages + 1)}
            completed = 1
            for future in as_completed(futures):
                page_number, soup = future.result()
                save_page(soup)
                completed += 1
                if completed % 25 == 0 or completed == total_pages:
                    print(f"Scanned {completed}/{total_pages} catalog pages", flush=True)

    def publication_time(movie: dict[str, str]) -> datetime:
        value = movie.get("published_date", "")
        if not value:
            return datetime.min
        return datetime.strptime(
            value.lower().replace(" ", ""),
            "%d-%b-%Y%I:%M:%S%p",
        )

    # Keep the newest published items at the top; undated items naturally sort last.
    movies = sorted(movies_by_url.values(), key=publication_time, reverse=True)
    if not movies:
        raise RuntimeError("No movie cards were found; output was not changed.")
    refreshed_count = sum(1 for movie in movies if movie_id_from_url(movie["detail_url"]) in home_dates)
    preserved_count = sum(
        1 for movie in movies
        if movie_id_from_url(movie["detail_url"]) not in home_dates
        and movie_id_from_url(movie["detail_url"]) in previous_dates
    )
    return movies, total_pages, len(home_dates), refreshed_count, preserved_count


def main() -> int:
    try:
        movies, pages_scanned, homepage_date_count, refreshed_count, preserved_count = scrape_all()
        result = {
            "title": f"Complete Movie List | {len(movies)} items collected",
            "description": (
                f"Collected {len(movies)} unique movie items from all "
                f"{pages_scanned} pages of the site's movie catalog. "
                f"Refreshed {refreshed_count} publication timestamps from homepage cards; "
                f"preserved {preserved_count} previously saved timestamps for items "
                f"not shown on the homepage."
            ),
            "source_url": MOVIES_URL,
            "published_date_source_url": HOME_URL,
            "published_date_match_method": "movie ID in homepage card detail URL",
            "homepage_dated_cards": homepage_date_count,
            "published_dates_refreshed_from_homepage": refreshed_count,
            "published_dates_preserved_from_previous_list": preserved_count,
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
