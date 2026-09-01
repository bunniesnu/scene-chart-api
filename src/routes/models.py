from datetime import datetime, date
from pydantic import BaseModel, ConfigDict
from uuid import UUID

from src.db.tables import ChartType


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SongResponse(APIModel):
    song_id: str
    title: str
    album_id: str | None
    album_cover_url: str | None
    play_time: int | None
    issue_date: str | None
    is_title_song: bool | None


class SongChartSnapshotResponse(APIModel):
    id: UUID
    song_id: str

    chart_type: ChartType
    fetched_at: datetime

    rank_day: date
    rank_hour: str | None

    current_rank: int
    past_rank: int
    rank_gap: int
    rank_type: str


class ChartEntryResponse(APIModel):
    song: SongResponse
    snapshot: SongChartSnapshotResponse


class ChartResponse(APIModel):
    chart_type: ChartType
    entries: list[ChartEntryResponse]


class ChartHistorySnapshotResponse(APIModel):
    current_rank: int
    rank_day: date
    rank_hour: str | None


class ChartHistoryEntryResponse(APIModel):
    song: SongResponse
    snapshots: list[ChartHistorySnapshotResponse]


class ChartHistoryResponse(APIModel):
    chart_type: ChartType
    entry: ChartHistoryEntryResponse


class ArtistSongsResponse(APIModel):
    artist_id: str
    songs: list[SongResponse]