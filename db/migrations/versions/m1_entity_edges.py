
"""Create entity_edges prerequisite for the M2 feature store.

M1 in this repository does not yet include the entity_edges table.
Entity identifiers use TEXT to support heterogeneous M1 entity IDs.
"""

import sqlalchemy as sa
from alembic import op

revision = "m1_entity_edges"
down_revision = "m1_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_edges",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("src_type", sa.String(length=16), nullable=False),
        sa.Column("src_id", sa.Text(), nullable=False),
        sa.Column("dst_type", sa.String(length=16), nullable=False),
        sa.Column("dst_id", sa.Text(), nullable=False),
        sa.Column("edge_type", sa.String(length=32), nullable=False),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "weight",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("entity_edges")
