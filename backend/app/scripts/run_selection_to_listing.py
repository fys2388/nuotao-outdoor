"""Complete selection-to-listing pipeline script.

Usage:
    # Full flow: selection + approval + listing
    python -m app.scripts.run_selection_to_listing

    # Selection only (no approval)
    python -m app.scripts.run_selection_to_listing --selection-only

    # Approval + listing only (skip selection)
    python -m app.scripts.run_selection_to_listing --listing-only

    # Process specific category only
    python -m app.scripts.run_selection_to_listing --category camping_lighting

    # Preview mode (dry run)
    python -m app.scripts.run_selection_to_listing --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.core.database import async_session_factory
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.services.selection_batch_service import (
    approve_and_trigger_pipeline,
    get_batch_status,
    process_batch_products,
)
from app.services.selection_listing_bridge import (
    get_pending_products,
    get_pipeline_status,
    trigger_listing_pipeline,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Selection-to-listing pipeline")
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Category filter (e.g. camping_lighting)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max count (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only, no execution",
    )
    parser.add_argument(
        "--selection-only",
        action="store_true",
        help="Selection only, no approval",
    )
    parser.add_argument(
        "--listing-only",
        action="store_true",
        help="Approval + listing only, skip selection",
    )
    args = parser.parse_args()

    workspace_id = DEFAULT_WORKSPACE_ID

    print("=" * 60)
    print("Nuotao Outdoor Selection-to-Listing Pipeline")
    print("=" * 60)

    async with async_session_factory() as session:
        # Show current status
        print("\n[STATUS] Current Status:")
        status = await get_batch_status(session, workspace_id=workspace_id)
        for stage, count in status.get("by_stage", {}).items():
            print(f"   {stage}: {count}")
        print(f"   Total: {status.get('total', 0)}")

        pending = await get_pending_products(session, workspace_id=workspace_id)
        print(f"   Pending approvals: {len(pending)}")

        # Step 1: Selection
        if not args.listing_only:
            print(f"\n{'='*60}")
            print("[STEP 1/3] Selection Workflow")
            print(f"{'='*60}")
            print(f"   Category filter: {args.category or 'ALL'}")
            print(f"   Max count: {args.limit}")
            print(f"   Dry run: {args.dry_run}")

            result = await process_batch_products(
                session,
                workspace_id=workspace_id,
                category=args.category,
                limit=args.limit,
                dry_run=args.dry_run,
            )

            await session.commit()

            print(f"\n[{'OK' if result['status'] == 'completed' else 'INFO'}] Selection complete:")
            print(f"   Found: {result['total_found']}")
            if 'succeeded' in result:
                print(f"   Succeeded: {result['succeeded']}")
                print(f"   Failed: {result['failed']}")
            if result.get('dry_run'):
                print(f"   (Dry run mode - no changes made)")

            if not args.dry_run:
                print("\n[DETAILS] Processing results:")
                for r in result["results"]:
                    icon = "OK" if r.get("status") == "completed" else "FAIL"
                    print(f"   [{icon}] {r.get('sku', '?')}: {r.get('name', '?')}")
                    if r.get("status") == "completed":
                        print(f"      Stage: {r.get('funnel_stage', '?')}")
                        print(f"      Decision: {r.get('decision', '?')}")
                        print(f"      Score: {r.get('nuotao_score', '?')} ({r.get('nuotao_grade', '?')})")
                    else:
                        print(f"      Error: {r.get('error', '?')}")
        else:
            print(f"\n{'='*60}")
            print("[SKIP] Selection (--listing-only)")
            print(f"{'='*60}")

        # Step 2: Approval
        if not args.selection_only and not args.listing_only:
            print(f"\n{'='*60}")
            print("[STEP 2/3] Approval")
            print(f"{'='*60}")

            result = await approve_and_trigger_pipeline(
                session,
                workspace_id=workspace_id,
                dry_run=args.dry_run,
            )

            print(f"\n[{'OK' if result['status'] == 'completed' else 'INFO'}] Approval complete:")
            print(f"   Pending: {result['pending_found']}")
            if 'approved' in result:
                print(f"   Approved: {result['approved']}")
                print(f"   Pipeline triggered: {result['pipeline_triggered']}")
            if result.get('status') == 'dry_run':
                print(f"   (Dry run mode - no changes made)")

        # Step 3: Listing
        if not args.selection_only:
            print(f"\n{'='*60}")
            print("[STEP 3/3] WooCommerce Listing")
            print(f"{'='*60}")

            result = await trigger_listing_pipeline(
                session,
                workspace_id=workspace_id,
                category=args.category,
                dry_run=args.dry_run,
            )

            print(f"\n[{'OK' if result['status'] == 'completed' else 'INFO'}] Listing trigger complete:")
            print(f"   Found: {result['total_found']}")
            if 'triggered' in result:
                print(f"   Triggered: {result['triggered']}")
                print(f"   Failed: {result.get('failed', 0)}")
            if result.get('status') == 'dry_run':
                print(f"   (Dry run mode - no changes made)")

            if not args.dry_run and result["pipeline_runs"]:
                print("\n[PIPELINE] Runs:")
                for r in result["pipeline_runs"]:
                    icon = "OK" if r.get("status") in ("started", "completed") else "FAIL"
                    print(f"   [{icon}] {r.get('sku', '?')}: {r.get('name', '?')}")
                    if r.get("run_id"):
                        print(f"      Pipeline ID: {r['run_id']}")

        # Show final status
        print(f"\n{'='*60}")
        print("[STATUS] Final Status:")
        print(f"{'='*60}")
        status = await get_pipeline_status(session, workspace_id=workspace_id)
        for stage, count in status.get("by_funnel_stage", {}).items():
            print(f"   {stage}: {count}")
        print(f"   Total: {status.get('total', 0)}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(1)
    except Exception as exc:
        logger.exception("Processing failed: %s", exc)
        sys.exit(1)
