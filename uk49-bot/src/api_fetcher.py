import requests
import os
import logging
from typing import Optional, List
from datetime import datetime
from src.database import insert_draw

logger = logging.getLogger(__name__)

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "lottery-results-api.p.rapidapi.com"


def fetch_live_results() -> Optional[dict]:
    """
    Fetch latest UK49 Lunchtime results from RapidAPI.
    Note: User needs to subscribe to a lottery API on RapidAPI first.
    """
    if not RAPIDAPI_KEY:
        logger.warning("RAPIDAPI_KEY not set. Skipping API fetch.")
        return None

    url = f"https://{RAPIDAPI_HOST}/getResults"

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }

    params = {
        "game": "uk49s",
        "draw": "lunchtime",
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Parse response (structure depends on the specific API)
        logger.info(f"API Response: {data}")
        return data

    except Exception as e:
        logger.error(f"API fetch failed: {e}")
        return None


def parse_and_store_api_result(api_data: dict) -> bool:
    """Parse API response and store in database."""
    try:
        # Generic parser - adjust based on actual API response format
        draw_date = api_data.get("date") or api_data.get("draw_date")
        numbers = api_data.get("numbers") or api_data.get("results", [])
        bonus = api_data.get("bonus") or api_data.get("bonus_ball", 0)

        if not draw_date or not numbers:
            logger.warning("Invalid API data format")
            return False

        # Convert date format if needed
        if isinstance(draw_date, str):
            try:
                dt = datetime.strptime(draw_date, "%Y-%m-%d")
                draw_date = dt.strftime("%Y-%m-%d")
            except:
                pass

        numbers_list = list(map(int, numbers[:6]))
        bonus = int(bonus) if bonus else 0

        return insert_draw(
            draw_date=draw_date,
            draw_time="12:49",
            numbers=numbers_list,
            bonus=bonus,
            draw_type="LUNCHTIME",
        )

    except Exception as e:
        logger.error(f"Failed to parse API result: {e}")
        return False


def get_latest_from_api() -> Optional[dict]:
    """Fetch and store the latest result from API."""
    data = fetch_live_results()
    if data:
        parse_and_store_api_result(data)
        return data
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = get_latest_from_api()
    if result:
        print(f"Latest result: {result}")
    else:
        print("No result fetched")
