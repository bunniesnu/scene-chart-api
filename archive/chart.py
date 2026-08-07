"""
Archive Melon chart data.

Stores:
- realtime chart
- top100 chart
- daily chart
- weekly chart
- hot100 chart
- chart reports
- hot100 graphs

All chart tables are append-only snapshots.
"""

from datetime import datetime, timezone

import logging

from melon.models import ChartSong
from sqlmodel import Session

from melon import MelonClient

from src.db.tables import (
    ChartType,
    GraphResolution,
    Song,
    SongChartSnapshot,
    ChartReportSnapshot,
    RankHistoryPoint,
    GraphPoint,
)

logger = logging.getLogger(__name__)


def archive_charts(
    session: Session,
    client: MelonClient,
) -> None:
    """
    Fetch and archive every Melon chart endpoint.
    """

    logger.info("[chart] archive start")

    archive_realtime_chart(session, client)
    archive_top100_chart(session, client)
    archive_daily_chart(session, client)
    archive_weekly_chart(session, client)
    archive_hot100_chart(session, client)

    archive_hot100_graph_hour(session, client)
    archive_hot100_graph_five(session, client)

    session.commit()

    logger.info("[chart] archive complete")


# ---------------------------------------------------------------------------
# Song charts
# ---------------------------------------------------------------------------


def _archive_song_chart(
    session: Session,
    chart_type: ChartType,
    songs: list[ChartSong],
) -> None:
    fetched_at = datetime.now(timezone.utc)

    count = 0

    for song in songs:
        _ensure_song(session, song)

        session.add(
            SongChartSnapshot(
                song_id=song.song_id,
                chart_type=chart_type,
                fetched_at=fetched_at,

                rank_day=getattr(song, "rank_day", None),
                rank_hour=getattr(song, "rank_hour", None),

                current_rank=song.current_rank,
                past_rank=song.past_rank,
                rank_gap=song.rank_gap,
                rank_type=song.rank_type,
            )
        )

        count += 1

    logger.info(
        f"[chart] {chart_type.value} +{count}"
    )


def archive_realtime_chart(
    session: Session,
    client: MelonClient,
):
    chart = client.get_realtime_chart()

    _archive_song_chart(
        session,
        ChartType.REALTIME,
        chart.songs,
    )


def archive_top100_chart(
    session: Session,
    client: MelonClient,
):
    chart = client.get_top100_chart()

    _archive_song_chart(
        session,
        ChartType.TOP100,
        chart.songs,
    )


def archive_daily_chart(
    session: Session,
    client: MelonClient,
):
    chart = client.get_daily_chart()

    _archive_song_chart(
        session,
        ChartType.DAILY,
        chart.songs,
    )


def archive_weekly_chart(
    session: Session,
    client: MelonClient,
):
    chart = client.get_weekly_chart()

    _archive_song_chart(
        session,
        ChartType.WEEKLY,
        chart.songs,
    )


def archive_hot100_chart(
    session: Session,
    client: MelonClient,
):
    chart = client.get_hot100_chart()

    _archive_song_chart(
        session,
        ChartType.HOT100,
        chart.songs,
    )


# ---------------------------------------------------------------------------
# Chart report
# ---------------------------------------------------------------------------


def archive_chart_report(
    session: Session,
    client: MelonClient,
    song_id: str,
):
    """
    Archive one song's detailed chart report.
    """

    report = client.get_chart_report(song_id)

    snapshot = ChartReportSnapshot(
        song_id=song_id,
        fetched_at=datetime.utcnow(),

        recent_time=getattr(
            report,
            "recent_time",
            None,
        ),

        current_rank=report.song_info.current_rank,
        past_rank=report.song_info.past_rank,
        rank_gap=report.song_info.rank_gap,
        rank_type=report.song_info.rank_type,

        listener_one_hour=(
            report.listener_data.one_hour
            if report.listener_data
            else None
        ),

        listener_one_day=(
            report.listener_data.one_day
            if report.listener_data
            else None
        ),
    )

    session.add(snapshot)
    session.flush()


    for point in report.rank_chart.data:
        session.add(
            RankHistoryPoint(
                report_snapshot_id=snapshot.id,
                is_predicted=False,

                x_index=point.x_index,
                value=point.value,
                label=point.label,
            )
        )


    for point in (
        report.rank_chart.predicted_data
        or []
    ):
        session.add(
            RankHistoryPoint(
                report_snapshot_id=snapshot.id,
                is_predicted=True,

                x_index=point.x_index,
                value=point.value,
                label=point.label,
            )
        )


    logger.info(
        f"[chart-report] {song_id}"
    )


# ---------------------------------------------------------------------------
# Hot100 graphs
# ---------------------------------------------------------------------------


def archive_hot100_graph_hour(
    session: Session,
    client: MelonClient,
):
    graph = client.get_hot100_graph_hour()

    _archive_graph(
        session,
        graph,
        GraphResolution.HOURLY,
    )


def archive_hot100_graph_five(
    session: Session,
    client: MelonClient,
):
    graph = client.get_hot100_graph_five()

    _archive_graph(
        session,
        graph,
        GraphResolution.FIVE_MIN,
    )


def _archive_graph(
    session: Session,
    graph,
    resolution: GraphResolution,
):
    fetch_batch_at = datetime.utcnow()

    count = 0

    for song_graph in graph.ent_graph_data:

        song_id = song_graph.song_id

        _ensure_song(
            session,
            song_graph,
        )

        for point in song_graph.data:

            session.add(
                GraphPoint(
                    song_id=song_id,
                    resolution=resolution,
                    fetch_batch_at=fetch_batch_at,

                    x=point.x,
                    value=point.value,
                    rank=getattr(
                        point,
                        "rank",
                        None,
                    ),
                )
            )

            count += 1


    logger.info(
        f"[graph] {resolution.value} +{count}"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_song(
    session: Session,
    song,
):
    """
    Create a minimal Song row if chart data contains an unknown song.
    """

    song_id = song.song_id

    if session.get(Song, song_id):
        return

    session.add(
        Song(
            song_id=song_id,

            title=getattr(
                song,
                "title",
                getattr(
                    song,
                    "song_name",
                    "",
                ),
            ),

            album_id=getattr(
                song,
                "album_id",
                None,
            ),

            play_time=getattr(
                song,
                "play_time",
                None,
            ),

            issue_date=getattr(
                song,
                "issue_date",
                None,
            ),
        )
    )

    logger.info(
        f"[song] stub + {song_id}"
    )