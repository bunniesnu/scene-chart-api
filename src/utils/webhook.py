from datetime import datetime, timezone
from os import getenv
from pydantic import BaseModel
import requests
from typing import Literal

def _get_webhook_url() -> str:
    url = getenv("WEBHOOK_URL")
    if url is None:
        raise ValueError("WEBHOOK_URL environment variable is not set")
    return url

CHART_NAMES = Literal["Melon"]

chart_colors: dict[CHART_NAMES, int] = {
    "Melon": 0x33FF00,
    # "Genie": 0xFF5733,
    # "Bugs": 0x3357FF,
    # "Flo": 0xFF33A1,
    # "Vibe": 0x33FFF5
}

class ChartUpdate(BaseModel):
    name: str
    new_value: int
    is_rising: bool
    rank_gap: int

def send_discord_webhook(chart_name: CHART_NAMES, chart_type: str, timeinfo: str, updates: list[ChartUpdate] = []):
    payload = {
        "username": "scene-chart bot",
        "embeds": [
            {
                "title": f"{chart_name} {chart_type} Chart Update{' (' if len(timeinfo) != 0 else ''}{timeinfo}{')' if len(timeinfo) != 0 else ''}",
                "color": chart_colors.get(chart_name, 0x000000),
                "fields": [
                    {
                        "name": "",
                        "value": f"**{update.name}** : {update.new_value} ({'🔺' if update.is_rising else ('-' if update.rank_gap == 0 else '🔻')}{f' {update.rank_gap}' if update.rank_gap != 0 else ''})",
                        "inline": False
                    } for update in updates
                ],
                "footer": {
                    "text": "scene-chart Bot"
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
    }

    response = requests.post(_get_webhook_url(), json=payload)

    if response.status_code != 204:
        raise Exception(f"Failed to send webhook: {response.status_code} - {response.text}")
    print("Sent!")

def send_something_went_wrong(error: Exception):
    payload = {
        "username": "scene-chart bot",
        "embeds": [
            {
                "title": "Something went wrong!",
                "color": 0xFF0000,
                "fields": [
                    {
                        "name": "Error",
                        "value": error.__class__.__name__,
                        "inline": False
                    }
                ],
                "footer": {
                    "text": "scene-chart Bot"
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
    }

    response = requests.post(_get_webhook_url(), json=payload)

    if response.status_code != 204:
        raise Exception(f"Failed to send webhook: {response.status_code} - {response.text}")
    print("Sent!")

if __name__ == "__main__":
    send_discord_webhook("Melon", "TOP 100", "00:00", [ChartUpdate(name="Test Song", new_value=1, is_rising=True, rank_gap=5)])