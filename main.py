import logging

from melon import MelonClient
from sqlmodel import Session

from archive.artist import archive_artist
from archive.chart import archive_charts
from src.db.db import engine


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

ARTIST_ID = "3709231"


def main() -> None:
    client = MelonClient()

    with Session(engine) as session:
        archive_artist(session, client, ARTIST_ID)
        # archive_charts(session, client)


if __name__ == "__main__":
    main()
