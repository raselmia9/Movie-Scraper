# Movie-Scraper

Collects movie metadata from every page of the public movie catalog at `http://103.203.93.2/movies`.

## Current collection

- **12,200 unique movie items collected** across **407 catalog pages** in the latest full run.
- `movies.json` includes a title, item count, source URL, pages scanned, collection time, and a `movies` array.
- Each movie record contains its thumbnail URL, full title, detail-page URL, and `published_date`.
- For publication timestamps, the scraper reads the home page cards and matches them to catalog records using the numeric ID in each `/video-details/{id}` URL.
- The home page currently shows only a subset of the full catalog. Matching records get the timestamp displayed on their home page card; records not currently on the home page retain their previously saved `published_date` rather than being replaced with the catalog's changing timestamp.
- The scraper requests the home page and catalog/listing pages only. It stores detail-page links but never requests those pages.

The catalog and home page can change, so item totals and available homepage timestamps are recalculated on every run.

## Run locally

```bash
python -m pip install -r requirements.txt
python scraper.py
```

Set `MOVIE_SITE_URL` to change the site's base URL, `OUTPUT_FILE` to change the output file, or `SCRAPER_WORKERS` to adjust catalog-page concurrency (1–8, default 8). The scraper uses parallel HTTP requests rather than browser tabs to avoid loading page assets.

## GitHub Actions

The workflow can be started manually from the Actions tab and also runs daily at 00:15 UTC. It reads home page timestamps, scans every page linked by the movie catalog pagination with up to 8 parallel requests by default, updates `movies.json`, and commits the file if it changed. The run time depends on the source site response speed and is not guaranteed to be under one minute. In repository Settings → Actions → General, workflow permissions must allow write access to repository contents.

This collects public listing metadata only; it does not visit detail pages or download movie files.
