"""listing_jobs table + workflow state machine (BUG #17)

Adds a human-approval work-order table so the 10-step SOP can stop
at the 'submit listing' gate instead of pushing directly to WooCommerce.

Revision: 0056
Revises: 0055

Notes on the unique index:
- We initially tried a partial unique index (only one active
  pending/approved/processing work-order per product). Alembic's
  postgresql_where kwarg caused CI deploy failures in the current
  runner (sa.text positional rendering). The raw SQL fallback
  (exec_driver_sql) also did not resolve the render error.
- To unblock deployment, this revision ships with a regular non-partial
  unique index on (workspace_id, product_id, status) - so a product
  can have at most one row per status value. This is slightly weaker
  than the original intent but enforces the business rule well enough:
  a product cannot have two pending OR two approved OR two processing
  work-orders simultaneously.
- The strict partial-unique semantic (one active regardless of which
  active status) is enforced at the application layer in
  backend/app/api/v1/endpoints/listing_jobs.py via a SELECT-then-insert
  check on create. If/when we want the DB-level guarantee back, we
  can add a follow-up migration with exec_driver_sql + a single-line
  SQL string.
"""
from alembic import op
import sqlalchemy as sa

revision = '0056'
down_revision = '0055'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'listing_jobs',
        # Identity
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        # Target product
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('sku', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),

        # Frozen WC payload snapshot
        sa.Column('payload', sa.JSON(), nullable=False),

        # State machine
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('reject_reasons', sa.JSON(), nullable=True),

        # Workflow actor timestamps
        sa.Column('submitted_by', sa.String(length=128), nullable=True),
        sa.Column('reviewed_by', sa.String(length=128), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pushed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),

        # WC linkage
        sa.Column('wc_product_id', sa.Integer(), nullable=True),
        sa.Column('wc_verify_status', sa.String(length=16), nullable=True),
        sa.Column('wc_verify_detail', sa.JSON(), nullable=True),

        # Trace
        sa.Column('trace_id', sa.String(length=64), nullable=True),

        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_listing_jobs_ws_status',
        'listing_jobs',
        ['workspace_id', 'status'],
    )
    op.create_index(
        'ix_listing_jobs_ws_product_created',
        'listing_jobs',
        ['workspace_id', 'product_id', 'created_at'],
    )
    # Non-partial unique on (workspace_id, product_id, status).
    # Ensures a product cannot have two rows with the same status
    # simultaneously (e.g. two pending). The stricter "one active
    # regardless of status" invariant is enforced at the application
    # layer in backend/app/api/v1/endpoints/listing_jobs.py.
    op.create_index(
        'uq_listing_jobs_ws_product_status',
        'listing_jobs',
        ['workspace_id', 'product_id', 'status'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        'uq_listing_jobs_ws_product_status',
        table_name='listing_jobs',
    )
    op.drop_index(
        'ix_listing_jobs_ws_product_created',
        table_name='listing_jobs',
    )
    op.drop_index(
        'ix_listing_jobs_ws_status',
        table_name='listing_jobs',
    )
    op.drop_table('listing_jobs')
