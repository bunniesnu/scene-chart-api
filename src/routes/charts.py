from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select, and_, col

from src.const import ARTIST_ID
from src.db.db import get_session
from src.db.tables import ChartType, SongChartSnapshot, Song, SongArtist
from src.routes.models import ChartEntryResponse, ChartHistoryEntryResponse, ChartHistoryResponse, ChartHistorySnapshotResponse, ChartResponse, SongChartSnapshotResponse, SongResponse


router = APIRouter(prefix="/charts", tags=["charts"])


@router.get(
    "/{chart_type}",
    response_model=ChartResponse,
)
def get_latest_chart(
    chart_type: ChartType,
    session: Session = Depends(get_session),
):
    latest = session.exec(
        select(SongChartSnapshot)
        .join(Song, and_(Song.song_id == SongChartSnapshot.song_id))
        .join(SongArtist, and_(SongArtist.song_id == Song.song_id))
        .where(
            SongArtist.artist_id == ARTIST_ID,
            SongChartSnapshot.chart_type == chart_type,
        )
        .order_by(
            col(SongChartSnapshot.rank_day).desc(),
            col(SongChartSnapshot.rank_hour).desc(),
        )
    ).first()

    if latest is None:
        raise HTTPException(
            status_code=404,
            detail="No chart data found",
        )

    latest_per_song = (
        select(
            SongChartSnapshot.song_id,
            func.max(SongChartSnapshot.fetched_at).label("latest_fetched_at"),
        )
        .join(SongArtist, and_(SongArtist.song_id == SongChartSnapshot.song_id))
        .where(
            SongArtist.artist_id == ARTIST_ID,
            SongChartSnapshot.chart_type == chart_type,
            SongChartSnapshot.rank_day == latest.rank_day,
            SongChartSnapshot.rank_hour == latest.rank_hour,
        )
        .group_by(SongChartSnapshot.song_id)
        .subquery()
    )

    snapshots = session.exec(
        select(SongChartSnapshot, Song)
        .join(Song, and_(Song.song_id == SongChartSnapshot.song_id))
        .join(
            latest_per_song,
            and_(
                latest_per_song.c.song_id == SongChartSnapshot.song_id,
                latest_per_song.c.latest_fetched_at == SongChartSnapshot.fetched_at,
            )
        )
        .where(
            SongChartSnapshot.chart_type == chart_type,
            SongChartSnapshot.rank_day == latest.rank_day,
            SongChartSnapshot.rank_hour == latest.rank_hour,
        )
        .order_by(col(SongChartSnapshot.current_rank))
    ).all()

    return ChartResponse(
        chart_type=chart_type,
        entries=[
            ChartEntryResponse(
                song=SongResponse(
                    song_id=song.song_id,
                    title=song.title,
                    album_id=song.album_id,
                    album_cover_url=(song.album.cover_url if song.album else None),
                    play_time=song.play_time,
                    issue_date=song.issue_date,
                    is_title_song=song.is_title_song,
                ),
                snapshot=SongChartSnapshotResponse(
                    id=snapshot.id,
                    song_id=snapshot.song_id,
                    chart_type=snapshot.chart_type,
                    fetched_at=snapshot.fetched_at,
                    current_rank=snapshot.current_rank,
                    past_rank=snapshot.past_rank,
                    rank_gap=snapshot.rank_gap,
                    rank_type=snapshot.rank_type,
                    rank_day=snapshot.rank_day,
                    rank_hour=snapshot.rank_hour,
                ),
            ) for snapshot, song in snapshots
        ],
    )


@router.get(
    "/history/{chart_type}",
    response_model=ChartHistoryResponse,
)
def get_chart_history(
    chart_type: ChartType,
    session: Session = Depends(get_session),
    songId: str = Query(),
):
    latest_per_slot = (
        select(
            col(SongChartSnapshot.song_id),
            col(SongChartSnapshot.rank_day),
            col(SongChartSnapshot.rank_hour),
            func.max(SongChartSnapshot.fetched_at).label("latest_fetched_at"),
        ) 
        .where(
            SongChartSnapshot.chart_type == chart_type,
            SongChartSnapshot.song_id == songId,
        )
        .group_by(
            col(SongChartSnapshot.song_id),
            col(SongChartSnapshot.rank_day),
            col(SongChartSnapshot.rank_hour),
        )
        .subquery()
    )
    song_snapshots = session.exec(
        select(SongChartSnapshot, Song)
        .join(Song, and_(Song.song_id == SongChartSnapshot.song_id))
        .join(SongArtist, and_(SongArtist.song_id == Song.song_id))
        .join(
            latest_per_slot,
            and_(
                latest_per_slot.c.song_id == SongChartSnapshot.song_id,
                latest_per_slot.c.rank_day == SongChartSnapshot.rank_day,
                col(latest_per_slot.c.rank_hour).is_not_distinct_from(
                    SongChartSnapshot.rank_hour
                ),
                latest_per_slot.c.latest_fetched_at == SongChartSnapshot.fetched_at,
            ),
        )
        .where(
            SongArtist.artist_id == ARTIST_ID,
            SongChartSnapshot.chart_type == chart_type,
            SongChartSnapshot.song_id == songId,
        )
        .order_by(
            col(SongChartSnapshot.rank_day).asc(),
            col(SongChartSnapshot.rank_hour).asc(),
        )
    ).all()

    song = song_snapshots[0][1] if song_snapshots else None
    if not song:
        raise HTTPException(
            status_code=404,
            detail="No chart history found for the given song ID",
        )

    return ChartHistoryResponse(
        chart_type=chart_type,
        entry=ChartHistoryEntryResponse(
            song=SongResponse(
                song_id=song.song_id,
                title=song.title,
                album_id=song.album_id,
                album_cover_url=(song.album.cover_url if song.album else None),
                play_time=song.play_time,
                issue_date=song.issue_date,
                is_title_song=song.is_title_song,
            ),
            snapshots=[
                ChartHistorySnapshotResponse(
                    current_rank=snapshot.current_rank,
                    rank_day=snapshot.rank_day,
                    rank_hour=snapshot.rank_hour,
                ) for snapshot, _ in song_snapshots
            ]
        )
    )