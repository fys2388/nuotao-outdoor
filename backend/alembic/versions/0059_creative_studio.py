"""Add AI Creative Studio tables (v0.17 C0).

Creates four new tables for the Creative Studio foundation:
- creative_briefs: structured briefs for creative production
- creative_assets: visual assets with version and QC metadata
- creative_generation_runs: AI generation/edit operation records
- creative_reviews: audit trail for asset review decisions

Revision: 0059
Revises: 0058
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0059'
down_revision = '0058'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # creative_briefs
    # ------------------------------------------------------------------
    op.create_table(
        'creative_briefs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=True),
        sa.Column('listing_id', sa.Uuid(), nullable=True),
        sa.Column('brief_type', sa.String(length=32), nullable=False),
        sa.Column('objective', sa.Text(), nullable=True),
        sa.Column('target_market', sa.String(length=64), nullable=True),
        sa.Column('channel', sa.String(length=32), nullable=True),
        sa.Column('visual_style', sa.String(length=128), nullable=True),
        sa.Column('required_assets', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('constraints', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_by', sa.String(length=128), nullable=True),
        sa.Column('approved_by', sa.String(length=128), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trace_id', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['listing_id'], ['listing_jobs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_creative_briefs_workspace_status', 'creative_briefs', ['workspace_id', 'status'])
    op.create_index('ix_creative_briefs_workspace_product', 'creative_briefs', ['workspace_id', 'product_id'])
    op.create_index('ix_creative_briefs_workspace_type', 'creative_briefs', ['workspace_id', 'brief_type'])

    # ------------------------------------------------------------------
    # creative_generation_runs
    # ------------------------------------------------------------------
    op.create_table(
        'creative_generation_runs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=True),
        sa.Column('brief_id', sa.Uuid(), nullable=True),
        sa.Column('operation', sa.String(length=32), nullable=False),
        sa.Column('provider', sa.String(length=64), nullable=True),
        sa.Column('model', sa.String(length=128), nullable=True),
        sa.Column('input_asset_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('prompt_template_id', sa.String(length=128), nullable=True),
        sa.Column('prompt_version', sa.String(length=64), nullable=True),
        sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('output_asset_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('provider_request_id', sa.String(length=256), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('input_units', sa.Integer(), nullable=True),
        sa.Column('output_units', sa.Integer(), nullable=True),
        sa.Column('estimated_cost', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('actual_cost', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('error_code', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('trace_id', sa.String(length=64), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['brief_id'], ['creative_briefs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_creative_runs_workspace_status', 'creative_generation_runs', ['workspace_id', 'status'])
    op.create_index('ix_creative_runs_workspace_product', 'creative_generation_runs', ['workspace_id', 'product_id'])
    op.create_index('ix_creative_runs_workspace_brief', 'creative_generation_runs', ['workspace_id', 'brief_id'])
    op.create_index('ix_creative_runs_workspace_model', 'creative_generation_runs', ['workspace_id', 'model'])

    # ------------------------------------------------------------------
    # creative_studio_assets
    # ------------------------------------------------------------------
    op.create_table(
        'creative_studio_assets',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=True),
        sa.Column('brief_id', sa.Uuid(), nullable=True),
        sa.Column('parent_asset_id', sa.Uuid(), nullable=True),
        sa.Column('asset_type', sa.String(length=32), nullable=False),
        sa.Column('source_type', sa.String(length=16), nullable=False),
        sa.Column('storage_key', sa.String(length=1024), nullable=True),
        sa.Column('preview_url', sa.String(length=2048), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('ratio', sa.String(length=16), nullable=True),
        sa.Column('mime_type', sa.String(length=32), nullable=True),
        sa.Column('generation_run_id', sa.Uuid(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('quality_result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('compliance_result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_by', sa.String(length=128), nullable=True),
        sa.Column('reviewed_by', sa.String(length=128), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trace_id', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['brief_id'], ['creative_briefs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['parent_asset_id'], ['creative_studio_assets.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['generation_run_id'], ['creative_generation_runs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_creative_studio_assets_workspace_status', 'creative_studio_assets', ['workspace_id', 'status'])
    op.create_index('ix_creative_studio_assets_workspace_product', 'creative_studio_assets', ['workspace_id', 'product_id'])
    op.create_index('ix_creative_studio_assets_workspace_brief', 'creative_studio_assets', ['workspace_id', 'brief_id'])
    op.create_index('ix_creative_studio_assets_workspace_parent', 'creative_studio_assets', ['workspace_id', 'parent_asset_id'])

    # ------------------------------------------------------------------
    # creative_reviews
    # ------------------------------------------------------------------
    op.create_table(
        'creative_reviews',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('asset_id', sa.Uuid(), nullable=False),
        sa.Column('review_type', sa.String(length=32), nullable=False),
        sa.Column('reviewer_type', sa.String(length=16), nullable=False),
        sa.Column('result', sa.String(length=16), nullable=False),
        sa.Column('reasons', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('reviewer_id', sa.String(length=128), nullable=True),
        sa.Column('trace_id', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['creative_studio_assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_creative_reviews_workspace_asset', 'creative_reviews', ['workspace_id', 'asset_id'])
    op.create_index('ix_creative_reviews_workspace_type', 'creative_reviews', ['workspace_id', 'review_type'])
    op.create_index('ix_creative_reviews_workspace_result', 'creative_reviews', ['workspace_id', 'result'])


def downgrade() -> None:
    # Drop reviews first (FK to assets)
    op.drop_index('ix_creative_reviews_workspace_result', table_name='creative_reviews')
    op.drop_index('ix_creative_reviews_workspace_type', table_name='creative_reviews')
    op.drop_index('ix_creative_reviews_workspace_asset', table_name='creative_reviews')
    op.drop_table('creative_reviews')

    # Drop assets (FK to runs, briefs, products)
    op.drop_index('ix_creative_studio_assets_workspace_parent', table_name='creative_studio_assets')
    op.drop_index('ix_creative_studio_assets_workspace_brief', table_name='creative_studio_assets')
    op.drop_index('ix_creative_studio_assets_workspace_product', table_name='creative_studio_assets')
    op.drop_index('ix_creative_studio_assets_workspace_status', table_name='creative_studio_assets')
    op.drop_table('creative_studio_assets')

    # Drop generation runs
    op.drop_index('ix_creative_runs_workspace_model', table_name='creative_generation_runs')
    op.drop_index('ix_creative_runs_workspace_brief', table_name='creative_generation_runs')
    op.drop_index('ix_creative_runs_workspace_product', table_name='creative_generation_runs')
    op.drop_index('ix_creative_runs_workspace_status', table_name='creative_generation_runs')
    op.drop_table('creative_generation_runs')

    # Drop briefs
    op.drop_index('ix_creative_briefs_workspace_type', table_name='creative_briefs')
    op.drop_index('ix_creative_briefs_workspace_product', table_name='creative_briefs')
    op.drop_index('ix_creative_briefs_workspace_status', table_name='creative_briefs')
    op.drop_table('creative_briefs')
