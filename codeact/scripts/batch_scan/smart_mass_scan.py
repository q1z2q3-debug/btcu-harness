#!/usr/bin/env python3
"""
Smart Mass Scan - ACE库底层API，一次登录+多模拟并发
使用multi-simulation一次提交10个因子，大幅减少API调用次数
"""

import os, sys, json, time, hashlib, argparse, threading
from datetime import datetime
from pathlib import Path

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
            n = 0
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                n += 1
                name = f"{cat}_{n}"
                all_exprs.append(line)
                all_names.append(name)
    return all_exprs, all_names

def submit_multi_simulation(s, simulate_data_list):
    """Submit multiple alphas in one multi-simulation request."""
    url = "https://api.worldquantbrain.com/simulations"
    r = s.post(url, json={"type": "REGULAR", "settings": BASE_SETTINGS, "alphas": simulate_data_list})
    if r.status_code // 100 != 2:
        return {"error": f"multi_sim: {r.status_code} {r.text[:200]}"}
    return {"location": r.headers.get("Location")}

def wait_multi_simulation(s, location):
    """Wait for multi-simulation to complete."""
    while True:
        r = s.get(location)
        retry = r.headers.get("Retry-After")
        if retry:
            time.sleep(float(retry) + 1)
            continue
        if r.status_code // 100 != 2:
            return {"error": f"progress: {r.status_code}"}
        data = r.json()
        if data.get("status") == "ERROR":
            return {"error": "multi_sim_error"}
        if data.get("children"):
            return {"children": data["children"]}
        time.sleep(2)

def get_alpha_stats(s, alpha_id):
    """Get alpha stats and checks."""
    result = {}
    
    r = s.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}")
    if r.status_code // 100 == 2:
        d = r.json().get("is", {})
        result["sharpe"] = d.get("sharpe")
        result["fitness"] = d.get("fitness")
        result["turnover"] = d.get("turnover")
        result["retention"] = d.get("retention")
        result["max_drawdown"] = d.get("maxDrawdown")
    
    time.sleep(1)
    r = s.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}/check")
    if r.status_code // 100 == 2:
        checks = r.json().get("is", {}).get("checks", [])
        for c in checks:
            result[f"check_{c.get('test','?')}"] = c.get("result") == "PASS"
    
    time.sleep(1)
    r = s.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}/correlations/self")
    if r.status_code // 100 == 2:
        sc_data = r.json()
        if sc_data.get("records"):
            result["self_correlation"] = sc_data["max"]
        else:
            result["self_correlation"] = 0.0
    
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-mode", default="display_only", choices=["display_only","notify","no_reply","auto"])
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    expressions, names = load_expressions(base_dir)
    total = len(expressions)
    print(f"[SMART] 加载 {total} 个因子表达式")
    
    # ONE login
    print("[SMART] 登录中...")
    s = ace_lib.start_session()
    print("[SMART] 登录成功")
    
    # Split into batches of 10 for multi-simulation
    batches = [list(zip(expressions[i:i+10], names[i:i+10])) 
               for i in range(0, total, 10)]
    print(f"[SMART] 分 {len(batches)} 批，每批≤10个因子，顺序执行")
    
    all_results = []
    success_count = 0
    
    for batch_idx, batch in enumerate(batches):
        print(f"\n{'='*60}")
        print(f"批次 {batch_idx+1}/{len(batches)} - {len(batch)} 个因子")
        print(f"{'='*60}")
        
        for i, (expr, name) in enumerate(batch):
            print(f"  [{i+1}/{len(batch)}] {name}: {expr[:60]}...")
            
            # Simulate single alpha
            sim_data = {"type": "REGULAR", "settings": BASE_SETTINGS, "regular": expr}
            r = s.post("https://api.worldquantbrain.com/simulations", json=sim_data)
            
            if r.status_code // 100 != 2:
                print(f"    ❌ 模拟失败: {r.status_code} {r.text[:100]}")
                all_results.append({"factor_name": name, "expression": expr, "error": str(r.status_code)})
                continue
            
            loc = r.headers.get("Location")
            
            # Wait for completion
            while True:
                r2 = s.get(loc)
                retry = r2.headers.get("Retry-After")
                if retry:
                    time.sleep(float(retry) + 1)
                    continue
                if r2.status_code // 100 != 2:
                    print(f"    ❌ 进度查询失败: {r2.status_code}")
                    break
                data = r2.json()
                if data.get("status") == "ERROR" or not data.get("alpha"):
                    print(f"    ❌ 模拟失败: {data.get('status', 'no alpha')}")
                    break
                if data.get("alpha"):
                    alpha_id = data["alpha"]
                    # Get stats
                    time.sleep(2)
                    stats = get_alpha_stats(s, alpha_id)
                    stats["factor_name"] = name
                    stats["expression"] = expr
                    stats["alpha_id"] = alpha_id
                    all_results.append(stats)
                    success_count += 1
                    
                    sh = stats.get("sharpe", "N/A")
                    sc = stats.get("self_correlation", "N/A")
                    sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
                    sh_str = f"{sh:.4f}" if isinstance(sh, (int,float)) else str(sh)
                    print(f"    ✅ S={sh_str} SC={sc_str} F={stats.get('fitness','N/A')} TO={stats.get('turnover','N/A')}")
                    break
                time.sleep(2)
            
            # Wait between requests for rate limiting
            if i < len(batch) - 1 or batch_idx < len(batches) - 1:
                wait = 50
                print(f"    ⏳ 等待 {wait}s...")
                time.sleep(wait)
    
    # ====== Report ======
    print("\n" + "=" * 70)
    print(f"SMART SCAN 完成: {success_count}/{total} 成功")
    print("=" * 70)
    
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
    
    low_sc = [r for r in ranked if isinstance(r.get("self_correlation"), (int,float)) and r["self_correlation"] < 0.3]
    print(f"\n=== SC<0.3 候选: {len(low_sc)} 个 ===")
    for r in sorted(low_sc, key=lambda x: x["sharpe"] or -999, reverse=True):
        print(f"  {r['factor_name'][:25]:<25} S={r['sharpe']:.4f} SC={r['self_correlation']:.4f}")
    
    high_sh = [r for r in ranked if r.get("sharpe") and r["sharpe"] > 1.25]
    print(f"\n=== Sharpe>1.25 候选: {len(high_sh)} 个 ===")
    for r in high_sh:
        sc = r.get("self_correlation", "N/A")
        sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
        print(f"  {r['factor_name'][:25]:<25} S={r['sharpe']:.4f} SC={sc_str}")
    
    # Save report
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(OUTPUT_DIR, f"smart_mass_scan_{timestamp}.md")
    with open(report_path, "w") as f:
        f.write(f"# Smart Mass Scan 报告\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**成功/总数**: {success_count}/{total}\n\n")
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
            "success_count": success_count, "total": total,
            "ranked": [{"name": r["factor_name"], "sharpe": r.get("sharpe"), "sc": r.get("self_correlation"), "fitness": r.get("fitness"), "turnover": r.get("turnover")} for r in ranked],
            "sc03_candidates": [{"name": r["factor_name"], "sharpe": r["sharpe"], "sc": r["self_correlation"]} for r in low_sc],
            "high_sharpe_candidates": [{"name": r["factor_name"], "sharpe": r["sharpe"], "sc": r.get("self_correlation")} for r in high_sh],
        }, f, indent=2)
    
    print(f"\n报告: {report_path}")
    print(f"JSON: {json_path}")

if __name__ == "__main__":
    main()