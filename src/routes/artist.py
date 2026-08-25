from fastapi import APIRouter, Depends
from sqlmodel import Session, and_, col, select

from src.const import ARTIST_ID
from src.db.db import get_session
from src.db.tables import Song, SongArtist
from src.routes.models import ArtistSongsResponse, SongResponse


router = APIRouter(prefix="/artist", tags=["artist"])


@router.get(
    "/songs",
    response_model=ArtistSongsResponse,
)
def get_artist_songs(
    session: Session = Depends(get_session),
):
    songs = session.exec(
        select(Song)
        .join(SongArtist, and_(SongArtist.song_id == Song.song_id))
        .where(SongArtist.artist_id == ARTIST_ID)
    ).all()

    return ArtistSongsResponse(
        artist_id=ARTIST_ID,
        songs=[
            SongResponse(
                song_id=song.song_id,
                title=song.title,
                album_id=song.album_id,
                album_cover_url=(song.album.cover_url if song.album else None),
                play_time=song.play_time,
                issue_date=song.issue_date,
                is_title_song=song.is_title_song,
            ) for song in songs
        ]
    )