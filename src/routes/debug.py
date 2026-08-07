# src/routes/debug.py

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from src.db.db import get_session
from src.db.tables import (
    Artist,
    ArtistMember,
    ArtistSnapshot,
    Album,
    AlbumArtist,
    Song,
    SongArtist,
    SongChartSnapshot,
    ChartReportSnapshot,
    RankHistoryPoint,
    GraphPoint,
    Video,
    VideoViewSnapshot,
    Photo,
    Magazine,
)

router = APIRouter(prefix="/debug", tags=["debug"])


def dump_rows(session: Session, model):
    rows = session.exec(select(model)).all()
    return [
        row.model_dump(mode="json")
        for row in rows
    ]


@router.get("/melon-db")
def dump_melon_database(
    session: Session = Depends(get_session),
):
    return {
        "artists": dump_rows(session, Artist),
        "artist_members": dump_rows(session, ArtistMember),
        "artist_snapshots": dump_rows(session, ArtistSnapshot),

        "albums": dump_rows(session, Album),
        "album_artists": dump_rows(session, AlbumArtist),

        "songs": dump_rows(session, Song),
        "song_artists": dump_rows(session, SongArtist),

        "song_chart_snapshots": dump_rows(session, SongChartSnapshot),
        "chart_report_snapshots": dump_rows(session, ChartReportSnapshot),
        "rank_history_points": dump_rows(session, RankHistoryPoint),

        "graph_points": dump_rows(session, GraphPoint),

        "videos": dump_rows(session, Video),
        "video_view_snapshots": dump_rows(session, VideoViewSnapshot),

        "photos": dump_rows(session, Photo),
        "magazines": dump_rows(session, Magazine),
    }