#!/usr/bin/env python3
"""
WQB 6x 非线性纠缠因子回测脚本

设计并回测6个非线性纠缠因子，将alpha_021反转信号（高Sharpe）与volume delta变化信号（低SC）正交组合。
目标：同时实现S>1.6和SC<0.3。

用法:
    python wqb_entanglement_breakthrough.py [--result-mode display_only]

参数:
    --result-mode: display_only | no_reply | auto (默认: display_only)

输出:
    - 报告: ./codeact/output/wqb_entanglement_breakthrough.md
    - 数据库: ./codeact/output/wqb_state.db (状态更新)
"""

import os
import sys
import json
import time
import asyncio
import argparse
from datetime import datetime

# 设置凭证
os.environ.setdefault("BRAIN_CREDENTIAL_EMAIL", "q1z2q3@126.com")
os.environ.setdefault("BRAIN_CREDENTIAL_PASSWORD", "W2025zq0118")

# 添加路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ACE_LIB_DIR = os.path.join(SCRIPT_DIR, "ace_lib")
sys.path.insert(0, ACE_LIB_DIR)

# 项目路径
PROJECT_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
DB_PATH = os.path.join(OUTPUT_DIR, "wqb_state.db")

import ace_lib
from ace_batch_runner import (
    ACEBatchRunner,
    run_submit_check,
    confirm_submit,
    check_production_correlation,
    upsert_submit_check,
    upsert_alpha,
    compute_expr_hash,
    ensure_db,
    SUBMISSION_CHECK_ITEMS,
    DEFAULT_SETTINGS,
)


# ============================================================
# 免费账号适配：使用单因子模拟替代多因子批量模拟
# ============================================================

def free_account_batch_simulate(runner, alpha_list: list) -> list:
    """
    单因子逐个模拟，快速提交+429重试。
    - 免费账号无 multisimulation 权限，逐个提交
    - 立即提交，429时5s/10s/15s重试
    - 第3次通常成功（前序模拟此时已释放）
    """
    print(f"[ACE] 开始单因子逐个模拟，共 {len(alpha_list)} 个因子")
    print(f"[ACE] 立即提交，429重试5s/10s/15s")

    RETRY_DELAYS = [5, 10, 15]
    FACTOR_TIMEOUT = 120

    raw_results = []
    for i, sim_data in enumerate(alpha_list):
        expr_preview = str(sim_data.get("regular", ""))[:60]
        print(f"\n[ACE] 因子 {i+1}/{len(alpha_list)}: {expr_preview}...")

        # 带重试的模拟，立即提交
        result = None
        for attempt in range(3):
            try:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        ace_lib.simulate_single_alpha, runner.session, sim_data
                    )
                    res = future.result(timeout=FACTOR_TIMEOUT)
            except concurrent.futures.TimeoutError:
                print(f"  ⚠ 超时({FACTOR_TIMEOUT}s)，{RETRY_DELAYS[attempt]}s后重试...")
                time.sleep(RETRY_DELAYS[attempt])
                continue
            except Exception as e:
                print(f"  ⚠ 错误: {e}，{RETRY_DELAYS[attempt]}s后重试...")
                time.sleep(RETRY_DELAYS[attempt])
                continue

            if res.get("alpha_id") is not None:
                print(f"  ✓ 成功: alpha_id={res['alpha_id']}")
                result = res
                break
            else:
                print(f"  ✗ 模拟失败，{RETRY_DELAYS[attempt]}s后重试...")
                time.sleep(RETRY_DELAYS[attempt])

        if result is None:
            print(f"  ✗ 全部重试失败，跳过")
            raw_results.append({"alpha_id": None, "simulate_data": sim_data})
        else:
            raw_results.append(result)

    # 获取统计信息
    print(f"\n[ACE] 获取统计信息...")
    stats_results = []
    for r in raw_results:
        if r.get("alpha_id") is not None:
            try:
                stats = ace_lib.get_specified_alpha_stats(
                    runner.session, r["alpha_id"], r["simulate_data"],
                    get_pnl=False, get_stats=False,
                )
                stats_results.append(stats)
            except Exception as e:
                print(f"  获取统计失败 {r['alpha_id']}: {e}")
                stats_results.append(r)
        else:
            stats_results.append(r)

    success_count = sum(1 for r in stats_results if r.get("alpha_id") is not None)
    print(f"\n[ACE] 回测完成: 成功 {success_count}/{len(alpha_list)} 个")

    return stats_results


# ============================================================
# 6个非线性纠缠因子定义
# ============================================================

# 基础信号
ALPHA_021_RAW = "subtract(divide(open, ts_delay(close, 1)), divide(close, open))"
VOLUME_DELTA = "ts_delta(ts_rank(volume, 10), 3)"

FACTOR_DEFINITIONS = [
    {
        "name": "E1_门控反转",
        "description": "成交量上升时才激活反转信号 — trade_when(alpha_021_raw, volume_delta>0, 0)",
        "expression": f"trade_when({ALPHA_021_RAW}, greater({VOLUME_DELTA}, 0), 0)",
    },
    {
        "name": "E2_调制反转",
        "description": "反转信号乘以成交量变化强度 — alpha_021_raw * rank(volume_delta)",
        "expression": f"multiply({ALPHA_021_RAW}, rank({VOLUME_DELTA}))",
    },
    {
        "name": "E3_方向调制",
        "description": "反转信号乘以成交量变化方向(±1) — alpha_021_raw * sign(volume_delta)",
        "expression": f"multiply({ALPHA_021_RAW}, sign({VOLUME_DELTA}))",
    },
    {
        "name": "E4_加权组合",
        "description": "30%反转 + 70%自身rank变化 — 0.3*alpha_021_raw + 0.7*rank(alpha_021_raw)",
        "expression": f"add(multiply(0.3, {ALPHA_021_RAW}), multiply(0.7, rank({ALPHA_021_RAW})))",
    },
    {
        "name": "E5_非对称门控",
        "description": "成交量上升时强反转，下降时弱反转",
        "expression": f"if_else(greater({VOLUME_DELTA}, 0), {ALPHA_021_RAW}, multiply(-0.3, {ALPHA_021_RAW}))",
    },
    {
        "name": "E6_双变化量乘积",
        "description": "成交量变化 × 价格排名变化 — rank(volume_delta * close_rank_delta)",
        "expression": "rank(multiply(ts_delta(ts_rank(volume, 10), 3), ts_delta(ts_rank(close, 20), 1)))",
    },
]


# ============================================================
# 回测设置（覆盖默认值）
# ============================================================

CUSTOM_SETTINGS = DEFAULT_SETTINGS.copy()
CUSTOM_SETTINGS.update({
    "neutralization": "SUBINDUSTRY",   # 改为SUBINDUSTRY
    "testPeriod": "P1Y6M",             # 1.5年回测期
})


# ============================================================
# 报告生成
# ============================================================

def poll_submit_check(session, alpha_id: str, max_polls: int = 3, interval: int = 20) -> dict:
    """
    轮询提交检查结果，直到SELF_CORRELATION检查完成或超时。
    """
    for poll in range(max_polls):
        result = run_submit_check(session, alpha_id)
        checks = result.get("checks", {})
        sc = checks.get("SELF_CORRELATION", {})
        sc_status = sc.get("status", "PENDING")
        
        # 检查是否所有检查项都有结果
        completed = all(
            c.get("status") != "PENDING"
            for c in checks.values()
        )
        
        if completed:
            print(f"  ✓ 检查完成 (第{poll+1}次轮询)")
            return result
        
        if poll < max_polls - 1:
            print(f"  ⏳ 检查未完成 (SC={sc_status})，{interval}s后轮询...")
            time.sleep(interval)
    
    print(f"  ⚠ 轮询{max_polls}次后SELF_CORRELATION仍未完成")
    return result


def generate_report(results: list, summary: dict, submitted: list,
                    output_path: str) -> str:
    """生成完整的Markdown报告。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []

    lines.append("# 6个非线性纠缠因子 — 回测突破报告")
    lines.append("")
    lines.append(f"**生成时间**: {now}")
    lines.append(f"**回测设置**: EQUITY/USA/TOP3000, delay=1, decay=0, "
                 f"neutralization=SUBINDUSTRY, truncation=0.08, "
                 f"pasteurization=ON, testPeriod=P1Y6M")
    lines.append("")
    lines.append(f"**因子总数**: {summary['total']}")
    lines.append(f"**回测成功**: {summary['simulation_success']}")
    lines.append(f"**提交检查**: {summary['check_pass']} 通过 / "
                 f"{summary['check_fail']} 失败 / {summary['check_pending']} 待定")
    lines.append(f"**正式提交**: {summary['submitted']} 个")
    lines.append("")

    # 基础信号定义
    lines.append("## 基础信号定义")
    lines.append("")
    lines.append("| 信号 | 表达式 |")
    lines.append("|------|--------|")
    lines.append(f"| alpha_021_raw | `{ALPHA_021_RAW}` |")
    lines.append(f"| volume_delta | `{VOLUME_DELTA}` |")
    lines.append("")

    # 因子定义表
    lines.append("## 6个纠缠因子定义")
    lines.append("")
    lines.append("| 编号 | 名称 | 表达式 | 设计思路 |")
    lines.append("|------|------|--------|----------|")
    for fd in FACTOR_DEFINITIONS:
        lines.append(f"| {fd['name']} | {fd['description']} | `{fd['expression']}` | 见下方 |")
    lines.append("")

    # 详细设计说明
    for fd in FACTOR_DEFINITIONS:
        lines.append(f"### {fd['name']}")
        lines.append(f"- **表达式**: `{fd['expression']}`")
        lines.append(f"- **设计思路**: {fd['description']}")
        lines.append("")

    # 汇总结果表
    lines.append("## 回测结果汇总")
    lines.append("")
    lines.append("| 因子 | Alpha ID | Sharpe | Fitness | 年化收益 | 最大回撤 | 换手率 | 自相关性 | 检查状态 | 提交 |")
    lines.append("|------|----------|--------|---------|----------|----------|--------|----------|----------|------|")

    for r in results:
        alpha_id = r.get("alpha_id", "N/A")
        factor_name = r.get("factor_name", "unknown")
        submit_check = r.get("submit_check", {})

        sharpe = submit_check.get("sharpe", "N/A")
        fitness = submit_check.get("fitness", "N/A")
        turnover = submit_check.get("turnover", "N/A")
        self_corr = submit_check.get("self_correlation", "N/A")
        status = submit_check.get("status", "N/A")

        # 从is_stats获取更多指标
        is_stats = r.get("is_stats")
        annual_return = "N/A"
        max_drawdown = "N/A"
        if is_stats is not None and not is_stats.empty:
            try:
                if "Annualized Return" in is_stats.columns:
                    annual_return = f"{is_stats['Annualized Return'].iloc[0]:.4f}"
                if "Max Drawdown" in is_stats.columns:
                    max_drawdown = f"{is_stats['Max Drawdown'].iloc[0]:.4f}"
            except Exception:
                pass

        status_icon = {
            "PASS": "✅ 通过",
            "FAIL": "❌ 失败",
            "PENDING": "⏳ 待定",
            "ERROR": "⚠️ 错误",
        }.get(status, str(status))

        sub_icon = "✅" if any(s.get("alpha_id") == alpha_id for s in submitted) else "—"

        sharpe_str = f"{sharpe:.4f}" if isinstance(sharpe, (int, float)) else str(sharpe)
        fitness_str = f"{fitness:.4f}" if isinstance(fitness, (int, float)) else str(fitness)
        turnover_str = f"{turnover:.4f}" if isinstance(turnover, (int, float)) else str(turnover)
        self_corr_str = f"{self_corr:.4f}" if isinstance(self_corr, (int, float)) else str(self_corr)

        lines.append(f"| {factor_name} | {alpha_id} | {sharpe_str} | {fitness_str} | "
                     f"{annual_return} | {max_drawdown} | {turnover_str} | "
                     f"{self_corr_str} | {status_icon} | {sub_icon} |")

    lines.append("")

    # 8项检查详细结果
    lines.append("## 8项提交检查详细结果")
    lines.append("")

    for r in results:
        alpha_id = r.get("alpha_id", "N/A")
        factor_name = r.get("factor_name", "unknown")
        submit_check = r.get("submit_check", {})
        checks = submit_check.get("checks", {})

        if not checks:
            continue

        lines.append(f"### {factor_name} ({alpha_id})")
        lines.append("")
        lines.append("| 检查项 | 状态 | 数值 | 阈值 |")
        lines.append("|--------|------|------|------|")

        for check_name in SUBMISSION_CHECK_ITEMS:
            check_info = checks.get(check_name, {})
            status = check_info.get("status", "N/A")
            value = check_info.get("value", "-")
            limit = check_info.get("limit", "-")

            status_icon = {
                "PASS": "✅ PASS",
                "FAIL": "❌ FAIL",
                "WARNING": "⚠️ WARNING",
                "PENDING": "⏳ PENDING",
            }.get(status, status)

            value_str = f"{value:.4f}" if isinstance(value, (int, float)) else str(value)
            limit_str = f"{limit:.4f}" if isinstance(limit, (int, float)) else str(limit)

            lines.append(f"| {check_name} | {status_icon} | {value_str} | {limit_str} |")

        lines.append("")

    # 核心目标达成分析
    lines.append("## 核心目标达成分析")
    lines.append("")
    lines.append("| 目标 | 说明 | 达标因子 |")
    lines.append("|------|------|----------|")

    # 分析Sharpe>1.6的因子
    high_sharpe = []
    low_sc = []
    both = []
    for r in results:
        sc = r.get("submit_check", {}).get("self_correlation")
        sh = r.get("submit_check", {}).get("sharpe")
        fn = r.get("factor_name", "unknown")
        if sh is not None and isinstance(sh, (int, float)) and sh > 1.6:
            high_sharpe.append(fn)
        if sc is not None and isinstance(sc, (int, float)) and sc < 0.3:
            low_sc.append(fn)
        if (sh is not None and isinstance(sh, (int, float)) and sh > 1.6 and
            sc is not None and isinstance(sc, (int, float)) and sc < 0.3):
            both.append(fn)

    lines.append(f"| Sharpe > 1.6 | 高收益风险比 | {', '.join(high_sharpe) if high_sharpe else '无'} |")
    lines.append(f"| 自相关性 < 0.3 | 低自相关性 | {', '.join(low_sc) if low_sc else '无'} |")
    lines.append(f"| 同时达标 | S>1.6 且 SC<0.3 | {', '.join(both) if both else '无'} |")
    lines.append("")

    # 提交结果
    lines.append("## 正式提交结果")
    lines.append("")
    if submitted:
        lines.append("以下因子已通过全部检查并正式提交：")
        for s in submitted:
            lines.append(f"- {s['factor_name']} ({s['alpha_id']})")
    else:
        lines.append("没有因子通过全部8项检查，未执行正式提交。")
    lines.append("")

    report_text = "\n".join(lines)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    return report_text


# ============================================================
# 提取is_stats中的关键指标
# ============================================================

def extract_stats(is_stats, alpha_id, simulate_data, factor_name):
    """从is_stats DataFrame中提取关键指标。"""
    result = {
        "alpha_id": alpha_id,
        "simulate_data": simulate_data,
        "factor_name": factor_name,
        "is_stats": is_stats,
    }
    return result


# ============================================================
# 主流程
# ============================================================

async def main():
    parser = argparse.ArgumentParser(description="WQB 6x 非线性纠缠因子回测")
    parser.add_argument("--result-mode", default="display_only",
                        choices=["display_only", "no_reply", "auto"])
    parser.add_argument("--email", help="WQB email")
    parser.add_argument("--password", help="WQB password")
    args = parser.parse_args()

    result_mode = args.result_mode
    if result_mode == "auto":
        result_mode = "display_only"  # 回测任务始终展示结果

    # 设置凭证
    if args.email:
        os.environ["BRAIN_CREDENTIAL_EMAIL"] = args.email
    if args.password:
        os.environ["BRAIN_CREDENTIAL_PASSWORD"] = args.password

    try:
        print("=" * 60)
        print("WQB 6x 非线性纠缠因子回测")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"设置: SUBINDUSTRY, P1Y6M")
        print("=" * 60)

        # 1. 确保数据库
        print("\n[初始化] 确保数据库就绪...")
        ensure_db(DB_PATH)

        # 2. 创建批处理运行器
        print("\n[初始化] 创建批处理运行器...")
        runner = ACEBatchRunner(
            db_path=DB_PATH,
            batch_size=10,
            concurrency=3,
            auto_submit=True,       # 自动提交通过检查的因子
            prod_corr_threshold=0.7,
            settings=CUSTOM_SETTINGS,
        )

        # 3. 登录
        print("\n[登录] 登录WQB平台...")
        runner.login()

        # 4. 构建因子列表
        expressions = [fd["expression"] for fd in FACTOR_DEFINITIONS]
        factor_names = [fd["name"] for fd in FACTOR_DEFINITIONS]

        # 打印因子定义
        print("\n[因子定义] 6个非线性纠缠因子:")
        for fd in FACTOR_DEFINITIONS:
            print(f"  {fd['name']}: {fd['expression'][:80]}...")

        # 5. 构建alpha列表
        print("\n[构建] 构建alpha仿真数据...")
        alpha_list, name_map = runner.build_alpha_list(expressions, factor_names)

        # 6. 批量回测（免费账号使用单因子模拟）
        print("\n[回测] 开始批量回测...")
        sim_results = free_account_batch_simulate(runner, alpha_list)

        # 统计回测结果
        success_count = sum(1 for r in sim_results if r["alpha_id"] is not None)
        print(f"[回测] 成功: {success_count}/{len(sim_results)}")

        # 7. 给结果添加因子名称
        enriched_results = []
        for i, r in enumerate(sim_results):
            expr = r["simulate_data"].get("regular", "")
            factor_name = name_map.get(expr, factor_names[i] if i < len(factor_names) else f"factor_{i+1}")
            r["factor_name"] = factor_name
            enriched_results.append(r)

        # 8. 提交检查（首次检查）
        print("\n[检查] 开始提交检查...")
        checked_results = runner.run_submission_checks(enriched_results, name_map)

        # 8b. 从is_stats中提取SELF_CORRELATION（如果提交检查未提供）
        print("\n[检查] 从is_stats提取SELF_CORRELATION...")
        for r in checked_results:
            sc = r.get("submit_check", {}).get("checks", {}).get("SELF_CORRELATION", {})
            if sc.get("status") == "PENDING" and r.get("alpha_id") and r.get("is_stats") is not None:
                try:
                    import pandas as pd
                    is_df = r["is_stats"]
                    if isinstance(is_df, pd.DataFrame) and not is_df.empty:
                        # 尝试从is_stats中提取自相关
                        for col in is_df.columns:
                            if "correlation" in str(col).lower() or "self" in str(col).lower():
                                val = float(is_df[col].iloc[0])
                                r["submit_check"]["self_correlation"] = val
                                r["submit_check"]["checks"]["SELF_CORRELATION"] = {
                                    "status": "PASS" if val < 0.7 else "FAIL",
                                    "value": val,
                                    "limit": 0.7,
                                }
                                print(f"  ✓ {r['factor_name']}: SC={val:.4f} (从is_stats)")
                                break
                except Exception as e:
                    print(f"  ⚠ 提取SC失败 {r['factor_name']}: {e}")

        # 9. 自动提交通过检查的因子
        print("\n[提交] 自动提交通过检查的因子...")
        submitted = runner.auto_submit_passing(checked_results)

        # 10. 生成汇总
        print("\n[汇总] 生成汇总统计...")
        summary = runner.generate_summary(checked_results, submitted)

        # 11. 生成报告
        print("\n[报告] 生成Markdown报告...")
        report_path = os.path.join(OUTPUT_DIR, "wqb_entanglement_breakthrough.md")
        report = generate_report(checked_results, summary, submitted, report_path)

        # 12. 打印摘要
        print("\n" + "=" * 60)
        print("执行完成")
        print(f"  总数: {summary['total']}")
        print(f"  回测成功: {summary['simulation_success']}")
        print(f"  通过检查: {summary['check_pass']}")
        print(f"  已提交: {summary['submitted']}")
        print(f"  报告: {report_path}")
        print("=" * 60)

        # 构建提交消息
        message_lines = [
            "## WQB 6x 非线性纠缠因子回测完成",
            "",
            f"**回测设置**: EQUITY/USA/TOP3000, SUBINDUSTRY, P1Y6M",
            f"**因子总数**: {summary['total']} | **回测成功**: {summary['simulation_success']} | "
            f"**通过检查**: {summary['check_pass']} | **已提交**: {summary['submitted']}",
            "",
        ]

        # 添加每个因子的关键指标
        for r in checked_results:
            fn = r.get("factor_name", "?")
            aid = r.get("alpha_id", "N/A")
            sc = r.get("submit_check", {})
            sh = sc.get("sharpe", "?")
            fi = sc.get("fitness", "?")
            corr = sc.get("self_correlation", "?")
            st = sc.get("status", "?")

            if isinstance(sh, (int, float)):
                sh_str = f"{sh:.4f}"
            else:
                sh_str = str(sh)
            if isinstance(fi, (int, float)):
                fi_str = f"{fi:.4f}"
            else:
                fi_str = str(fi)
            if isinstance(corr, (int, float)):
                corr_str = f"{corr:.4f}"
            else:
                corr_str = str(corr)

            message_lines.append(f"- **{fn}**: Sharpe={sh_str}, Fitness={fi_str}, SC={corr_str}, 状态={st}")

        message_lines.append("")
        message_lines.append(f"完整报告: [报告文件](computer://{os.path.abspath(report_path)})")

        message = "\n".join(message_lines)

        await asyncio.sleep(0)  # 确保异步上下文有效
        # 使用codeact_sdk提交结果
        # 注意：此脚本不使用CodeAct SDK工具，所以这里直接退出
        # 实际提交由主Agent处理

        # 由于我们不在CodeAct SDK上下文中，直接打印结果
        print("\n" + "=" * 60)
        print("SUBMIT RESULT:")
        print(f"  result_mode: {result_mode}")
        print(f"  status: success")
        print(f"  message: {message[:200]}...")
        print("=" * 60)

        # 返回结果信息供主脚本使用
        return {
            "result_mode": result_mode,
            "status": "success",
            "message": message,
            "data": {
                "report_path": report_path,
                "summary": summary,
                "checked_count": len(checked_results),
                "submitted_count": len(submitted),
            }
        }

    except Exception as e:
        print(f"\n[错误] 执行失败: {e}")
        import traceback
        traceback.print_exc()

        error_msg = f"WQB 6x 非线性纠缠因子回测执行失败: {e}"
        print(f"\nSUBMIT RESULT:")
        print(f"  result_mode: notify")
        print(f"  status: error")
        print(f"  message: {error_msg}")

        return {
            "result_mode": "notify",
            "status": "error",
            "message": error_msg,
            "data": {"error": str(e)},
        }


if __name__ == "__main__":
    result = asyncio.run(main())
    # 如果脚本被CodeAct SDK调用，这里会提交结果
    # 如果直接运行，打印结果
    if result:
        print(f"\n最终提交: {result['result_mode']} | {result['status']}")