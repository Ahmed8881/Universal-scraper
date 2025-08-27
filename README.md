# Lead Generation Scraper (Tkinter)

A Python desktop app to find potential clients for web development services by scraping business directories (Yellow Pages and Yelp). Enter a business keyword and location, scrape results with pagination, enrich with emails/phones from websites, and export to CSV/Excel.

## Features
- Search Yellow Pages and Yelp by keyword and location
- Pagination handling and ad filtering
- Concurrency for fetching and enriching website details
- Email validation (format and basic sanity checks)
- Respectful delays to avoid server overload
- Export to CSV and Excel
- Simple Tkinter UI

## Tech Stack
- Python 3.9+
- requests, BeautifulSoup, httpx, pandas, openpyxl, lxml

## Installation
1. Ensure Python 3.9+ is installed.
2. Create and activate a virtual environment (recommended):
```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell
```
3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage
Run the desktop app:
```bash
python -m lead_scraper.main_tk
```

1. Enter a business keyword and location.
2. Click "Start Scraping".
3. When finished, click "Export CSV" or "Export Excel" to save results.

## Notes and Limits
- Google search is intentionally excluded due to TOS and bot detection. This project focuses on Yellow Pages and Yelp.
- Use responsibly. Add delays and lower concurrency if you encounter rate limits.
- You can extend by adding new sources under `lead_scraper/sources/` implementing `BaseDirectoryScraper`.

## Project Structure
```
lead_scraper/
  __init__.py
  main_tk.py
  utils.py
  details.py
  exporter.py
  sources/
    __init__.py
    base.py
    yellowpages.py
    yelp.py
```

## Development
- Modular design makes it easy to add sources or change export formats.
- PRs welcome.
