#!/usr/bin/env python3
"""
d5自相关诊断 - 第三阶段：原始d5变体优化
===========================================

基于Phase 2发现：原始d5(decay=15设置+5日表达式衰减)自相关仅0.5838。
测试不同中性化和极小比例vol组合，寻找能通过全部8项检查的因子。

策略：利用原始d5的低自相关基础(0.5838)，小幅调整settings或添加极少量vol，
目标：保持SC<0.7的同时，确保其他所有检查项通过。
"""

import asyncio
import sys
import os
import json
import time
import sqlite3
import hashlib
from datetime import datetime
from typing import Dict, List, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

ACE_LIB_DIR = os.path.join(SCRIPT_DIR, "ace_lib")
sys.path.insert(0, ACE_LIB_DIR)
sys.path.insert(0, SCRIPT_DIR)

from codeact_sdk import CodeActSDK

SUBMIT_INTERVAL = 45.0

ALPHA021_SIGNAL = "subtract(divide(open, ts_delay(close, 1)), divide(close, open))"
ALPHA021_D5_EXPR = f"ts_decay_linear({ALPHA021_SIGNAL}, 5)"
VOL20_EXPR = "multiply(ts_std_dev(log(divide(close, ts_delay(close, 1))), 20), sqrt(252))"

DEFAULT_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 15,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "maxTrade": "ON",
    "pasteurization": "ON",
    "testPeriod": "P1Y6M",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
}


def normalize_settings(settings: Dict) -> Dict:
    full = dict(DEFAULT_SETTINGS)
    full.update(settings)
    return full


def expr_hash(expr: str, settings: Dict) -> str:
    key = expr + "|" + json.dumps(normalize_settings(settings), sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()[:16]


def create_session(email: str, password: str):
    import ace_lib
    os.environ["BRAIN_CREDENTIAL_EMAIL"] = email
    os.environ["BRAIN_CREDENTIAL_PASSWORD"] = password
    if hasattr(ace_lib.SingleSession, '_instance'):
        ace_lib.SingleSession._instance = None
        ace_lib.SingleSession._initialized = False
    s = ace_lib.start_session()
    return s


def get_alpha_by_hash(conn, h: str) -> Optional[Dict]:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alphas WHERE expr_hash = ? ORDER BY completed_at DESC LIMIT 1", (h,))
    row = cursor.fetchone()
    if row:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    return None


def submit_and_check(s, name: str, expr: str, settings: Dict, conn, do_check: bool = True) -> Dict:
    """提交单个因子并可选执行提交检查"""
    import ace_lib
    
    h = expr_hash(expr, settings)
    existing = get_alpha_by_hash(conn, h)
    
    if existing and existing.get("status") == "COMPLETED" and existing.get("alpha_id"):
        print(f"  {name}: 已存在 (S={existing.get('sharpe')}, F={existing.get('fitness')}, T={existing.get('turnover')})")
        result = {
            "name": name, "alpha_id": existing["alpha_id"],
            "status": "COMPLETED", "sharpe": existing.get("sharpe"),
            "fitness": existing.get("fitness"), "turnover": existing.get("turnover"),
            "existing": True
        }
    else:
        print(f"  提交: {name}")
        try:
            simulate_data = {"type": "REGULAR", "settings": settings, "regular": expr}
            sim_result = ace_lib.simulate_single_alpha(s, simulate_data)
            alpha_id = sim_result.get("alpha_id")
            
            if alpha_id:
                stats_result = ace_lib.get_specified_alpha_stats(s, alpha_id, simulate_data)
                stats = {}
                if stats_result.get("is_stats") is not None and not stats_result["is_stats"].empty:
                    row = stats_result["is_stats"].iloc[0]
                    stats = {"sharpe": row.get("sharpe"), "fitness": row.get("fitness"),
                             "turnover": row.get("turnover"), "ic": row.get("ic")}
                
                # 保存
                settings_json = json.dumps(normalize_settings(settings), sort_keys=True)
                now = datetime.now().isoformat()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO alphas 
                    (expr_hash, expression, factor_name, settings_json, alpha_id, status,
                     sharpe, fitness, turnover, submitted_at, completed_at)
                    VALUES (?, ?, ?, ?, ?, 'COMPLETED', ?, ?, ?, ?, ?)
                """, (h, expr, name, settings_json, alpha_id,
                      stats.get("sharpe"), stats.get("fitness"), stats.get("turnover"),
                      now, now))
                conn.commit()
                
                print(f"    ✅ S={stats.get('sharpe'):.2f}, F={stats.get('fitness'):.2f}, T={stats.get('turnover'):.4f}")
                result = {"name": name, "alpha_id": alpha_id, "status": "COMPLETED",
                          "sharpe": stats.get("sharpe"), "fitness": stats.get("fitness"),
                          "turnover": stats.get("turnover"), "existing": False}
            else:
                print(f"    ❌ 模拟失败")
                return {"name": name, "alpha_id": None, "status": "FAILED", "existing": False}
        except Exception as e:
            print(f"    ❌ 异常: {e}")
            return {"name": name, "alpha_id": None, "status": "FAILED", "error": str(e), "existing": False}
    
    # 执行提交检查
    if do_check and result.get("alpha_id") and result.get("status") == "COMPLETED":
        # 只对达标的做检查
        s_val = result.get("sharpe")
        f_val = result.get("fitness")
        t_val = result.get("turnover")
        
        if (isinstance(s_val, float) and s_val >= 1.25 and
            isinstance(f_val, float) and f_val >= 1.0 and
            isinstance(t_val, float) and t_val <= 0.7):
            
            print(f"    📋 执行提交检查...")
            try:
                checks_df = ace_lib.get_check_submission(s, result["alpha_id"])
                checks = []
                all_pass = True
                if not checks_df.empty:
                    for _, row in checks_df.iterrows():
                        cname = row.get("name", row.get("check", "UNKNOWN"))
                        cresult = row.get("result", "")
                        cvalue = row.get("value", None)
                        climit = row.get("limit", None)
                        if cresult and "FAIL" in str(cresult).upper():
                            all_pass = False
                        checks.append({"name": cname, "result": cresult, "value": cvalue, "limit": climit})
                
                passed = sum(1 for c in checks if c["result"].upper() == "PASS")
                status = "🎉" if all_pass else "⚠️"
                print(f"    {status} {passed}/{len(checks)} 通过")
                if not all_pass:
                    failed = [c for c in checks if c["result"].upper() == "FAIL"]
                    for c in failed:
                        print(f"       ❌ {c['name']}: {c['value']} (阈值: {c['limit']})")
                
                result["checks"] = checks
                result["all_pass"] = all_pass
            except Exception as e:
                print(f"    ⚠ 检查失败: {e}")
                result["check_error"] = str(e)
    
    return result


async def main():
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    email = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("BRAIN_CREDENTIAL_EMAIL", "q1z2q3@126.com")
    password = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("BRAIN_CREDENTIAL_PASSWORD", "W2025zq0118")
    db_path = sys.argv[4] if len(sys.argv) > 4 else os.path.join(OUTPUT_DIR, "wqb_state.db")
    report_path = sys.argv[5] if len(sys.argv) > 5 else os.path.join(OUTPUT_DIR, "wqb_d5_selfcorr_breakthrough_report.md")
    
    sdk = CodeActSDK()
    if result_mode == "auto":
        result_mode = "display_only"
    
    try:
        print("=" * 70)
        print("Phase 3: 原始d5变体优化 - 寻找通过全部检查的因子")
        print("=" * 70)
        
        conn = sqlite3.connect(db_path)
        
        # 确保alphas表存在
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alphas (
                expr_hash TEXT PRIMARY KEY,
                expression TEXT NOT NULL,
                factor_name TEXT,
                category TEXT,
                settings_json TEXT NOT NULL,
                alpha_id TEXT,
                status TEXT DEFAULT 'PENDING',
                sharpe REAL,
                fitness REAL,
                ic REAL,
                rank_ic REAL,
                turnover REAL,
                annual_return REAL,
                max_drawdown REAL,
                is_summary TEXT,
                yearly_json TEXT,
                submitted_at TEXT,
                completed_at TEXT,
                error TEXT
            )
        """)
        conn.commit()
        print(f"✅ 数据库就绪")
        
        print(f"\n📡 登录WQB...")
        s = create_session(email, password)
        print(f"✅ 登录成功\n")
        
        # ========================================
        # 定义要测试的变体
        # ========================================
        print("🧪 测试因子变体（基于原始d5：decay=15 + ts_decay_linear(5)）")
        print("-" * 50)
        
        variants = []
        
        # 1. 不同中性化等级
        variants.append({
            "name": "alpha_021_d5_v2_sector",
            "expr": ALPHA021_D5_EXPR,
            "settings": normalize_settings({"neutralization": "SECTOR"}),
            "desc": "SECTOR中性化，可能提升Fitness",
            "category": "neutralization",
        })
        
        variants.append({
            "name": "alpha_021_d5_v2_industry",
            "expr": ALPHA021_D5_EXPR,
            "settings": normalize_settings({"neutralization": "INDUSTRY"}),
            "desc": "INDUSTRY中性化，SUBINDUSTRY和SECTOR之间",
            "category": "neutralization",
        })
        
        variants.append({
            "name": "alpha_021_d5_v2_none",
            "expr": ALPHA021_D5_EXPR,
            "settings": normalize_settings({"neutralization": "NONE"}),
            "desc": "无中性化，最大化Fitness(但可能SC升高)",
            "category": "neutralization",
        })
        
        # 2. 极小比例vol20组合（基于原始d5的衰减水平）
        variants.append({
            "name": "combo_d5_v2_vol20_w995_05",
            "expr": f"add(multiply({ALPHA021_D5_EXPR}, 0.995), multiply({VOL20_EXPR}, -0.005))",
            "settings": normalize_settings({}),
            "desc": "99.5% d5 + 0.5% vol20，极小比例测试SC耐受度",
            "category": "vol_combo",
        })
        
        variants.append({
            "name": "combo_d5_v2_vol20_w99_1",
            "expr": f"add(multiply({ALPHA021_D5_EXPR}, 0.99), multiply({VOL20_EXPR}, -0.01))",
            "settings": normalize_settings({}),
            "desc": "99% d5 + 1% vol20",
            "category": "vol_combo",
        })
        
        variants.append({
            "name": "combo_d5_v2_vol20_w98_2",
            "expr": f"add(multiply({ALPHA021_D5_EXPR}, 0.98), multiply({VOL20_EXPR}, -0.02))",
            "settings": normalize_settings({}),
            "desc": "98% d5 + 2% vol20",
            "category": "vol_combo",
        })
        
        # 3. d5 + 不同truncation
        variants.append({
            "name": "alpha_021_d5_v2_trunc05",
            "expr": ALPHA021_D5_EXPR,
            "settings": normalize_settings({"truncation": 0.05}),
            "desc": "降低truncation至0.05，可能提升Sharpe",
            "category": "truncation",
        })
        
        print(f"共 {len(variants)} 个变体\n")
        
        # ========================================
        # 逐个提交并检查
        # ========================================
        results = []
        for i, v in enumerate(variants):
            print(f"[{i+1}/{len(variants)}] {v['name']} ({v['desc']})")
            result = submit_and_check(s, v["name"], v["expr"], v["settings"], conn, do_check=True)
            result["category"] = v["category"]
            result["desc"] = v["desc"]
            results.append(result)
            
            if i < len(variants) - 1:
                print(f"  等待 {SUBMIT_INTERVAL}s...")
                time.sleep(SUBMIT_INTERVAL)
            print()
        
        # ========================================
        # 汇总结果
        # ========================================
        print("\n" + "=" * 70)
        print("📊 结果汇总")
        print("=" * 70)
        
        completed = [r for r in results if r.get("status") == "COMPLETED"]
        qualifying = [r for r in completed 
                     if isinstance(r.get("sharpe"), float) and r["sharpe"] >= 1.25
                     and isinstance(r.get("fitness"), float) and r["fitness"] >= 1.0
                     and isinstance(r.get("turnover"), float) and r["turnover"] <= 0.7]
        all_pass = [r for r in results if r.get("all_pass") == True]
        
        print(f"\n完成: {len(completed)}/{len(results)}")
        print(f"达标(S≥1.25, F≥1.0, T≤0.7): {len(qualifying)}")
        print(f"全部检查通过: {len(all_pass)}")
        
        if all_pass:
            print(f"\n🎉 发现通过全部检查的因子!")
            for r in all_pass:
                print(f"  - {r['name']}: S={r['sharpe']:.2f}, F={r['fitness']:.2f} (ID: {r['alpha_id']})")
        else:
            print(f"\n⚠️ 暂无因子通过全部检查")
            # 分析失败原因
            checked = [r for r in results if r.get("checks")]
            for r in checked:
                if not r.get("all_pass"):
                    failed = [c for c in r["checks"] if c["result"].upper() == "FAIL"]
                    fail_names = [c["name"] for c in failed]
                    print(f"  - {r['name']}: 失败项 = {fail_names}")
        
        # ========================================
        # 更新报告
        # ========================================
        print(f"\n📝 更新报告...")
        
        # 读取现有报告
        existing_report = ""
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                existing_report = f.read()
        
        # 构建Phase 3追加内容
        lines = []
        lines.append("\n\n---\n\n")
        lines.append("## 六、Phase 3：原始d5变体深度优化\n")
        lines.append(f"**更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        lines.append("### 6.1 测试策略\n")
        lines.append("基于Phase 2发现原始d5(decay=15 + 5日表达式衰减)自相关仅0.5838，")
        lines.append("测试以下变体寻找能通过全部8项检查的因子：\n")
        lines.append("- **中性化调整**: SECTOR / INDUSTRY / NONE")
        lines.append("- **极小vol组合**: 0.5% / 1% / 2% vol20（测试SC耐受度）")
        lines.append("- **Truncation调整**: 0.05（降低至5%）\n")
        
        lines.append("### 6.2 完整结果表\n")
        lines.append("| 因子 | 类别 | Sharpe | Fitness | 换手率 | 8项检查 | 失败项 |")
        lines.append("|------|------|--------|---------|--------|---------|--------|")
        
        for r in sorted(results, key=lambda x: x.get("fitness") or 0, reverse=True):
            name = r["name"]
            cat = r.get("category", "")
            s_val = r.get("sharpe")
            f_val = r.get("fitness")
            t_val = r.get("turnover")
            status = r.get("status", "")
            
            s_str = f"{s_val:.2f}" if isinstance(s_val, float) else str(s_val)
            f_str = f"{f_val:.2f}" if isinstance(f_val, float) else str(f_val)
            t_str = f"{t_val:.4f}" if isinstance(t_val, float) else str(t_val)
            
            if r.get("all_pass") == True:
                check_status = "🎉 全部通过"
                fail_items = "-"
            elif r.get("checks"):
                passed = sum(1 for c in r["checks"] if c["result"].upper() == "PASS")
                total = len(r["checks"])
                check_status = f"{passed}/{total}"
                failed = [c["name"] for c in r["checks"] if c["result"].upper() == "FAIL"]
                fail_items = ", ".join(failed) if failed else "-"
            else:
                check_status = status
                fail_items = "-"
            
            marks = []
            if isinstance(s_val, float) and s_val >= 1.25:
                marks.append("📈")
            if isinstance(f_val, float) and f_val >= 1.0:
                marks.append("💪")
            mark_str = " " + "".join(marks) if marks else ""
            
            lines.append(f"| {name}{mark_str} | {cat} | {s_str} | {f_str} | {t_str} | {check_status} | {fail_items} |")
        
        lines.append("")
        
        # 结论
        lines.append("### 6.3 关键发现\n")
        
        if all_pass:
            lines.append(f"🎉 **突破！发现 {len(all_pass)} 个通过全部8项检查的因子：**\n")
            for r in all_pass:
                lines.append(f"- **{r['name']}**: Sharpe={r['sharpe']:.2f}, Fitness={r['fitness']:.2f}")
                lines.append(f"  Alpha ID: `{r['alpha_id']}`\n")
        else:
            lines.append("#### 未能通过全部检查的原因分析\n")
            
            # 统计失败原因
            fail_reasons = {}
            for r in results:
                if r.get("checks") and not r.get("all_pass"):
                    for c in r["checks"]:
                        if c["result"].upper() == "FAIL":
                            cname = c["name"]
                            if cname not in fail_reasons:
                                fail_reasons[cname] = []
                            fail_reasons[cname].append(r["name"])
            
            for reason, factors in fail_reasons.items():
                lines.append(f"- **{reason}**: {len(factors)} 个因子失败")
                for fname in factors:
                    r = next((x for x in results if x["name"] == fname), None)
                    if r:
                        val = next((c["value"] for c in r["checks"] if c["name"] == reason), "N/A")
                        limit = next((c["limit"] for c in r["checks"] if c["name"] == reason), "N/A")
                        lines.append(f"  - {fname}: {val} (阈值: {limit})")
                lines.append("")
        
        lines.append("### 6.4 最终结论与建议\n")
        lines.append("1. **d5低自相关特性确认可靠**: 基于decay=15的原始d5，自相关仅0.5838")
        lines.append("2. **中性化对自相关影响**：（根据SECTOR/INDUSTRY/NONE结果）")
        lines.append("3. **vol组合的SC阈值**：（根据0.5%/1%/2%结果，找到SC<0.7的最大vol比例）")
        lines.append("")
        lines.append("**下一步建议**：")
        lines.append("- 若SECTOR/INDUSTRY中性化版本通过 → 直接提交")
        lines.append("- 若vol组合在某个权重下通过 → 精细化扫描该权重附近")
        lines.append("- 若全部失败在同一项 → 针对性优化该项\n")
        
        # 写入报告
        final_report = existing_report + "\n".join(lines)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(final_report)
        
        print(f"✅ 报告已更新: {report_path}")
        
        conn.close()
        
        # 提交结果
        summary = []
        summary.append("## 🚀 Phase 3：d5变体优化结果\n")
        
        if all_pass:
            summary.append(f"### 🎉 突破！{len(all_pass)} 个因子通过全部8项检查")
            for r in all_pass:
                summary.append(f"- **{r['name']}**: S={r['sharpe']:.2f}, F={r['fitness']:.2f}")
            summary.append("")
        else:
            summary.append(f"### ⚠️ 暂无全部通过的因子（测试了 {len(completed)} 个变体）")
            # 显示最接近的
            checked = [r for r in results if r.get("checks")]
            if checked:
                best = max(checked, key=lambda r: sum(1 for c in r["checks"] if c["result"].upper() == "PASS"))
                passed = sum(1 for c in best["checks"] if c["result"].upper() == "PASS")
                total = len(best["checks"])
                failed = [c["name"] for c in best["checks"] if c["result"].upper() == "FAIL"]
                summary.append(f"- 最佳: {best['name']} ({passed}/{total} 通过, 失败: {', '.join(failed)})")
            summary.append("")
        
        # 显示完整结果表
        summary.append("### 📊 完整结果")
        for r in sorted(results, key=lambda x: x.get("fitness") or 0, reverse=True):
            s_val = r.get("sharpe")
            f_val = r.get("fitness")
            t_val = r.get("turnover")
            s_str = f"{s_val:.2f}" if isinstance(s_val, float) else "N/A"
            f_str = f"{f_val:.2f}" if isinstance(f_val, float) else "N/A"
            t_str = f"{t_val:.4f}" if isinstance(t_val, float) else "N/A"
            
            check_str = ""
            if r.get("all_pass") == True:
                check_str = " 🎉全过"
            elif r.get("checks"):
                passed = sum(1 for c in r["checks"] if c["result"].upper() == "PASS")
                total = len(r["checks"])
                check_str = f" ({passed}/{total})"
            
            summary.append(f"- {r['name']}: S={s_str}, F={f_str}, T={t_str}{check_str}")
        
        summary.append(f"\n📄 完整报告: `{report_path}`")
        
        message = "\n".join(summary)
        
        await sdk.submit_result(
            status="success",
            result_mode=result_mode,
            message=message,
            data={
                "report_path": report_path,
                "total_variants": len(results),
                "completed": len(completed),
                "qualifying": len(qualifying),
                "all_pass": len(all_pass),
                "all_pass_names": [r["name"] for r in all_pass],
            }
        )
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"\n❌ 执行失败: {e}")
        print(error_detail)
        
        try:
            await sdk.submit_result(
                status="error",
                result_mode="notify",
                message=f"Phase 3失败: {str(e)}",
                data={"error": str(e), "traceback": error_detail}
            )
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())
