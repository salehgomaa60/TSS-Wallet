"""
Test script to verify Phase 1 models are correctly defined.

This script validates that all SQLAlchemy models can be imported
and their metadata is properly configured, without requiring
a running PostgreSQL database.
"""

import sys

def test_imports():
    """Test that all model modules can be imported."""
    print("Testing model imports...")
    try:
        from models import Base, get_engine, AsyncSessionLocal
        from models.company import Company
        from models.user import User
        from models.transaction import Transaction
        from models.approval import Approval
        from models.audit_log import AuditLog
        from models.invitation import Invitation
        print("  All imports successful!")
        return True
    except Exception as e:
        print(f"  Import failed: {e}")
        return False


def test_table_names():
    """Test that all tables are properly registered."""
    print("\nTesting table registration...")
    from models import Base
    
    expected_tables = {
        'companies',
        'users',
        'transactions',
        'approvals',
        'audit_log',
        'invitations',
    }
    
    actual_tables = set(Base.metadata.tables.keys())
    
    missing = expected_tables - actual_tables
    if missing:
        print(f"  Missing tables: {missing}")
        return False
    
    print(f"  All {len(expected_tables)} tables registered!")
    for name in sorted(actual_tables):
        print(f"    - {name}")
    return True


def test_columns():
    """Test that key columns exist on tables."""
    print("\nTesting column definitions...")
    from models import Base
    
    checks = [
        ('companies', ['id', 'name', 'email', 'threshold', 'contract_address', 'eth_address']),
        ('users', ['id', 'email', 'company_id', 'role', 'node_id']),
        ('transactions', ['id', 'company_id', 'to_address', 'value_wei', 'status', 'tx_hash']),
        ('approvals', ['id', 'transaction_id', 'user_id', 'partial_signature']),
        ('audit_log', ['id', 'action', 'timestamp']),
        ('invitations', ['id', 'token', 'email', 'expires_at']),
    ]
    
    all_pass = True
    for table_name, expected_cols in checks:
        table = Base.metadata.tables.get(table_name)
        if table is None:
            print(f"  Table {table_name} not found!")
            all_pass = False
            continue
            
        actual_cols = set(table.columns.keys())
        missing = set(expected_cols) - actual_cols
        if missing:
            print(f"  Table {table_name} missing columns: {missing}")
            all_pass = False
        else:
            print(f"  Table {table_name}: {len(table.columns)} columns OK")
    
    return all_pass


def main():
    print("=" * 60)
    print("PHASE 1: DATABASE MODELS TEST")
    print("=" * 60)
    
    results = []
    results.append(("Imports", test_imports()))
    results.append(("Table Registration", test_table_names()))
    results.append(("Column Definitions", test_columns()))
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_pass = False
    
    print("=" * 60)
    if all_pass:
        print("ALL TESTS PASSED - Phase 1 models are correctly configured!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Install and start PostgreSQL")
        print("2. Create database: CREATE DATABASE tss_vault;")
        print("3. Run: python -m alembic upgrade head")
        print("4. Verify: python -c \"from models import Company; print('DB OK')\"")
        return 0
    else:
        print("SOME TESTS FAILED - Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
