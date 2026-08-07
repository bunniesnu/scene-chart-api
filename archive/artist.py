"""Archive functions: fetch melon-api data for one artist and log it into the
SQLModel schema defined in melon_models.py.

archive_artist() is one "fetch cycle": it upserts the artist's dimension rows
(Artist, ArtistMember, Album, Song, SongArtist) and appends a new
ArtistSnapshot row. Re-running it on a schedule (e.g. hourly, via cron/Celery)
builds the time series.
"""

from datetime import datetime, timezone

from melon.models import ArtistAlbum, Artist as ArtistDBModel, ArtistDetail, ArtistSong
from melon.models.artist import ArtistMember as ArtistMemberDBModel
from sqlmodel import Session, select

from melon import MelonClient
from src.db.tables import (
    Album,
    AlbumArtist,
    Artist,
    ArtistMember,
    ArtistSnapshot,
    Song,
    SongArtist,
)

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def archive_artist(session: Session, client: MelonClient, artist_id: str) -> Artist:
    """Fetch artist detail, chart standing, albums, and songs for `artist_id`
    and log them via `session`.

    Upserts Artist / ArtistMember / Album / Song / SongArtist. Appends one new
    ArtistSnapshot row for this fetch (the artist chart is scanned for the
    entry matching `artist_id`; if the artist isn't currently charting, no
    snapshot row is added). Commits and returns the upserted Artist row.
    """
    logger.info(f"[archive] artist={artist_id}")

    detail = client.get_artist_detail(artist_id)
    artist = _upsert_artist(session, detail)
    logger.info(f"[archive] artist {'created' if artist.first_seen_at == artist.last_updated_at else 'updated'}")

    for member in detail.member_list:
        _upsert_member(session, artist_id, member)

    chart = client.get_artist_chart()
    entry = next((e for e in chart.artists if e.artist_id == artist_id), None)
    if entry is not None:
        session.add(
            ArtistSnapshot(
                artist_id=artist_id,
                current_rank=entry.current_rank,
                past_rank=entry.past_rank,
                rank_gap=entry.rank_gap,
                top_rank=entry.top_rank,
                past_week_rank=entry.past_week_rank,
                total_fan_count=entry.total_fan_count,
                increment_fan_count=entry.increment_fan_count,
                increment_type=entry.increment_type,
                song_index=entry.song_index,
                mv_index=entry.mv_index,
                photo_index=entry.photo_index,
                fan_index=entry.fan_index,
                like_index=entry.like_index,
                toc_index=entry.toc_index,
            )
        )
        logger.info(f"[archive] snapshot rank={entry.current_rank}")

    albums = client.get_artist_albums(artist_id)
    for album in albums.albums:
        _upsert_album(session, artist_id, album)

    songs = client.get_artist_songs(artist_id)
    for song in songs.songs:
        _upsert_song(session, song)

    session.commit()
    session.refresh(artist)
    logger.info(f"[archive] done artist={artist_id}")
    return artist


def _upsert_artist(session: Session, detail: ArtistDetail) -> Artist:
    artist = session.get(Artist, detail.artist_id)
    if artist is None:
        artist = Artist(artist_id=detail.artist_id, name=detail.artist_name)
        session.add(artist)
        logger.info(f"[archive] artist + {detail.artist_id}")

    artist.name = detail.artist_name
    artist.debut_date = detail.debut_date
    artist.nationality = detail.nationality
    artist.gender = detail.gender
    artist.act_type = detail.act_type
    artist.act_genre = detail.act_genre
    artist.company_name = detail.company_name
    artist.intro = detail.intro
    artist.last_updated_at = datetime.now(timezone.utc)
    return artist


def _upsert_member(session: Session, artist_id: str, member: ArtistMemberDBModel) -> None:
    existing = session.exec(
        select(ArtistMember).where(
            ArtistMember.artist_id == artist_id,
            ArtistMember.member_artist_id == member.artist_id,
        )
    ).first()
    if existing is not None:
        return
    session.add(
        ArtistMember(
            artist_id=artist_id,
            member_artist_id=member.artist_id,
            member_name=member.artist_name,
            act_type_name=member.act_type_name,
            debut_day=member.debut_day,
            birthday=member.birthday,
        )
    )
    logger.info(f"[archive] member + {member.artist_id}")


def _upsert_album(session: Session, artist_id: str, album: ArtistAlbum) -> None:
    existing = session.get(Album, album.album_id)
    if existing is None:
        session.add(
            Album(
                album_id=album.album_id,
                name=album.album_name,
                issue_date=album.issue_date,
                song_count=album.song_cnt,
                content_type=album.content_type,
            )
        )
        session.add(
            AlbumArtist(
                album_id=album.album_id,
                artist_id=artist_id,
            )
        )
        logger.info(f"[archive] album + {album.album_id}")


def _upsert_song(session: Session, song: ArtistSong) -> None:
    existing = session.get(Song, song.song_id)
    if existing is None:
        session.add(
            Song(
                song_id=song.song_id,
                title=song.title,
                album_id=song.album_id,
                play_time=song.play_time,
                issue_date=song.issue_date,
                is_title_song=getattr(song, "is_title_song", None),
            )
        )
        logger.info(f"[archive] song + {song.song_id}")

    for credited in song.artists:
        _upsert_song_artist(session, song.song_id, credited)


def _upsert_song_artist(session: Session, song_id: str, credited: ArtistDBModel) -> None:
    # Ensure a minimal Artist stub exists so the FK resolves, without
    # clobbering a fuller row already fetched via get_artist_detail.
    stub = session.get(Artist, credited.artist_id)
    if stub is None:
        session.add(Artist(artist_id=credited.artist_id, name=credited.name))
        logger.info(f"[archive] artist stub + {credited.artist_id}")

    link = session.exec(
        select(SongArtist).where(
            SongArtist.song_id == song_id,
            SongArtist.artist_id == credited.artist_id,
        )
    ).first()
    if link is None:
        session.add(
            SongArtist(
                song_id=song_id,
                artist_id=credited.artist_id,
                credited_name=credited.name,
            )
        )
        logger.info(f"[archive] credit + {song_id}/{credited.artist_id}")