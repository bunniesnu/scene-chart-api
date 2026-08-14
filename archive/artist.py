"""Archive functions: fetch melon-api data for one artist and log it into the
SQLModel schema defined in melon_models.py.

archive_artist() is one "fetch cycle": it upserts the artist's dimension rows
(Artist, ArtistMember, Album, AlbumArtist, Song, SongArtist).

Changes to existing dimension rows are recorded in ArchiveChangeLog.
Re-running it on a schedule (e.g. hourly, via cron/Celery) keeps the dimension
tables up to date while preserving metadata change history.
"""

from src.utils.logger import archive_log
import logging

logger = logging.getLogger(__name__)

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
    Song,
    SongArtist,
)

from src.utils.log import update_with_change_log


@archive_log
def archive_artist(session: Session, client: MelonClient, artist_id: str) -> Artist:
    """Fetch and archive all available artist metadata for `artist_id`.

    Upserts Artist / ArtistMember / Album / AlbumArtist / Song / SongArtist.
    Changes to existing dimension rows are recorded in ArchiveChangeLog.

    Commits the entire fetch cycle atomically and returns the upserted Artist.
    """
    logger.info(
        "[archive] artist created id=%s",
        artist_id,
    )
    detail = client.get_artist_detail(artist_id)
    artist = _upsert_artist(session, detail)

    for member in detail.member_list:
        _upsert_member(session, artist_id, member)

    albums = client.get_artist_albums(artist_id)
    for album in albums.albums:
        _upsert_album(session, artist_id, album)

    songs = client.get_artist_songs(artist_id)
    for song in songs.songs:
        _upsert_song(session, song)

    try:
        session.commit()
    except Exception:
        logger.exception(
            "[archive] commit failed for artist=%s",
            artist_id,
        )
        session.rollback()
        raise
    session.refresh(artist)
    logger.info(
        "[archive] done artist=%s",
        artist_id,
    )
    return artist


def _upsert_artist(session: Session, detail: ArtistDetail) -> Artist:
    artist = session.get(Artist, detail.artist_id)

    is_new = artist is None

    if is_new:
        artist = Artist(artist_id=detail.artist_id, name=detail.artist_name)
        session.add(artist)

    changes = update_with_change_log(
        session,
        entity_type="artist",
        entity_id=artist.artist_id,
        obj=artist,
        skip_log=is_new,
        updates={
            "name": detail.artist_name,
            "debut_date": detail.debut_date,
            "nationality": detail.nationality,
            "gender": detail.gender,
            "act_type": detail.act_type,
            "act_genre": detail.act_genre,
            "company_name": detail.company_name,
            "intro": detail.intro,
        },
    )

    if changes or is_new:
        artist.last_updated_at = datetime.now(timezone.utc)

    if is_new:
        logger.info(
            "[archive] artist created id=%s",
            artist.artist_id,
        )
    elif changes:
        logger.info(
            "[archive] artist updated id=%s changes=%s",
            artist.artist_id,
            changes,
        )

    return artist


def _upsert_member(session: Session, artist_id: str, member: ArtistMemberDBModel) -> None:
    existing = session.exec(
        select(ArtistMember).where(
            ArtistMember.artist_id == artist_id,
            ArtistMember.member_artist_id == member.artist_id,
        )
    ).first()
    is_new = existing is None
    if is_new:
        existing = ArtistMember(
            artist_id=artist_id,
            member_artist_id=member.artist_id,
            member_name=member.artist_name,
            act_type_name=member.act_type_name,
            debut_day=member.debut_day,
            birthday=member.birthday,
        )
        session.add(existing)
    changes = update_with_change_log(
        session,
        entity_type="artist_member",
        entity_id=str(existing.id),
        obj=existing,
        skip_log=is_new,
        updates={
            "member_name": member.artist_name,
            "act_type_name": member.act_type_name,
            "debut_day": member.debut_day,
            "birthday": member.birthday,
        },
    )

    if is_new:
        logger.info(
            "[archive] member created id=%s",
            member.artist_id,
        )
    elif changes:
        logger.info(
            "[archive] member updated id=%s changes=%s",
            member.artist_id,
            changes,
        )


def _upsert_album(session: Session, artist_id: str, album: ArtistAlbum) -> None:
    existing = session.get(Album, album.album_id)
    is_new = existing is None
    if is_new:
        existing = Album(
            album_id=album.album_id,
            name=album.album_name,
            issue_date=album.issue_date,
            song_count=album.song_cnt,
            content_type=album.content_type,
        )
        session.add(existing)
    changes = update_with_change_log(
        session,
        entity_type="album",
        entity_id=album.album_id,
        obj=existing,
        skip_log=is_new,
        updates={
            "name": album.album_name,
            "issue_date": album.issue_date,
            "song_count": album.song_cnt,
            "content_type": album.content_type,
        },
    )

    if changes or is_new:
        existing.last_updated_at = datetime.now(timezone.utc)

    if is_new:
        logger.info(
            "[archive] album created id=%s",
            album.album_id,
        )
    elif changes:
        logger.info(
            "[archive] album updated id=%s changes=%s",
            album.album_id,
            changes,
        )


    link = session.exec(
        select(AlbumArtist).where(
            AlbumArtist.album_id == album.album_id,
            AlbumArtist.artist_id == artist_id,
        )
    ).first()
    if link is None:
        session.add(
            AlbumArtist(
                album_id=album.album_id,
                artist_id=artist_id,
            )
        )


def _upsert_song(session: Session, song: ArtistSong) -> None:
    existing = session.get(Song, song.song_id)
    is_new = existing is None
    if is_new:
        existing = Song(
            song_id=song.song_id,
            title=song.title,
            album_id=song.album_id,
            play_time=song.play_time,
            issue_date=song.issue_date,
            is_title_song=getattr(song, "is_title_song", None),
        )
        session.add(existing)
    changes = update_with_change_log(
        session,
        entity_type="song",
        entity_id=song.song_id,
        obj=existing,
        skip_log=is_new,
        updates={
            "title": song.title,
            "album_id": song.album_id,
            "play_time": song.play_time,
            "issue_date": song.issue_date,
            "is_title_song": getattr(song, "is_title_song", None),
        },
    )

    for credited in song.artists:
        _upsert_song_artist(session, song.song_id, credited)

    if changes or is_new:
        existing.last_updated_at = datetime.now(timezone.utc)

    if is_new:
        logger.info(
            "[archive] song created id=%s",
            song.song_id,
        )
    elif changes:
        logger.info(
            "[archive] song updated id=%s changes=%s",
            song.song_id,
            changes,
        )


def _upsert_song_artist(session: Session, song_id: str, credited: ArtistDBModel) -> None:
    # Ensure a minimal Artist stub exists so the FK resolves, without
    # clobbering a fuller row already fetched via get_artist_detail.
    stub = session.get(Artist, credited.artist_id)
    is_new = stub is None
    if is_new:
        stub = Artist(artist_id=credited.artist_id, name=credited.name)
        session.add(stub)
    changes = update_with_change_log(
        session,
        entity_type="artist",
        entity_id=credited.artist_id,
        obj=stub,
        skip_log=is_new,
        updates={
            "name": credited.name,
        },
    )
    if is_new:
        logger.info(
            "[archive] artist stub created id=%s",
            credited.artist_id,
        )
    elif changes:
        logger.info(
            "[archive] artist stub updated id=%s changes=%s",
            credited.artist_id,
            changes,
        )

    link = session.exec(
        select(SongArtist).where(
            SongArtist.song_id == song_id,
            SongArtist.artist_id == credited.artist_id,
        )
    ).first()
    if link is None:
        link = SongArtist(
            song_id=song_id,
            artist_id=credited.artist_id,
            credited_name=credited.name,
        )
        session.add(link)
        logger.info(
            "[archive] credit created %s/%s",
            song_id,
            credited.artist_id,
        )
    else:
        changes = update_with_change_log(
            session,
            entity_type="song_artist",
            entity_id=str(link.id),
            obj=link,
            updates={
                "credited_name": credited.name,
            },
        )
        if changes:
            logger.info(
                "[archive] credit updated %s/%s changes=%s",
                song_id,
                credited.artist_id,
                changes,
            )