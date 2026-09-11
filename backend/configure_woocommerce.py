"""WooCommerce configuration and testing utility.

This script helps configure and test the WooCommerce integration:
1. Test API connection with provided credentials
2. Fetch and display store information
3. Sync products, orders, and customers
4. Save configuration to .env file

Usage:
    python configure_woocommerce.py --test --base-url https://store.com --consumer-key ck_xxx --consumer-secret cs_xxx
    python configure_woocommerce.py --sync products
    python configure_woocommerce.py --sync orders
    python configure_woocommerce.py --sync customers
    python configure_woocommerce.py --save-env --base-url https://store.com --consumer-key ck_xxx --consumer-secret cs_xxx
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx


class WooCommerceTester:
    """Test and configure WooCommerce API connection."""

    def __init__(self, base_url: str, consumer_key: str, consumer_secret: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.timeout = timeout
        self.api_url = f"{self.base_url}/wp-json/wc/v3"

    async def test_connection(self) -> dict[str, Any]:
        """Test WooCommerce API connection and fetch store information."""
        print(f"\n{'='*60}")
        print(f"Testing WooCommerce Connection")
        print(f"{'='*60}")
        print(f"Base URL: {self.base_url}")
        print(f"API URL: {self.api_url}")
        print(f"Consumer Key: {self.consumer_key[:10]}...")
        print(f"Consumer Secret: {self.consumer_secret[:10]}...")
        print()

        results: dict[str, Any] = {
            "connection": False,
            "store_info": None,
            "products_count": None,
            "orders_count": None,
            "customers_count": None,
            "errors": [],
        }

        async with httpx.AsyncClient(
            auth=(self.consumer_key, self.consumer_secret),
            timeout=self.timeout,
            verify=True,
        ) as client:
            # Test 1: Fetch store information
            print("1. Testing API connection (fetching store info)...")
            try:
                response = await client.get(f"{self.api_url}/system_status")
                if response.status_code == 200:
                    data = response.json()
                    results["store_info"] = {
                        "name": data.get("site", {}).get("name", "N/A"),
                        "url": data.get("site", {}).get("url", "N/A"),
                        "version": data.get("version", "N/A"),
                        "woo_version": data.get("wooCommerce", {}).get("version", "N/A"),
                        "currency": data.get("settings", {}).get("currency", "N/A"),
                    }
                    results["connection"] = True
                    print(f"   ✅ Connection successful!")
                    print(f"   Store: {results['store_info']['name']}")
                    print(f"   WooCommerce Version: {results['store_info']['woo_version']}")
                    print(f"   Currency: {results['store_info']['currency']}")
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    results["errors"].append(f"system_status: {error_msg}")
                    print(f"   ❌ Failed: {error_msg}")
            except httpx.HTTPError as e:
                error_msg = f"HTTP Error: {str(e)[:200]}"
                results["errors"].append(f"system_status: {error_msg}")
                print(f"   ❌ {error_msg}")
            except Exception as e:
                error_msg = f"Error: {str(e)[:200]}"
                results["errors"].append(f"system_status: {error_msg}")
                print(f"   ❌ {error_msg}")

            if not results["connection"]:
                print("\n❌ Connection failed. Please check your credentials and URL.")
                return results

            # Test 2: Fetch products count
            print("\n2. Fetching products...")
            try:
                response = await client.get(f"{self.api_url}/products", params={"per_page": 1, "page": 1})
                if response.status_code == 200:
                    total = int(response.headers.get("X-WP-Total", 0))
                    results["products_count"] = total
                    print(f"   ✅ Found {total} products")
                else:
                    print(f"   ⚠️  Failed to fetch products: HTTP {response.status_code}")
            except Exception as e:
                print(f"   ⚠️  Error fetching products: {str(e)[:100]}")

            # Test 3: Fetch orders count
            print("\n3. Fetching orders...")
            try:
                response = await client.get(f"{self.api_url}/orders", params={"per_page": 1, "page": 1})
                if response.status_code == 200:
                    total = int(response.headers.get("X-WP-Total", 0))
                    results["orders_count"] = total
                    print(f"   ✅ Found {total} orders")
                else:
                    print(f"   ⚠️  Failed to fetch orders: HTTP {response.status_code}")
            except Exception as e:
                print(f"   ⚠️  Error fetching orders: {str(e)[:100]}")

            # Test 4: Fetch customers count
            print("\n4. Fetching customers...")
            try:
                response = await client.get(f"{self.api_url}/customers", params={"per_page": 1, "page": 1})
                if response.status_code == 200:
                    total = int(response.headers.get("X-WP-Total", 0))
                    results["customers_count"] = total
                    print(f"   ✅ Found {total} customers")
                else:
                    print(f"   ⚠️  Failed to fetch customers: HTTP {response.status_code}")
            except Exception as e:
                print(f"   ⚠️  Error fetching customers: {str(e)[:100]}")

        print(f"\n{'='*60}")
        print("Connection Test Summary")
        print(f"{'='*60}")
        print(f"Connection: {'✅ Successful' if results['connection'] else '❌ Failed'}")
        if results["store_info"]:
            print(f"Store: {results['store_info']['name']}")
        print(f"Products: {results['products_count'] or 'N/A'}")
        print(f"Orders: {results['orders_count'] or 'N/A'}")
        print(f"Customers: {results['customers_count'] or 'N/A'}")
        if results["errors"]:
            print(f"\nErrors:")
            for error in results["errors"]:
                print(f"  - {error}")
        print()

        return results

    async def fetch_products(self, page: int = 1, per_page: int = 10) -> list[dict[str, Any]]:
        """Fetch products from WooCommerce."""
        async with httpx.AsyncClient(
            auth=(self.consumer_key, self.consumer_secret),
            timeout=self.timeout,
        ) as client:
            response = await client.get(
                f"{self.api_url}/products",
                params={"page": page, "per_page": per_page, "status": "publish"},
            )
            response.raise_for_status()
            return response.json()

    async def fetch_orders(self, page: int = 1, per_page: int = 10) -> list[dict[str, Any]]:
        """Fetch orders from WooCommerce."""
        async with httpx.AsyncClient(
            auth=(self.consumer_key, self.consumer_secret),
            timeout=self.timeout,
        ) as client:
            response = await client.get(
                f"{self.api_url}/orders",
                params={"page": page, "per_page": per_page},
            )
            response.raise_for_status()
            return response.json()

    async def fetch_customers(self, page: int = 1, per_page: int = 10) -> list[dict[str, Any]]:
        """Fetch customers from WooCommerce."""
        async with httpx.AsyncClient(
            auth=(self.consumer_key, self.consumer_secret),
            timeout=self.timeout,
        ) as client:
            response = await client.get(
                f"{self.api_url}/customers",
                params={"page": page, "per_page": per_page},
            )
            response.raise_for_status()
            return response.json()


def save_to_env(base_url: str, consumer_key: str, consumer_secret: str, env_path: Path) -> None:
    """Save WooCommerce configuration to .env file."""
    print(f"\nSaving configuration to {env_path}...")

    if not env_path.exists():
        print(f"❌ .env file not found at {env_path}")
        return

    content = env_path.read_text(encoding="utf-8")

    # Update or add WooCommerce configuration
    updates = {
        "WOOCOMMERCE_BASE_URL": base_url,
        "WOOCOMMERCE_CONSUMER_KEY": consumer_key,
        "WOOCOMMERCE_CONSUMER_SECRET": consumer_secret,
    }

    for key, value in updates.items():
        if f"{key}=" in content:
            # Replace existing value
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={value}"
                    break
            content = "\n".join(lines)
            print(f"  ✅ Updated {key}")
        else:
            # Add new value
            content += f"\n{key}={value}\n"
            print(f"  ✅ Added {key}")

    env_path.write_text(content, encoding="utf-8")
    print(f"\n✅ Configuration saved to {env_path}")
    print("   Please restart the backend service to apply changes.")


def main() -> None:
    parser = argparse.ArgumentParser(description="WooCommerce Configuration and Testing Utility")
    parser.add_argument("--base-url", help="WooCommerce store base URL (e.g., https://store.com)")
    parser.add_argument("--consumer-key", help="WooCommerce API Consumer Key")
    parser.add_argument("--consumer-secret", help="WooCommerce API Consumer Secret")
    parser.add_argument("--test", action="store_true", help="Test API connection")
    parser.add_argument("--sync", choices=["products", "orders", "customers"], help="Sync data type")
    parser.add_argument("--save-env", action="store_true", help="Save configuration to .env file")
    parser.add_argument("--page", type=int, default=1, help="Page number for fetching")
    parser.add_argument("--per-page", type=int, default=10, help="Items per page")
    parser.add_argument("--output", help="Output JSON file path")

    args = parser.parse_args()

    # Load from .env if not provided
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        env_content = env_path.read_text(encoding="utf-8")
        for line in env_content.split("\n"):
            if line.startswith("WOOCOMMERCE_BASE_URL=") and not args.base_url:
                args.base_url = line.split("=", 1)[1].strip()
            elif line.startswith("WOOCOMMERCE_CONSUMER_KEY=") and not args.consumer_key:
                args.consumer_key = line.split("=", 1)[1].strip()
            elif line.startswith("WOOCOMMERCE_CONSUMER_SECRET=") and not args.consumer_secret:
                args.consumer_secret = line.split("=", 1)[1].strip()

    if not args.base_url or not args.consumer_key or not args.consumer_secret:
        print("❌ Missing required parameters.")
        print("Please provide --base-url, --consumer-key, and --consumer-secret")
        print("Or set WOOCOMMERCE_BASE_URL, WOOCOMMERCE_CONSUMER_KEY, WOOCOMMERCE_CONSUMER_SECRET in .env")
        print()
        print("Example:")
        print("  python configure_woocommerce.py --test \\")
        print("    --base-url https://store.com \\")
        print("    --consumer-key ck_xxxxxxxx \\")
        print("    --consumer-secret cs_xxxxxxxx")
        sys.exit(1)

    tester = WooCommerceTester(args.base_url, args.consumer_key, args.consumer_secret)

    if args.test:
        results = asyncio.run(tester.test_connection())
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Results saved to {output_path}")

    elif args.sync:
        print(f"\nFetching {args.sync} (page {args.page}, {args.per_page} per page)...")
        if args.sync == "products":
            data = asyncio.run(tester.fetch_products(args.page, args.per_page))
        elif args.sync == "orders":
            data = asyncio.run(tester.fetch_orders(args.page, args.per_page))
        else:
            data = asyncio.run(tester.fetch_customers(args.page, args.per_page))

        print(f"✅ Fetched {len(data)} items")
        if data:
            print(f"\nFirst item preview:")
            print(json.dumps(data[0], indent=2, ensure_ascii=False)[:500])

        if args.output:
            output_path = Path(args.output)
            output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\nData saved to {output_path}")

    elif args.save_env:
        save_to_env(args.base_url, args.consumer_key, args.consumer_secret, env_path)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
