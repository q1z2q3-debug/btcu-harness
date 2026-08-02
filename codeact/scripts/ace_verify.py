#!/usr/bin/env python3
"""
ACE Library Integration Verification Script

Tests the following functionality:
1. start_session() - login verification
2. get_operators() - operator list retrieval
3. get_datasets() - dataset list retrieval
4. get_simulation_result_json() - result query with known alpha_id
"""

import os
import sys
import json

# Set credentials via environment variables
os.environ["BRAIN_CREDENTIAL_EMAIL"] = "q1z2q3@126.com"
os.environ["BRAIN_CREDENTIAL_PASSWORD"] = "W2025zq0118"

# Add ace_lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ace_lib"))

import ace_lib


def verify_login():
    """Test start_session() and verify login works."""
    print("=" * 60)
    print("TEST 1: Login Verification (start_session)")
    print("=" * 60)
    try:
        s = ace_lib.start_session()
        # Check session timeout to verify it's valid
        timeout = ace_lib.check_session_timeout(s)
        print(f"  ✓ Login successful")
        print(f"  ✓ Session ID: {id(s)}")
        print(f"  ✓ Session expires in: {timeout} seconds ({timeout/3600:.1f} hours)")
        print(f"  ✓ trust_env setting: {s.trust_env}")
        return s, True
    except Exception as e:
        print(f"  ✗ Login failed: {e}")
        return None, False


def verify_operators(s):
    """Test get_operators()."""
    print("\n" + "=" * 60)
    print("TEST 2: Operators List (get_operators)")
    print("=" * 60)
    try:
        ops = ace_lib.get_operators(s)
        unique_ops = ops["id"].unique() if "id" in ops.columns else []
        print(f"  ✓ Total operator entries: {len(ops)}")
        print(f"  ✓ Unique operators: {len(unique_ops)}")
        if len(ops) > 0 and "id" in ops.columns:
            sample = ops["id"].unique()[:10]
            print(f"  ✓ Sample operators: {', '.join(sample)}")
        return True
    except Exception as e:
        print(f"  ✗ Failed to get operators: {e}")
        return False


def verify_datasets(s):
    """Test get_datasets()."""
    print("\n" + "=" * 60)
    print("TEST 3: Datasets List (get_datasets)")
    print("=" * 60)
    try:
        datasets = ace_lib.get_datasets(s, region="USA", delay=1, universe="TOP3000")
        print(f"  ✓ Total datasets: {len(datasets)}")
        if len(datasets) > 0:
            if "name" in datasets.columns:
                sample = datasets["name"].head(5).tolist()
                print(f"  ✓ Sample datasets: {', '.join(sample)}")
            if "id" in datasets.columns:
                print(f"  ✓ Dataset IDs count: {datasets['id'].nunique()}")
        return True
    except Exception as e:
        print(f"  ✗ Failed to get datasets: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_simulation_result(s, alpha_id="O0xZv69J"):
    """Test get_simulation_result_json() with a known alpha_id."""
    print("\n" + "=" * 60)
    print(f"TEST 4: Simulation Result Query (alpha_id={alpha_id})")
    print("=" * 60)
    try:
        result = ace_lib.get_simulation_result_json(s, alpha_id)
        if not result:
            print(f"  ✗ Empty result returned")
            return False

        # Check key fields
        has_id = "id" in result
        has_settings = "settings" in result
        has_is = "is" in result

        print(f"  ✓ Result retrieved successfully")
        print(f"  ✓ Alpha ID: {result.get('id', 'N/A')}")
        print(f"  ✓ Has settings: {has_settings}")
        print(f"  ✓ Has IS stats: {has_is}")

        if has_is and result["is"]:
            is_data = result["is"]
            print(f"  IS Stats:")
            for key in ["sharpe", "fitness", "returns", "turnover"]:
                if key in is_data:
                    print(f"    - {key}: {is_data[key]}")

            # Check submission checks
            if "checks" in is_data:
                checks = is_data["checks"]
                print(f"  ✓ Submission checks available: {len(checks)} items")

        return True
    except Exception as e:
        print(f"  ✗ Failed to get simulation result: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_submission_check(s, alpha_id="O0xZv69J"):
    """Test get_check_submission() with a known alpha_id."""
    print("\n" + "=" * 60)
    print(f"TEST 5: Submission Check (alpha_id={alpha_id})")
    print("=" * 60)
    try:
        checks = ace_lib.get_check_submission(s, alpha_id)
        if checks.empty:
            print(f"  ✗ Empty submission checks returned")
            return False

        print(f"  ✓ Submission checks retrieved: {len(checks)} items")
        print(f"  Check results:")
        for _, row in checks.iterrows():
            name = row.get("name", row.get("test", "unknown"))
            result_val = row.get("result", "N/A")
            print(f"    - {name}: {result_val}")

        # Count pass/fail
        if "result" in checks.columns:
            pass_count = (checks["result"] == "PASS").sum()
            fail_count = (checks["result"] == "FAIL").sum()
            warn_count = (checks["result"] == "WARNING").sum()
            print(f"  Summary: {pass_count} PASS, {fail_count} FAIL, {warn_count} WARNING")

        return True
    except Exception as e:
        print(f"  ✗ Failed to get submission check: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_self_corr(s, alpha_id="O0xZv69J"):
    """Test self-correlation check."""
    print("\n" + "=" * 60)
    print(f"TEST 6: Self-Correlation Check (alpha_id={alpha_id})")
    print("=" * 60)
    try:
        result = ace_lib.check_self_corr_test(s, alpha_id, threshold=0.7)
        if result.empty:
            print(f"  ✗ Empty self-correlation result")
            return False

        print(f"  ✓ Self-correlation check completed")
        for _, row in result.iterrows():
            print(f"    - Test: {row.get('test', 'N/A')}")
            print(f"    - Result: {row.get('result', 'N/A')}")
            print(f"    - Value: {row.get('value', 'N/A')}")
            print(f"    - Limit: {row.get('limit', 'N/A')}")

        return True
    except Exception as e:
        print(f"  ✗ Failed self-correlation check: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_prod_corr(s, alpha_id="O0xZv69J"):
    """Test production correlation check."""
    print("\n" + "=" * 60)
    print(f"TEST 7: Production Correlation Check (alpha_id={alpha_id})")
    print("=" * 60)
    try:
        result = ace_lib.check_prod_corr_test(s, alpha_id, threshold=0.7)
        if result.empty:
            print(f"  ✗ Empty production correlation result")
            return False

        print(f"  ✓ Production correlation check completed")
        for _, row in result.iterrows():
            print(f"    - Test: {row.get('test', 'N/A')}")
            print(f"    - Result: {row.get('result', 'N/A')}")
            print(f"    - Value: {row.get('value', 'N/A')}")
            print(f"    - Limit: {row.get('limit', 'N/A')}")

        return True
    except Exception as e:
        print(f"  ✗ Failed production correlation check: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("ACE Library Integration Verification")
    print("=" * 60)

    results = {}

    # Test 1: Login
    s, login_ok = verify_login()
    results["login"] = login_ok

    if not login_ok or s is None:
        print("\n❌ Login failed - cannot continue with other tests")
        return 1

    # Test 2: Operators
    results["operators"] = verify_operators(s)

    # Test 3: Datasets
    results["datasets"] = verify_datasets(s)

    # Test 4: Simulation result
    results["simulation_result"] = verify_simulation_result(s, "O0xZv69J")

    # Test 5: Submission check
    results["submission_check"] = verify_submission_check(s, "O0xZv69J")

    # Test 6: Self correlation
    results["self_correlation"] = verify_self_corr(s, "O0xZv69J")

    # Test 7: Production correlation
    results["prod_correlation"] = verify_prod_corr(s, "O0xZv69J")

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    for test, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test}")

    all_passed = all(results.values())
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
