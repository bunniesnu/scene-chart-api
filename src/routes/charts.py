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
        select(func.max(SongChartSnapshot.rank_day), func.max(SongChartSnapshot.rank_hour))
        .join(Song, and_(Song.song_id == SongChartSnapshot.song_id))
        .join(SongArtist, and_(SongArtist.song_id == Song.song_id))
        .where(
            SongArtist.artist_id == ARTIST_ID,
            SongChartSnapshot.chart_type == chart_type,
        )
    ).one_or_none()

    if latest is None:
        raise HTTPException(
            status_code=404,
            detail="No chart data found",
        )

    latest_rank_day, latest_rank_hour = latest

    snapshots = session.exec(
        select(SongChartSnapshot, Song)
        .join(Song, and_(Song.song_id == SongChartSnapshot.song_id))
        .join(SongArtist, and_(SongArtist.song_id == Song.song_id))
        .where(
            SongArtist.artist_id == ARTIST_ID,
            SongChartSnapshot.chart_type == chart_type,
            SongChartSnapshot.rank_day == latest_rank_day,
            SongChartSnapshot.rank_hour == latest_rank_hour,
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
    fromDate: date | None = Query(default=None, alias="from"),
    toDate: date | None = Query(default=None, alias="to"),
):
    song_snapshots = session.exec(
        select(SongChartSnapshot, Song)
        .join(Song, and_(Song.song_id == SongChartSnapshot.song_id))
        .join(SongArtist, and_(SongArtist.song_id == Song.song_id))
        .where(
            SongArtist.artist_id == ARTIST_ID,
            SongChartSnapshot.chart_type == chart_type,
            SongChartSnapshot.song_id == songId,
            (SongChartSnapshot.rank_day >= fromDate if fromDate else True),
            (SongChartSnapshot.rank_day <= toDate if toDate else True),
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