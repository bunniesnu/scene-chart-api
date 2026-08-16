from melon import MelonClient
from sqlmodel import Session

from archive.artist import archive_artist
from archive.chart import archive_charts
from src.db.db import engine

ARTIST_ID = "3709231"


def run_archive_artist():
    client = MelonClient()

    with Session(engine) as session:
        archive_artist(session, client, ARTIST_ID)


def run_archive_charts():
    client = MelonClient()

    with Session(engine) as session:
        archive_charts(session, client, ARTIST_ID)
