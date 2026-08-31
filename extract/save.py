from decimal import Decimal
import logging
import traceback

logger = logging.getLogger(__name__)

from sqlmodel import Session, and_, select

from src.db.tables import ChartType, Song, SongArtist, SongChartSnapshot, SongStreamReport

from extract.data import get_daily_rank_data, get_rank_data
from src.utils.logger import archive_log

from src.db.db import engine

from src.const import ARTIST_ID


def process_daily(song_id: str, session: Session):
    data = get_daily_rank_data(song_id)
    for point in data:
        # Check if the record already exists
        existing_record = session.exec(
            select(SongStreamReport)
            .where(
                and_(
                    SongStreamReport.song_id == song_id,
                    SongStreamReport.report_date == point.report_date,
                )
            )
        ).first()

        if existing_record:
            if (
                existing_record.daily_listener_count != point.listener_count
                or existing_record.male_percent != point.male_percent
                or existing_record.female_percent != point.female_percent
                or existing_record.age_percent is None
                or existing_record.age_percent[0] != point.age_10s_percent
                or existing_record.age_percent[1] != point.age_20s_percent
                or existing_record.age_percent[2] != point.age_30s_percent
                or existing_record.age_percent[3] != point.age_40s_percent
                or existing_record.age_percent[4] != point.age_50s_percent
                or existing_record.age_percent[5] != point.age_60s_percent
            ):
                logger.warning(
                    f"Record {point.report_date.strftime('%Y-%m-%d')} differ value: existing: {existing_record.daily_listener_count}, {existing_record.male_percent}, {existing_record.female_percent}, {existing_record.age_percent} | new: {point.listener_count}, {point.male_percent}, {point.female_percent}, {[point.age_10s_percent, point.age_20s_percent, point.age_30s_percent, point.age_40s_percent, point.age_50s_percent, point.age_60s_percent]}."
                )
            else:
                logger.info(f"Record already exists for {point.report_date}, skipping.")
            continue

        if (
            point.male_percent is None
            or point.female_percent is None
            or point.age_10s_percent is None
            or point.age_20s_percent is None
            or point.age_30s_percent is None
            or point.age_40s_percent is None
            or point.age_50s_percent is None
            or point.age_60s_percent is None
        ):
            logger.warning(f"Record {point.report_date.strftime('%Y-%m-%d')} has missing percent data. Still saving the record. {song_id} | {point.listener_count}, {point.male_percent}, {point.female_percent}, {[point.age_10s_percent, point.age_20s_percent, point.age_30s_percent, point.age_40s_percent, point.age_50s_percent, point.age_60s_percent]}")

        # Create a new record
        new_record = SongStreamReport(
            song_id=song_id,
            report_date=point.report_date,
            daily_listener_count=point.listener_count,
            male_percent=Decimal(point.male_percent) if point.male_percent else None,
            female_percent=Decimal(point.female_percent) if point.female_percent else None,
            age_percent=[
                point.age_10s_percent,
                point.age_20s_percent,
                point.age_30s_percent,
                point.age_40s_percent,
                point.age_50s_percent,
                point.age_60s_percent,
            ] if point.age_10s_percent is not None and point.age_20s_percent is not None and point.age_30s_percent is not None and point.age_40s_percent is not None and point.age_50s_percent is not None and point.age_60s_percent is not None else None,
        )
        session.add(new_record)

        logger.info(
            "[chart] %s %s %s",
            point.report_date.strftime("%Y-%m-%d"),
            ChartType.DAILY.value,
            song_id
        )


@archive_log
def main(chart_type: ChartType, commit: bool = False):
    try:
        with Session(engine) as session:
            archive_songs = list(session.exec(
                select(Song.song_id)
                .join(SongArtist, and_(SongArtist.song_id == Song.song_id))
                .where(SongArtist.artist_id == ARTIST_ID)
            ).all())
            for song_id in archive_songs:
                if chart_type == ChartType.DAILY:
                    process_daily(song_id, session)
                    continue
                data = get_rank_data(chart_type, song_id)
                print(f"Total: {len(data)}")
                for i, point in enumerate(data):
                    timestamp = point.timestamp
                    rank = point.rank

                    # Check if the record already exists
                    existing_record = session.exec(
                        select(SongChartSnapshot)
                        .where(
                            and_(
                                SongChartSnapshot.song_id == song_id,
                                SongChartSnapshot.chart_type == chart_type,
                                SongChartSnapshot.rank_day == timestamp.date(),
                                SongChartSnapshot.rank_hour == f"{timestamp.hour:0>2}:00",
                            )
                        )
                    ).first()

                    if chart_type == ChartType.TOP100:
                        if timestamp.hour in [1,8]:
                            past_rank = rank
                        elif i > 0 and (timestamp - data[i - 1].timestamp).total_seconds() == 3600:
                            past_rank = data[i - 1].rank
                        else:
                            past_rank = 0

                        if past_rank != 0:
                            rank_gap = abs(rank - past_rank)
                        else:
                            rank_gap = 0

                        if timestamp.hour in [1, 8]:
                            rank_type = "NONE"
                        elif past_rank == 0:
                            rank_type = "NEW"
                        elif rank < past_rank:
                            rank_type = "UP"
                        elif rank > past_rank:
                            rank_type = "DOWN"
                        else:
                            rank_type = "NONE"
                    elif chart_type == ChartType.REALTIME:
                        if i == 0 or rank > 100:
                            if rank <= 100:
                                logger.warning(f"First record for {timestamp.strftime('%Y-%m-%d %H:%M')} has rank {rank}, which is not greater than 100. Skipping. {song_id}")
                            continue
                        past_rank = data[i - 1].rank
                        if past_rank > 100:
                            rank_gap = 0
                        else:
                            rank_gap = abs(rank - past_rank)
                        if past_rank > 100:
                            rank_type = "NEW"
                        elif rank < past_rank:
                            rank_type = "UP"
                        elif rank > past_rank:
                            rank_type = "DOWN"
                        else:
                            rank_type = "NONE"
                    elif chart_type == ChartType.HOT100:
                        if i == 0:
                            past_rank = 0
                        elif timestamp.hour == 7 and data[i - 1].timestamp.hour == 1:
                            past_rank = data[i - 1].rank
                        elif (timestamp - data[i - 1].timestamp).total_seconds() == 3600:
                            past_rank = data[i - 1].rank
                        else:
                            past_rank = 0

                        if past_rank != 0:
                            rank_gap = abs(rank - past_rank)
                        else:
                            rank_gap = 0

                        if past_rank == 0:
                            rank_type = "NEW"
                        elif rank < past_rank:
                            rank_type = "UP"
                        elif rank > past_rank:
                            rank_type = "DOWN"
                        else:
                            rank_type = "NONE"
                    else:
                        raise ValueError(f"Unsupported chart type: {chart_type}")

                    if existing_record:
                        if existing_record.current_rank != rank or existing_record.past_rank != past_rank or existing_record.rank_gap != rank_gap or existing_record.rank_type != rank_type:
                            logger.warning(
                                f"Record {timestamp.strftime('%Y-%m-%d %H:%M')} differ value: existing: {existing_record.current_rank}, {existing_record.past_rank}, {existing_record.rank_gap}, {existing_record.rank_type} | new: {rank}, {past_rank}, {rank_gap}, {rank_type}."
                            )
                        else:
                            logger.info(f"Record already exists for {timestamp.strftime("%Y-%m-%d %H:%M")}, skipping.")
                        continue

                    # Create a new record
                    new_record = SongChartSnapshot(
                        chart_type=chart_type,
                        current_rank=rank,
                        rank_day=timestamp.date(),
                        rank_hour=f"{timestamp.hour:0>2}:00",
                        song_id=song_id,
                        past_rank=past_rank,
                        rank_gap=rank_gap,
                        rank_type=rank_type,
                    )
                    session.add(new_record)

                    logger.info(
                        "[chart] %s %s %s",
                        timestamp.strftime("%Y-%m-%d %H:%M"),
                        chart_type.value,
                        rank
                    )

                if commit:
                    session.commit()
                    logger.info("[chart] Committed changes for song_id: %s", song_id)
    except Exception as e:
        error = traceback.format_exc()
        print(error)
        return error


if __name__ == "__main__":
    main(ChartType.TOP100, True)
    main(ChartType.REALTIME, True)
    main(ChartType.HOT100, True)