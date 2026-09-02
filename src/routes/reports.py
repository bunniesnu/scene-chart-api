from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from src.db.db import get_session
from src.db.tables import Song, SongStreamReport
from src.routes.models import SongStreamReportHistoryResponse, SongStreamReportSnapshotResponse


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get(
    "/history",
    response_model=SongStreamReportHistoryResponse,
)
def get_song_stream_report_history(
    session: Session = Depends(get_session),
    songId: str = Query(),
):
    song_snapshots = session.exec(select(SongStreamReport).where(Song.song_id == songId)).all()

    return SongStreamReportHistoryResponse(
        song_id=songId,
        snapshots=[
            SongStreamReportSnapshotResponse(
                fetched_at=snapshot.fetched_at,
                updated_at=snapshot.updated_at,
                report_date=snapshot.report_date,
                daily_listener_count=snapshot.daily_listener_count,
                total_listen_count=snapshot.total_listen_count,
                total_listener_count=snapshot.total_listener_count,
                male_percent=snapshot.male_percent,
                female_percent=snapshot.female_percent,
                yesterday_rank=snapshot.yesterday_rank,
                age_percent=snapshot.age_percent,
            ) for snapshot in song_snapshots
        ]
    )