"""SQLModel schema for logging melon-api data for a specific artist over time.

Design notes
------------
- "Dimension" tables (Artist, Album, Song, Video, Photo, Magazine) hold the
  latest known metadata for an entity and are upserted on each fetch, keyed
  by Melon's own id (ARTISTID / ALBUMID / SONGID / ...).
- "Snapshot" tables are append-only time series: every fetch inserts a new
  row stamped with `fetched_at`, so you can track how a value changed over
  time (fan count, chart rank, listener count, view count, ...).
- All Melon ids are stored as `str`, matching melon-api's own models (Melon
  serializes ARTISTID/SONGID/etc. as strings, not ints).
- Field comments reference the melon-api pydantic model + Melon's original
  ALLCAPS JSON key so you can trace each column back to the source payload.
"""

from datetime import datetime, date
from enum import Enum
import uuid

from sqlalchemy import Column, Index, Enum as SAEnum, UUID as SAUUID
from sqlmodel import ARRAY, INTEGER, SQLModel, Field, Relationship, UniqueConstraint
from sqlalchemy.sql.functions import now


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ChartType(str, Enum):
    """Which chart endpoint a SongChartSnapshot row came from."""
    REALTIME = "realtime"    # ChartClient.get_realtime_chart -> RealtimeChart
    TOP100 = "top100"        # ChartClient.get_top100_chart   -> Top100Chart
    DAILY = "daily"          # ChartClient.get_daily_chart    -> DailyChart
    WEEKLY = "weekly"        # ChartClient.get_weekly_chart   -> WeeklyChart
    HOT100 = "hot100"        # ChartClient.get_hot100_chart   -> Hot100Chart


class GraphResolution(str, Enum):
    """Which Hot100 graph endpoint a GraphPoint row came from."""
    HOURLY = "hourly"        # ChartClient.get_hot100_graph_hour -> ChartGraph
    FIVE_MIN = "five_min"    # ChartClient.get_hot100_graph_five -> FiveGraph


# ---------------------------------------------------------------------------
# Dimension: Artist
# ---------------------------------------------------------------------------

class Artist(SQLModel, table=True):
    """Static artist profile. Source: ArtistClient.get_artist_detail -> ArtistDetail.
    Upsert (insert-or-update) on artist_id each time you re-fetch."""

    artist_id: str = Field(primary_key=True)             # ARTISTID
    name: str                                             # ARTISTNAME
    debut_date: str | None = None                         # DEBUTDATE
    nationality: str | None = None                        # NATIONALITY
    gender: str | None = None                             # GENDER
    act_type: str | None = None                           # ACTTYPE
    act_genre: str | None = None                          # ACTGENRE
    company_name: str | None = None                       # COMPNAME
    intro: str | None = None                              # INTRO
    first_seen_at: datetime = Field(default_factory=now)
    last_updated_at: datetime = Field(default_factory=now)

    members: list["ArtistMember"] = Relationship(back_populates="artist")
    chart_snapshots: list["ArtistSnapshot"] = Relationship(back_populates="artist")
    credited_songs: list["SongArtist"] = Relationship(back_populates="artist")
    albums: list["AlbumArtist"] = Relationship(back_populates="artist")


class ArtistMember(SQLModel, table=True):
    """Group member entry. Source: ArtistDetail.member_list (MEMBERLIST).
    Upsert on (artist_id, member_artist_id)."""

    __table_args__ = (UniqueConstraint("artist_id", "member_artist_id"),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    artist_id: str = Field(foreign_key="artist.artist_id", index=True)
    member_artist_id: str                                 # ARTISTID
    member_name: str                                      # ARTISTNAME
    act_type_name: str | None = None                      # ACTTYPENAME
    debut_day: str | None = None                          # DEBUTDAY
    birthday: str | None = None                           # BIRTHDAY

    artist: Artist = Relationship(back_populates="members")


# ---------------------------------------------------------------------------
# Time series: artist chart entry (fan counts + composite indices)
# ---------------------------------------------------------------------------

class ArtistSnapshot(SQLModel, table=True):
    """One point-in-time reading of the artist's chart entry: rank, fan count,
    and Melon's composite popularity indices.
    Source: ChartClient.get_artist_chart -> ArtistChart.artists[i] (ArtistChartEntry).
    Insert a new row every time you poll — this table is append-only."""

    __table_args__ = (
        Index(
            "ix_artistsnapshot_artist_fetched",
            "artist_id",
            "fetched_at",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    artist_id: str = Field(foreign_key="artist.artist_id")
    fetched_at: datetime = Field(default_factory=now)

    current_rank: int                # CURRANK
    past_rank: int                   # PASTRANK
    rank_gap: int                    # RANKGAP
    top_rank: int                    # TOPRANK
    past_week_rank: int              # PASTWEEKRANK

    total_fan_count: int             # TOTFANCNT
    increment_fan_count: int         # INCREMFANCNT
    increment_type: str              # INCREMTYPE

    song_index: float                # SONGIDX
    mv_index: float                  # MVIDX
    photo_index: float               # PHOTOIDX
    fan_index: float                 # FANIDX
    like_index: float                # LIKEIDX
    toc_index: float                 # TOCIDX

    artist: Artist = Relationship(back_populates="chart_snapshots")


# ---------------------------------------------------------------------------
# Dimension: Album / Song
# ---------------------------------------------------------------------------

class AlbumArtist(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("album_id", "artist_id"),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    album_id: str = Field(foreign_key="album.album_id", index=True)
    artist_id: str = Field(foreign_key="artist.artist_id", index=True)

    album: "Album" = Relationship(back_populates="artists")
    artist: "Artist" = Relationship(back_populates="albums")


class Album(SQLModel, table=True):
    """Static album metadata. Source: ArtistClient.get_artist_albums -> ArtistAlbums
    (or AlbumClient.get_album_info for the full detail). Upsert on album_id."""

    album_id: str = Field(primary_key=True)               # ALBUMID
    name: str                                              # ALBUMNAME
    issue_date: str | None = None                          # ISSUEDATE
    song_count: int | None = None                          # SONGCNT
    content_type: str | None = None                        # CTYPE
    cover_url: str | None = None                            # ALBUMIMGLARGE
    first_seen_at: datetime = Field(default_factory=now)
    last_updated_at: datetime = Field(default_factory=now)

    artists: list["AlbumArtist"] = Relationship(back_populates="album")
    songs: list["Song"] = Relationship(back_populates="album")


class Song(SQLModel, table=True):
    """Static song metadata, shared shape across chart/artist song lists.
    Source: BaseSong subclasses (ChartSong, ArtistSong, AlbumSong, ...).
    Upsert on song_id.

    Every credited artist (ARTISTLIST) — the artist you're tracking plus any
    collaborators/features — is logged in SongArtist below, not as a single
    FK column here, since a song can carry more than one credit."""

    song_id: str = Field(primary_key=True)                 # SONGID
    title: str                                             # SONGNAME
    album_id: str | None = Field(default=None, foreign_key="album.album_id", index=True)
    play_time: int | None = None                           # PLAYTIME
    issue_date: str | None = None                          # ISSUEDATE
    is_title_song: bool | None = None                      # ISTITLESONG
    first_seen_at: datetime = Field(default_factory=now)
    last_updated_at: datetime = Field(default_factory=now)

    album: Album | None = Relationship(back_populates="songs")
    credited_artists: list["SongArtist"] = Relationship(back_populates="song")
    chart_snapshots: list["SongChartSnapshot"] = Relationship(back_populates="song")
    report_snapshots: list["ChartReportSnapshot"] = Relationship(back_populates="song")


class SongArtist(SQLModel, table=True):
    """Link table: every artist credited on a song (BaseSong.ARTISTLIST),
    including collaborators/features beyond whichever artist you're tracking.
    One row per (song_id, artist_id).

    `credited_name` stores the ARTISTNAME as it appeared on *this* song's
    credit list — Melon occasionally varies a group's display name across
    releases, so it's kept alongside the FK rather than always trusting
    Artist.name.

    Note: a collaborator may not have a full ArtistDetail fetched yet. Upsert
    a minimal Artist stub (artist_id + name only, other fields left null) for
    every id seen here so the FK always resolves, then backfill the rest of
    Artist's columns later if/when you call get_artist_detail for them."""

    __table_args__ = (UniqueConstraint("song_id", "artist_id"),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    song_id: str = Field(foreign_key="song.song_id", index=True)
    artist_id: str = Field(foreign_key="artist.artist_id", index=True)  # ARTISTID
    credited_name: str                                                  # ARTISTNAME

    song: Song = Relationship(back_populates="credited_artists")
    artist: Artist = Relationship(back_populates="credited_songs")


# ---------------------------------------------------------------------------
# Time series: chart rank snapshots (realtime / top100 / daily / weekly / hot100)
# ---------------------------------------------------------------------------

class SongChartSnapshot(SQLModel, table=True):
    """One point-in-time chart-rank reading for a song, from ChartSong.
    Covers RealtimeChart, Top100Chart, DailyChart, WeeklyChart, and Hot100Chart
    — they all share the ChartSong shape, distinguished here by `chart_type`.
    One row per (song, chart_type, fetch)."""

    __table_args__ = (
        Index(
            "ix_songchartsnapshot_song_chart_ranktime",
            "song_id",
            "chart_type",
            "rank_day",
            "rank_hour",
        ),
        Index(
            "ix_songchartsnapshot_song_chart_fetched",
            "song_id",
            "chart_type",
            "fetched_at",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    song_id: str = Field(foreign_key="song.song_id")
    chart_type: ChartType = Field(
        sa_column=Column(
            SAEnum(
                ChartType,
                values_callable=lambda enum: [item.value for item in enum],
                name="charttype",
            ),
            nullable=False,
        )
    )
    fetched_at: datetime = Field(default_factory=now)

    rank_day: date                   # RANKDAY (chart's own snapshot date)
    rank_hour: str | None = None     # RANKHOUR

    current_rank: int                # CURRANK
    past_rank: int                   # PASTRANK
    rank_gap: int                    # RANKGAP
    rank_type: str                   # RANKTYPE ("UP" / "DOWN" / ...)

    song: Song = Relationship(back_populates="chart_snapshots")


# ---------------------------------------------------------------------------
# Time series: chart report (listener stats + rank), from ChartReport
# ---------------------------------------------------------------------------

class ChartReportSnapshot(SQLModel, table=True):
    """One point-in-time chart-report reading for a song.
    Source: ChartClient.get_chart_report -> ChartReport."""

    __table_args__ = (
        Index(
            "ix_chartreportsnapshot_song_fetched",
            "song_id",
            "fetched_at",
        ),
        Index(
            "ix_chartreportsnapshot_song_report_date",
            "song_id",
            "report_date",
            "recent_time",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    song_id: str = Field(foreign_key="song.song_id")
    fetched_at: datetime = Field(default_factory=now)
    recent_time: str | None = None       # RECENTTIME
    report_date: date

    current_rank: int                    # SONGINFO.CURRANK
    past_rank: int                       # SONGINFO.PASTRANK
    rank_gap: int                        # SONGINFO.RANKGAP
    rank_type: str                       # SONGINFO.RANKTYPE

    listener_one_hour: str | None = None  # LISTENERDATA.ONEHOUR ('-' if unavailable)
    listener_one_day: str | None = None   # LISTENERDATA.ONEDAY

    song: Song = Relationship(back_populates="report_snapshots")
    rank_history_points: list["RankHistoryPoint"] = Relationship(back_populates="report_snapshot")


class RankHistoryPoint(SQLModel, table=True):
    """One point on the rank-trend/prediction graph embedded in a chart report.
    `is_predicted` splits RankChart.DATA (actual, False) from
    RankChart.PREDICTEDDATA (forecast, True) — PREDICTEDDATA may be absent."""

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    report_snapshot_id: uuid.UUID = Field(foreign_key="chartreportsnapshot.id", index=True)
    is_predicted: bool = False       # False -> DATA, True -> PREDICTEDDATA
    x_index: int                      # XINDEX
    value: int                        # VALUE
    label: str                        # LABEL

    report_snapshot: ChartReportSnapshot = Relationship(back_populates="rank_history_points")


# ---------------------------------------------------------------------------
# Time series: Hot100 graph series (hourly and five-minute resolution)
# ---------------------------------------------------------------------------

class GraphPoint(SQLModel, table=True):
    """One point of a Hot100 score/rank series.
    Source: ChartClient.get_hot100_graph_hour -> ChartGraph (hourly, includes
    ENTGRAPHDATA rank) and ChartClient.get_hot100_graph_five -> FiveGraph
    (five-minute, score only). Each fetch returns a full series per song;
    `fetch_batch_at` groups the points that came from the same request."""

    __table_args__ = (
        Index(
            "ix_graphpoint_song_resolution_batch",
            "song_id",
            "resolution",
            "fetch_batch_at",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    song_id: str = Field(foreign_key="song.song_id")
    resolution: GraphResolution = Field(
        sa_column=Column(
            SAEnum(
                GraphResolution,
                values_callable=lambda enum: [item.value for item in enum],
                name="graphresolution",
            ),
            nullable=False,
        )
    )
    fetch_batch_at: datetime = Field(default_factory=now)
    point_at: datetime

    value: float | None          # VAL
    rank: int | None = None      # RANK (hourly only, from ENTGRAPHDATA)


# ---------------------------------------------------------------------------
# Dimension + time series: artist content lists (videos, photos, magazines)
# ---------------------------------------------------------------------------

class Video(SQLModel, table=True):
    """Artist video-list entry. Source: ArtistClient.get_artist_videos -> ArtistVideos.
    Upsert on mv_id; log view_count growth via VideoViewSnapshot."""

    mv_id: str = Field(primary_key=True)         # MVID
    artist_id: str = Field(foreign_key="artist.artist_id", index=True)
    name: str                                     # MVNAME
    song_id: str | None = None                    # SONGID
    issue_date: str | None = None                 # ISSUEDATE
    first_seen_at: datetime = Field(default_factory=now)

    view_snapshots: list["VideoViewSnapshot"] = Relationship(back_populates="video")


class VideoViewSnapshot(SQLModel, table=True):
    """Time series of a video's view_count (VIEWCNT), which changes on every fetch."""

    __table_args__ = (
        Index(
            "ix_videoviewsnapshot_mv_fetched",
            "mv_id",
            "fetched_at",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    mv_id: str = Field(foreign_key="video.mv_id")
    fetched_at: datetime = Field(default_factory=now)
    view_count: int              # VIEWCNT

    video: Video = Relationship(back_populates="view_snapshots")


class Photo(SQLModel, table=True):
    """Artist photo-list entry. Source: ArtistClient.get_artist_photos -> ArtistPhotos.
    Upsert on photo_id."""

    photo_id: str = Field(primary_key=True)      # PHOTOID
    artist_id: str = Field(foreign_key="artist.artist_id", index=True)
    photo_name: str | None = None                # PHOTONAME
    first_seen_at: datetime = Field(default_factory=now)


class Magazine(SQLModel, table=True):
    """Artist magazine-list entry. Source: ArtistClient.get_artist_magazines -> ArtistMagazines.
    Upsert on content_id."""

    content_id: str = Field(primary_key=True)    # CONTSID
    artist_id: str = Field(foreign_key="artist.artist_id", index=True)
    content_name: str | None = None              # CONTSNAME
    first_seen_at: datetime = Field(default_factory=now)


class ArchiveChangeLog(SQLModel, table=True):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    entity_type: str        # "artist", "album", "song"
    entity_id: str          # ARTISTID, ALBUMID, SONGID

    field_name: str         # "company_name"
    old_value: str | None
    new_value: str | None

    changed_at: datetime = Field(default_factory=now)


class SongStreamReport(SQLModel, table=True):
    """Time series of a song's streaming report"""

    __table_args__ = (
        UniqueConstraint(
            "song_id",
            "report_date",
            name="uq_song_stream_report_song_date",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=SAUUID
    )
    song_id: str = Field(foreign_key="song.song_id")

    fetched_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    report_date: date

    daily_listener_count: int | None = None
    total_listen_count: int | None = None
    total_listener_count: int | None = None

    male_percent: int | None = None
    female_percent: int | None = None

    yesterday_rank: int | None = None

    age_percent: list[int] | None = Field(
        default=None,
        sa_column=Column(ARRAY(INTEGER))
    )