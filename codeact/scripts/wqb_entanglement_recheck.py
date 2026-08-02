#!/usr/bin/env python3
"""
重新检查6个非线性纠缠因子的提交状态（跳过模拟，仅做提交检查）。
"""
import os, sys, json, time, sqlite3
from datetime import datetime

os.environ.setdefault("BRAIN_CREDENTIAL_EMAIL", "q1z2q3@126.com")
os.environ.setdefault("BRAIN_CREDENTIAL_PASSWORD", "W2025zq0118")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ACE_LIB_DIR = os.path.join(SCRIPT_DIR, "ace_lib")
sys.path.insert(0, ACE_LIB_DIR)

PROJECT_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
DB_PATH = os.path.join(OUTPUT_DIR, "wqb_state.db")

import ace_lib
from ace_batch_runner import (
    run_submit_check, check_production_correlation,
    upsert_submit_check, SUBMISSION_CHECK_ITEMS, DEFAULT_SETTINGS
)

# 6个因子定义
FACTORS = [
    ("E1_门控反转", "Vk3m5RL8"),
    ("E2_调制反转", "78nvMeK5"),
    ("E3_方向调制", "78nvlE1Z"),
    ("E4_加权组合", "WjVoJmzQ"),
    ("E5_非对称门控", "np8erzA8"),
    ("E6_双变化量乘积", "omgJZKJb"),
]

def poll_submit_check(session, alpha_id, max_polls=5, interval=20):
    """轮询提交检查直到SELF_CORRELATION完成。"""
    for poll in range(max_polls):
        result = run_submit_check(session, alpha_id)
        checks = result.get("checks", {})
        sc = checks.get("SELF_CORRELATION", {})
        completed = all(c.get("status") != "PENDING" for c in checks.values() if c.get("status"))
        if completed:
            return result, poll + 1
        if poll < max_polls - 1:
            print(f"    ⏳ 第{poll+1}次轮询: SC={sc.get('status','?')}, 等{interval}s...")
            time.sleep(interval)
    return result, max_polls

def main():
    print("=" * 60)
    print(f"非线性纠缠因子 - 提交检查重检")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 登录
    print("\n[登录] 登录WQB...")
    session = ace_lib.start_session()
    timeout = ace_lib.check_session_timeout(session)
    print(f"  会话有效期: {timeout/3600:.1f} 小时")
    
    results = []
    for name, alpha_id in FACTORS:
        print(f"\n[{name}] ({alpha_id})...")
        
        # 先等30s避免429
        if results:
            print(f"  等待30s...")
            time.sleep(30)
        
        try:
            check_result, polls = poll_submit_check(session, alpha_id, max_polls=5, interval=20)
            
            # 提取关键指标
            sharpe = check_result.get("sharpe")
            fitness = check_result.get("fitness")
            turnover = check_result.get("turnover")
            self_corr = check_result.get("self_correlation")
            status = check_result.get("status", "UNKNOWN")
            checks = check_result.get("checks", {})
            
            # 检查SC
            sc_check = checks.get("SELF_CORRELATION", {})
            if sc_check.get("status") != "PENDING" and sc_check.get("value") is not None:
                self_corr = float(sc_check["value"])
            
            print(f"  Sharpe={sharpe}, Fitness={fitness}, SC={self_corr}, 状态={status} (轮询{polls}次)")
            
            # 更新数据库
            passed = 1 if status == "PASS" else 0
            upsert_submit_check(
                DB_PATH, alpha_id=alpha_id, factor_name=name,
                status=status, self_correlation=self_corr,
                sharpe=sharpe, fitness=fitness, turnover=turnover,
                checks=checks, passed=passed,
            )
            
            results.append({
                "name": name, "alpha_id": alpha_id,
                "sharpe": sharpe, "fitness": fitness,
                "turnover": turnover, "self_corr": self_corr,
                "status": status, "checks": checks,
            })
            
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            results.append({"name": name, "alpha_id": alpha_id, "status": "ERROR", "error": str(e)})
    
    # 生成报告
    print("\n" + "=" * 60)
    print("重检完成，生成报告...")
    
    report_lines = [
        "# 6个非线性纠缠因子 — 提交检查重检报告",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**回测设置**: EQUITY/USA/TOP3000, delay=1, decay=0, neutralization=SUBINDUSTRY, truncation=0.08, pasteurization=ON, testPeriod=P1Y6M",
        "",
        "## 回测与检查结果",
        "",
        "| 因子 | Alpha ID | Sharpe | Fitness | 换手率 | 自相关性 | 检查状态 |",
        "|------|----------|--------|---------|--------|----------|----------|",
    ]
    
    for r in results:
        sh = f"{r['sharpe']:.4f}" if isinstance(r.get('sharpe'), (int, float)) else str(r.get('sharpe', '?'))
        fi = f"{r['fitness']:.4f}" if isinstance(r.get('fitness'), (int, float)) else str(r.get('fitness', '?'))
        to = f"{r['turnover']:.4f}" if isinstance(r.get('turnover'), (int, float)) else str(r.get('turnover', '?'))
        sc = f"{r['self_corr']:.4f}" if isinstance(r.get('self_corr'), (int, float)) else str(r.get('self_corr', '?'))
        st = r.get('status', '?')
        st_icon = {"PASS": "✅ 通过", "FAIL": "❌ 失败", "PENDING": "⏳ 待定"}.get(st, st)
        report_lines.append(f"| {r['name']} | {r['alpha_id']} | {sh} | {fi} | {to} | {sc} | {st_icon} |")
    
    report_lines.append("")
    report_lines.append("## 8项检查详细结果")
    report_lines.append("")
    
    for r in results:
        checks = r.get("checks", {})
        if not checks:
            continue
        report_lines.append(f"### {r['name']} ({r['alpha_id']})")
        report_lines.append("")
        report_lines.append("| 检查项 | 状态 | 数值 | 阈值 |")
        report_lines.append("|--------|------|------|------|")
        for cn in SUBMISSION_CHECK_ITEMS:
            ci = checks.get(cn, {})
            s = ci.get("status", "N/A")
            v = ci.get("value", "-")
            l = ci.get("limit", "-")
            si = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "WARNING": "⚠️ WARNING", "PENDING": "⏳ PENDING"}.get(s, s)
            vs = f"{v:.4f}" if isinstance(v, (int, float)) else str(v)
            ls = f"{l:.4f}" if isinstance(l, (int, float)) else str(l)
            report_lines.append(f"| {cn} | {si} | {vs} | {ls} |")
        report_lines.append("")
    
    # 目标达成分析
    report_lines.append("## 核心目标达成分析")
    report_lines.append("")
    report_lines.append("| 目标 | 达标因子 | 说明 |")
    report_lines.append("|------|----------|------|")
    
    high_sh = [r['name'] for r in results if isinstance(r.get('sharpe'), (int, float)) and r['sharpe'] > 1.6]
    low_sc = [r['name'] for r in results if isinstance(r.get('self_corr'), (int, float)) and r['self_corr'] < 0.3]
    both = [r['name'] for r in results 
            if isinstance(r.get('sharpe'), (int, float)) and r['sharpe'] > 1.6 
            and isinstance(r.get('self_corr'), (int, float)) and r['self_corr'] < 0.3]
    
    report_lines.append(f"| Sharpe > 1.6 | {', '.join(high_sh) if high_sh else '无'} | 高收益风险比 |")
    report_lines.append(f"| 自相关性 < 0.3 | {', '.join(low_sc) if low_sc else '无'} | 低自相关性 |")
    report_lines.append(f"| 同时达标 | {', '.join(both) if both else '无'} | S>1.6 且 SC<0.3 |")
    report_lines.append("")
    
    report_path = os.path.join(OUTPUT_DIR, "wqb_entanglement_breakthrough.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"报告已保存: {report_path}")
    
    # 打印摘要
    print("\n" + "=" * 60)
    print("最终结果:")
    for r in results:
        sh = f"{r['sharpe']:.4f}" if isinstance(r.get('sharpe'), (int, float)) else "?"
        sc = f"{r['self_corr']:.4f}" if isinstance(r.get('self_corr'), (int, float)) else "?"
        print(f"  {r['name']}: Sharpe={sh}, SC={sc}, {r.get('status','?')}")
    print("=" * 60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())