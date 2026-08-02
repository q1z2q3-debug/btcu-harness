#!/usr/bin/env python3
"""
WQB 第五批优化 + 提交检查脚本 - wqb_batch5_optimize_submit.py
============================================================

两大目标：
1. 提交已有的高潜力因子做提交检查（combo_raw_3f_w503020 等）
2. 设计并回测第五批跃迁因子，目标 Fitness ≥ 1.0

第五批优化方向（方向十二）：
  - 基于 combo_5f_weighted(Fit=0.93) 的深度优化
  - 加入更多多样化信号（Amihud非流动性、波动变化率等）
  - 尝试raw-signal组合模式（参考combo_raw_3f_w503020的成功模式）
  - 非线性组合（乘积、条件加权）

用法：
  python wqb_batch5_optimize_submit.py [mode]
  mode: all / backtest_only / check_only
"""

import asyncio
import sys
import os
import json
import time
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from codeact_sdk import CodeActSDK
from wqb_api_client import WQBApiClient, WQBSimulation, retry_with_backoff


# ============================================================
# 工具 Schema 版本常量
# ============================================================
TOOL_SCHEMA_VERSIONS = {
    "codeact_search_web": "v1_5ac1b0eba8c26f2a",
    "codeact_fetch_web": "v1_2c8d0580b3f93a58",
    "file_to_url": "v1_fe3416acf3d7b53b",
}

# 提交间隔（严格限流）
SUBMIT_INTERVAL = 55.0
# 检查轮询间隔
CHECK_POLL_INTERVAL = 15.0

# 合格阈值
SHARPE_THRESHOLD = 1.25
FITNESS_THRESHOLD = 1.0
TURNOVER_MIN = 0.01
TURNOVER_MAX = 0.7

# 状态库路径
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "output", "wqb_state.db")

# 默认回测设置
DEFAULT_SIM_SETTINGS = {
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 15,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "testPeriod": "P1Y6M",
}


# ============================================================
# 第五批因子（方向十二：冲击Fitness≥1.0 v2）
# ============================================================

BATCH5_FACTORS = {
    # ================================================================
    # 子方向A：raw-signal组合模式（参考combo_raw_3f_w503020的成功）
    # 特点：不单独rank每个因子，而是先加权求和再rank
    # ================================================================
    "rawcombo_4f_w40302010": {
        "category": "第五批-raw组合",
        "direction": "方向十二A：raw-signal四因子组合",
        "description": "四因子raw组合：oi_div(40%)+rev_vol(30%)+amihud(20%)+vsr(10%)",
        "logic": "raw信号加权求和后rank，减少rank损耗提高Fitness",
        "fastexpr": "rank(add(add(add(multiply(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 0.4), multiply(reverse(ts_std_dev(returns, 120)), 0.3)), multiply(reverse(ts_mean(divide(abs(returns), volume), 20)), 0.2)), multiply(reverse(divide(ts_delta(close, 1), ts_delay(close, 1))), 0.1)))",
        "version": "breakthrough_v5",
    },
    "rawcombo_5f_balanced": {
        "category": "第五批-raw组合",
        "direction": "方向十二A：raw-signal五因子组合",
        "description": "五因子raw平衡组合：oi_div+rev_vol+amihud+vsr+rev5d",
        "logic": "5个raw信号等权后rank，最大化分散化",
        "fastexpr": "rank(divide(add(add(add(add(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), reverse(ts_std_dev(returns, 120))), reverse(ts_mean(divide(abs(returns), volume), 20))), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))), reverse(divide(ts_delta(close, 5), ts_delay(close, 5)))), 5.0))",
        "version": "breakthrough_v5",
    },
    "rawcombo_oi_vsr_amihud": {
        "category": "第五批-raw组合",
        "direction": "方向十二A：raw-signal三因子",
        "description": "三因子raw：oi_div(50%)+vsr(30%)+amihud(20%)",
        "logic": "最强三因子raw组合，去掉慢变vol因子降低自相关",
        "fastexpr": "rank(add(add(multiply(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 0.5), multiply(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))), 0.3)), multiply(reverse(ts_mean(divide(abs(returns), volume), 20)), 0.2)))",
        "version": "breakthrough_v5",
    },

    # ================================================================
    # 子方向B：6-7因子加权组合（rank后组合）
    # 在combo_5f_weighted基础上加更多弱因子
    # ================================================================
    "combo_6f_weighted_v2": {
        "category": "第五批-多因子加权",
        "direction": "方向十二B：六因子加权组合",
        "description": "六因子加权：oi_div(28%)+vsr(22%)+ext_rev(18%)+low_vol(12%)+rev5d(10%)+amihud(10%)",
        "logic": "加入amihud非流动性因子，增加第六维度",
        "fastexpr": "add(multiply(0.28, rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5))), add(multiply(0.22, rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), add(multiply(0.18, rank(multiply(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), add(multiply(0.12, reverse(rank(ts_std_dev(returns, 20)))), add(multiply(0.1, rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 5), ts_delay(close, 5)))))), multiply(0.1, reverse(rank(ts_mean(divide(abs(returns), volume), 20)))))))))",
        "version": "breakthrough_v5",
    },
    "combo_7f_diverse_v2": {
        "category": "第五批-多因子加权",
        "direction": "方向十二B：七因子多样化",
        "description": "七因子多样化等权：7个不同逻辑因子",
        "logic": "极致分散化，7个不同逻辑维度",
        "fastexpr": "divide(add(add(add(add(add(add(rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5)), rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), rank(multiply(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), reverse(rank(ts_std_dev(returns, 20)))), rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 5), ts_delay(close, 5)))))), reverse(rank(ts_mean(divide(abs(returns), volume), 20)))), reverse(rank(ts_delta(ts_std_dev(returns, 20), 5))))), 7.0)",
        "version": "breakthrough_v5",
    },

    # ================================================================
    # 子方向C：权重微调（基于combo_5f_weighted的权重优化）
    # 提高强因子权重，降低弱因子权重
    # ================================================================
    "combo_5f_w35_30_20_10_5": {
        "category": "第五批-权重优化",
        "direction": "方向十二C：权重微调",
        "description": "五因子加权v2：oi_div(35%)+vsr(30%)+ext_rev(20%)+low_vol(10%)+rev5d(5%)",
        "logic": "提高最强两个因子权重，降低弱因子",
        "fastexpr": "add(multiply(0.35, rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5))), add(multiply(0.3, rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), add(multiply(0.2, rank(multiply(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), add(multiply(0.1, reverse(rank(ts_std_dev(returns, 20)))), multiply(0.05, rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 5), ts_delay(close, 5))))))))))",
        "version": "breakthrough_v5",
    },
    "combo_5f_w40_25_15_12_8": {
        "category": "第五批-权重优化",
        "direction": "方向十二C：权重微调",
        "description": "五因子加权v3：oi_div(40%)+vsr(25%)+ext_rev(15%)+low_vol(12%)+rev5d(8%)",
        "logic": "提高核心oi_div权重，调整其他因子比例",
        "fastexpr": "add(multiply(0.4, rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5))), add(multiply(0.25, rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), add(multiply(0.15, rank(multiply(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), add(multiply(0.12, reverse(rank(ts_std_dev(returns, 20)))), multiply(0.08, rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 5), ts_delay(close, 5))))))))))",
        "version": "breakthrough_v5",
    },

    # ================================================================
    # 子方向D：非线性组合（乘积增强）
    # 用乘积代替加法，放大强信号
    # ================================================================
    "combo_oi_vsr_multiply": {
        "category": "第五批-非线性",
        "direction": "方向十二D：非线性乘积组合",
        "description": "oi_div × vsr 乘积组合（非线性增强）",
        "logic": "两个因子都强时信号更强，非线性放大",
        "fastexpr": "rank(multiply(rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5)), rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1))))))))",
        "version": "breakthrough_v5",
    },

    # ================================================================
    # 子方向E：条件加权（波动率状态下的动态权重）
    # ================================================================
    "combo_cond_vol_regime": {
        "category": "第五批-条件组合",
        "direction": "方向十二E：波动率状态切换",
        "description": "高波动时偏反转，低波动时偏oi_div（状态切换）",
        "logic": "波动率状态自适应：高波动用反转，低波动用分化",
        "fastexpr": "if_else(greater(ts_std_dev(returns, 20), ts_mean(ts_std_dev(returns, 60), 20)), rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1))))), rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5)))",
        "version": "breakthrough_v5",
    },
}

# 已有的高潜力因子（用于提交检查）
# alpha_id从数据库读取
HIGH_POTENTIAL_NAMES = [
    "combo_raw_3f_w503020",   # Fit=1.05, Sharpe=1.45, Turn=0.307
    "combo_d10_vol60_w7525",   # Fit=1.28, Sharpe=1.96, Turn=0.398
    "combo_5f_weighted",       # Fit=0.93, Sharpe=1.43, Turn=0.363 (作为对照)
]


# ============================================================
# 数据库辅助函数
# ============================================================

def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_alpha_by_name(factor_name: str) -> Optional[dict]:
    """从数据库获取因子信息"""
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alphas WHERE factor_name = ?", (factor_name,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_submit_check(alpha_id: str, factor_name: str, checks_data: dict, passed: bool):
    """保存提交检查结果"""
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        checks_json = json.dumps(checks_data, ensure_ascii=False)
        sharpe = checks_data.get("is_sharpe")
        fitness = checks_data.get("is_fitness")
        turnover = checks_data.get("is_turnover")
        self_corr = None
        if "checks" in checks_data and isinstance(checks_data["checks"], dict):
            sc = checks_data["checks"].get("SELF_CORRELATION", {})
            if isinstance(sc, dict):
                self_corr = sc.get("value")

        cursor.execute("""
            INSERT OR REPLACE INTO submit_checks
            (alpha_id, factor_name, checked_at, status, self_correlation, 
             sharpe, fitness, turnover, checks_json, passed, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alpha_id, factor_name, now,
            checks_data.get("status", "COMPLETED"),
            self_corr,
            sharpe, fitness, turnover,
            checks_json,
            1 if passed else 0,
            None
        ))
        conn.commit()
    finally:
        conn.close()


def get_unchecked_candidates() -> List[dict]:
    """获取未检查的高潜力候选因子"""
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.factor_name, a.alpha_id, a.sharpe, a.fitness, a.turnover, a.category
            FROM alphas a
            LEFT JOIN submit_checks sc ON a.alpha_id = sc.alpha_id
            WHERE a.sharpe >= 1.25 
              AND a.fitness >= 0.9
              AND a.turnover BETWEEN 0.01 AND 0.7
              AND sc.alpha_id IS NULL
              AND a.alpha_id IS NOT NULL
            ORDER BY a.fitness DESC
            LIMIT 10
        """)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# ============================================================
# 提交检查相关函数
# ============================================================

def submit_alpha_for_check(client: WQBApiClient, alpha_id: str) -> Optional[str]:
    """提交Alpha进行检查"""
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/submit"
    try:
        @retry_with_backoff(max_retries=3, base_delay=10.0)
        def _do_submit():
            response = client._session.post(url)
            response.raise_for_status()
            return response.headers.get("Location")
        check_url = _do_submit()
        print(f"  [提交检查] {alpha_id} → {check_url}")
        return check_url
    except Exception as e:
        print(f"  [提交检查失败] {alpha_id}: {e}")
        return None


def poll_check_result(client: WQBApiClient, alpha_id: str, max_wait: float = 600.0) -> Optional[dict]:
    """轮询检查结果"""
    start = time.time()
    while time.time() - start < max_wait:
        try:
            alpha_data = client.get_alpha(alpha_id)
            stage = alpha_data.get("stage", "")
            is_data = alpha_data.get("is", {})
            
            result = {
                "stage": stage,
                "status": alpha_data.get("status", ""),
                "grade": alpha_data.get("grade", ""),
                "is_sharpe": is_data.get("sharpe"),
                "is_fitness": is_data.get("fitness"),
                "is_turnover": is_data.get("turnover"),
            }
            
            # 检查各项检查是否完成
            checks = alpha_data.get("checks", {})
            if checks:
                result["checks"] = checks
                # 判断是否所有检查都完成了
                all_done = True
                all_pass = True
                for check_name, check_info in checks.items():
                    if isinstance(check_info, dict):
                        status = check_info.get("status", "")
                        if status in ("PENDING", "RUNNING", "PROCESSING"):
                            all_done = False
                        elif status == "FAIL":
                            all_pass = False
                
                result["all_checks_done"] = all_done
                result["all_checks_pass"] = all_pass
                
                if all_done:
                    return result
            
            elapsed = time.time() - start
            if elapsed % 60 < CHECK_POLL_INTERVAL:
                print(f"  [等待检查] {alpha_id} stage={stage} 已等待{elapsed:.0f}s")
            
            time.sleep(CHECK_POLL_INTERVAL)
            
        except Exception as e:
            print(f"  [查询异常] {alpha_id}: {e}")
            time.sleep(CHECK_POLL_INTERVAL)
    
    return None


# ============================================================
# 回测相关函数
# ============================================================

async def batch_backtest(client: WQBApiClient, factors: dict) -> List[dict]:
    """批量回测因子"""
    results = []
    settings = DEFAULT_SIM_SETTINGS.copy()
    
    for i, (name, info) in enumerate(factors.items()):
        print(f"\n[{i+1}/{len(factors)}] 提交回测: {name}")
        print(f"  描述: {info.get('description', '')}")
        
        expr = info["fastexpr"]
        
        # 检查是否已有缓存
        cached = client.get_cached_alpha(expr, settings)
        if cached and cached.get("sharpe") is not None:
            print(f"  [缓存命中] Sharpe={cached['sharpe']:.3f}, Fit={cached.get('fitness', 0):.3f}")
            results.append({
                "name": name,
                "info": info,
                "sharpe": cached.get("sharpe"),
                "fitness": cached.get("fitness"),
                "turnover": cached.get("turnover"),
                "alpha_id": cached.get("alpha_id"),
                "from_cache": True,
            })
            continue
        
        # 提交新的回测
        try:
            sim = client.simulate(expr, settings)
            print(f"  [提交] progress_url: {sim.progress_url}")
            
            # 等待完成
            success = sim.wait(verbose=False, poll_interval=8.0)
            
            if success:
                metrics = sim.get_metrics()
                sharpe = metrics.get("sharpe", 0)
                fitness = metrics.get("fitness", 0)
                turnover = metrics.get("turnover", 0)
                
                print(f"  [完成] Sharpe={sharpe:.3f}, Fit={fitness:.3f}, Turn={turnover:.3f}")
                
                results.append({
                    "name": name,
                    "info": info,
                    "sharpe": sharpe,
                    "fitness": fitness,
                    "turnover": turnover,
                    "alpha_id": sim.alpha_id,
                    "from_cache": False,
                })
                
                # 保存到数据库
                client.save_alpha_result(
                    expression=expr,
                    settings=settings,
                    factor_name=name,
                    category=info.get("category", "第五批"),
                    alpha_id=sim.alpha_id,
                    sharpe=sharpe,
                    fitness=fitness,
                    turnover=turnover,
                    status="DONE",
                )
            else:
                print(f"  [失败] 回测未成功完成")
                results.append({
                    "name": name,
                    "info": info,
                    "error": "simulation failed",
                    "alpha_id": sim.alpha_id,
                })
                
        except Exception as e:
            print(f"  [异常] {e}")
            results.append({
                "name": name,
                "info": info,
                "error": str(e),
            })
        
        # 限流等待（最后一个不用等）
        if i < len(factors) - 1:
            print(f"  [限流等待] {SUBMIT_INTERVAL:.0f}秒...")
            await asyncio.sleep(SUBMIT_INTERVAL)
    
    return results


# ============================================================
# 主函数
# ============================================================

async def main():
    sdk = CodeActSDK()
    
    # 解析参数
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    result_mode = sys.argv[2] if len(sys.argv) > 2 else "display_only"
    
    print("=" * 70)
    print("WQB 第五批优化 + 提交检查")
    print(f"模式: {mode}")
    print(f"时间: {datetime.now().isoformat()}")
    print("=" * 70)
    
    # 登录WQB
    print("\n[1/4] 登录 WQB...")
    email = "q1z2q3@126.com"
    password = "W2025zq0118"
    
    try:
        client = WQBApiClient.login(email, password, db_path=DB_PATH)
        print(f"  登录成功，账号: {client.email}")
    except Exception as e:
        print(f"  登录失败: {e}")
        await sdk.submit_result(
            status="error",
            message=f"WQB登录失败: {e}",
            result_mode="notify",
        )
        return
    
    # ----------------------------------------------------------
    # 第一部分：提交检查
    # ----------------------------------------------------------
    if mode in ("all", "check_only"):
        print("\n[2/4] 获取待检查的高潜力因子...")
        candidates = get_unchecked_candidates()
        print(f"  找到 {len(candidates)} 个候选因子")
        
        for c in candidates[:5]:  # 最多检查5个
            print(f"    {c['factor_name']:<35} Sharpe={c['sharpe']:.3f} Fit={c['fitness']:.3f} Turn={c['turnover']:.3f}")
        
        check_results = []
        for i, c in enumerate(candidates[:5]):
            alpha_id = c["alpha_id"]
            name = c["factor_name"]
            print(f"\n  [{i+1}] 提交检查: {name} (ID: {alpha_id})")
            
            check_url = submit_alpha_for_check(client, alpha_id)
            if not check_url:
                print(f"    提交失败，跳过")
                continue
            
            print(f"    等待检查结果...")
            result = poll_check_result(client, alpha_id, max_wait=600.0)
            
            if result:
                passed = result.get("all_checks_pass", False)
                print(f"    检查完成! 全部通过: {passed}")
                
                if "checks" in result:
                    for check_name, check_info in result["checks"].items():
                        if isinstance(check_info, dict):
                            val = check_info.get("value", "N/A")
                            status = check_info.get("status", "")
                            print(f"      {check_name:<30} {status:<10} value={val}")
                
                save_submit_check(alpha_id, name, result, passed)
                check_results.append({
                    "name": name,
                    "alpha_id": alpha_id,
                    "passed": passed,
                    "result": result,
                })
            else:
                print(f"    检查超时或失败")
            
            # 检查之间的间隔
            if i < len(candidates[:5]) - 1:
                print(f"    [限流] 等待{SUBMIT_INTERVAL:.0f}秒...")
                await asyncio.sleep(SUBMIT_INTERVAL)
        
        # 检查是否有通过的
        passed_factors = [r for r in check_results if r["passed"]]
        print(f"\n  提交检查总结: {len(check_results)}个因子，{len(passed_factors)}个通过全部检查")
    
    # ----------------------------------------------------------
    # 第二部分：第五批因子回测
    # ----------------------------------------------------------
    if mode in ("all", "backtest_only"):
        print("\n[3/4] 第五批因子回测...")
        print(f"  共 {len(BATCH5_FACTORS)} 个因子")
        
        # 检查语法
        print("  语法检查（括号匹配）...")
        for name, info in BATCH5_FACTORS.items():
            expr = info["fastexpr"]
            open_count = expr.count("(")
            close_count = expr.count(")")
            if open_count != close_count:
                print(f"    [警告] {name}: 括号不匹配 ({open_count} vs {close_count})")
            else:
                print(f"    [OK] {name}")
        
        batch_results = await batch_backtest(client, BATCH5_FACTORS)
        
        # 打印总结
        print("\n" + "=" * 70)
        print("第五批因子回测结果（按Fitness排序）:")
        print("=" * 70)
        print(f"{'Name':<30} {'Sharpe':>7} {'Fit':>7} {'Turn':>8} {'Status':<10}")
        print("-" * 70)
        
        valid_results = [r for r in batch_results if r.get("sharpe") is not None]
        valid_results.sort(key=lambda x: x.get("fitness", 0), reverse=True)
        
        for r in valid_results:
            status = "✓" if r.get("fitness", 0) >= FITNESS_THRESHOLD and r.get("sharpe", 0) >= SHARPE_THRESHOLD else ""
            print(f"{r['name']:<30} {r['sharpe']:>7.3f} {r['fitness']:>7.3f} {r['turnover']:>8.3f} {status:<10}")
        
        # 找出合格因子
        qualified = [r for r in valid_results 
                    if r.get("fitness", 0) >= FITNESS_THRESHOLD 
                    and r.get("sharpe", 0) >= SHARPE_THRESHOLD
                    and TURNOVER_MIN <= r.get("turnover", 0) <= TURNOVER_MAX]
        
        print(f"\n合格因子 (Sharpe≥{SHARPE_THRESHOLD}, Fit≥{FITNESS_THRESHOLD}, 换手率0.01-0.7): {len(qualified)}")
        for r in qualified:
            print(f"  ✓ {r['name']}: Sharpe={r['sharpe']:.3f}, Fit={r['fitness']:.3f}")
    
    # ----------------------------------------------------------
    # 第三部分：最终总结
    # ----------------------------------------------------------
    print("\n[4/4] 生成总结...")
    
    # 读取所有跃迁因子做统计
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT factor_name, sharpe, fitness, turnover, category
            FROM alphas 
            WHERE category LIKE '%第五批%' OR category LIKE '%冲击Fitness%' 
               OR category LIKE '%Fitness优化%' OR category LIKE '%组合因子%'
               OR category LIKE '%隔夜日内%' OR category LIKE '%事件驱动%'
               OR category LIKE '%变化率%' OR category LIKE '%排名%'
               OR category LIKE '%非线性%' OR category LIKE '%反转%'
               OR category LIKE '%量价%'
              AND sharpe IS NOT NULL
            ORDER BY fitness DESC
        """)
        all_breakthrough = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
    
    total_bt = len([a for a in all_breakthrough if a.get("sharpe") is not None])
    above_125 = len([a for a in all_breakthrough if a.get("sharpe", 0) >= 1.25])
    above_10 = len([a for a in all_breakthrough if a.get("fitness", 0) >= 1.0])
    
    summary = f"""
WQB 跃迁因子研究进展总结：
- 已设计并回测: {total_bt} 个全新因子
- Sharpe ≥ 1.25: {above_125} 个
- Fitness ≥ 1.0: {above_10} 个
"""
    print(summary)
    
    # 提交结果
    await sdk.submit_result(
        status="success",
        message=summary.strip(),
        result_mode=result_mode,
    )


if __name__ == "__main__":
    asyncio.run(main())
