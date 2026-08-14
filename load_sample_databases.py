#!/usr/bin/env python3
"""
Load Sample Databases Script

This script populates the Distributed Key-Value Store with sample data
for demonstration purposes.

Usage:
    python load_sample_databases.py
    python load_sample_databases.py --database user
    python load_sample_databases.py --database ecommerce
    python load_sample_databases.py --api-url http://localhost:8000
"""

import requests
import json
import argparse
import sys
from typing import Dict, Any, Optional

# Configuration
API_BASE_URL = 'http://localhost:8000'
TIMEOUT = 5


# ============================================
# SAMPLE DATA DEFINITIONS
# ============================================

USER_PROFILE_DATABASE = {
    "user:1001": {
        "id": 1001,
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "role": "admin",
        "status": "active",
        "created_at": "2026-01-15T10:30:00Z",
        "last_login": "2026-08-14T09:45:00Z"
    },
    "user:1002": {
        "id": 1002,
        "name": "Bob Smith",
        "email": "bob@example.com",
        "role": "user",
        "status": "active",
        "created_at": "2026-02-20T14:15:00Z",
        "last_login": "2026-08-13T16:20:00Z"
    },
    "user:1003": {
        "id": 1003,
        "name": "Carol Williams",
        "email": "carol@example.com",
        "role": "user",
        "status": "inactive",
        "created_at": "2026-03-10T11:00:00Z",
        "last_login": "2026-07-01T08:30:00Z"
    },
    "settings:theme": {
        "mode": "dark",
        "accent_color": "indigo",
        "language": "en"
    },
    "settings:notifications": {
        "email": True,
        "push": True,
        "sms": False
    }
}

ECOMMERCE_DATABASE = {
    "product:SKU-001": {
        "sku": "SKU-001",
        "name": "Laptop Pro 15\"",
        "category": "Electronics",
        "price": 1299.99,
        "currency": "USD",
        "stock": 25,
        "rating": 4.8,
        "reviews": 342,
        "description": "High-performance laptop with 16GB RAM and 512GB SSD"
    },
    "product:SKU-002": {
        "sku": "SKU-002",
        "name": "Wireless Headphones",
        "category": "Audio",
        "price": 149.99,
        "currency": "USD",
        "stock": 87,
        "rating": 4.5,
        "reviews": 156,
        "description": "Noise-cancelling Bluetooth headphones with 30-hour battery"
    },
    "product:SKU-003": {
        "sku": "SKU-003",
        "name": "USB-C Hub",
        "category": "Accessories",
        "price": 49.99,
        "currency": "USD",
        "stock": 156,
        "rating": 4.3,
        "reviews": 89,
        "description": "7-in-1 USB-C hub with HDMI, USB 3.0, and SD card reader"
    },
    "order:ORD-2026-001": {
        "order_id": "ORD-2026-001",
        "customer_id": 1001,
        "items": [
            {"sku": "SKU-001", "quantity": 1, "price": 1299.99},
            {"sku": "SKU-003", "quantity": 2, "price": 49.99}
        ],
        "total": 1399.97,
        "status": "shipped",
        "created_at": "2026-08-10T10:15:00Z",
        "shipped_at": "2026-08-12T14:30:00Z"
    },
    "order:ORD-2026-002": {
        "order_id": "ORD-2026-002",
        "customer_id": 1002,
        "items": [
            {"sku": "SKU-002", "quantity": 1, "price": 149.99}
        ],
        "total": 149.99,
        "status": "pending",
        "created_at": "2026-08-14T08:00:00Z"
    },
    "inventory:summary": {
        "total_products": 3,
        "total_items": 268,
        "low_stock_threshold": 20,
        "low_stock_items": 0,
        "last_updated": "2026-08-14T09:00:00Z"
    }
}


# ============================================
# FUNCTIONS
# ============================================

def load_database(
    data: Dict[str, Any],
    api_url: str,
    database_name: str,
    verbose: bool = True
) -> tuple[int, int]:
    """
    Load a database into the distributed KV store.
    
    Args:
        data: Dictionary of key-value pairs to load
        api_url: Base URL of the API
        database_name: Name of the database (for display)
        verbose: Whether to print progress
        
    Returns:
        Tuple of (successful_loads, failed_loads)
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"Loading {database_name} Database")
        print(f"{'='*60}")
        print(f"Total keys to load: {len(data)}")
    
    successful = 0
    failed = 0
    
    for key, value in data.items():
        try:
            response = requests.post(
                f"{api_url}/kv/{key}",
                headers={"Content-Type": "application/json"},
                json={"value": value},
                timeout=TIMEOUT
            )
            
            if response.status_code in [200, 201]:
                successful += 1
                if verbose:
                    print(f"✅ Loaded {key}")
            else:
                failed += 1
                if verbose:
                    print(f"❌ Failed to load {key}: {response.status_code}")
        except requests.exceptions.ConnectionError:
            failed += 1
            if verbose:
                print(f"❌ Connection error for {key}")
        except requests.exceptions.Timeout:
            failed += 1
            if verbose:
                print(f"❌ Timeout for {key}")
        except Exception as e:
            failed += 1
            if verbose:
                print(f"❌ Error loading {key}: {str(e)}")
    
    return successful, failed


def verify_database(api_url: str, verbose: bool = True) -> Dict[str, Any]:
    """
    Verify that data was loaded successfully.
    
    Args:
        api_url: Base URL of the API
        verbose: Whether to print progress
        
    Returns:
        Dictionary with verification results
    """
    if verbose:
        print(f"\n{'='*60}")
        print("Verifying Database Load")
        print(f"{'='*60}")
    
    try:
        response = requests.get(f"{api_url}/kv", timeout=TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            total_keys = len(data.get('data', {}))
            
            if verbose:
                print(f"✅ Successfully verified!")
                print(f"Total keys in store: {total_keys}")
                
                # Count keys by category
                user_keys = sum(1 for k in data.get('data', {}) if k.startswith('user:') or k.startswith('settings:'))
                product_keys = sum(1 for k in data.get('data', {}) if k.startswith('product:') or k.startswith('order:') or k.startswith('inventory:'))
                
                if user_keys > 0:
                    print(f"  • User Profile keys: {user_keys}")
                if product_keys > 0:
                    print(f"  • E-Commerce keys: {product_keys}")
            
            return {
                "success": True,
                "total_keys": total_keys,
                "user_keys": user_keys if 'user_keys' in locals() else 0,
                "product_keys": product_keys if 'product_keys' in locals() else 0
            }
        else:
            if verbose:
                print(f"❌ Verification failed: {response.status_code}")
            return {"success": False, "error": f"HTTP {response.status_code}"}
    
    except requests.exceptions.ConnectionError:
        if verbose:
            print(f"❌ Cannot connect to API at {api_url}")
        return {"success": False, "error": "Connection failed"}
    except Exception as e:
        if verbose:
            print(f"❌ Verification error: {str(e)}")
        return {"success": False, "error": str(e)}


def display_summary(successful: int, failed: int, database_name: str):
    """Display summary of load operation."""
    print(f"\n{'='*60}")
    print(f"Summary: {database_name}")
    print(f"{'='*60}")
    print(f"✅ Successfully loaded: {successful}")
    print(f"❌ Failed: {failed}")
    print(f"Total attempted: {successful + failed}")
    
    if failed == 0 and successful > 0:
        print(f"🎉 All {successful} keys loaded successfully!")
    elif failed > 0:
        print(f"⚠️  {failed} keys failed to load")


# ============================================
# MAIN
# ============================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Load sample databases into the Distributed Key-Value Store',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python load_sample_databases.py
  python load_sample_databases.py --database user
  python load_sample_databases.py --database ecommerce
  python load_sample_databases.py --api-url http://localhost:8000
        """
    )
    
    parser.add_argument(
        '--database',
        choices=['user', 'ecommerce', 'all'],
        default='all',
        help='Which database(s) to load (default: all)'
    )
    
    parser.add_argument(
        '--api-url',
        default=API_BASE_URL,
        help=f'API base URL (default: {API_BASE_URL})'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress progress output'
    )
    
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify existing data, do not load'
    )
    
    args = parser.parse_args()
    
    # Verify connection
    try:
        response = requests.get(f"{args.api_url}/health", timeout=TIMEOUT)
        if response.status_code != 200:
            print(f"❌ Error: API not responding properly at {args.api_url}")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"❌ Error: Cannot connect to API at {args.api_url}")
        print("Make sure the Distributed Key-Value Store is running.")
        sys.exit(1)
    
    if args.verify_only:
        result = verify_database(args.api_url, not args.quiet)
        sys.exit(0 if result.get('success') else 1)
    
    # Load databases
    total_successful = 0
    total_failed = 0
    
    if args.database in ['user', 'all']:
        successful, failed = load_database(
            USER_PROFILE_DATABASE,
            args.api_url,
            "User Profile",
            not args.quiet
        )
        total_successful += successful
        total_failed += failed
        if not args.quiet:
            display_summary(successful, failed, "User Profile Database")
    
    if args.database in ['ecommerce', 'all']:
        successful, failed = load_database(
            ECOMMERCE_DATABASE,
            args.api_url,
            "E-Commerce",
            not args.quiet
        )
        total_successful += successful
        total_failed += failed
        if not args.quiet:
            display_summary(successful, failed, "E-Commerce Database")
    
    # Verify all data
    if not args.quiet:
        verify_database(args.api_url, not args.quiet)
    
    # Final summary
    if not args.quiet:
        print(f"\n{'='*60}")
        print("Final Summary")
        print(f"{'='*60}")
        print(f"✅ Total successfully loaded: {total_successful}")
        print(f"❌ Total failed: {total_failed}")
        if total_failed == 0 and total_successful > 0:
            print(f"🎉 All {total_successful} keys loaded successfully!")
            print("\nYou can now browse the data in the Dashboard tab!")
    
    sys.exit(0 if total_failed == 0 else 1)


if __name__ == '__main__':
    main()
