import logging
import traceback

logger = logging.getLogger(__name__)

from sqlmodel import Session, and_, select

from src.db.tables import ChartType, Song, SongArtist, SongChartSnapshot

from extract.data import get_rank_data
from src.utils.logger import archive_log

from src.db.db import engine

from src.const import ARTIST_ID


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