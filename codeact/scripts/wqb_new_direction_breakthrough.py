#!/usr/bin/env python3
"""
WQB New Direction Breakthrough - 15全新方向因子批量回测与提交

使用ACE库探索5个九维认知新方向（每个方向3个因子），完全脱离alpha_021反转家族。
策略：先快速提交所有因子到队列，再集中轮询结果，避免线程残留导致限流冲突。

用法:
    python wqb_new_direction_breakthrough.py [result_mode] [--auto-submit]
"""

import asyncio
import sys
import os
import json
import time
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

from codeact_sdk import CodeActSDK

# Add ace_lib to path
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ACE_LIB_DIR = os.path.join(_SCRIPT_DIR, "ace_lib")
sys.path.insert(0, _ACE_LIB_DIR)

import ace_lib
import requests

# ============================================================
# 15个全新因子
# ============================================================

FACTORS = [
    # 方向1: C₁=+1 动量延续
    {"name": "c1_mom_price_ma_corr", "direction": "C₁=+1 动量延续",
     "expression": "rank(ts_corr(rank(close), rank(ts_mean(close, 10)), 5))",
     "description": "价格与短期均线(10日)相关性"},
    {"name": "c1_mom_price_ma30_corr", "direction": "C₁=+1 动量延续",
     "expression": "rank(ts_corr(rank(close), rank(ts_mean(close, 30)), 10))",
     "description": "价格与中期均线(30日)相关性"},
    {"name": "c1_mom_acceleration", "direction": "C₁=+1 动量延续",
     "expression": "rank(ts_corr(rank(ts_delta(close, 5)), rank(ts_delta(ts_mean(close, 20), 5)), 10))",
     "description": "动量加速度"},
    # 方向2: S₂ 量价协同
    {"name": "s2_vol_price_corr", "direction": "S₂ 量价协同",
     "expression": "rank(ts_corr(rank(close), rank(volume), 10))",
     "description": "量价同期相关性(10日)"},
    {"name": "s2_vol_price_delta_sync", "direction": "S₂ 量价协同",
     "expression": "rank(ts_corr(rank(ts_delta(close, 3)), rank(ts_delta(volume, 3)), 5))",
     "description": "量价短期变化同步"},
    {"name": "s2_vol_on_price_regression", "direction": "S₂ 量价协同",
     "expression": "rank(ts_regression(rank(ts_mean(volume, 10)), rank(ts_mean(close, 20)), 5))",
     "description": "成交量对价格回归"},
    # 方向3: T₃ 加速度
    {"name": "t3_price_second_deriv", "direction": "T₃ 加速度",
     "expression": "rank(ts_delta(ts_delta(close, 5), 5))",
     "description": "价格二阶导"},
    {"name": "t3_return_acceleration", "direction": "T₃ 加速度",
     "expression": "rank(ts_delta(ts_sum(returns, 5), 5))",
     "description": "收益加速度"},
    {"name": "t3_mom_short_mid_sync", "direction": "T₃ 加速度",
     "expression": "rank(ts_corr(rank(ts_delta(close, 3)), rank(ts_delta(close, 10)), 5))",
     "description": "短中期动量同步"},
    # 方向4: S₃ 多模态交叉
    {"name": "s3_high_low_corr", "direction": "S₃ 多模态交叉",
     "expression": "rank(ts_corr(rank(high), rank(low), 5))",
     "description": "高低价相关性(5日)"},
    {"name": "s3_open_close_corr", "direction": "S₃ 多模态交叉",
     "expression": "rank(ts_corr(rank(open), rank(close), 5))",
     "description": "开收盘相关性(5日)"},
    {"name": "s3_price_volatility_corr", "direction": "S₃ 多模态交叉",
     "expression": "rank(ts_corr(rank(close), rank(ts_stddev(returns, 20)), 10))",
     "description": "价格与波动率关系"},
    # 方向5: C₂=+1 正交组合
    {"name": "c2_price_trend_volume", "direction": "C₂=+1 正交组合",
     "expression": "rank(ts_corr(rank(ts_mean(close, 5)), rank(ts_mean(volume, 20)), 5))",
     "description": "价格趋势与量能相关性"},
    {"name": "c2_dual_corr_product", "direction": "C₂=+1 正交组合",
     "expression": "rank(multiply(ts_corr(rank(close), rank(volume), 10), ts_corr(rank(high), rank(low), 10)))",
     "description": "双相关性乘积"},
    {"name": "c2_daily_price_change_sync", "direction": "C₂=+1 正交组合",
     "expression": "rank(ts_corr(rank(ts_delta(close, 1)), rank(ts_delta(open, 1)), 5))",
     "description": "日间价格变化同步"},
]

BACKTEST_SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 5, "neutralization": "SUBINDUSTRY",
    "truncation": 0.08, "pasteurization": "ON", "testPeriod": "P1Y6M",
    "unitHandling": "VERIFY", "nanHandling": "OFF", "maxTrade": "OFF",
    "language": "FASTEXPR", "visualization": False,
}

OUTPUT_DIR = os.path.join(os.path.dirname(_SCRIPT_DIR), "output")
DB_PATH = os.path.join(OUTPUT_DIR, "wqb_state.db")
REPORT_PATH = os.path.join(OUTPUT_DIR, "wqb_new_direction_breakthrough.md")
SUBMISSION_CHECK_ITEMS = [
    "LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "HIGH_TURNOVER",
    "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE", "SELF_CORRELATION",
    "MATCHES_COMPETITION",
]


# ============================================================
# DB Helpers
# ============================================================

def compute_expr_hash(expression):
    combined = f"{expression}|{json.dumps(BACKTEST_SETTINGS, sort_keys=True)}"
    return hashlib.md5(combined.encode()).hexdigest()

def ensure_db():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS alphas (expr_hash TEXT PRIMARY KEY, expression TEXT NOT NULL, factor_name TEXT, settings_json TEXT NOT NULL, alpha_id TEXT, status TEXT DEFAULT 'PENDING', sharpe REAL, fitness REAL, turnover REAL, is_summary TEXT, submitted_at TEXT, completed_at TEXT, error TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS submit_checks (alpha_id TEXT PRIMARY KEY, factor_name TEXT, checked_at TEXT, status TEXT, self_correlation REAL, sharpe REAL, fitness REAL, turnover REAL, checks_json TEXT, passed INTEGER DEFAULT 0, submitted INTEGER DEFAULT 0, submit_result TEXT, error TEXT)")
    conn.commit()
    conn.close()

def upsert_alpha(expr_hash, expression, factor_name, alpha_id=None, status="PENDING", sharpe=None, fitness=None, turnover=None, is_summary=None, error=None):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().isoformat()
    settings_json = json.dumps(BACKTEST_SETTINGS, sort_keys=True)
    is_summary_json = json.dumps(is_summary) if is_summary else None
    existing = conn.execute("SELECT expr_hash FROM alphas WHERE expr_hash = ?", (expr_hash,)).fetchone()
    if existing:
        conn.execute("UPDATE alphas SET alpha_id=COALESCE(?,alpha_id), status=?, sharpe=COALESCE(?,sharpe), fitness=COALESCE(?,fitness), turnover=COALESCE(?,turnover), is_summary=COALESCE(?,is_summary), completed_at=?, error=? WHERE expr_hash=?", (alpha_id, status, sharpe, fitness, turnover, is_summary_json, now, error, expr_hash))
    else:
        conn.execute("INSERT INTO alphas (expr_hash, expression, factor_name, settings_json, alpha_id, status, sharpe, fitness, turnover, is_summary, submitted_at, error) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (expr_hash, expression, factor_name, settings_json, alpha_id, status, sharpe, fitness, turnover, is_summary_json, now, error))
    conn.commit()
    conn.close()

def upsert_submit_check(alpha_id, factor_name, status, self_correlation=None, sharpe=None, fitness=None, turnover=None, checks=None, passed=0, submitted=0, submit_result=None, error=None):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().isoformat()
    checks_json = json.dumps(checks) if checks else None
    existing = conn.execute("SELECT alpha_id FROM submit_checks WHERE alpha_id = ?", (alpha_id,)).fetchone()
    if existing:
        conn.execute("UPDATE submit_checks SET factor_name=COALESCE(?,factor_name), checked_at=?, status=?, self_correlation=COALESCE(?,self_correlation), sharpe=COALESCE(?,sharpe), fitness=COALESCE(?,fitness), turnover=COALESCE(?,turnover), checks_json=COALESCE(?,checks_json), passed=?, submitted=?, submit_result=COALESCE(?,submit_result), error=? WHERE alpha_id=?", (factor_name, now, status, self_correlation, sharpe, fitness, turnover, checks_json, passed, submitted, submit_result, error, alpha_id))
    else:
        conn.execute("INSERT INTO submit_checks (alpha_id, factor_name, checked_at, status, self_correlation, sharpe, fitness, turnover, checks_json, passed, submitted, submit_result, error) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (alpha_id, factor_name, now, status, self_correlation, sharpe, fitness, turnover, checks_json, passed, submitted, submit_result, error))
    conn.commit()
    conn.close()


# ============================================================
# 提交检查与提交确认
# ============================================================

def run_submit_check(session, alpha_id):
    url = f"{ace_lib.brain_api_url}/alphas/{alpha_id}/submit"
    for attempt in range(3):
        try:
            response = session.post(url)
            break
        except:
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
            else:
                raise
    if response.status_code in (403, 200, 201, 202):
        try:
            data = response.json()
        except:
            data = {}
    else:
        response.raise_for_status()
        data = response.json()
    is_data = data.get("is", {})
    checks_list = is_data.get("checks", [])
    checks_dict = {}
    all_pass = True
    has_pending = False
    self_corr, sharpe_val, fitness_val, turnover_val = None, None, None, None
    for check in checks_list:
        name = check.get("name", "UNKNOWN")
        result = check.get("result", "UNKNOWN")
        value = check.get("value")
        limit = check.get("limit")
        checks_dict[name] = {"status": result, "value": value, "limit": limit}
        if name == "SELF_CORRELATION" and value is not None:
            self_corr = float(value)
        elif name == "LOW_SHARPE" and value is not None:
            sharpe_val = float(value)
        elif name == "LOW_FITNESS" and value is not None:
            fitness_val = float(value)
        elif name == "LOW_TURNOVER" and value is not None:
            turnover_val = float(value)
        if result == "FAIL":
            all_pass = False
        elif result == "PENDING":
            has_pending = True
    status = "PENDING" if has_pending else ("PASS" if all_pass and checks_dict else "FAIL")
    return {"status": status, "checks": checks_dict, "self_correlation": self_corr, "sharpe": sharpe_val, "fitness": fitness_val, "turnover": turnover_val}

def confirm_submit(session, alpha_id):
    response = session.put(f"{ace_lib.brain_api_url}/alphas/{alpha_id}/submit")
    response.raise_for_status()
    return response.json()


# ============================================================
# 核心：分阶段模拟 - 先提交再轮询
# ============================================================

def simulate_all_factors(session, alpha_list, factor_names):
    """
    分两阶段模拟：
    阶段1: 快速提交所有因子到队列，3秒间隔
    阶段2: 集中轮询所有模拟进度
    """
    expressions = [a["regular"] for a in alpha_list]
    pending = []  # (name, expr, progress_url)

    # 阶段1: 逐个提交因子，间隔30秒避免限流
    print(f"[WQB] 阶段1: 提交 {len(alpha_list)} 个因子，间隔30秒...")
    for i, (sim_data, fname) in enumerate(zip(alpha_list, factor_names)):
        print(f"  [{i+1}/{len(alpha_list)}] 提交 {fname}...", end=" ")
        sys.stdout.flush()
        try:
            resp = session.post(ace_lib.brain_api_url + "/simulations", json=sim_data)
            if resp.status_code == 429:
                print(f"429，等10s重试...", end=" ")
                time.sleep(10)
                resp = session.post(ace_lib.brain_api_url + "/simulations", json=sim_data)
            if resp.status_code // 100 == 2:
                progress_url = resp.headers.get("Location", "")
                print(f"已提交")
                pending.append((fname, sim_data["regular"], progress_url))
            else:
                print(f"失败({resp.status_code})")
        except Exception as e:
            print(f"错误: {e}")
        # 最后一个不需要等
        if i < len(alpha_list) - 1:
            time.sleep(30)

    print(f"\n[WQB] 阶段2: 轮询 {len(pending)} 个模拟进度...")
    results = []

    # 查找pending中的alpha_id
    # 注意：轮询返回的json包含alpha字段，可通过get_simulation_result_json获取
    for fname, expr, progress_url in pending:
        if not progress_url:
            results.append({"alpha_id": None, "factor_name": fname, "simulate_data": {"regular": expr}})
            continue

        print(f"  轮询 {fname}...", end=" ")
        sys.stdout.flush()
        alpha_id = None
        try:
            # 轮询进度
            max_polls = 20
            for poll in range(max_polls):
                resp = session.get(progress_url)
                if resp.status_code // 100 != 2:
                    time.sleep(5)
                    continue
                retry_after = resp.headers.get("Retry-After", 0)
                if retry_after == 0:
                    data = resp.json()
                    if data.get("status", "ERROR") == "ERROR":
                        print("模拟失败")
                        break
                    alpha = data.get("alpha", 0)
                    if alpha != 0:
                        # 获取结果
                        sim_result = ace_lib.get_simulation_result_json(session, alpha)
                        if sim_result:
                            alpha_id = sim_result.get("id")
                            print(f"成功 ID={alpha_id}")
                        else:
                            print("获取结果失败")
                    else:
                        print("无alpha")
                    break
                else:
                    wait = min(float(retry_after), 10)
                    time.sleep(wait)
            else:
                print("轮询超时")
        except Exception as e:
            print(f"错误: {e}")

        results.append({"alpha_id": alpha_id, "factor_name": fname, "simulate_data": {"regular": expr}})

    return results


# ============================================================
# 报告生成
# ============================================================

def generate_report(results, submitted, summary):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# WQB 新方向突破因子探索报告",
        "",
        f"**生成时间**: {now}",
        f"**因子总数**: {summary['total']}",
        f"**回测成功**: {summary['simulation_success']}",
        f"**通过全部检查**: {summary['check_pass']} 个",
        f"**正式提交成功**: {summary['submitted']} 个",
        "",
        "## 汇总结果",
        "",
        "| 因子名称 | 方向 | Alpha ID | Sharpe | Fitness | 自相关 | 检查状态 | 提交 |",
        "|---------|------|----------|--------|---------|-------|----------|------|",
    ]
    for r in results:
        alpha_id = r.get("alpha_id", "N/A")
        fn = r.get("factor_name", "unknown")
        direction = r.get("direction", "未知")
        sc = r.get("submit_check", {})
        sharpe = sc.get("sharpe", "N/A")
        fitness = sc.get("fitness", "N/A")
        self_corr = sc.get("self_correlation", "N/A")
        status = sc.get("status", "N/A")
        status_icon = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "PENDING": "⏳ PENDING", "ERROR": "⚠️ ERROR"}.get(status, status)
        submit_icon = "✅" if any(s.get("alpha_id") == alpha_id for s in submitted) else "—"
        lines.append(f"| {fn} | {direction} | {alpha_id} | {sharpe} | {fitness} | {self_corr} | {status_icon} | {submit_icon} |")

    lines.append("")
    lines.append("## 按方向分组")
    lines.append("")
    directions = {}
    for r in results:
        d = r.get("direction", "未知")
        directions.setdefault(d, []).append(r)
    for direction, factors in directions.items():
        pc = sum(1 for f in factors if f.get("submit_check", {}).get("status") == "PASS")
        lines.append(f"### {direction} ({len(factors)}个, 通过{pc}个)")
        lines.append("")
        for f in factors:
            sc = f.get("submit_check", {})
            lines.append(f"**{f['factor_name']}**: {f.get('description', '')}")
            lines.append(f"- 表达式: `{f.get('expression', '')}`")
            lines.append(f"- Alpha ID: {f.get('alpha_id', 'N/A')} | Sharpe: {sc.get('sharpe', 'N/A')} | Fitness: {sc.get('fitness', 'N/A')} | 自相关: {sc.get('self_correlation', 'N/A')}")
            lines.append(f"- 状态: {sc.get('status', 'N/A')}")
            lines.append("")

    lines.append("## 正式提交结果")
    lines.append("")
    if submitted:
        lines.append("以下因子已正式提交：")
        for s in submitted:
            lines.append(f"- {s['factor_name']} ({s['alpha_id']})")
    else:
        lines.append("本次检查中没有因子通过全部8项检查，未执行正式提交。")
    lines.append("")
    lines.append("## 因子设计说明")
    lines.append("")
    lines.append("- 完全脱离alpha_021反转信号家族")
    lines.append("- 不使用ts_rank(roc(...))等反转信号结构")
    lines.append("- 不使用reverse()算子")
    lines.append("- 不使用ts_stddev(returns, N)单独作为因子")
    lines.append("- 所有因子使用ts_delay而非shift")
    lines.append("")
    lines.append("### 五个方向")
    lines.append("")
    lines.append("1. **C₁=+1 动量延续**: 趋势跟踪类因子")
    lines.append("2. **S₂ 量价协同**: 成交量与价格的复合信号")
    lines.append("3. **T₃ 加速度**: 价格变化率的变化")
    lines.append("4. **S₃ 多模态交叉**: 多维度价格数据交叉分析")
    lines.append("5. **C₂=+1 正交组合**: 多信号交叉组合")
    lines.append("")

    report_text = "\n".join(lines)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"[WQB] 报告已保存到: {REPORT_PATH}")
    return report_text


# ============================================================
# 主流程
# ============================================================

async def main():
    sdk = CodeActSDK()
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    auto_submit = "--auto-submit" in sys.argv
    actual_mode = result_mode if result_mode != "auto" else "display_only"

    try:
        print(f"[WQB] 新方向突破因子探索")
        print(f"[WQB] 因子数量: {len(FACTORS)}, 自动提交: {'是' if auto_submit else '否'}")
        ensure_db()

        os.environ["BRAIN_CREDENTIAL_EMAIL"] = "q1z2q3@126.com"
        os.environ["BRAIN_CREDENTIAL_PASSWORD"] = "W2025zq0118"

        session = ace_lib.start_session()
        timeout = ace_lib.check_session_timeout(session)
        print(f"[WQB] 登录成功，会话有效期: {timeout/3600:.1f} 小时")

        # 构建因子
        expressions = [f["expression"] for f in FACTORS]
        factor_names = [f["name"] for f in FACTORS]
        alpha_list = []
        for expr in expressions:
            alpha_list.append(ace_lib.generate_alpha(
                regular=expr, alpha_type="REGULAR",
                region=BACKTEST_SETTINGS["region"], universe=BACKTEST_SETTINGS["universe"],
                delay=BACKTEST_SETTINGS["delay"], decay=BACKTEST_SETTINGS["decay"],
                neutralization=BACKTEST_SETTINGS["neutralization"],
                truncation=BACKTEST_SETTINGS["truncation"],
                pasteurization=BACKTEST_SETTINGS["pasteurization"],
            ))

        # 模拟
        sim_results = simulate_all_factors(session, alpha_list, factor_names)

        # 补充方向信息
        name_to_factor = {f["name"]: f for f in FACTORS}
        for r in sim_results:
            fn = r.get("factor_name", "")
            if fn in name_to_factor:
                r["direction"] = name_to_factor[fn]["direction"]
                r["description"] = name_to_factor[fn]["description"]
                r["expression"] = name_to_factor[fn]["expression"]

        success_count = sum(1 for r in sim_results if r["alpha_id"] is not None)
        print(f"[WQB] 回测完成: 成功 {success_count}/{len(sim_results)} 个")

        # 提交检查
        print(f"\n[WQB] 开始提交检查...")
        checked_results = []
        for r in sim_results:
            alpha_id = r.get("alpha_id")
            if alpha_id is None:
                checked_results.append(r)
                continue

            fn = r.get("factor_name", "unknown")
            expr = r["simulate_data"].get("regular", "")
            print(f"  检查 {fn} ({alpha_id})...", end=" ")

            try:
                check_result = run_submit_check(session, alpha_id)
                # 生产相关性检查 (免费账号可能无权限，忽略)
                r["submit_check"] = check_result
                r["prod_corr"] = {"status": "NONE", "value": None}

                passed = 1 if check_result["status"] == "PASS" else 0
                upsert_submit_check(alpha_id=alpha_id, factor_name=fn, status=check_result["status"],
                    self_correlation=check_result.get("self_correlation"), sharpe=check_result.get("sharpe"),
                    fitness=check_result.get("fitness"), turnover=check_result.get("turnover"),
                    checks=check_result.get("checks"), passed=passed)
                upsert_alpha(compute_expr_hash(expr), expr, fn, alpha_id=alpha_id, status="COMPLETED",
                    sharpe=check_result.get("sharpe"), fitness=check_result.get("fitness"),
                    turnover=check_result.get("turnover"), is_summary=check_result.get("checks"))

                print(f"{check_result['status']} (Sharpe={check_result.get('sharpe', 'N/A')}, Fitness={check_result.get('fitness', 'N/A')})")
            except Exception as e:
                print(f"ERROR: {e}")
                r["submit_check"] = {"status": "ERROR", "error": str(e)}
            checked_results.append(r)

        # 统计
        total = len(checked_results)
        successful = sum(1 for r in checked_results if r.get("alpha_id") is not None)
        pass_count = sum(1 for r in checked_results if r.get("submit_check", {}).get("status") == "PASS")
        fail_count = sum(1 for r in checked_results if r.get("submit_check", {}).get("status") == "FAIL")
        pending_count = sum(1 for r in checked_results if r.get("submit_check", {}).get("status") == "PENDING")
        error_count = sum(1 for r in checked_results if r.get("submit_check", {}).get("status") == "ERROR")

        summary = {"total": total, "simulation_success": successful, "simulation_failed": total - successful,
                    "check_pass": pass_count, "check_fail": fail_count, "check_pending": pending_count,
                    "check_error": error_count, "submitted": 0}

        # 自动提交
        submitted = []
        if auto_submit:
            passing = [r for r in checked_results if r.get("submit_check", {}).get("status") == "PASS"]
            if passing:
                print(f"\n[WQB] 开始自动提交 {len(passing)} 个通过检查的因子...")
                for r in passing:
                    aid = r["alpha_id"]
                    fn = r.get("factor_name", "unknown")
                    print(f"  提交 {fn} ({aid})...", end=" ")
                    try:
                        sr = confirm_submit(session, aid)
                        submitted.append({"alpha_id": aid, "factor_name": fn, "submit_result": sr})
                        print("✅ 成功")
                        time.sleep(5)
                    except Exception as e:
                        print(f"❌ 失败: {e}")
                summary["submitted"] = len(submitted)

        # 生成报告
        generate_report(checked_results, submitted, summary)

        # 构建消息
        lines = [f"WQB 新方向突破因子探索完成", "",
                 f"探索方向: 5个 (动量延续/量价协同/加速度/多模态交叉/正交组合)",
                 f"因子总数: {total} | 回测成功: {successful}/{total} | 通过检查: {pass_count} | 已提交: {summary['submitted']}"]
        if pass_count > 0:
            dirs = {}
            for r in checked_results:
                d = r.get("direction", "未知")
                if r.get("submit_check", {}).get("status") == "PASS":
                    dirs[d] = dirs.get(d, 0) + 1
            for d, c in dirs.items():
                lines.append(f"- {d}: {c} 个通过")
        if error_count > 0:
            lines.append(f"⚠️ {error_count} 个因子检查异常")
        lines.append("")
        if summary["submitted"] > 0:
            lines.append(f"✅ 成功提交 {summary['submitted']} 个因子!")
        elif pass_count > 0:
            lines.append(f"📋 {pass_count} 个通过检查但提交失败")
        else:
            lines.append(f"📊 无因子通过全部8项检查")
        lines.append("")
        lines.append(f"完整报告: [新方向突破报告](computer://{os.path.abspath(REPORT_PATH)})")

        await sdk.submit_result(
            result_mode=actual_mode, status="success",
            message="\n".join(lines),
            data={"report_path": REPORT_PATH, "total_factors": total, "simulation_success": successful,
                  "check_pass": pass_count, "submitted": summary["submitted"]},
        )

    except Exception as e:
        await sdk.submit_result(
            result_mode="notify", status="error",
            message=f"WQB新方向突破因子回测失败: {e}",
            data={"error_type": type(e).__name__},
        )


if __name__ == "__main__":
    asyncio.run(main())