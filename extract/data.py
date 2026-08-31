from zoneinfo import ZoneInfo
from pydantic import BaseModel

from src.db.tables import ChartType

localtimezone = ZoneInfo("Asia/Seoul")

import requests
from bs4 import BeautifulSoup
from datetime import datetime, date


TOP100_URL = "https://xn--o39an51b2re.com/chart/melon/top100/trend/ranking/"
REALTIME_URL = "https://xn--o39an51b2re.com/chart/melon/realtime/trend/ranking/"
HOT100_URL = "https://xn--o39an51b2re.com/chart/melon/hot100-d100/trend/ranking/"
DAILY_URL = "https://xn--o39an51b2re.com/chart/melon/daily/trend/ranking/"

def get_url(chart_type: ChartType, song_id: str) -> str:
    if chart_type == ChartType.TOP100:
        return f"{TOP100_URL}{song_id}"
    elif chart_type == ChartType.REALTIME:
        return f"{REALTIME_URL}{song_id}"
    elif chart_type == ChartType.HOT100:
        return f"{HOT100_URL}{song_id}"
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")


class RankData(BaseModel):
    timestamp: datetime
    rank: int

def get_rank_data(chart_type: ChartType, song_id: str) -> list[RankData]:
    response = requests.get(
        get_url(chart_type, song_id),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
            )
        },
        timeout=10,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.select_one("#trend-table")
    if table is None:
        raise ValueError("Could not find #trend-table")

    results: list[RankData] = []

    for row in table.select("tbody tr"):
        cells = row.select("td")

        if not cells:
            continue

        date = cells[0].get_text(strip=True)

        if len(date) != 8 or not date.isdigit():
            continue

        for hour, cell in enumerate(cells[1:25]):
            value = cell.get_text(strip=True)

            # Empty cell = no chart data
            if not value:
                continue

            try:
                rank = int(value)
            except ValueError:
                continue

            timestamp = datetime.strptime(
                f"{date}{hour:02d}",
                "%Y%m%d%H",
            ).replace(tzinfo=ZoneInfo("Asia/Seoul"))

            results.append(
                RankData(
                    timestamp=timestamp,
                    rank=rank
                )
            )

    return results


# Daily rank data extraction

class DailyRankData(BaseModel):
    report_date: date
    rank: int | None
    listener_count: int | None
    listener_change: int | None

    male_percent: float | None
    female_percent: float | None

    age_10s_percent: int | None
    age_20s_percent: int | None
    age_30s_percent: int | None
    age_40s_percent: int | None
    age_50s_percent: int | None
    age_60s_percent: int | None

def parse_int(value: str) -> int | None:
    value = value.strip()

    if value == "-":
        return None

    return int(value.replace(",", "").replace("+", ""))

def parse_percent(value: str) -> float | None:
    value = value.strip()

    if value == "-":
        return None

    return float(value.rstrip("%"))

def parse_int_percent(value: str) -> int | None:
    value = value.strip()

    if value == "-":
        return None

    value = value.rstrip("%")

    parsed = float(value)

    if not parsed.is_integer():
        raise ValueError(f"Expected integer percentage, got: {value}")

    return int(parsed)

def get_daily_rank_data(song_id: str) -> list[DailyRankData]:
    response = requests.get(
        f"{DAILY_URL}{song_id}",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
            )
        },
        timeout=10,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.select_one("#trend-table")
    if table is None:
        raise ValueError("Could not find #trend-table")

    results: list[DailyRankData] = []

    for row in table.select("tbody tr"):
        cells = row.select("td")

        if len(cells) < 12:
            continue

        date = cells[0].get_text(strip=True)

        if len(date) != 8 or not date.isdigit():
            continue

        report_date = datetime.strptime(
            date,
            "%Y%m%d",
        ).replace(tzinfo=localtimezone).date()

        results.append(
            DailyRankData(
                report_date=report_date,
                rank=parse_int(cells[1].get_text(strip=True)),
                listener_count=parse_int(cells[2].get_text(strip=True)),
                listener_change=parse_int(cells[3].get_text(strip=True)),
                male_percent=parse_percent(cells[4].get_text(strip=True)),
                female_percent=parse_percent(cells[5].get_text(strip=True)),
                age_10s_percent=parse_int_percent(cells[6].get_text(strip=True)),
                age_20s_percent=parse_int_percent(cells[7].get_text(strip=True)),
                age_30s_percent=parse_int_percent(cells[8].get_text(strip=True)),
                age_40s_percent=parse_int_percent(cells[9].get_text(strip=True)),
                age_50s_percent=parse_int_percent(cells[10].get_text(strip=True)),
                age_60s_percent=parse_int_percent(cells[11].get_text(strip=True)),
            )
        )

    return results

if __name__ == "__main__":
    rank_data = get_rank_data(ChartType.TOP100, "37928381")
    for data in rank_data:
        print(data)
    daily_rank_data = get_daily_rank_data("37928381")
    for data in daily_rank_data:
        print(data)