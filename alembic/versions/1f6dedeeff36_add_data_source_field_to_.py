"""add data source field to songchartsnapshot and songstreamreport table

Revision ID: 1f6dedeeff36
Revises: ae57b8598e6d
Create Date: 2026-09-02 03:13:04.077634

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f6dedeeff36'
down_revision: Union[str, Sequence[str], None] = 'ae57b8598e6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    datasource = sa.Enum(
        "melon_api",
        "guysome",
        "manual",
        name="datasource",
    )

    datasource.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "songchartsnapshot",
        sa.Column("source", datasource, nullable=True),
    )

    op.add_column(
        "songstreamreport",
        sa.Column("source", datasource, nullable=True),
    )

    # Existing data came from the Melon API.
    op.execute(
        "UPDATE songchartsnapshot SET source = 'melon_api'"
    )

    op.execute(
        "UPDATE songstreamreport SET source = 'melon_api'"
    )

    # Make the columns required.
    op.alter_column(
        "songchartsnapshot",
        "source",
        nullable=False,
    )

    op.alter_column(
        "songstreamreport",
        "source",
        nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("songstreamreport", "source")
    op.drop_column("songchartsnapshot", "source")

    sa.Enum(
        "melon_api",
        "guysome",
        "manual",
        name="datasource",
    ).drop(op.get_bind(), checkfirst=True)
