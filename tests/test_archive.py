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
from src.db.tables import Album, ArchiveChangeLog, Artist, ArtistMember, Song, SongArtist

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

    def test_logs_artist_field_changes(self, session: Session):
        client = _make_client()

        # First archive creates the artist.
        archive_artist(session, client, ARTIST_ID)

        # Simulate Melon metadata change.
        client.get_artist_detail.return_value.company_name = "Changed Ent."
        client.get_artist_detail.return_value.intro = "Updated intro."

        archive_artist(session, client, ARTIST_ID)

        changes = session.exec(
            select(ArchiveChangeLog).where(
                ArchiveChangeLog.entity_type == "artist",
                ArchiveChangeLog.entity_id == ARTIST_ID,
            )
        ).all()

        assert len(changes) == 2

        company_change = next(
            c for c in changes
            if c.field_name == "company_name"
        )

        assert company_change.old_value == "Test Ent."
        assert company_change.new_value == "Changed Ent."

        intro_change = next(
            c for c in changes
            if c.field_name == "intro"
        )

        assert intro_change.old_value == "A test artist."
        assert intro_change.new_value == "Updated intro."

    def test_does_not_create_change_log_when_nothing_changed(self, session: Session):
        client = _make_client()

        archive_artist(session, client, ARTIST_ID)
        archive_artist(session, client, ARTIST_ID)

        changes = session.exec(
            select(ArchiveChangeLog).where(
                ArchiveChangeLog.entity_type == "artist",
                ArchiveChangeLog.entity_id == ARTIST_ID,
            )
        ).all()

        assert changes == []


    def test_updates_existing_artist_fields(self, session: Session):
        client = _make_client()

        archive_artist(session, client, ARTIST_ID)

        client.get_artist_detail.return_value.intro = "new intro"

        archive_artist(session, client, ARTIST_ID)

        artist = session.get(Artist, ARTIST_ID)

        assert artist.intro == "new intro"


    def test_updates_existing_member_fields(self, session: Session):
        client = _make_client()

        archive_artist(session, client, ARTIST_ID)

        client.get_artist_detail.return_value.member_list[0].birthday = "20000101"

        archive_artist(session, client, ARTIST_ID)

        member = session.exec(
            select(ArtistMember).where(
                ArtistMember.artist_id == ARTIST_ID
            )
        ).first()

        assert member.birthday == "20000101"


    def test_logs_member_field_changes(self, session: Session):
        client = _make_client()

        archive_artist(session, client, ARTIST_ID)

        client.get_artist_detail.return_value.member_list[0].birthday = "20000101"

        archive_artist(session, client, ARTIST_ID)

        changes = session.exec(
            select(ArchiveChangeLog).where(
                ArchiveChangeLog.entity_type == "artist_member"
            )
        ).all()

        assert any(
            c.field_name == "birthday"
            and c.old_value == "19990101"
            and c.new_value == "20000101"
            for c in changes
        )


    def test_updates_album_metadata(self, session: Session):
        client = _make_client()

        archive_artist(session, client, ARTIST_ID)

        client.get_artist_albums.return_value.albums[0].album_name = "Changed Album"

        archive_artist(session, client, ARTIST_ID)

        album = session.get(Album, "ALBUM1")

        assert album.name == "Changed Album"


    def test_logs_album_changes(self, session: Session):
        client = _make_client()

        archive_artist(session, client, ARTIST_ID)

        client.get_artist_albums.return_value.albums[0].song_cnt = 5

        archive_artist(session, client, ARTIST_ID)

        changes = session.exec(
            select(ArchiveChangeLog).where(
                ArchiveChangeLog.entity_type == "album",
                ArchiveChangeLog.entity_id == "ALBUM1",
            )
        ).all()

        assert any(
            c.field_name == "song_count"
            for c in changes
        )


    def test_does_not_duplicate_album_artist_relation(self, session: Session):
        client = _make_client()

        archive_artist(session, client, ARTIST_ID)
        archive_artist(session, client, ARTIST_ID)

        album = session.get(Album, "ALBUM1")

        assert len(album.artists) == 1


    def test_updates_song_metadata(self, session: Session):
        client = _make_client()

        archive_artist(session, client, ARTIST_ID)

        client.get_artist_songs.return_value.songs[0].title = "Changed Song"

        archive_artist(session, client, ARTIST_ID)

        song = session.get(Song, "SONG1")

        assert song.title == "Changed Song"


    def test_logs_song_changes(self, session: Session):
        client = _make_client()

        archive_artist(session, client, ARTIST_ID)

        client.get_artist_songs.return_value.songs[0].play_time = 300

        archive_artist(session, client, ARTIST_ID)

        changes = session.exec(
            select(ArchiveChangeLog).where(
                ArchiveChangeLog.entity_type == "song",
                ArchiveChangeLog.entity_id == "SONG1",
            )
        ).all()

        assert any(
            c.field_name == "play_time"
            for c in changes
        )


    def test_updates_song_artist_credit_name(self, session: Session):
        client = _make_client()

        archive_artist(session, client, ARTIST_ID)

        client.get_artist_songs.return_value.songs[0].artists[1].name = (
            "Changed Collab"
        )

        archive_artist(session, client, ARTIST_ID)

        credit = session.exec(
            select(SongArtist).where(
                SongArtist.artist_id == COLLAB_ID
            )
        ).first()

        assert credit.credited_name == "Changed Collab"


    def test_does_not_overwrite_full_artist_with_credit_name(self, session: Session):
        client = _make_client()

        archive_artist(session, client, ARTIST_ID)

        client.get_artist_songs.return_value.songs[0].artists[0].name = (
            "Different Display Name"
        )

        archive_artist(session, client, ARTIST_ID)

        artist = session.get(Artist, ARTIST_ID)

        assert artist.name == "Test Artist"


    def test_handles_empty_member_list(self, session: Session):
        client = _make_client()

        client.get_artist_detail.return_value.member_list = []

        archive_artist(session, client, ARTIST_ID)

        members = session.exec(
            select(ArtistMember)
        ).all()

        assert members == []


    def test_handles_empty_album_list(self, session: Session):
        client = _make_client()

        client.get_artist_albums.return_value.albums = []

        archive_artist(session, client, ARTIST_ID)

        albums = session.exec(
            select(Album)
        ).all()

        assert albums == []


    def test_handles_empty_song_list(self, session: Session):
        client = _make_client()

        client.get_artist_songs.return_value.songs = []

        archive_artist(session, client, ARTIST_ID)

        songs = session.exec(
            select(Song)
        ).all()

        assert songs == []


    def test_archive_rolls_back_when_fetch_fails(self, session: Session):
        client = _make_client()

        client.get_artist_songs.side_effect = Exception(
            "melon api failed"
        )

        with pytest.raises(Exception):
            archive_artist(session, client, ARTIST_ID)

        artists = session.exec(
            select(Artist)
        ).all()

        assert artists == []


    def test_creates_independent_artists(self, session: Session):
        client = _make_client()

        archive_artist(session, client, ARTIST_ID)

        other = _make_client()
        other.get_artist_detail.return_value.artist_id = "2222222"
        other.get_artist_detail.return_value.artist_name = "Other Artist"

        archive_artist(session, other, "2222222")

        artists = session.exec(
            select(Artist)
        ).all()

        ids = {artist.artist_id for artist in artists}

        assert ARTIST_ID in ids
        assert "2222222" in ids


    def test_change_log_contains_correct_entity_types(self, session: Session):
        client = _make_client()

        archive_artist(session, client, ARTIST_ID)

        client.get_artist_detail.return_value.company_name = "Changed"

        archive_artist(session, client, ARTIST_ID)

        logs = session.exec(
            select(ArchiveChangeLog)
        ).all()

        assert {
            log.entity_type
            for log in logs
        } == {"artist"}