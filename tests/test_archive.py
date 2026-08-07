"""Tests for archive_artist() (melon_archive.py).

No network calls: MelonClient is replaced with a MagicMock whose methods
return lightweight SimpleNamespace fixtures carrying only the attributes
archive_artist() reads. The DB is a fresh in-memory SQLite session per test.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from archive.artist import archive_artist
from src.db.tables import Album, Artist, ArtistMember, ArtistSnapshot, Song, SongArtist

ARTIST_ID = "1234567"
OTHER_CHARTING_ARTIST_ID = "9999999"
COLLAB_ID = "7654321"


def _make_client() -> MagicMock:
    """Build a MelonClient stub covering one artist's detail/chart/albums/songs."""
    client = MagicMock()

    client.get_artist_detail.return_value = SimpleNamespace(
        artist_id=ARTIST_ID,
        artist_name="Test Artist",
        debut_date="20200101",
        nationality="KOR",
        gender="FEMALE",
        act_type="GROUP",
        act_genre="GROUP",
        company_name="Test Ent.",
        intro="A test artist.",
        member_list=[
            SimpleNamespace(
                artist_id="1111111",
                artist_name="Member One",
                act_type_name="Singer",
                debut_day="20200101",
                birthday="19990101",
            )
        ],
    )

    client.get_artist_chart.return_value = SimpleNamespace(
        artists=[
            SimpleNamespace(
                artist_id=ARTIST_ID,
                current_rank=5,
                past_rank=6,
                rank_gap=1,
                top_rank=1,
                past_week_rank=6,
                total_fan_count=100_000,
                increment_fan_count=500,
                increment_type="UP",
                song_index=1.1,
                mv_index=2.2,
                photo_index=3.3,
                fan_index=4.4,
                like_index=5.5,
                toc_index=6.6,
            ),
            # A different artist's entry in the same page — must be ignored.
            SimpleNamespace(artist_id=OTHER_CHARTING_ARTIST_ID, current_rank=1),
        ]
    )

    client.get_artist_albums.return_value = SimpleNamespace(
        albums=[
            SimpleNamespace(
                album_id="ALBUM1",
                album_name="Test Album",
                issue_date="20200101",
                song_cnt=1,
                content_type="ALBUM",
            )
        ]
    )

    client.get_artist_songs.return_value = SimpleNamespace(
        songs=[
            SimpleNamespace(
                song_id="SONG1",
                title="Test Song",
                album_id="ALBUM1",
                play_time=200,
                issue_date="20200101",
                is_title_song=True,
                artists=[
                    SimpleNamespace(artist_id=ARTIST_ID, name="Test Artist"),
                    SimpleNamespace(artist_id=COLLAB_ID, name="Collab Artist"),
                ],
            )
        ]
    )

    return client


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


class TestArchiveArtist:
    def test_upserts_artist_row(self, session: Session):
        archive_artist(session, _make_client(), ARTIST_ID)

        artist = session.get(Artist, ARTIST_ID)
        assert artist is not None
        assert artist.name == "Test Artist"
        assert artist.company_name == "Test Ent."

    def test_logs_artist_member(self, session: Session):
        archive_artist(session, _make_client(), ARTIST_ID)

        members = session.exec(
            select(ArtistMember).where(ArtistMember.artist_id == ARTIST_ID)
        ).all()
        assert len(members) == 1
        assert members[0].member_name == "Member One"

    def test_appends_snapshot_for_the_requested_artist_only(self, session: Session):
        archive_artist(session, _make_client(), ARTIST_ID)

        snapshots = session.exec(
            select(ArtistSnapshot).where(ArtistSnapshot.artist_id == ARTIST_ID)
        ).all()
        assert len(snapshots) == 1
        assert snapshots[0].current_rank == 5
        assert snapshots[0].total_fan_count == 100_000

        other = session.exec(
            select(ArtistSnapshot).where(
                ArtistSnapshot.artist_id == OTHER_CHARTING_ARTIST_ID
            )
        ).all()
        assert other == []

    def test_upserts_album(self, session: Session):
        archive_artist(session, _make_client(), ARTIST_ID)

        album = session.get(Album, "ALBUM1")
        assert album is not None
        assert album.name == "Test Album"
        assert ARTIST_ID in {a.artist_id for a in album.artists}

    def test_upserts_song_and_all_credited_artists(self, session: Session):
        archive_artist(session, _make_client(), ARTIST_ID)

        song = session.get(Song, "SONG1")
        assert song is not None
        assert song.title == "Test Song"

        credits = session.exec(
            select(SongArtist).where(SongArtist.song_id == "SONG1")
        ).all()
        credited_ids = {c.artist_id for c in credits}
        assert credited_ids == {ARTIST_ID, COLLAB_ID}

    def test_creates_stub_artist_for_uncredited_collaborator(self, session: Session):
        archive_artist(session, _make_client(), ARTIST_ID)

        collaborator = session.get(Artist, COLLAB_ID)
        assert collaborator is not None
        assert collaborator.name == "Collab Artist"
        # Only a stub — no get_artist_detail call was ever made for them.
        assert collaborator.company_name is None

    def test_running_twice_does_not_duplicate_dimension_rows(self, session: Session):
        client = _make_client()
        archive_artist(session, client, ARTIST_ID)
        archive_artist(session, client, ARTIST_ID)

        assert len(session.exec(select(Album)).all()) == 1
        assert len(session.exec(select(Song)).all()) == 1
        assert len(session.exec(select(SongArtist)).all()) == 2  # not duplicated

        # Snapshots are append-only: two fetches -> two rows.
        snapshots = session.exec(
            select(ArtistSnapshot).where(ArtistSnapshot.artist_id == ARTIST_ID)
        ).all()
        assert len(snapshots) == 2