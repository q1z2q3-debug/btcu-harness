#!/usr/bin/env python3
"""
Benchmark Test: Validate ACE library results against known 4 candidate factors.

Compares ACE library query results with previously recorded values.
"""

import os
import sys
import json

# Set credentials
os.environ["BRAIN_CREDENTIAL_EMAIL"] = "q1z2q3@126.com"
os.environ["BRAIN_CREDENTIAL_PASSWORD"] = "W2025zq0118"

# Add ace_lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ace_lib"))

import ace_lib


# Known expected values from previous scripts
EXPECTED_FACTORS = {
    "E5eE3Zp1": {
        "name": "alpha_021_d1_raw",
        "sharpe": 1.73,
        "fitness": 1.22,
        "turnover": 0.4034,
    },
    "E5eEALEL": {
        "name": "alpha_021_d3",
        "sharpe": 1.69,
        "fitness": 1.42,
        "turnover": 0.2719,
    },
    "O0xZv69J": {
        "name": "alpha_021_d5",
        "sharpe": 1.66,
        "fitness": 1.50,
        "turnover": 0.2261,
    },
    "pwKl0XoX": {
        "name": "combo_d5_vol20_w9505",
        "sharpe": 1.58,
        "fitness": 1.23,
        "turnover": 0.1791,
    },
}


def query_factor_stats(s, alpha_id):
    """Query factor statistics using ACE library."""
    result = ace_lib.get_simulation_result_json(s, alpha_id)
    if not result or "is" not in result:
        return None
    
    is_data = result["is"]
    return {
        "sharpe": is_data.get("sharpe"),
        "fitness": is_data.get("fitness"),
        "returns": is_data.get("returns"),
        "turnover": is_data.get("turnover"),
        "checks": is_data.get("checks", []),
    }


def query_self_corr(s, alpha_id):
    """Query self-correlation using ACE library."""
    try:
        result = ace_lib.check_self_corr_test(s, alpha_id, threshold=0.7)
        if result.empty:
            return None
        row = result.iloc[0]
        return {
            "value": row.get("value"),
            "result": row.get("result"),
            "limit": row.get("limit"),
        }
    except Exception as e:
        return {"error": str(e)}


def query_submit_check(s, alpha_id):
    """Query submission check via POST /submit."""
    url = f"{ace_lib.brain_api_url}/alphas/{alpha_id}/submit"
    try:
        response = s.post(url)
        # 403 is normal
        if response.status_code in (403, 200, 201, 202):
            data = response.json()
        else:
            data = {"status_code": response.status_code, "text": response.text[:200]}
        return data
    except Exception as e:
        return {"error": str(e)}


def query_prod_corr(s, alpha_id):
    """Query production correlation using ACE library."""
    try:
        result = ace_lib.check_prod_corr_test(s, alpha_id, threshold=0.7)
        if result.empty:
            return {"status": "NONE", "value": None}
        row = result.iloc[0]
        return {
            "value": row.get("value"),
            "result": row.get("result"),
            "limit": row.get("limit"),
        }
    except Exception as e:
        return {"error": str(e)}


def run_benchmark():
    print("=" * 70)
    print("ACE Library Benchmark Test - 4 Candidate Factors")
    print("=" * 70)
    
    # Login
    print("\n[1/6] 登录...")
    s = ace_lib.start_session()
    print(f"  ✓ 登录成功 (trust_env={s.trust_env})")
    
    results = {}
    all_match = True
    
    # Test each factor
    for i, (alpha_id, expected) in enumerate(EXPECTED_FACTORS.items(), 2):
        print(f"\n[{i}/6] 查询 {expected['name']} ({alpha_id})...")
        
        factor_result = {"expected": expected, "actual": {}}
        
        # 1. Basic stats
        stats = query_factor_stats(s, alpha_id)
        if stats:
            factor_result["actual"]["sharpe"] = stats["sharpe"]
            factor_result["actual"]["fitness"] = stats["fitness"]
            factor_result["actual"]["turnover"] = stats["turnover"]
            factor_result["actual"]["is_checks_count"] = len(stats.get("checks", []))
            
            sharpe_match = abs(stats["sharpe"] - expected["sharpe"]) < 0.01
            fitness_match = abs(stats["fitness"] - expected["fitness"]) < 0.01
            turnover_match = abs(stats["turnover"] - expected["turnover"]) < 0.001
            
            factor_result["matches"] = {
                "sharpe": sharpe_match,
                "fitness": fitness_match,
                "turnover": turnover_match,
            }
            
            all_match = all_match and sharpe_match and fitness_match and turnover_match
            
            print(f"  IS Stats:")
            print(f"    Sharpe:   {stats['sharpe']} (expected {expected['sharpe']}) {'✓' if sharpe_match else '✗'}")
            print(f"    Fitness:  {stats['fitness']} (expected {expected['fitness']}) {'✓' if fitness_match else '✗'}")
            print(f"    Turnover: {stats['turnover']} (expected {expected['turnover']}) {'✓' if turnover_match else '✗'}")
            print(f"    IS checks: {len(stats.get('checks', []))} items")
        else:
            print(f"  ✗ Failed to get stats")
            factor_result["error"] = "Failed to query stats"
            all_match = False
        
        # 2. Self-correlation
        self_corr = query_self_corr(s, alpha_id)
        if self_corr and "error" not in self_corr:
            factor_result["actual"]["self_corr"] = self_corr
            print(f"  Self-correlation: {self_corr['value']} ({self_corr['result']})")
        else:
            print(f"  Self-correlation: ERROR - {self_corr.get('error', 'unknown')}")
        
        # 3. Submission check
        submit_data = query_submit_check(s, alpha_id)
        if "error" not in submit_data:
            is_data = submit_data.get("is", {})
            checks = is_data.get("checks", [])
            check_names = [c.get("name") for c in checks]
            check_results = {c.get("name"): c.get("result") for c in checks}
            factor_result["actual"]["submit_checks"] = check_results
            factor_result["actual"]["submit_check_count"] = len(checks)
            print(f"  Submission check: {len(checks)} items")
            for name, result_val in check_results.items():
                print(f"    - {name}: {result_val}")
        else:
            print(f"  Submission check: ERROR - {submit_data.get('error', 'unknown')}")
        
        # 4. Production correlation
        prod_corr = query_prod_corr(s, alpha_id)
        if prod_corr and "error" not in prod_corr:
            factor_result["actual"]["prod_corr"] = prod_corr
            print(f"  Production corr: {prod_corr.get('value', 'N/A')} ({prod_corr.get('result', prod_corr.get('status', 'N/A'))})")
        else:
            print(f"  Production corr: ERROR - {prod_corr.get('error', 'unknown')}")
        
        results[alpha_id] = factor_result
    
    # Summary
    print("\n" + "=" * 70)
    print("BENCHMARK SUMMARY")
    print("=" * 70)
    
    print(f"\nMetric Comparison (expected vs ACE library):")
    print(f"{'Factor':<25} {'Sharpe':<20} {'Fitness':<20} {'Turnover':<20}")
    print("-" * 85)
    
    all_metrics_match = True
    for alpha_id, expected in EXPECTED_FACTORS.items():
        r = results.get(alpha_id, {})
        actual = r.get("actual", {})
        matches = r.get("matches", {})
        
        name = expected["name"]
        sharpe_str = f"{actual.get('sharpe', 'N/A')}/{expected['sharpe']}"
        if matches.get("sharpe"):
            sharpe_str += " ✓"
        else:
            sharpe_str += " ✗"
            all_metrics_match = False
        
        fitness_str = f"{actual.get('fitness', 'N/A')}/{expected['fitness']}"
        if matches.get("fitness"):
            fitness_str += " ✓"
        else:
            fitness_str += " ✗"
            all_metrics_match = False
        
        turnover_str = f"{actual.get('turnover', 'N/A')}/{expected['turnover']}"
        if matches.get("turnover"):
            turnover_str += " ✓"
        else:
            turnover_str += " ✗"
            all_metrics_match = False
        
        print(f"{name:<25} {sharpe_str:<20} {fitness_str:<20} {turnover_str:<20}")
    
    print(f"\nOverall metrics match: {'✓ YES' if all_metrics_match else '✗ NO'}")
    
    # Save detailed results
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    output_dir = os.path.normpath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    detail_path = os.path.join(output_dir, "ace_benchmark_results.json")
    
    # Convert for JSON serialization
    json_results = {}
    for alpha_id, r in results.items():
        json_results[alpha_id] = {
            "name": r["expected"]["name"],
            "expected": r["expected"],
            "actual": r.get("actual", {}),
            "matches": r.get("matches", {}),
        }
    
    with open(detail_path, "w") as f:
        json.dump(json_results, f, indent=2, default=str)
    
    print(f"\nDetailed results saved to: {detail_path}")
    
    return 0 if all_metrics_match else 1


if __name__ == "__main__":
    sys.exit(run_benchmark())
