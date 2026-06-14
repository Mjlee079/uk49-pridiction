import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import logging
from typing import List, Optional, Dict
from src.database import insert_draw

logger = logging.getLogger(__name__)

BASE_URL = "https://www.bet49s.com/historical-results"


def parse_date(date_str: str) -> Optional[str]:
    """Parse date string like 'Wednesday 3rd June 2026' to '2026-06-03'."""
    try:
        # Remove ordinal suffixes (1st, 2nd, 3rd, 4th, etc.)
        cleaned = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
        # Remove parenthetical text like (Today), (Yesterday)
        cleaned = re.sub(r'\s*\([^)]*\)', '', cleaned)
        # Parse the date
        dt = datetime.strptime(cleaned.strip(), "%A %d %B %Y")
        return dt.strftime("%Y-%m-%d")
    except Exception as e:
        logger.warning(f"Failed to parse date '{date_str}': {e}")
        return None


def fetch_page() -> Optional[BeautifulSoup]:
    """Fetch and parse the historical results page."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.5",
    }

    try:
        logger.info(f"Fetching {BASE_URL}...")
        response = requests.get(BASE_URL, headers=headers, timeout=30)
        response.raise_for_status()
        logger.info(f"Page fetched successfully: {len(response.text)} bytes")
        return BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        logger.error(f"Failed to fetch page: {e}")
        return None


def extract_draw_results(soup: BeautifulSoup, panel_id: str, draw_type: str, draw_time: str) -> List[Dict]:
    """Extract results from a specific tab panel."""
    results = []

    # Find the tab panel
    panel = soup.find("div", {"id": panel_id})
    if not panel:
        logger.error(f"Could not find {draw_type} results panel (id='{panel_id}')")
        return results

    logger.info(f"Found {draw_type} panel, parsing results...")

    # Find all h6 elements (dates) within the panel
    h6_elements = panel.find_all("h6")
    logger.info(f"Found {len(h6_elements)} date entries in {draw_type}")

    for h6 in h6_elements:
        # Parse date
        date_str = h6.get_text(strip=True)
        date_str = re.sub(r'\s*\([^)]*\)', '', date_str)
        draw_date = parse_date(date_str)

        if not draw_date:
            logger.warning(f"Could not parse date: {date_str}")
            continue

        # Find the next 6 results-number spans after this h6
        numbers = []
        bonus = None

        # Get all sibling elements after h6
        next_sibling = h6.find_next_sibling()
        count = 0
        while next_sibling and count < 7:
            if next_sibling.name == "span":
                text = next_sibling.get_text(strip=True)
                if text and text.isdigit():
                    num = int(text)
                    classes = next_sibling.get('class', [])

                    if 'results-number-bonus' in classes:
                        bonus = num
                        count += 1
                        break
                    elif 'results-number' in classes:
                        numbers.append(num)
                        count += 1

            next_sibling = next_sibling.find_next_sibling()

        # Validate we have 6 numbers and 1 bonus
        if len(numbers) == 6 and bonus is not None:
            results.append({
                "draw_date": draw_date,
                "numbers": numbers,
                "bonus": bonus,
                "draw_type": draw_type,
                "draw_time": draw_time,
            })
            logger.debug(f"Extracted: {draw_date} {draw_time} - {numbers} + {bonus}")
        else:
            logger.warning(f"Incomplete data for {draw_date} {draw_type}: {len(numbers)} numbers, bonus={bonus}")

    logger.info(f"Extracted {len(results)} {draw_type} results from page")
    return results


def extract_lunchtime_results(soup: BeautifulSoup) -> List[Dict]:
    """Extract Lunchtime results from the parsed HTML."""
    return extract_draw_results(soup, "bookmaker", "LUNCHTIME", "12:49")


def extract_brunchtime_results(soup: BeautifulSoup) -> List[Dict]:
    """Extract Brunchtime results from the parsed HTML."""
    return extract_draw_results(soup, "brunchtime", "BRUNCHTIME", "11:49")


def scrape_draw_history(draw_type: str) -> int:
    """Scrape draw history for a specific type."""
    soup = fetch_page()
    if not soup:
        return 0

    if draw_type == "LUNCHTIME":
        results = extract_lunchtime_results(soup)
    elif draw_type == "BRUNCHTIME":
        results = extract_brunchtime_results(soup)
    else:
        logger.error(f"Unknown draw type: {draw_type}")
        return 0

    inserted_count = 0
    for result in results:
        try:
            success = insert_draw(
                draw_date=result["date"],
                draw_time=result["draw_time"],
                numbers=result["numbers"],
                bonus=result["bonus"],
                draw_type=result["draw_type"],
            )
            if success:
                inserted_count += 1
        except Exception as e:
            logger.error(f"Error inserting draw {result['date']}: {e}")

    logger.info(f"Scraped {inserted_count} new {draw_type} draws")
    return inserted_count


def scrape_lunchtime_history() -> int:
    """Scrape Lunchtime draw history."""
    return scrape_draw_history("LUNCHTIME")


def scrape_brunchtime_history() -> int:
    """Scrape Brunchtime draw history."""
    return scrape_draw_history("BRUNCHTIME")


def scrape_latest_results(draw_type: str = "LUNCHTIME") -> Optional[Dict]:
    """Scrape only the latest result for a specific draw type."""
    soup = fetch_page()
    if not soup:
        return None

    if draw_type == "LUNCHTIME":
        results = extract_lunchtime_results(soup)
    elif draw_type == "BRUNCHTIME":
        results = extract_brunchtime_results(soup)
    else:
        logger.error(f"Unknown draw type: {draw_type}")
        return None

    if not results:
        logger.warning(f"No {draw_type} results found")
        return None

    # Return the first result (most recent)
    latest = results[0]

    # Insert into database
    try:
        insert_draw(
            draw_date=latest["draw_date"],
            draw_time=latest["draw_time"],
            numbers=latest["numbers"],
            bonus=latest["bonus"],
            draw_type=latest["draw_type"],
        )
        logger.info(f"Latest {draw_type} result: {latest['draw_date']} - {latest['numbers']} + {latest['bonus']}")
    except Exception as e:
        logger.error(f"Error inserting latest draw: {e}")

    return latest


def run_full_scrape():
    """Run the full historical scrape for both draw types."""
    logger.info("=" * 50)
    logger.info("Running full historical scrape for all draw types...")
    logger.info("=" * 50)
    
    brunchtime_count = scrape_brunchtime_history()
    lunchtime_count = scrape_lunchtime_history()
    
    total = brunchtime_count + lunchtime_count
    logger.info(f"Scraped {brunchtime_count} Brunchtime + {lunchtime_count} Lunchtime = {total} draws total")
    return total


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    run_full_scrape()
