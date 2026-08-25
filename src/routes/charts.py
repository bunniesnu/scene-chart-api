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
    latest_fetch_at = session.exec(
        select(func.max(SongChartSnapshot.fetched_at))
        .join(Song, and_(Song.song_id == SongChartSnapshot.song_id))
        .join(SongArtist, and_(SongArtist.song_id == Song.song_id))
        .where(
            SongArtist.artist_id == ARTIST_ID,
            SongChartSnapshot.chart_type == chart_type,
        )
    ).one()

    if latest_fetch_at is None:
        raise HTTPException(
            status_code=404,
            detail="No chart data found",
        )

    snapshots = session.exec(
        select(SongChartSnapshot, Song)
        .join(Song, and_(Song.song_id == SongChartSnapshot.song_id))
        .join(SongArtist, and_(SongArtist.song_id == Song.song_id))
        .where(
            SongArtist.artist_id == ARTIST_ID,
            SongChartSnapshot.chart_type == chart_type,
            SongChartSnapshot.fetched_at == latest_fetch_at,
        )
        .order_by(col(SongChartSnapshot.current_rank))
    ).all()

    return ChartResponse(
        chart_type=chart_type,
        fetched_at=latest_fetch_at,
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
    songs: list[str] = Query(),
):
    snapshots = session.exec(
        select(SongChartSnapshot, Song)
        .join(Song, and_(Song.song_id == SongChartSnapshot.song_id))
        .join(SongArtist, and_(SongArtist.song_id == Song.song_id))
        .where(
            SongArtist.artist_id == ARTIST_ID,
            SongChartSnapshot.chart_type == chart_type,
            col(SongChartSnapshot.song_id).in_(songs),
        )
        .order_by(
            SongChartSnapshot.song_id,
            col(SongChartSnapshot.rank_day).asc(),
            col(SongChartSnapshot.rank_hour).asc(),
        )
    ).all()

    song_snapshots: dict[str, tuple[Song, list[SongChartSnapshot]]] = {}

    for snapshot, song in snapshots:
        if song.song_id not in song_snapshots:
            song_snapshots[song.song_id] = (song, [])
        song_snapshots[song.song_id][1].append(snapshot)

    return ChartHistoryResponse(
        chart_type=chart_type,
        entries=[
            ChartHistoryEntryResponse(
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
                    ) for snapshot in snapshots
                ]
            ) for song, snapshots in song_snapshots.values()
        ],
    )