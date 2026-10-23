
"""Baseline marker for the existing AegisFlow M1 database.

The M1 schema already exists in PostgreSQL through scripts/init_db.sql.
This revision records that starting point; it must not recreate M1 tables.
"""

revision = "m1_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Record the existing M1 schema without modifying it."""
    pass


def downgrade() -> None:
    """Do not automatically remove the existing M1 schema."""
    pass
