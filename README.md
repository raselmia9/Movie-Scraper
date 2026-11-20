# Movie-Scraper

Collects movie metadata from every page of the public movie catalog at `http://103.203.93.2/movies`.

## Current collection

- **12,200 unique movie items collected** across **407 catalog pages** in the latest run.
- The first lines of `movies.json` show the list title, total item count, source URL, pages scanned, and collection time.
- Every movie record contains its thumbnail URL, full title, detail-page URL, and the publication date/time shown on its listing card.
- The scraper requests catalog/listing pages only; it stores detail-page links but never requests those pages.

The catalog can change, so the total is recalculated on every run.

## Run locally

```bash
python -m pip install -r requirements.txt
python scraper.py
```

Set `MOVIE_SITE_URL` to change the site's base URL, `OUTPUT_FILE` to change the output file, or `SCRAPER_WORKERS` to adjust page-fetch concurrency (1–8, default 4).

## GitHub Actions

The workflow can be started manually from the Actions tab and also runs daily at 00:15 UTC. It scans every page linked by the catalog's pagination, updates `movies.json`, and commits the file if it changed. In repository Settings → Actions → General, workflow permissions must allow write access to repository contents.

This collects public listing metadata only; it does not visit detail pages or download movie files.
