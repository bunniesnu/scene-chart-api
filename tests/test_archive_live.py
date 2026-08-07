"""Live integration tests for archive_artist() (src/archive.py).

Hits the real Melon API for artist_id "3709231" — no mocks. Marked `live`,
matching melon-api's own convention (see melon-api/tests/test_chart_live.py):
run explicitly with `uv run pytest -m live`, or add
    [tool.pytest.ini_options]
    addopts = '-m "not live"'
to this project's pyproject.toml if you want `uv run pytest` to skip these
by default the way melon-api's Makefile `test` target does.

Assertions are intentionally loose where the real payload can legitimately
vary run to run (ranks, fan counts, chart membership) and strict where the
archive function's own contract should always hold (row upserted, no
duplicate dimension rows on a second run, etc).
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from melon import MelonClient
from archive.artist import archive_artist
from src.db.tables import Album, AlbumArtist, Artist, ArtistMember, ArtistSnapshot, Song, SongArtist

ARTIST_ID = "3709231"


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def melon_client():
    with MelonClient() as client:
        yield client


@pytest.mark.live
class TestArchiveArtist:
    """Integration tests that hit the real Melon API for artist_id 3709231."""

    def test_upserts_artist_row(self, session: Session, melon_client):
        archive_artist(session, melon_client, ARTIST_ID)

        artist = session.get(Artist, ARTIST_ID)
        assert artist is not None
        assert artist.name
        assert artist.debut_date

    def test_logs_at_least_one_member(self, session: Session, melon_client):
        archive_artist(session, melon_client, ARTIST_ID)

        members = session.exec(
            select(ArtistMember).where(ArtistMember.artist_id == ARTIST_ID)
        ).all()
        assert len(members) >= 1
        assert all(m.member_name for m in members)

    def test_appends_plausible_artist_snapshot_if_charting(self, session: Session, melon_client):
        archive_artist(session, melon_client, ARTIST_ID)

        snapshots = session.exec(
            select(ArtistSnapshot).where(ArtistSnapshot.artist_id == ARTIST_ID)
        ).all()
        # get_artist_chart() is paginated (default page_size=50); the artist
        # may or may not land on the fetched page right now, so 0 rows is a
        # legitimate outcome. If a snapshot WAS logged, sanity-check it.
        assert len(snapshots) in (0, 1)
        if snapshots:
            snap = snapshots[0]
            assert snap.current_rank >= 1
            assert snap.total_fan_count >= 0

    def test_upserts_at_least_one_album(self, session: Session, melon_client):
        archive_artist(session, melon_client, ARTIST_ID)

        albums = session.exec(
            select(Album)
            .join(AlbumArtist)
            .where(AlbumArtist.artist_id == ARTIST_ID)
        ).all()
        assert len(albums) >= 1
        assert all(a.name for a in albums)

    def test_upserts_songs_all_crediting_the_archived_artist(self, session: Session, melon_client):
        archive_artist(session, melon_client, ARTIST_ID)

        songs = session.exec(select(Song)).all()
        assert len(songs) >= 1

        credits = session.exec(
            select(SongArtist).where(SongArtist.artist_id == ARTIST_ID)
        ).all()
        # Every song fetched from get_artist_songs(ARTIST_ID) should credit
        # ARTIST_ID somewhere in its ARTISTLIST.
        assert len(credits) == len(songs)

    def test_running_twice_does_not_duplicate_dimension_rows(self, session: Session, melon_client):
        archive_artist(session, melon_client, ARTIST_ID)
        album_count_1 = len(session.exec(select(Album)).all())
        song_count_1 = len(session.exec(select(Song)).all())
        credit_count_1 = len(session.exec(select(SongArtist)).all())

        archive_artist(session, melon_client, ARTIST_ID)
        album_count_2 = len(session.exec(select(Album)).all())
        song_count_2 = len(session.exec(select(Song)).all())
        credit_count_2 = len(session.exec(select(SongArtist)).all())

        # Dimension rows are upserted, not duplicated, across two fetches...
        assert album_count_2 == album_count_1
        assert song_count_2 == song_count_1
        assert credit_count_2 == credit_count_1

        # ...but ArtistSnapshot is append-only, so a second fetch adds at
        # most one more row than the first (0 if the artist wasn't charting
        # on either fetch).
        snapshot_count = len(
            session.exec(
                select(ArtistSnapshot).where(ArtistSnapshot.artist_id == ARTIST_ID)
            ).all()
        )
        assert snapshot_count in (0, 1, 2)