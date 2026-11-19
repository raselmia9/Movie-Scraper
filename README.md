# Movie-Scraper

A small Python scraper that collects public movie-card metadata from `http://103.203.93.2/`.

Each record in `movies.json` contains:

- `thumbnail`: thumbnail image URL
- `title`: full movie title
- `detail_url`: link to the movie's detail page
- `published_date`: the site's displayed upload/publish timestamp

## Run locally

```bash
python -m pip install -r requirements.txt
python scraper.py
```

Set `MOVIE_SITE_URL` to use a different listing URL, or `OUTPUT_FILE` to change the output path.

## GitHub Actions

The workflow can be run manually from the Actions tab and also runs every day at 00:15 UTC. It updates `movies.json` and commits the file when its contents change. The repository's Actions settings must allow workflows to write repository contents.

The scraper requests only the public listing page and collects metadata; it does not download movie files.
