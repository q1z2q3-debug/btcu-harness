#!/usr/bin/env python3
"""
Direct API Mass Scan - 一次登录，顺序扫描，避开ACE库的并发登录问题

策略：
- 一次登录，复用session
- 相邻请求间隔50秒，配合rate limit header
- 顺序扫描，每批10个因子并行
- 完整记录每个因子的Sharpe/SC/Fitness/换手率
"""

import os, sys, json, time, hashlib, argparse
from datetime import datetime
from pathlib import Path

# Clear proxy
for v in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy'):
    os.environ.pop(v, None)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ace_lib'))
import requests
import ace_lib

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

CATEGORIES = {
    "A_volume": "expressions_category_A_volume.txt",
    "B_corr": "expressions_category_B_corr.txt",
    "C_nonlinear": "expressions_category_C_nonlinear.txt",
    "D_price": "expressions_category_D_price.txt",
}

BASE_SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 0, "neutralization": "SUBINDUSTRY",
    "truncation": 0.08, "pasteurization": "ON", "testPeriod": "P1Y6M",
    "unitHandling": "VERIFY", "nanHandling": "OFF", "maxTrade": "OFF",
    "language": "FASTEXPR", "visualization": False,
}

def load_expressions(base_dir):
    all_exprs, all_names = [], []
    for cat, filename in CATEGORIES.items():
        fp = os.path.join(base_dir, filename)
        if not os.path.exists(fp): continue
        with open(fp) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                all_exprs.append(line)
                all_names.append(f"{cat}_{len(all_exprs)}")
    return all_exprs, all_names

def simulate_one(s, expr, name, settings):
    """Simulate a single factor expression and get full stats."""
    sim_data = {"type": "REGULAR", "settings": settings, "regular": expr}
    
    # Start simulation
    r = s.post("https://api.worldquantbrain.com/simulations", json=sim_data)
    if r.status_code // 100 != 2:
        return {"factor_name": name, "expression": expr, "error": f"sim_start: {r.status_code} {r.text[:200]}", "alpha_id": None}
    
    loc = r.headers.get("Location")
    if not loc:
        return {"factor_name": name, "expression": expr, "error": "no Location header", "alpha_id": None}
    
    # Wait for completion
    while True:
        r2 = s.get(loc)
        retry = r2.headers.get("Retry-After")
        if retry:
            time.sleep(float(retry) + 1)
            continue
        if r2.status_code // 100 != 2:
            return {"factor_name": name, "expression": expr, "error": f"progress: {r2.status_code}", "alpha_id": None}
        data = r2.json()
        if data.get("status") == "ERROR" or data.get("alpha") is None:
            return {"factor_name": name, "expression": expr, "error": f"sim_error: {data.get('status', 'unknown')}", "alpha_id": None}
        if data.get("alpha"):
            alpha_id = data["alpha"]
            break
        time.sleep(2)
    
    # Get alpha stats
    time.sleep(2)
    r3 = s.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}")
    alpha_data = r3.json()
    
    # Get submission check
    time.sleep(1)
    r4 = s.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}/check")
    
    # Get self correlation
    time.sleep(1)
    r5 = s.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}/correlations/self")
    
    result = {
        "factor_name": name,
        "expression": expr,
        "alpha_id": alpha_id,
        "sharpe": alpha_data.get("is", {}).get("sharpe"),
        "fitness": alpha_data.get("is", {}).get("fitness"),
        "turnover": alpha_data.get("is", {}).get("turnover"),
        "retention": alpha_data.get("is", {}).get("retention"),
        "max_drawdown": alpha_data.get("is", {}).get("maxDrawdown"),
    }
    
    # Parse check results
    if r4.status_code // 100 == 2:
        checks = r4.json().get("is", {}).get("checks", [])
        for c in checks:
            result[f"check_{c.get('test','?')}"] = c.get("result") == "PASS"
    
    # Parse self correlation
    if r5.status_code // 100 == 2:
        sc_data = r5.json()
        if sc_data.get("records"):
            result["self_correlation"] = sc_data["max"]
        else:
            result["self_correlation"] = 0.0
    
    return result

def main():
    parser = argparse.ArgumentParser(description="Direct API Mass Scan")
    parser.add_argument("--result-mode", default="display_only", choices=["display_only","notify","no_reply","auto"])
    parser.add_argument("--concurrency", type=int, default=3, help="按照ACE库的多因子并发模式")
    args = parser.parse_args()
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    expressions, names = load_expressions(base_dir)
    print(f"[DIRECT] 加载 {len(expressions)} 个因子表达式")
    
    # ONE login - single session, reused throughout
    print("[DIRECT] 登录中...")
    s = ace_lib.start_session()
    print(f"[DIRECT] 登录成功")
    
    all_results = []
    success_count = 0
    
    for i, (expr, name) in enumerate(zip(expressions, names)):
        print(f"\n[{i+1}/{len(expressions)}] {name}: {expr[:60]}...")
        
        result = simulate_one(s, expr, name, BASE_SETTINGS)
        all_results.append(result)
        
        if result.get("alpha_id"):
            success_count += 1
            sh = result.get("sharpe", "N/A")
            sc = result.get("self_correlation", "N/A")
            ft = result.get("fitness", "N/A")
            to = result.get("turnover", "N/A")
            sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
            sh_str = f"{sh:.4f}" if isinstance(sh, (int,float)) else str(sh)
            print(f"  ✅ S={sh_str} SC={sc_str} F={ft} TO={to}")
        else:
            print(f"  ❌ {result.get('error','unknown error')}")
        
        # Rate limit: 50s between requests (conservative for free account)
        if i < len(expressions) - 1:
            wait = 50
            print(f"  ⏳ 等待 {wait}s...")
            time.sleep(wait)
    
    # Final report
    print("\n" + "=" * 70)
    print(f"扫描完成: {success_count}/{len(expressions)} 成功")
    print("=" * 70)
    
    # Sort by Sharpe descending
    ranked = sorted([r for r in all_results if r.get("sharpe") is not None],
                    key=lambda r: r["sharpe"], reverse=True)
    
    print(f"\n{'排名':<4} {'因子名':<25} {'Sharpe':<8} {'Fitness':<8} {'SC':<8} {'换手率':<8}")
    print("-" * 65)
    for i, r in enumerate(ranked):
        sc = r.get("self_correlation", "N/A")
        sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
        sh_str = f"{r['sharpe']:.4f}" if r.get("sharpe") else "N/A"
        ft_str = f"{r['fitness']:.4f}" if r.get("fitness") else "N/A"
        to_str = f"{r['turnover']:.4f}" if r.get("turnover") else "N/A"
        print(f"{i+1:<4} {r['factor_name'][:25]:<25} {sh_str:<8} {ft_str:<8} {sc_str:<8} {to_str:<8}")
    
    # SC<0.3 candidates
    low_sc = [r for r in ranked if isinstance(r.get("self_correlation"), (int,float)) and r["self_correlation"] < 0.3]
    print(f"\n=== SC<0.3 候选: {len(low_sc)} 个 ===")
    for r in sorted(low_sc, key=lambda x: x["sharpe"] or -999, reverse=True):
        print(f"  {r['factor_name'][:25]:<25} S={r['sharpe']:.4f} SC={r['self_correlation']:.4f} F={r.get('fitness','N/A')} TO={r.get('turnover','N/A')}")
    
    # Sharpe>1.25 candidates
    high_sh = [r for r in ranked if r.get("sharpe") and r["sharpe"] > 1.25]
    print(f"\n=== Sharpe>1.25 候选: {len(high_sh)} 个 ===")
    for r in high_sh:
        sc = r.get("self_correlation", "N/A")
        sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
        print(f"  {r['factor_name'][:25]:<25} S={r['sharpe']:.4f} SC={sc_str} F={r.get('fitness','N/A')} TO={r.get('turnover','N/A')}")
    
    # Save report
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(OUTPUT_DIR, f"direct_mass_scan_{timestamp}.md")
    with open(report_path, "w") as f:
        f.write(f"# 直接API大规模扫描报告\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**成功/总数**: {success_count}/{len(expressions)}\n\n")
        f.write(f"## 全量排名\n\n")
        f.write(f"| 排名 | 因子名 | Sharpe | Fitness | SC | 换手率 |\n")
        f.write(f"|------|--------|--------|---------|----|--------|\n")
        for i, r in enumerate(ranked):
            sc = r.get("self_correlation", "N/A")
            sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
            sh_str = f"{r['sharpe']:.4f}" if r.get("sharpe") else "N/A"
            ft_str = f"{r['fitness']:.4f}" if r.get("fitness") else "N/A"
            to_str = f"{r['turnover']:.4f}" if r.get("turnover") else "N/A"
            f.write(f"| {i+1} | {r['factor_name']} | {sh_str} | {ft_str} | {sc_str} | {to_str} |\n")
        f.write(f"\n## SC<0.3 候选\n\n")
        for r in low_sc:
            f.write(f"- {r['factor_name']}: S={r['sharpe']:.4f} SC={r['self_correlation']:.4f}\n")
        f.write(f"\n## Sharpe>1.25 候选\n\n")
        for r in high_sh:
            sc = r.get("self_correlation", "N/A")
            sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
            f.write(f"- {r['factor_name']}: S={r['sharpe']:.4f} SC={sc_str}\n")
    
    json_path = report_path.replace(".md", ".json")
    with open(json_path, "w") as f:
        json.dump({
            "success_count": success_count,
            "total": len(expressions),
            "ranked": [{"name": r["factor_name"], "sharpe": r.get("sharpe"), "sc": r.get("self_correlation"), "fitness": r.get("fitness"), "turnover": r.get("turnover")} for r in ranked],
            "sc03_candidates": [{"name": r["factor_name"], "sharpe": r["sharpe"], "sc": r["self_correlation"]} for r in low_sc],
            "high_sharpe_candidates": [{"name": r["factor_name"], "sharpe": r["sharpe"], "sc": r.get("self_correlation")} for r in high_sh],
        }, f, indent=2)
    
    print(f"\n报告: {report_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()