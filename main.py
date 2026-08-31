import traceback

from melon import MelonClient
from sqlmodel import Session

from archive.artist import archive_artist
from archive.chart import archive_charts, archive_charts_midnight, archive_stream_reports
from src.const import ARTIST_ID
from src.db.db import engine
from src.utils.webhook import send_something_went_wrong


def run_archive_artist():
    try:
        client = MelonClient()

        with Session(engine) as session:
            archive_artist(session, client, ARTIST_ID)
    except Exception as e:
        send_something_went_wrong(e)
        return traceback.format_exc()


def run_archive_charts():
    try:
        client = MelonClient()

        with Session(engine) as session:
            archive_charts(session, client, ARTIST_ID)
    except Exception as e:
        send_something_went_wrong(e)
        return traceback.format_exc()

def run_archive_charts_midnight():
    try:
        client = MelonClient()

        with Session(engine) as session:
            archive_charts_midnight(session, client, ARTIST_ID)
    except Exception as e:
        send_something_went_wrong(e)
        return traceback.format_exc()

def run_archive_stream_reports():
    try:
        client = MelonClient()

        with Session(engine) as session:
            archive_stream_reports(session, client, ARTIST_ID)
    except Exception as e:
        send_something_went_wrong(e)
        return traceback.format_exc()

if __name__ == "__main__":
    run_archive_artist()
    run_archive_charts()