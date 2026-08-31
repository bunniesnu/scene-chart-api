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

from decimal import Decimal

from src.utils.logger import archive_log
import logging

logger = logging.getLogger(__name__)

from datetime import date, datetime, timezone, timedelta
from dateutil import parser
from zoneinfo import ZoneInfo
from pydantic import BaseModel
from typing import Literal, TypeGuard
import pathlib
import hashlib

localtimezone = ZoneInfo("Asia/Seoul")

from melon.models import ChartSong, SongDetail
from sqlmodel import Session, select, and_
from src.utils.log import update_with_change_log

from melon import MelonClient

from src.db.tables import (
    ChartType,
    GraphResolution,
    Song,
    SongArtist,
    SongChartSnapshot,
    ChartReportSnapshot,
    RankHistoryPoint,
    GraphPoint,
    SongStreamReport,
)
from melon.chart import (
    FiveGraph,
    ChartGraph,
)
from melon.models.song import StreamReportInfo

from src.utils.webhook import send_discord_webhook, ChartUpdate


@archive_log
def archive_charts_midnight(
    session: Session,
    client: MelonClient,
    artist_id: str,
) -> None:
    """
    Fetch and archive TOP100 chart at midnight.
    """

    logger.info("[chart] archive start (midnight)")

    archive_songs = list(session.exec(
        select(Song.song_id)
        .join(SongArtist, and_(SongArtist.song_id == Song.song_id))
        .where(SongArtist.artist_id == artist_id)
    ).all())

    archive_top100_chart(session, client, archive_songs)

    try:
        session.commit()
    except Exception:
        logger.exception("[chart] archive failed")
        session.rollback()
        raise

    logger.info("[chart] archive complete")


@archive_log
def archive_charts(
    session: Session,
    client: MelonClient,
    artist_id: str,
) -> None:
    """
    Fetch and archive all bulk Melon chart and graph endpoints.
    """

    logger.info("[chart] archive start")

    archive_songs = list(session.exec(
        select(Song.song_id)
        .join(SongArtist, and_(SongArtist.song_id == Song.song_id))
        .where(SongArtist.artist_id == artist_id)
    ).all())

    archive_realtime_chart(session, client, archive_songs)
    archive_top100_chart(session, client, archive_songs)
    archive_daily_chart(session, client, archive_songs)
    archive_weekly_chart(session, client, archive_songs)
    archive_hot100_chart(session, client, archive_songs)

    archive_hot100_graph_hour(session, client, archive_songs)
    archive_hot100_graph_five(session, client, archive_songs)

    for song_id in archive_songs:
        archive_chart_report(session, client, song_id)

    try:
        session.commit()
    except Exception:
        logger.exception("[chart] archive failed")
        session.rollback()
        raise

    logger.info("[chart] archive complete")


# ---------------------------------------------------------------------------
# Song charts
# ---------------------------------------------------------------------------


def _archive_song_chart(
    session: Session,
    chart_type: ChartType,
    songs: list[ChartSong],
    archive_songs: list[str],
    rank_day: date | None,
    rank_hour: str | None,
    bypass_and_run: bool = False,
) -> None:
    fetched_at = datetime.now(timezone.utc)

    count = 0

    updates: list[ChartUpdate] = []

    for song in songs:
        if song.song_id not in archive_songs:
            continue

        if not bypass_and_run and session.exec(
            select(SongChartSnapshot)
            .where(SongChartSnapshot.song_id == song.song_id)
            .where(SongChartSnapshot.chart_type == chart_type)
            .where(SongChartSnapshot.rank_day == rank_day)
            .where(SongChartSnapshot.rank_hour == rank_hour)
        ).first() is not None:
            continue

        session.add(
            SongChartSnapshot(
                song_id=song.song_id,
                chart_type=chart_type,
                fetched_at=fetched_at,

                rank_day=rank_day if rank_day else fetched_at.astimezone(localtimezone).date(),
                rank_hour=rank_hour,

                current_rank=song.current_rank,
                past_rank=song.past_rank,
                rank_gap=song.rank_gap,
                rank_type=song.rank_type,
            )
        )

        logger.info(
            "[chart] %s %s %s (%s)",
            chart_type,
            song.title,
            song.current_rank,
            f"{"+" if song.is_rising else ("" if song.rank_gap == 0 else "-")}{abs(song.rank_gap)}",
        )

        updates.append(
            ChartUpdate(
                name=song.title,
                new_value=song.current_rank,
                is_rising=song.is_rising,
                rank_gap=song.rank_gap,
            )
        )

        count += 1

    if count > 0:
        send_discord_webhook(
            chart_name="Melon",
            chart_type=chart_type.name,
            timeinfo=(f"{rank_day.strftime("%Y-%m-%d")} {rank_hour}" if rank_hour else rank_day.strftime("%Y-%m-%d")) if rank_day else fetched_at.strftime("%Y-%m-%d"),
            updates=updates
        )

    logger.info(
        "[chart] %s %s songs archived for %s %s",
        chart_type,
        count,
        rank_day if rank_day else "",
        rank_hour if rank_hour else "",
    )


def archive_realtime_chart(
    session: Session,
    client: MelonClient,
    archive_songs: list[str],
):
    chart = client.get_realtime_chart()

    _archive_song_chart(
        session,
        ChartType.REALTIME,
        chart.songs,
        archive_songs,
        parser.parse(chart.rank_day, ignoretz=True).date(),
        chart.rank_hour,
    )


def archive_top100_chart(
    session: Session,
    client: MelonClient,
    archive_songs: list[str],
):
    chart = client.get_top100_chart()

    _archive_song_chart(
        session,
        ChartType.TOP100,
        chart.songs,
        archive_songs,
        parser.parse(chart.rank_day, ignoretz=True).date(),
        chart.rank_hour,
    )


def get_comparable_hash(comparable_text: str):
    return hashlib.sha256(
        comparable_text.encode()
    ).hexdigest()


def archive_daily_chart(
    session: Session,
    client: MelonClient,
    archive_songs: list[str],
):
    chart = client.get_daily_chart()

    cursor_path = pathlib.Path("/app/cursor/daily.json")

    old_cursor = None
    if cursor_path.exists():
        old_cursor = cursor_path.read_text().strip()

    new_comparable_text = chart.model_dump_json(exclude_none=False)
    new_cursor = get_comparable_hash(new_comparable_text)

    if old_cursor == new_cursor:
        logger.info("[chart] daily chart unchanged")
        return

    _archive_song_chart(
        session,
        ChartType.DAILY,
        chart.songs,
        archive_songs,
        None,
        None,
        bypass_and_run=True
    )

    cursor_path.parent.mkdir(parents=True, exist_ok=True)
    cursor_path.write_text(new_cursor)


def archive_weekly_chart(
    session: Session,
    client: MelonClient,
    archive_songs: list[str],
):
    chart = client.get_weekly_chart()

    _archive_song_chart(
        session,
        ChartType.WEEKLY,
        chart.songs,
        archive_songs,
        parser.parse(chart.end_day, ignoretz=True).date(),
        None,
    )


def archive_hot100_chart(
    session: Session,
    client: MelonClient,
    archive_songs: list[str],
):
    chart = client.get_hot100_chart()

    _archive_song_chart(
        session,
        ChartType.HOT100,
        chart.songs,
        archive_songs,
        parser.parse(chart.rank_day, ignoretz=True).date(),
        chart.rank_hour,
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
    if report is None:
        return
    
    recent_time = report.recent_time
    report_date = datetime.now(localtimezone).date()

    existing = session.exec(
        select(ChartReportSnapshot)
        .where(ChartReportSnapshot.song_id == song_id)
        .where(ChartReportSnapshot.report_date == report_date)
        .where(ChartReportSnapshot.recent_time == recent_time)
    ).first()

    if existing is not None:
        logger.info(
            "[chart-report] %s already archived at %s",
            song_id,
            recent_time,
        )
        return

    snapshot = ChartReportSnapshot(
        song_id=song_id,
        fetched_at=datetime.now(timezone.utc),

        recent_time=recent_time,
        report_date=report_date,

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
        "[chart-report] %s archived at %s %s",
        song_id,
        report_date,
        recent_time,
    )


# ---------------------------------------------------------------------------
# Hot100 graphs
# ---------------------------------------------------------------------------


def archive_hot100_graph_hour(
    session: Session,
    client: MelonClient,
    archive_songs: list[str],
):
    graph = client.get_hot100_graph_hour()

    _archive_graph(
        session,
        graph,
        GraphResolution.HOURLY,
        archive_songs,
    )


def archive_hot100_graph_five(
    session: Session,
    client: MelonClient,
    archive_songs: list[str],
):
    graph = client.get_hot100_graph_five()

    if graph is None:
        logger.info("[graph] hot100 five graph is None")
        return

    _archive_graph(
        session,
        graph,
        GraphResolution.FIVE_MIN,
        archive_songs,
    )


def hourly_config(rank_day: str, x_categories: list[str]):
    new_rank_day = datetime.strptime(
        rank_day,
        "%Y.%m.%d",
    )

    hours = [
        int(category.removesuffix("시"))
        for category in x_categories
    ]

    midnight_index = next(
        (
            i
            for i in range(1, len(hours))
            if hours[i] < hours[i - 1]
        ),
        None,
    )

    return new_rank_day, hours, midnight_index


class NotHourlyConfig(BaseModel):
    is_hourly: Literal[False] = False

class IsHourlyConfig(BaseModel):
    is_hourly: Literal[True] = True
    rank_day: datetime
    hours: list[int]
    midnight_index: int | None

Config = IsHourlyConfig | NotHourlyConfig

def is_hourly_config(
    config: Config,
) -> TypeGuard[IsHourlyConfig]:
    return config.is_hourly


def _archive_graph(
    session: Session,
    graph: ChartGraph | FiveGraph,
    resolution: GraphResolution,
    archive_songs: list[str],
):
    fetch_batch_at = datetime.now(timezone.utc)

    count = 0

    is_hourly = "시" in graph.x_categories[0]
    if is_hourly:
        rank_day, hours, midnight_index = hourly_config(graph.rank_day, graph.x_categories)
        config = IsHourlyConfig(
            rank_day=rank_day,
            hours=hours,
            midnight_index=midnight_index,
        )
    else:
        config = NotHourlyConfig()

    for song_graph in graph.graph_data_list:
        str_song_id = str(song_graph.song_id)
        if str_song_id not in archive_songs:
            continue

        for point in song_graph.graph_data:
            if is_hourly_config(config):
                hour = config.hours[point.x]

                point_at = config.rank_day.replace(
                    hour=hour,
                    minute=0,
                    second=0,
                    microsecond=0,
                )

                if config.midnight_index is not None and point.x < config.midnight_index:
                    point_at -= timedelta(days=1)
            else:
                point_at = datetime.strptime(
                    f"{graph.rank_day} {graph.x_categories[point.x]}",
                    "%Y.%m.%d %H:%M",
                )
            point_at = point_at.replace(tzinfo=localtimezone)

            existing = session.exec(
                select(GraphPoint)
                .where(GraphPoint.song_id == str_song_id)
                .where(GraphPoint.resolution == resolution)
                .where(GraphPoint.point_at == point_at)
            ).first()

            if existing is None:
                item = GraphPoint(
                    song_id=str_song_id,
                    resolution=resolution,
                    fetch_batch_at=fetch_batch_at,
                    point_at=point_at,

                    value=point.value,
                    rank=getattr(
                        point,
                        "rank",
                        None,
                    ),
                )
                session.add(item)
                logger.info("%s", item.point_at)
                count += 1
            elif (
                existing.value != point.value
                or existing.rank != getattr(point, "rank", None)
            ):
                updates = {
                    "value": point.value,
                    "rank": getattr(point, "rank", None),
                }
                changes = update_with_change_log(
                    session,
                    entity_type="graph_point",
                    entity_id=str(existing.id),
                    obj=existing,
                    updates=updates,
                )

                if changes:
                    logger.info(
                        "[graph] changed song=%s point_at=%s: %s",
                        song_graph.song_id,
                        point_at,
                        changes,
                    )


    logger.info(
        "[graph] %s +%s",
        resolution.value,
        count,
    )


# ---------------------------------------------------------------------------
# Song stream report
# ---------------------------------------------------------------------------


@archive_log
def archive_stream_reports(
    session: Session,
    client: MelonClient,
    artist_id: str,
) -> None:
    """
    Fetch and archive song reports.
    """

    logger.info("[stream-report] archive start")

    archive_songs = session.exec(
        select(Song.song_id)
        .join(SongArtist, and_(SongArtist.song_id == Song.song_id))
        .where(SongArtist.artist_id == artist_id)
    ).all()

    logger.info("[stream-report] %s songs to archive", len(archive_songs))

    for song in archive_songs:
        song_detail = client.get_song_detail(song)
        if song_detail is None:
            logger.warning("[stream-report] %s detail not found", song)
            continue

        _archive_stream_report(session, song_detail)

    try:
        session.commit()
    except Exception:
        logger.exception("[stream-report] archive failed")
        session.rollback()
        raise

    logger.info("[stream-report] archive complete")

def _archive_stream_report(
    session: Session,
    song_detail: SongDetail,
):
    song_id = song_detail.song.song_id
    new_report = song_detail.stream_report
    fetched_at = datetime.now(timezone.utc)
    today_date = fetched_at.astimezone(localtimezone).date()

    gender = new_report.gender_percent
    new = SongStreamReport(
        song_id=song_id,

        fetched_at=fetched_at,
        updated_at=fetched_at,

        report_date=today_date,

        daily_listener_count=new_report.daily_listener_count,
        total_listen_count=new_report.total_listen_count,
        total_listener_count=new_report.total_listener_count,

        male_percent=Decimal(gender.male) if gender else None,
        female_percent=Decimal(gender.female) if gender else None,
        age_percent=new_report.age_percent,

        yesterday_rank=song_detail.achievement.yesterday_chart_rank if song_detail.achievement else None
    )
    session.add(new)
    logger.info(
        "[stream-report] %s archived at %s",
        song_id,
        today_date,
    )