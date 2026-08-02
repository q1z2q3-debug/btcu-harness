#!/usr/bin/env python3
"""
alpha_021 全方位优化脚本 - wqb_alpha021_optimizer.py
=====================================================

功能：
  1. 参数矩阵测试（decay × neutralization × universe × truncation）
  2. alpha_021 变体因子扩展（7种变体）
  3. 原始信号加权组合验证（先加权再rank）
  4. SQLite 去重，避免重复提交
  5. 生成完整优化对比报告
  6. 更新全因子排名报告

用法：
  python wqb_alpha021_optimizer.py [result_mode] [mode]

参数：
  result_mode: display_only / notify / auto (默认: display_only)
  mode:        all / params / variants / combos / rescan (默认: all)
               - all:      运行所有三部分优化
               - params:   只运行参数矩阵
               - variants: 只运行变体因子
               - combos:   只运行组合因子
               - rescan:   只重试失败/pending的因子
"""

import asyncio
import sys
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# 确保能导入同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from codeact_sdk import CodeActSDK
from wqb_api_client import WQBApiClient, WQBSimulation, DEFAULT_SETTINGS


# ============================================================
# 工具 Schema 版本常量
# ============================================================
TOOL_SCHEMA_VERSIONS = {
    "codeact_search_web": "v1_5ac1b0eba8c26f2a",
    "codeact_fetch_web": "v1_2c8d0580b3f93a58",
    "file_to_url": "v1_fe3416acf3d7b53b",
}

# ============================================================
# 提交间隔（严格限流，40秒）
# ============================================================
SUBMIT_INTERVAL = 40.0

# ============================================================
# alpha_021 基准表达式与设置
# ============================================================

# 原始信号（未rank）
ALPHA021_RAW_EXPR = (
    "subtract("
    "divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), "
    "divide(subtract(close, open), open)"
    ")"
)

# 基准表达式（带rank）
ALPHA021_BASE_EXPR = f"rank({ALPHA021_RAW_EXPR})"

# 基准设置
BASE_SETTINGS = {
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 15,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "testPeriod": "P1Y6M",
}


def normalize_settings(settings: Dict) -> Dict:
    """
    规范化设置，确保与 WQB API 提交的 settings 一致
    （与 DEFAULT_SETTINGS 合并，保证哈希一致）
    """
    full = dict(DEFAULT_SETTINGS)
    full.update(settings)
    return full

# ============================================================
# 第一部分：参数矩阵定义
# ============================================================

# decay 单维度扫描
DECAY_SCANS = [5, 10, 15, 20, 30]

# neutralization 单维度扫描
NEUTRALIZATION_SCANS = ["SECTOR", "INDUSTRY", "SUBINDUSTRY", "MARKET", "NONE"]

# universe 单维度扫描
UNIVERSE_SCANS = ["TOP1000", "TOP2000", "TOP3000"]

# truncation 单维度扫描
TRUNCATION_SCANS = [0.05, 0.08, 0.12]

# 交叉验证组合（从单维度中挑选最优的做交叉）
# 先做单维度扫描，交叉验证可以后续补充


def build_param_matrix() -> List[Dict]:
    """
    构建参数矩阵测试列表
    
    策略：单维度扫描，其他参数保持基准值
    """
    tests = []
    
    # 1. Decay 扫描
    for decay in DECAY_SCANS:
        settings = dict(BASE_SETTINGS)
        settings["decay"] = decay
        tests.append({
            "factor_name": f"alpha_021_decay{decay}",
            "category": "参数优化-decay",
            "description": f"alpha_021 decay={decay} 版本",
            "expression": ALPHA021_BASE_EXPR,
            "settings": settings,
            "param_type": "decay",
            "param_value": decay,
        })
    
    # 2. Neutralization 扫描
    for neut in NEUTRALIZATION_SCANS:
        settings = dict(BASE_SETTINGS)
        settings["neutralization"] = neut
        tests.append({
            "factor_name": f"alpha_021_neut_{neut.lower()}",
            "category": "参数优化-neutralization",
            "description": f"alpha_021 neutralization={neut} 版本",
            "expression": ALPHA021_BASE_EXPR,
            "settings": settings,
            "param_type": "neutralization",
            "param_value": neut,
        })
    
    # 3. Universe 扫描
    for uni in UNIVERSE_SCANS:
        settings = dict(BASE_SETTINGS)
        settings["universe"] = uni
        tests.append({
            "factor_name": f"alpha_021_{uni.lower()}",
            "category": "参数优化-universe",
            "description": f"alpha_021 universe={uni} 版本",
            "expression": ALPHA021_BASE_EXPR,
            "settings": settings,
            "param_type": "universe",
            "param_value": uni,
        })
    
    # 4. Truncation 扫描
    for trunc in TRUNCATION_SCANS:
        settings = dict(BASE_SETTINGS)
        settings["truncation"] = trunc
        tests.append({
            "factor_name": f"alpha_021_trunc{int(trunc*100)}",
            "category": "参数优化-truncation",
            "description": f"alpha_021 truncation={trunc} 版本",
            "expression": ALPHA021_BASE_EXPR,
            "settings": settings,
            "param_type": "truncation",
            "param_value": trunc,
        })
    
    return tests


# ============================================================
# 第二部分：alpha_021 变体因子定义
# ============================================================

# 隔夜收益原始表达式
OVERNIGHT_RETURN = "divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1))"

# 日内收益原始表达式
INTRADAY_RETURN = "divide(subtract(close, open), open)"


def build_variants() -> List[Dict]:
    """
    构建 alpha_021 变体因子列表
    """
    base_settings = dict(BASE_SETTINGS)
    variants = []
    
    # v2: 只用隔夜收益排名
    variants.append({
        "factor_name": "alpha_021_v2_overnight_only",
        "category": "变体因子",
        "description": "alpha_021 v2: 只用隔夜收益排名（去掉日内收益部分）",
        "expression": f"rank({OVERNIGHT_RETURN})",
        "settings": base_settings,
        "variant_type": "overnight_only",
    })
    
    # v3: 只用日内收益排名取反
    variants.append({
        "factor_name": "alpha_021_v3_intraday_rev",
        "category": "变体因子",
        "description": "alpha_021 v3: 只用日内收益排名取反（rank(-日内收益)）",
        "expression": f"rank(reverse({INTRADAY_RETURN}))",
        "settings": base_settings,
        "variant_type": "intraday_reverse",
    })
    
    # v4: 隔夜/日内收益的比值排名
    variants.append({
        "factor_name": "alpha_021_v4_ratio",
        "category": "变体因子",
        "description": "alpha_021 v4: 隔夜收益与日内收益绝对值的比值排名",
        "expression": f"rank(divide({OVERNIGHT_RETURN}, add(abs({INTRADAY_RETURN}), 0.01)))",
        "settings": base_settings,
        "variant_type": "ratio",
    })
    
    # v5: 隔夜收益5日均 - 日内收益5日均
    variants.append({
        "factor_name": "alpha_021_v5_ma5_diff",
        "category": "变体因子",
        "description": "alpha_021 v5: 隔夜收益5日均值 - 日内收益5日均值",
        "expression": (
            f"rank(subtract("
            f"ts_mean({OVERNIGHT_RETURN}, 5), "
            f"ts_mean({INTRADAY_RETURN}, 5)"
            f"))"
        ),
        "settings": base_settings,
        "variant_type": "ma5_diff",
    })
    
    # v6: ts_rank版本（用ts_rank而非截面rank，取20日窗口）
    variants.append({
        "factor_name": "alpha_021_v6_tsrank",
        "category": "变体因子",
        "description": "alpha_021 v6: 时序排名版本（ts_rank 20日窗口）+ 截面rank",
        "expression": f"rank(ts_rank({ALPHA021_RAW_EXPR}, 20))",
        "settings": base_settings,
        "variant_type": "ts_rank",
    })
    
    # v7: 成交量加权版本（隔夜收益 × 成交量排名）
    variants.append({
        "factor_name": "alpha_021_v7_vol_weighted",
        "category": "变体因子",
        "description": "alpha_021 v7: 原始信号 × 成交量排名 的加权版本",
        "expression": f"rank(multiply({ALPHA021_RAW_EXPR}, rank(volume)))",
        "settings": base_settings,
        "variant_type": "volume_weighted",
    })
    
    return variants


# ============================================================
# 第三部分：原始信号加权组合验证
# ============================================================

# hist_vol_120 原始信号（未取反，未rank）
HIST_VOL_120_RAW = "ts_std_dev(log(divide(close, ts_delay(close, 1))), 120)"

# reversal_5 原始信号（未取反，未rank）— 5日收益率
REVERSAL_5_RAW = "divide(ts_delta(close, 5), ts_delay(close, 5))"

# amihud_illiq 原始信号（未取反，未rank）— 20日|收益|/成交量均值
AMIHUD_ILLIQ_RAW = "ts_mean(divide(abs(returns), volume), 20)"


def build_combos() -> List[Dict]:
    """
    构建原始信号加权组合因子列表
    
    关键假设：先加权原始信号再rank，比先rank再加权效果更好
    """
    base_settings = dict(BASE_SETTINGS)
    combos = []
    
    # === 组合0: 基准组合（用于对比）===
    # alpha_021 单独作为基准已经有了
    
    # === 组合1: alpha_021 + hist_vol_120 ===
    # 低波异象：买低波卖高波 → 信号应该是 -波动率
    # 权重比例测试：70/30, 60/40, 50/50
    
    for w_alpha, w_vol in [(0.7, 0.3), (0.6, 0.4), (0.5, 0.5)]:
        # alpha_021 是正收益信号（高隔夜-低日内 → 看涨）
        # hist_vol_120 是低波异象（低波动 → 看涨）→ 需要取反
        expr = (
            f"rank(add("
            f"multiply({ALPHA021_RAW_EXPR}, {w_alpha}), "
            f"multiply(reverse({HIST_VOL_120_RAW}), {w_vol})"
            f"))"
        )
        combos.append({
            "factor_name": f"combo_raw_a021_vol120_w{int(w_alpha*100)}{int(w_vol*100)}",
            "category": "原始信号组合",
            "description": (
                f"原始信号加权组合：alpha_021({w_alpha:.0%}) + "
                f"hist_vol_120取反({w_vol:.0%})，先加权再rank"
            ),
            "expression": expr,
            "settings": base_settings,
            "combo_type": "a021_vol120",
            "weights": {"alpha_021": w_alpha, "hist_vol_120": w_vol},
        })
    
    # === 组合2: alpha_021 + reversal_5 ===
    # reversal_5 是反转信号（过去5天跌的未来涨）→ 取反
    for w_alpha, w_rev in [(0.7, 0.3), (0.6, 0.4), (0.5, 0.5)]:
        expr = (
            f"rank(add("
            f"multiply({ALPHA021_RAW_EXPR}, {w_alpha}), "
            f"multiply(reverse({REVERSAL_5_RAW}), {w_rev})"
            f"))"
        )
        combos.append({
            "factor_name": f"combo_raw_a021_rev5_w{int(w_alpha*100)}{int(w_rev*100)}",
            "category": "原始信号组合",
            "description": (
                f"原始信号加权组合：alpha_021({w_alpha:.0%}) + "
                f"reversal_5取反({w_rev:.0%})，先加权再rank"
            ),
            "expression": expr,
            "settings": base_settings,
            "combo_type": "a021_rev5",
            "weights": {"alpha_021": w_alpha, "reversal_5": w_rev},
        })
    
    # === 组合3: 三因子等权 alpha_021 + hist_vol_120 + amihud_illiq ===
    # amihud_illiq 是非流动性因子（低流动性 → 高收益？需要取反因为illiqud高的应该看涨）
    # 这里先验证一下方向，用等权测试
    for weights in [
        {"a021": 1/3, "vol": 1/3, "illiq": 1/3},
        {"a021": 0.5, "vol": 0.3, "illiq": 0.2},
        {"a021": 0.4, "vol": 0.4, "illiq": 0.2},
    ]:
        wa = weights["a021"]
        wv = weights["vol"]
        wi = weights["illiq"]
        expr = (
            f"rank(add("
            f"add(multiply({ALPHA021_RAW_EXPR}, {wa}), "
            f"multiply(reverse({HIST_VOL_120_RAW}), {wv})), "
            f"multiply(reverse({AMIHUD_ILLIQ_RAW}), {wi})"
            f"))"
        )
        combos.append({
            "factor_name": (
                f"combo_raw_3f_w{int(wa*100)}{int(wv*100)}{int(wi*100)}"
            ),
            "category": "原始信号组合",
            "description": (
                f"三因子原始信号组合：alpha_021({wa:.0%}) + "
                f"hist_vol_120({wv:.0%}) + amihud_illiq({wi:.0%})，先加权再rank"
            ),
            "expression": expr,
            "settings": base_settings,
            "combo_type": "3f_raw",
            "weights": {"alpha_021": wa, "hist_vol_120": wv, "amihud_illiq": wi},
        })
    
    return combos


# ============================================================
# 第四部分：交叉验证（最优参数 + 最优组合的叠加）
# ============================================================

def build_cross_combos() -> List[Dict]:
    """
    构建交叉验证组合
    
    基于前面的发现：
    - decay=5 时 Sharpe 最高（1.84）
    - combo_raw_a021_vol120_w7030 Fitness 最高（1.21）
    
    测试：不同 decay 下的组合效果，寻找全局最优
    """
    combos = []
    
    # 1. 最优组合 + 不同 decay
    # combo_raw_a021_vol120_w7030 (基准 decay=15, Sharpe=1.78, Fitness=1.21)
    for decay in [5, 10, 20]:
        settings = dict(BASE_SETTINGS)
        settings["decay"] = decay
        
        expr = (
            f"rank(add("
            f"multiply({ALPHA021_RAW_EXPR}, 0.7), "
            f"multiply(reverse({HIST_VOL_120_RAW}), 0.3)"
            f"))"
        )
        combos.append({
            "factor_name": f"combo_raw_vol120_w7030_decay{decay}",
            "category": "交叉验证",
            "description": (
                f"交叉验证：alpha_021(70%) + vol120(30%) 原始信号组合, "
                f"decay={decay}"
            ),
            "expression": expr,
            "settings": settings,
            "cross_type": "vol120_decay",
            "decay": decay,
            "weights": "70/30",
        })
    
    # 2. 最优 decay=5 + 不同权重比例
    settings_d5 = dict(BASE_SETTINGS)
    settings_d5["decay"] = 5
    
    for w_alpha, w_vol in [(0.8, 0.2), (0.6, 0.4), (0.5, 0.5)]:
        expr = (
            f"rank(add("
            f"multiply({ALPHA021_RAW_EXPR}, {w_alpha}), "
            f"multiply(reverse({HIST_VOL_120_RAW}), {w_vol})"
            f"))"
        )
        combos.append({
            "factor_name": f"combo_d5_vol120_w{int(w_alpha*100)}{int(w_vol*100)}",
            "category": "交叉验证",
            "description": (
                f"交叉验证：decay=5, alpha_021({w_alpha:.0%}) + "
                f"vol120({w_vol:.0%}) 原始信号组合"
            ),
            "expression": expr,
            "settings": settings_d5,
            "cross_type": "d5_weight_sweep",
            "decay": 5,
            "weights": f"{int(w_alpha*100)}/{int(w_vol*100)}",
        })
    
    # 3. decay=10 + 不同权重（Fitness 更高的 decay）
    settings_d10 = dict(BASE_SETTINGS)
    settings_d10["decay"] = 10
    
    for w_alpha, w_vol in [(0.8, 0.2), (0.7, 0.3), (0.6, 0.4)]:
        expr = (
            f"rank(add("
            f"multiply({ALPHA021_RAW_EXPR}, {w_alpha}), "
            f"multiply(reverse({HIST_VOL_120_RAW}), {w_vol})"
            f"))"
        )
        combos.append({
            "factor_name": f"combo_d10_vol120_w{int(w_alpha*100)}{int(w_vol*100)}",
            "category": "交叉验证",
            "description": (
                f"交叉验证：decay=10, alpha_021({w_alpha:.0%}) + "
                f"vol120({w_vol:.0%}) 原始信号组合"
            ),
            "expression": expr,
            "settings": settings_d10,
            "cross_type": "d10_weight_sweep",
            "decay": 10,
            "weights": f"{int(w_alpha*100)}/{int(w_vol*100)}",
        })
    
    return combos


# ============================================================
# 辅助函数：从因子名解析参数
# ============================================================

def enrich_result(result: Dict) -> Dict:
    """
    从因子名和设置中补充参数信息，用于报告展示
    """
    import re
    
    fname = result.get("factor_name", "")
    settings = result.get("settings") or {}
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except Exception:
            settings = {}
    
    # 补充 param_type 和 param_value
    if "param_type" not in result and fname.startswith("alpha_021_"):
        if "decay" in fname:
            result["param_type"] = "decay"
            # 从 settings 中取，或从名字解析
            result["param_value"] = settings.get("decay", 
                fname.replace("alpha_021_decay", ""))
        elif "neut_" in fname:
            result["param_type"] = "neutralization"
            neut = fname.replace("alpha_021_neut_", "").upper()
            result["param_value"] = settings.get("neutralization", neut)
        elif "top" in fname.lower():
            result["param_type"] = "universe"
            uni = fname.replace("alpha_021_", "").upper()
            result["param_value"] = settings.get("universe", uni)
        elif "trunc" in fname:
            result["param_type"] = "truncation"
            trunc_str = fname.replace("alpha_021_trunc", "")
            try:
                result["param_value"] = settings.get("truncation", 
                    float(trunc_str) / 100)
            except ValueError:
                result["param_value"] = trunc_str
    
    # 补充 variant_type
    if "variant_type" not in result and fname.startswith("alpha_021_v"):
        if "overnight" in fname:
            result["variant_type"] = "overnight_only"
        elif "intraday" in fname:
            result["variant_type"] = "intraday_reverse"
        elif "_v4_" in fname or "_ratio" in fname:
            result["variant_type"] = "ratio"
        elif "_v5_" in fname or "ma5" in fname:
            result["variant_type"] = "ma5_diff"
        elif "_v6_" in fname or "tsrank" in fname:
            result["variant_type"] = "ts_rank"
        elif "_v7_" in fname or "vol_weighted" in fname:
            result["variant_type"] = "volume_weighted"
    
    # 补充 combo_type
    if "combo_type" not in result and "combo_raw" in fname:
        if "vol120" in fname and "a021" in fname:
            result["combo_type"] = "a021_vol120"
        elif "rev5" in fname:
            result["combo_type"] = "a021_rev5"
        elif "3f" in fname:
            result["combo_type"] = "3f_raw"
        else:
            result["combo_type"] = "cross_validation"
    
    # 补充交叉验证的 decay 和 weights 字段
    if "decay" not in result or "weights" not in result:
        # combo_d5_vol120_w8020 格式
        if fname.startswith("combo_d5_") or fname.startswith("combo_d10_"):
            # 解析 decay
            if "_d5_" in fname:
                result["decay"] = 5
            elif "_d10_" in fname:
                result["decay"] = 10
            # 解析权重 w8020 -> 80/20
            w_match = re.search(r'_w(\d{2})(\d{2})', fname)
            if w_match:
                result["weights"] = f"{w_match.group(1)}/{w_match.group(2)}"
            result["cross_type"] = "weight_sweep"
        
        # combo_raw_vol120_w7030_decay5 格式
        elif fname.startswith("combo_raw_vol120_") and "_decay" in fname:
            # 解析 decay
            d_match = re.search(r'_decay(\d+)', fname)
            if d_match:
                result["decay"] = int(d_match.group(1))
            # 解析权重
            w_match = re.search(r'_w(\d{2})(\d{2})', fname)
            if w_match:
                result["weights"] = f"{w_match.group(1)}/{w_match.group(2)}"
            result["cross_type"] = "decay_sweep"
    
    # 补充 description
    if not result.get("description"):
        cat = result.get("category", "")
        if cat == "参数优化-decay":
            result["description"] = f"alpha_021 decay={result.get('param_value', '?')}"
        elif cat == "参数优化-neutralization":
            result["description"] = f"alpha_021 {result.get('param_value', '?')} 中性"
        elif cat == "参数优化-universe":
            result["description"] = f"alpha_021 {result.get('param_value', '?')} 股票池"
        elif cat == "参数优化-truncation":
            result["description"] = f"alpha_021 truncation={result.get('param_value', '?')}"
    
    return result


# ============================================================
# 批量提交 + 等待结果
# ============================================================

async def submit_and_wait(client: WQBApiClient, tests: List[Dict],
                          submit_interval: float = SUBMIT_INTERVAL) -> List[Dict]:
    """
    批量提交模拟并等待结果
    
    Args:
        client: WQB API 客户端
        tests: 测试列表，每个包含 expression, settings, factor_name 等
        submit_interval: 提交间隔（秒）
    
    Returns:
        结果列表
    """
    # ---- 0. 规范化 settings（确保与 WQB API 提交的一致）----
    normalized_tests = []
    for test in tests:
        t = dict(test)
        t["settings"] = normalize_settings(t["settings"])
        normalized_tests.append(t)
    tests = normalized_tests
    
    # ---- 1. 检查缓存 ----
    to_submit = []
    cached_results = []
    
    for test in tests:
        cached = client.get_cached_alpha(test["expression"], test["settings"])
        if cached and cached.get("status") == "COMPLETED":
            cached_results.append({**test, **cached, "from_cache": True})
            print(f"  [缓存] {test['factor_name']}: Sharpe={cached.get('sharpe', 'N/A')}")
        elif cached and cached.get("status") == "PENDING" and cached.get("progress_url"):
            # PENDING 的也加入等待队列
            sim = WQBSimulation(client, cached["progress_url"],
                               test["expression"], test["settings"])
            sim.factor_name = test["factor_name"]
            sim.category = test["category"]
            sim.description = test.get("description", "")
            sim._submitted = False
            cached_results.append({**test, "sim": sim, "from_cache": "pending"})
            print(f"  [等待] {test['factor_name']}: 已有PENDING任务")
        else:
            to_submit.append(test)
    
    print(f"\n[信息] 缓存命中 {len(cached_results)} 个，需提交 {len(to_submit)} 个")
    
    # ---- 2. 批量提交 ----
    simulations = []
    for i, test in enumerate(to_submit):
        factor_name = test["factor_name"]
        expression = test["expression"]
        settings = test["settings"]
        
        # 标记为 PENDING
        client.save_alpha_result(
            expression=expression,
            settings=settings,
            factor_name=factor_name,
            category=test.get("category", "未知"),
            status="PENDING",
        )
        
        try:
            sim = client.simulate(expression, settings)
            sim.factor_name = factor_name
            sim.category = test.get("category", "未知")
            sim.description = test.get("description", "")
            sim._submitted = True
            sim._test_info = test
            simulations.append(sim)
            
            # 保存 progress_url
            client.save_alpha_result(
                expression=expression,
                settings=settings,
                factor_name=factor_name,
                category=test.get("category", "未知"),
                progress_url=sim.progress_url,
                status="PENDING",
            )
            print(f"  [{i+1}/{len(to_submit)}] ✓ 提交 {factor_name}")
        except Exception as e:
            error_str = str(e)
            print(f"  [{i+1}/{len(to_submit)}] ✗ 提交失败 {factor_name}: {error_str[:80]}")
            client.save_alpha_result(
                expression=expression,
                settings=settings,
                factor_name=factor_name,
                category=test.get("category", "未知"),
                status="FAILED",
                error=error_str,
            )
            sim = WQBSimulation(client, None, expression, settings)
            sim.factor_name = factor_name
            sim.category = test.get("category", "未知")
            sim.status = "FAILED"
            sim.error = error_str
            sim._submitted = False
            sim._test_info = test
            simulations.append(sim)
        
        # 提交间隔
        if i < len(to_submit) - 1:
            await asyncio.sleep(submit_interval)
    
    # 把缓存中 pending 的也加入等待队列
    for item in cached_results:
        if item.get("from_cache") == "pending" and "sim" in item:
            simulations.append(item["sim"])
    
    # ---- 3. 批量等待结果 ----
    submitted_sims = [s for s in simulations if s.status == "PENDING"]
    
    if submitted_sims:
        print(f"\n[等待] {len(submitted_sims)} 个模拟进行中...")
        max_wait = 900.0  # 最多等 15 分钟
        start_time = asyncio.get_event_loop().time()
        completed_count = 0
        failed_count = 0
        
        while submitted_sims and (asyncio.get_event_loop().time() - start_time) < max_wait:
            still_pending = []
            
            for sim in submitted_sims:
                try:
                    response = client._session.get(sim.progress_url)
                    retry_after = float(response.headers.get("Retry-After", 0))
                    
                    if retry_after == 0:
                        response.raise_for_status()
                        result = response.json()
                        sim.alpha_id = result.get("alpha")
                        sim.status = "COMPLETED"
                        completed_count += 1
                        
                        # 获取指标
                        try:
                            metrics = sim.get_metrics()
                            is_summary = metrics.pop("is_summary", None)
                            yearly = sim.get_yearly()
                            
                            client.save_alpha_result(
                                expression=sim.expression,
                                settings=sim.settings,
                                factor_name=sim.factor_name,
                                category=sim.category,
                                alpha_id=sim.alpha_id,
                                status="COMPLETED",
                                metrics=metrics,
                                is_summary=is_summary,
                                yearly=yearly,
                            )
                            print(f"  ✓ [{completed_count}] {sim.factor_name}: "
                                  f"Sharpe={metrics.get('sharpe', 'N/A')}, "
                                  f"Fitness={metrics.get('fitness', 'N/A')}")
                        except Exception as e:
                            print(f"  ✗ 获取结果失败 {sim.factor_name}: {e}")
                            client.save_alpha_result(
                                expression=sim.expression,
                                settings=sim.settings,
                                factor_name=sim.factor_name,
                                category=sim.category,
                                status="FAILED",
                                error=f"结果获取失败: {e}",
                            )
                            sim.status = "FAILED"
                            sim.error = f"结果获取失败: {e}"
                            failed_count += 1
                    else:
                        still_pending.append(sim)
                except Exception as e:
                    sim.status = "FAILED"
                    sim.error = str(e)
                    failed_count += 1
                    print(f"  ✗ {sim.factor_name} 失败: {str(e)[:80]}")
                    client.save_alpha_result(
                        expression=sim.expression,
                        settings=sim.settings,
                        factor_name=sim.factor_name,
                        category=sim.category,
                        status="FAILED",
                        error=str(e),
                    )
            
            submitted_sims = still_pending
            if submitted_sims:
                await asyncio.sleep(5.0)
        
        # 处理超时
        for sim in submitted_sims:
            print(f"  ⏳ {sim.factor_name} 超时，保持 PENDING")
    
    # ---- 4. 收集所有结果 ----
    all_results = []
    
    # 缓存命中的 COMPLETED
    for item in cached_results:
        if item.get("from_cache") == True:
            all_results.append(item)
    
    # 新提交/等待的
    for sim in simulations:
        result = {
            "factor_name": sim.factor_name,
            "category": sim.category,
            "expression": sim.expression,
            "settings": sim.settings,
            "status": sim.status,
            "error": getattr(sim, "error", None),
        }
        
        if sim.status == "COMPLETED":
            try:
                cached = client.get_cached_alpha(sim.expression, sim.settings)
                if cached:
                    result.update(cached)
            except Exception:
                pass
        
        # 补充 test_info 中的元数据
        if hasattr(sim, '_test_info'):
            for k, v in sim._test_info.items():
                if k not in result:
                    result[k] = v
        
        all_results.append(result)
    
    return all_results


# ============================================================
# 报告生成
# ============================================================

def generate_optimization_report(all_results: List[Dict], report_path: str,
                                 baseline: Dict = None) -> str:
    """
    生成 alpha_021 优化报告
    
    Args:
        all_results: 所有测试结果
        report_path: 报告输出路径
        baseline: 基准 alpha_021 数据
    
    Returns:
        报告文件路径
    """
    # 先丰富结果数据（从因子名解析参数等）
    enriched_results = [enrich_result(dict(r)) for r in all_results]
    
    # 按类别分组
    by_category = defaultdict(list)
    for r in enriched_results:
        cat = r.get("category", "未知")
        by_category[cat].append(r)
    
    # 找出 completed 的
    completed = [r for r in enriched_results if r.get("status") == "COMPLETED"]
    failed = [r for r in enriched_results if r.get("status") == "FAILED"]
    pending = [r for r in enriched_results if r.get("status") == "PENDING"]
    
    # 按 Sharpe 排序
    completed.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
    
    # Top 3 发布候选
    top_candidates = [r for r in completed if (r.get("fitness") or 0) >= 0.5][:3]
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    lines = []
    lines.append("# Alpha_021 全方位优化报告")
    lines.append("")
    lines.append(f"**生成时间**: {now}")
    lines.append(f"**总测试数**: {len(all_results)} | **成功**: {len(completed)} | **失败**: {len(failed)} | **进行中**: {len(pending)}")
    lines.append("")
    
    # 基准信息
    if baseline:
        lines.append("## 基准表现")
        lines.append("")
        lines.append(f"- **基准因子**: alpha_021 (原始版)")
        lines.append(f"- **Sharpe**: {baseline.get('sharpe', 'N/A')}")
        lines.append(f"- **Fitness**: {baseline.get('fitness', 'N/A')}")
        lines.append(f"- **年化收益**: {baseline.get('annual_return', 'N/A')}")
        lines.append(f"- **换手率**: {baseline.get('turnover', 'N/A')}")
        lines.append(f"- **最大回撤**: {baseline.get('max_drawdown', 'N/A')}")
        lines.append("")
    
    # Top 10 总排名
    lines.append("## Top 10 总排名（按 Sharpe）")
    lines.append("")
    lines.append("| 排名 | 因子名称 | 类别 | Sharpe | Fitness | 年化收益 | 换手率 | 相对基准 |")
    lines.append("|------|----------|------|--------|---------|----------|--------|----------|")
    
    baseline_sharpe = baseline.get("sharpe", 0) if baseline else 0
    for i, r in enumerate(completed[:10]):
        sharpe = r.get("sharpe", 0) or 0
        fitness = r.get("fitness", 0) or 0
        annual = r.get("annual_return", 0) or 0
        turnover = r.get("turnover", 0) or 0
        diff = sharpe - baseline_sharpe
        diff_str = f"+{diff:.3f}" if diff > 0 else f"{diff:.3f}"
        if diff > 0:
            diff_str = f"**{diff_str}**"
        lines.append(
            f"| {i+1} | {r.get('factor_name', '?')} | {r.get('category', '?')} | "
            f"{sharpe:.3f} | {fitness:.3f} | {annual:.2%} | {turnover:.2%} | {diff_str} |"
        )
    lines.append("")
    
    # === 第一部分：参数矩阵结果 ===
    lines.append("## 第一部分：参数矩阵测试")
    lines.append("")
    
    # Decay 扫描
    decay_results = by_category.get("参数优化-decay", [])
    decay_completed = [r for r in decay_results if r.get("status") == "COMPLETED"]
    decay_completed.sort(key=lambda x: x.get("param_value", 0))
    
    if decay_completed:
        lines.append("### 1.1 Decay 扫描")
        lines.append("")
        lines.append("| Decay | Sharpe | Fitness | 年化收益 | 换手率 | 最大回撤 |")
        lines.append("|-------|--------|---------|----------|--------|----------|")
        for r in decay_completed:
            sharpe = r.get("sharpe", 0) or 0
            fitness = r.get("fitness", 0) or 0
            annual = r.get("annual_return", 0) or 0
            turnover = r.get("turnover", 0) or 0
            mdd = r.get("max_drawdown", 0) or 0
            is_best = " ⭐" if sharpe == max(x.get("sharpe", 0) or 0 for x in decay_completed) else ""
            lines.append(
                f"| {r.get('param_value', '?')} | {sharpe:.3f}{is_best} | {fitness:.3f} | "
                f"{annual:.2%} | {turnover:.2%} | {mdd:.2%} |"
            )
        
        best_decay = max(decay_completed, key=lambda x: x.get("sharpe") or 0)
        lines.append("")
        lines.append(
            f"**最佳 Decay**: {best_decay.get('param_value', '?')} "
            f"(Sharpe={best_decay.get('sharpe', 0):.3f}, "
            f"Fitness={best_decay.get('fitness', 0):.3f})"
        )
        lines.append("")
    
    # Neutralization 扫描
    neut_results = by_category.get("参数优化-neutralization", [])
    neut_completed = [r for r in neut_results if r.get("status") == "COMPLETED"]
    
    if neut_completed:
        lines.append("### 1.2 Neutralization 扫描")
        lines.append("")
        lines.append("| Neutralization | Sharpe | Fitness | 年化收益 | 换手率 | 最大回撤 |")
        lines.append("|----------------|--------|---------|----------|--------|----------|")
        for r in neut_completed:
            sharpe = r.get("sharpe", 0) or 0
            fitness = r.get("fitness", 0) or 0
            annual = r.get("annual_return", 0) or 0
            turnover = r.get("turnover", 0) or 0
            mdd = r.get("max_drawdown", 0) or 0
            is_best = " ⭐" if sharpe == max(x.get("sharpe", 0) or 0 for x in neut_completed) else ""
            lines.append(
                f"| {r.get('param_value', '?')} | {sharpe:.3f}{is_best} | {fitness:.3f} | "
                f"{annual:.2%} | {turnover:.2%} | {mdd:.2%} |"
            )
        
        best_neut = max(neut_completed, key=lambda x: x.get("sharpe") or 0)
        lines.append("")
        lines.append(
            f"**最佳 Neutralization**: {best_neut.get('param_value', '?')} "
            f"(Sharpe={best_neut.get('sharpe', 0):.3f}, "
            f"Fitness={best_neut.get('fitness', 0):.3f})"
        )
        lines.append("")
    
    # Universe 扫描
    uni_results = by_category.get("参数优化-universe", [])
    uni_completed = [r for r in uni_results if r.get("status") == "COMPLETED"]
    
    if uni_completed:
        lines.append("### 1.3 Universe 扫描")
        lines.append("")
        lines.append("| Universe | Sharpe | Fitness | 年化收益 | 换手率 | 最大回撤 |")
        lines.append("|----------|--------|---------|----------|--------|----------|")
        for r in uni_completed:
            sharpe = r.get("sharpe", 0) or 0
            fitness = r.get("fitness", 0) or 0
            annual = r.get("annual_return", 0) or 0
            turnover = r.get("turnover", 0) or 0
            mdd = r.get("max_drawdown", 0) or 0
            is_best = " ⭐" if sharpe == max(x.get("sharpe", 0) or 0 for x in uni_completed) else ""
            lines.append(
                f"| {r.get('param_value', '?')} | {sharpe:.3f}{is_best} | {fitness:.3f} | "
                f"{annual:.2%} | {turnover:.2%} | {mdd:.2%} |"
            )
        
        best_uni = max(uni_completed, key=lambda x: x.get("sharpe") or 0)
        lines.append("")
        lines.append(
            f"**最佳 Universe**: {best_uni.get('param_value', '?')} "
            f"(Sharpe={best_uni.get('sharpe', 0):.3f}, "
            f"Fitness={best_uni.get('fitness', 0):.3f})"
        )
        lines.append("")
    
    # Truncation 扫描
    trunc_results = by_category.get("参数优化-truncation", [])
    trunc_completed = [r for r in trunc_results if r.get("status") == "COMPLETED"]
    
    if trunc_completed:
        lines.append("### 1.4 Truncation 扫描")
        lines.append("")
        lines.append("| Truncation | Sharpe | Fitness | 年化收益 | 换手率 | 最大回撤 |")
        lines.append("|------------|--------|---------|----------|--------|----------|")
        for r in trunc_completed:
            sharpe = r.get("sharpe", 0) or 0
            fitness = r.get("fitness", 0) or 0
            annual = r.get("annual_return", 0) or 0
            turnover = r.get("turnover", 0) or 0
            mdd = r.get("max_drawdown", 0) or 0
            is_best = " ⭐" if sharpe == max(x.get("sharpe", 0) or 0 for x in trunc_completed) else ""
            lines.append(
                f"| {r.get('param_value', '?')} | {sharpe:.3f}{is_best} | {fitness:.3f} | "
                f"{annual:.2%} | {turnover:.2%} | {mdd:.2%} |"
            )
        
        best_trunc = max(trunc_completed, key=lambda x: x.get("sharpe") or 0)
        lines.append("")
        lines.append(
            f"**最佳 Truncation**: {best_trunc.get('param_value', '?')} "
            f"(Sharpe={best_trunc.get('sharpe', 0):.3f}, "
            f"Fitness={best_trunc.get('fitness', 0):.3f})"
        )
        lines.append("")
    
    # === 第二部分：变体因子 ===
    lines.append("## 第二部分：变体因子测试")
    lines.append("")
    
    variant_results = by_category.get("变体因子", [])
    variant_completed = [r for r in variant_results if r.get("status") == "COMPLETED"]
    variant_completed.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
    
    if variant_completed:
        lines.append("| 排名 | 变体名称 | 类型 | Sharpe | Fitness | 年化收益 | 换手率 | 相对基准 |")
        lines.append("|------|----------|------|--------|---------|----------|--------|----------|")
        
        for i, r in enumerate(variant_completed):
            sharpe = r.get("sharpe", 0) or 0
            fitness = r.get("fitness", 0) or 0
            annual = r.get("annual_return", 0) or 0
            turnover = r.get("turnover", 0) or 0
            diff = sharpe - baseline_sharpe
            diff_str = f"+{diff:.3f}" if diff > 0 else f"{diff:.3f}"
            if diff > 0:
                diff_str = f"**{diff_str}**"
            lines.append(
                f"| {i+1} | {r.get('factor_name', '?')} | {r.get('variant_type', '?')} | "
                f"{sharpe:.3f} | {fitness:.3f} | {annual:.2%} | {turnover:.2%} | {diff_str} |"
            )
        lines.append("")
        
        best_variant = variant_completed[0]
        lines.append(
            f"**最佳变体**: {best_variant.get('factor_name', '?')} "
            f"(Sharpe={best_variant.get('sharpe', 0):.3f}, "
            f"Fitness={best_variant.get('fitness', 0):.3f})"
        )
        lines.append("")
    else:
        lines.append("暂无完成的变体因子测试。")
        lines.append("")
    
    # === 第三部分：原始信号组合 ===
    lines.append("## 第三部分：原始信号加权组合验证")
    lines.append("")
    lines.append("> **假设验证**：先加权原始信号再 rank，是否比先 rank 再加权效果更好？")
    lines.append("")
    
    combo_results = by_category.get("原始信号组合", [])
    combo_completed = [r for r in combo_results if r.get("status") == "COMPLETED"]
    combo_completed.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
    
    if combo_completed:
        lines.append("| 排名 | 组合名称 | 类型 | Sharpe | Fitness | 年化收益 | 换手率 | 相对基准 |")
        lines.append("|------|----------|------|--------|---------|----------|--------|----------|")
        
        for i, r in enumerate(combo_completed):
            sharpe = r.get("sharpe", 0) or 0
            fitness = r.get("fitness", 0) or 0
            annual = r.get("annual_return", 0) or 0
            turnover = r.get("turnover", 0) or 0
            diff = sharpe - baseline_sharpe
            diff_str = f"+{diff:.3f}" if diff > 0 else f"{diff:.3f}"
            if diff > 0:
                diff_str = f"**{diff_str}**"
            lines.append(
                f"| {i+1} | {r.get('factor_name', '?')} | {r.get('combo_type', '?')} | "
                f"{sharpe:.3f} | {fitness:.3f} | {annual:.2%} | {turnover:.2%} | {diff_str} |"
            )
        lines.append("")
        
        best_combo = combo_completed[0]
        lines.append(
            f"**最佳组合**: {best_combo.get('factor_name', '?')} "
            f"(Sharpe={best_combo.get('sharpe', 0):.3f}, "
            f"Fitness={best_combo.get('fitness', 0):.3f})"
        )
        lines.append("")
        
        # 对比：先rank再加权 vs 先加权再rank
        lines.append("### 组合方式对比")
        lines.append("")
        lines.append("| 组合方式 | 代表因子 | Sharpe | Fitness |")
        lines.append("|----------|----------|--------|---------|")
        lines.append(
            f"| 先rank再加权 | combo_weighted_3f | 0.760 | 0.420 |"
        )
        best_combo_sharpe = best_combo.get("sharpe", 0)
        best_combo_fitness = best_combo.get("fitness", 0)
        lines.append(
            f"| **先加权再rank** | **{best_combo.get('factor_name', '?')}** | "
            f"**{best_combo_sharpe:.3f}** | **{best_combo_fitness:.3f}** |"
        )
        lines.append("")
        
        if best_combo_sharpe > 0.76:
            improvement = best_combo_sharpe - 0.76
            lines.append(
                f"✅ **假设成立**：原始信号加权后再 rank 的方式比先 rank 再加权提升了 "
                f"{improvement:.3f} 的 Sharpe ({improvement/0.76:.1%})"
            )
        else:
            lines.append("❌ **假设不成立**：原始信号加权方式并未超越先 rank 再加权。")
        lines.append("")
    else:
        lines.append("暂无完成的组合因子测试。")
        lines.append("")
    
    # === 第四部分：交叉验证 ===
    lines.append("## 第四部分：交叉验证（参数优化 × 组合优化）")
    lines.append("")
    lines.append("> 目标：将最优 decay 参数与最优组合策略结合，寻找全局最优因子")
    lines.append("")
    
    cross_results = by_category.get("交叉验证", [])
    cross_completed = [r for r in cross_results if r.get("status") == "COMPLETED"]
    cross_completed.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
    
    if cross_completed:
        lines.append("| 排名 | 因子名称 | Decay | 权重 | Sharpe | Fitness | 年化收益 | 换手率 |")
        lines.append("|------|----------|-------|------|--------|---------|----------|--------|")
        for i, r in enumerate(cross_completed[:10]):
            sharpe = r.get("sharpe", 0) or 0
            fitness = r.get("fitness", 0) or 0
            annual = r.get("annual_return", 0) or 0
            turnover = r.get("turnover", 0) or 0
            decay = r.get("decay", "?")
            weights = r.get("weights", "?")
            is_best = " ⭐" if i == 0 else ""
            lines.append(
                f"| {i+1} | {r.get('factor_name', '?')} | {decay} | {weights} | "
                f"{sharpe:.3f}{is_best} | {fitness:.3f} | {annual:.2%} | {turnover:.2%} |"
            )
        lines.append("")
        
        best_cross = cross_completed[0]
        lines.append(
            f"**交叉验证最优**: {best_cross.get('factor_name', '?')} "
            f"(Sharpe={best_cross.get('sharpe', 0):.3f}, "
            f"Fitness={best_cross.get('fitness', 0):.3f})"
        )
        lines.append("")
        
        # 与基准对比
        baseline_sharpe = baseline.get("sharpe", 0) if baseline else 0
        best_cross_sharpe = best_cross.get("sharpe", 0) or 0
        if best_cross_sharpe > baseline_sharpe:
            improvement = best_cross_sharpe - baseline_sharpe
            lines.append(
                f"🎉 **超过基准**: Sharpe 提升 {improvement:.3f} "
                f"({improvement/baseline_sharpe:.1%})"
            )
        lines.append("")
    else:
        lines.append("暂无完成的交叉验证测试。")
        lines.append("")
    
    # === 第五部分：发布候选 ===
    lines.append("## 第五部分：最佳发布候选")
    lines.append("")
    
    # 筛选 Fitness >= 0.5 的
    publishable = [r for r in completed if (r.get("fitness") or 0) >= 0.5]
    publishable.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
    
    if publishable:
        lines.append(f"满足发布条件（Fitness ≥ 0.5）的因子共 {len(publishable)} 个：")
        lines.append("")
        lines.append("| 排名 | 因子名称 | 类别 | Sharpe | Fitness | 年化收益 | 换手率 |")
        lines.append("|------|----------|------|--------|---------|----------|--------|")
        for i, r in enumerate(publishable[:5]):
            sharpe = r.get("sharpe", 0) or 0
            fitness = r.get("fitness", 0) or 0
            annual = r.get("annual_return", 0) or 0
            turnover = r.get("turnover", 0) or 0
            medal = ""
            if i == 0:
                medal = " 🥇"
            elif i == 1:
                medal = " 🥈"
            elif i == 2:
                medal = " 🥉"
            lines.append(
                f"| {i+1} | {r.get('factor_name', '?')}{medal} | {r.get('category', '?')} | "
                f"{sharpe:.3f} | {fitness:.3f} | {annual:.2%} | {turnover:.2%} |"
            )
        lines.append("")
        
        top1 = publishable[0]
        lines.append(f"### 🏆 推荐发布：{top1.get('factor_name', '?')}")
        lines.append("")
        lines.append(f"- **Sharpe**: {top1.get('sharpe', 0):.3f}")
        lines.append(f"- **Fitness**: {top1.get('fitness', 0):.3f}")
        lines.append(f"- **年化收益**: {top1.get('annual_return', 0):.2%}")
        lines.append(f"- **换手率**: {top1.get('turnover', 0):.2%}")
        lines.append(f"- **最大回撤**: {top1.get('max_drawdown', 0):.2%}")
        lines.append(f"- **类别**: {top1.get('category', '?')}")
        if top1.get("description"):
            lines.append(f"- **说明**: {top1['description']}")
        lines.append("")
    else:
        lines.append("⚠️ 暂无满足 Fitness ≥ 0.5 的发布候选因子。")
        lines.append("")
    
    # 失败因子
    if failed:
        lines.append("## 失败因子列表")
        lines.append("")
        for r in failed:
            lines.append(f"- **{r.get('factor_name', '?')}**: {r.get('error', '未知错误')[:100]}")
        lines.append("")
    
    # 进行中
    if pending:
        lines.append("## 进行中的因子")
        lines.append("")
        for r in pending:
            lines.append(f"- {r.get('factor_name', '?')}")
        lines.append("")
    
    report_content = "\n".join(lines)
    
    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    return report_path


def update_master_report(client: WQBApiClient, report_path: str) -> str:
    """
    更新全因子排名报告
    
    Args:
        client: WQB API 客户端
        report_path: 报告输出路径
    
    Returns:
        报告文件路径
    """
    all_results = client.list_all_results()
    
    # 补充描述信息
    for r in all_results:
        fname = r.get("factor_name", "")
        if "yearly_data" not in r and r.get("yearly_json"):
            try:
                r["yearly_data"] = json.loads(r["yearly_json"])
            except Exception:
                pass
    
    completed = [r for r in all_results if r.get("status") == "COMPLETED"]
    failed = [r for r in all_results if r.get("status") == "FAILED"]
    pending = [r for r in all_results if r.get("status") == "PENDING"]
    completed.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    lines = []
    lines.append("# WorldQuant BRAIN 因子回测报告")
    lines.append("")
    lines.append(f"**生成时间**: {now}")
    lines.append(f"**回测设置**: USA / TOP3000 / delay=1 / decay=15 / SUBINDUSTRY / P1Y6M (基准设置)")
    lines.append(f"**成功**: {len(completed)} 个 | **失败**: {len(failed)} 个 | **进行中**: {len(pending)} 个")
    lines.append("")
    
    # Top 20 排名
    lines.append("## 核心指标汇总（按 Sharpe 排名 Top 20）")
    lines.append("")
    lines.append("| 排名 | 因子名称 | 类别 | Sharpe | Fitness | 年化收益 | 换手率 |")
    lines.append("|------|----------|------|--------|---------|----------|--------|")
    for i, r in enumerate(completed[:20]):
        sharpe = f"{r.get('sharpe', 0):.3f}" if r.get('sharpe') is not None else "N/A"
        fitness = f"{r.get('fitness', 0):.3f}" if r.get('fitness') is not None else "N/A"
        annual = f"{r.get('annual_return', 0):.2%}" if r.get('annual_return') is not None else "N/A"
        turnover = f"{r.get('turnover', 0):.2%}" if r.get('turnover') is not None else "N/A"
        cat = r.get('category', '?')
        lines.append(f"| {i+1} | {r.get('factor_name', '?')} | {cat} | {sharpe} | {fitness} | {annual} | {turnover} |")
    lines.append("")
    
    # 按类别统计
    category_stats = defaultdict(list)
    for r in completed:
        cat = r.get("category", "未知")
        category_stats[cat].append(r)
    
    lines.append("## 按类别统计")
    lines.append("")
    for cat, items in sorted(category_stats.items()):
        avg_sharpe = sum(x.get("sharpe", 0) or 0 for x in items) / len(items) if items else 0
        best = max(items, key=lambda x: x.get("sharpe") or -999)
        lines.append(
            f"- **{cat}**: {len(items)}个因子, 平均Sharpe={avg_sharpe:.3f}, "
            f"最佳={best.get('factor_name')}(Sharpe={best.get('sharpe', 0):.3f})"
        )
    lines.append("")
    
    report_content = "\n".join(lines)
    
    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    return report_path


# ============================================================
# 主逻辑
# ============================================================

async def main():
    # ---- 参数解析 ----
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    mode = sys.argv[2] if len(sys.argv) > 2 else "all"
    
    # 账号配置（从 SECRET.md 读取，这里硬编码和原脚本保持一致）
    email = "q1z2q3@126.com"
    password = "W2025zq0118"
    
    # 路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.normpath(os.path.join(script_dir, "..", "output"))
    os.makedirs(output_dir, exist_ok=True)
    
    db_path = os.path.join(output_dir, "wqb_state.db")
    opt_report_path = os.path.join(output_dir, "wqb_alpha021_optimization_report.md")
    master_report_path = os.path.join(output_dir, "wqb_backtest_report.md")
    
    actual_mode = result_mode if result_mode != "auto" else "display_only"
    
    print(f"[参数] result_mode={actual_mode}, mode={mode}")
    print(f"[路径] 数据库: {db_path}")
    print(f"[路径] 优化报告: {opt_report_path}")
    print(f"[限流] 提交间隔: {SUBMIT_INTERVAL}s")
    
    sdk = CodeActSDK()
    
    try:
        # ---- 1. 构建测试列表 ----
        all_tests = []
        
        if mode in ("all", "params"):
            param_tests = build_param_matrix()
            all_tests.extend(param_tests)
            print(f"[参数矩阵] {len(param_tests)} 个组合")
        
        if mode in ("all", "variants"):
            variant_tests = build_variants()
            all_tests.extend(variant_tests)
            print(f"[变体因子] {len(variant_tests)} 个变体")
        
        if mode in ("all", "combos"):
            combo_tests = build_combos()
            all_tests.extend(combo_tests)
            print(f"[组合因子] {len(combo_tests)} 个组合")
        
        if mode in ("all", "cross"):
            cross_tests = build_cross_combos()
            all_tests.extend(cross_tests)
            print(f"[交叉验证] {len(cross_tests)} 个交叉验证组合")
        
        if mode == "rescan":
            # rescan 模式：从数据库读取失败/pending的alpha_021相关因子
            print("[模式] 重扫模式，将从数据库读取失败/待处理的因子")
            # 这里交给后面的逻辑处理
        
        print(f"[总计] {len(all_tests)} 个测试任务")
        
        # ---- 2. 登录 API ----
        print("\n[WQB] 正在登录...")
        client = WQBApiClient.login(email, password, db_path=db_path)
        
        # ---- 3. 获取基准数据 ----
        baseline_expr = ALPHA021_BASE_EXPR
        baseline_settings = normalize_settings(dict(BASE_SETTINGS))
        baseline = client.get_cached_alpha(baseline_expr, baseline_settings)
        
        if baseline and baseline.get("status") == "COMPLETED":
            print(f"[基准] alpha_021: Sharpe={baseline.get('sharpe')}, "
                  f"Fitness={baseline.get('fitness')}")
        else:
            print("[基准] alpha_021 未找到或未完成，将作为普通因子加入测试")
            all_tests.insert(0, {
                "factor_name": "alpha_021",
                "category": "基准",
                "description": "alpha_021 基准版",
                "expression": ALPHA021_BASE_EXPR,
                "settings": BASE_SETTINGS,
            })
        
        # ---- 4. 提交并等待结果 ----
        if mode == "rescan":
            # rescan 模式：从数据库找失败/pending的
            all_db = client.list_all_results()
            rescan_tests = []
            for r in all_db:
                if r.get("status") in ("FAILED", "PENDING"):
                    fname = r.get("factor_name", "")
                    # 只重跑 alpha_021 相关的
                    if fname.startswith("alpha_021") or fname.startswith("combo_raw") or fname.startswith("combo_alpha021") or fname.startswith("combo_d") or cat == "交叉验证":
                        rescan_tests.append({
                            "factor_name": fname,
                            "category": r.get("category", "未知"),
                            "description": r.get("description", ""),
                            "expression": r["expression"],
                            "settings": json.loads(r["settings_json"]),
                        })
            all_tests = rescan_tests
            print(f"[Rescan] 找到 {len(all_tests)} 个需重试的因子")
        
        if not all_tests:
            print("[信息] 没有需要测试的因子，直接生成报告")
        else:
            all_results = await submit_and_wait(client, all_tests, SUBMIT_INTERVAL)
            print(f"\n[完成] {len(all_results)} 个因子已处理")
        
        # ---- 5. 生成优化报告 ----
        # 从数据库读取所有相关结果
        all_db = client.list_all_results()
        related_results = []
        for r in all_db:
            fname = r.get("factor_name", "")
            cat = r.get("category", "")
            if (fname.startswith("alpha_021") and fname != "alpha_021") or \
               fname.startswith("combo_raw") or \
               fname.startswith("combo_alpha021") or \
               fname.startswith("combo_d5") or \
               fname.startswith("combo_d10") or \
               cat.startswith("参数优化-") or \
               cat == "变体因子" or \
               cat == "原始信号组合" or \
               cat == "交叉验证":
                related_results.append(r)
        
        # 确保 baseline 也在里面
        if baseline and baseline.get("status") == "COMPLETED":
            baseline["factor_name"] = "alpha_021"
            baseline["category"] = "基准"
            # 避免重复
            if not any(r.get("factor_name") == "alpha_021" and r.get("category") == "基准" 
                      for r in related_results):
                related_results.append(baseline)
        
        opt_report_path = generate_optimization_report(
            related_results, opt_report_path, baseline=baseline
        )
        abs_opt_report = os.path.abspath(opt_report_path)
        print(f"[报告] 优化报告已生成: {opt_report_path}")
        
        # ---- 6. 更新全因子排名报告 ----
        master_report_path = update_master_report(client, master_report_path)
        abs_master_report = os.path.abspath(master_report_path)
        print(f"[报告] 全因子排名已更新: {master_report_path}")
        
        # ---- 7. 输出摘要 ----
        completed = [r for r in related_results if r.get("status") == "COMPLETED"]
        failed = [r for r in related_results if r.get("status") == "FAILED"]
        pending = [r for r in related_results if r.get("status") == "PENDING"]
        completed.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
        
        summary_lines = [
            f"Alpha_021 全方位优化完成！",
            f"测试范围：参数矩阵 + 变体因子 + 原始信号组合",
            f"结果：成功 {len(completed)} / 失败 {len(failed)} / 进行中 {len(pending)}",
        ]
        
        if completed:
            top = completed[0]
            baseline_sharpe = baseline.get("sharpe", 0) if baseline else 0
            top_sharpe = top.get("sharpe", 0) or 0
            improvement = top_sharpe - baseline_sharpe
            
            summary_lines.append(
                f"最佳因子：{top.get('factor_name')} "
                f"(Sharpe={top_sharpe:.3f}, Fitness={top.get('fitness', 0):.3f})"
            )
            
            if improvement > 0:
                summary_lines.append(
                    f"相对基准提升：Sharpe +{improvement:.3f} ({improvement/baseline_sharpe:.1%})"
                )
            else:
                summary_lines.append(
                    f"相对基准变化：Sharpe {improvement:.3f}"
                )
            
            # Top 5
            summary_lines.append("\nTop 5 优化因子：")
            for i, r in enumerate(completed[:5]):
                sharpe = f"{r.get('sharpe', 0):.3f}" if r.get('sharpe') is not None else "N/A"
                fitness = f"{r.get('fitness', 0):.3f}" if r.get('fitness') is not None else "N/A"
                cat = r.get('category', '?')
                summary_lines.append(
                    f"  {i+1}. {r.get('factor_name')} [{cat}]: Sharpe={sharpe}, Fitness={fitness}"
                )
        
        summary_lines.append(f"\n📊 优化报告：[Alpha_021优化报告](computer://{abs_opt_report})")
        summary_lines.append(f"📊 全因子排名：[回测报告](computer://{abs_master_report})")
        summary_lines.append(f"💾 状态数据库：./codeact/output/wqb_state.db")
        
        summary_message = "\n".join(summary_lines)
        
        await sdk.submit_result(
            result_mode=actual_mode,
            status="success",
            message=summary_message,
            data={
                "total_tests": len(related_results),
                "completed": len(completed),
                "failed": len(failed),
                "pending": len(pending),
                "opt_report_path": opt_report_path,
                "master_report_path": master_report_path,
                "top_factor": completed[0].get("factor_name") if completed else None,
                "top_sharpe": completed[0].get("sharpe") if completed else None,
                "top_fitness": completed[0].get("fitness") if completed else None,
                "baseline_sharpe": baseline.get("sharpe") if baseline else None,
                "mode": mode,
            },
        )
    
    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {e}"
        print(f"[错误] {error_msg}")
        traceback.print_exc()
        
        await sdk.submit_result(
            result_mode="notify",
            status="error",
            message=f"Alpha_021 优化脚本执行失败: {error_msg}",
            data={"error_type": type(e).__name__},
        )


if __name__ == "__main__":
    asyncio.run(main())
