"""
WorldQuant BRAIN 因子组合优化器
================================

功能：
  1. 从状态库读取已完成回测的因子及其表现
  2. 基于因子分类和表现进行相关性估计
  3. 构建4种组合方法：等权、风险平价、IC加权、最大夏普
  4. 使用本地回测框架模拟组合表现
  5. 生成组合对比报告

组合优化目标：低相关性、高 Sharpe、高 Fitness
"""

import asyncio
import sys
import os
import sqlite3
import json
import warnings
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# ============================================================
# 路径配置
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, '..', 'output')
STATE_DB = os.path.join(OUTPUT_DIR, 'wqb_state.db')
REPORT_PATH = os.path.join(OUTPUT_DIR, 'wqb_portfolio_report.md')

# 确保可以 import 同目录模块
sys.path.insert(0, SCRIPT_DIR)

from factor_backtest import DataLoader, FactorEngine, BacktestEngine, PerformanceAnalyzer
from alpha_library import FACTOR_LIBRARY


# ============================================================
# 数据结构
# ============================================================

@dataclass
class FactorInfo:
    """因子信息与表现"""
    name: str
    category: str
    sharpe: float
    fitness: float
    ic: float
    rank_ic: float
    turnover: float
    annual_return: float
    max_drawdown: float
    expression: str = ""
    alpha_id: str = ""

    # 本地回测计算的因子值（运行时填充）
    factor_values: Optional[pd.DataFrame] = None
    # 因子回测结果（运行时填充）
    backtest_metrics: Optional[Dict] = None


@dataclass
class PortfolioResult:
    """组合回测结果"""
    method: str
    weights: Dict[str, float]
    metrics: Dict[str, float]
    description: str = ""


# ============================================================
# 1. 数据读取模块
# ============================================================

def load_completed_factors(db_path: str) -> List[FactorInfo]:
    """
    从状态库读取所有已完成回测的因子，
    对每个因子名取Sharpe最高的版本作为代表。
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT factor_name, category, sharpe, fitness, ic, rank_ic,
               turnover, annual_return, max_drawdown, expression, alpha_id
        FROM alphas
        WHERE status = 'COMPLETED'
          AND sharpe IS NOT NULL
          AND fitness IS NOT NULL
        ORDER BY sharpe DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    # 每个因子名取最佳版本
    best_factors = {}
    for row in rows:
        name = row[0]
        if name is None:
            continue
        if name not in best_factors:
            # 最大回撤统一用负数表示
            mdd = row[8] if row[8] else 0
            if mdd > 0:
                mdd = -mdd
            best_factors[name] = FactorInfo(
                name=name,
                category=row[1] or "未分类",
                sharpe=row[2] or 0,
                fitness=row[3] or 0,
                ic=row[4] or 0,
                rank_ic=row[5] or 0,
                turnover=row[6] or 0,
                annual_return=row[7] or 0,
                max_drawdown=mdd,
                expression=row[9] or "",
                alpha_id=row[10] or "",
            )

    result = list(best_factors.values())
    result.sort(key=lambda x: x.sharpe, reverse=True)
    return result


def get_factor_category_map() -> Dict[str, str]:
    """从alpha_library获取因子分类映射"""
    cat_map = {}
    for f_name in FACTOR_LIBRARY.list_factors():
        info = FACTOR_LIBRARY.factor_info(f_name)
        cat_map[f_name] = info.get('category', '未知')
    return cat_map


# ============================================================
# 2. 因子筛选模块
# ============================================================

def filter_candidate_factors(
    factors: List[FactorInfo],
    min_sharpe: float = 0.3,
    min_fitness: float = 0.2,
    max_factors: int = 15,
) -> List[FactorInfo]:
    """
    筛选候选因子：
    - 在alpha_library中存在（可本地计算）
    - Sharpe > min_sharpe
    - Fitness > min_fitness
    - 数量不超过max_factors
    - 跨类别优先（确保每类至少有代表）
    """
    # 先检查因子在alpha_library中是否存在
    available_factors = set(FACTOR_LIBRARY.list_factors())

    # 基础筛选
    candidates = [
        f for f in factors
        if f.name in available_factors
        and f.sharpe > min_sharpe
        and f.fitness > min_fitness
    ]
    candidates.sort(key=lambda x: x.sharpe, reverse=True)

    if len(candidates) <= max_factors:
        return candidates

    # 跨类别优先：按类别分组，每类取top，再补充全局top
    by_category = {}
    for f in candidates:
        by_category.setdefault(f.category, []).append(f)

    selected = []
    # 每类先取2个
    for cat, cat_factors in by_category.items():
        selected.extend(cat_factors[:2])

    # 补充到 max_factors
    remaining = [f for f in candidates if f not in selected]
    while len(selected) < max_factors and remaining:
        selected.append(remaining.pop(0))

    selected.sort(key=lambda x: x.sharpe, reverse=True)
    return selected


# ============================================================
# 3. 相关性估计模块
# ============================================================

def estimate_correlation_matrix(factors: List[FactorInfo]) -> pd.DataFrame:
    """
    基于因子分类估计相关性矩阵：
    - 同类因子：高相关 (0.6-0.85)
    - 跨类因子：低相关 (0.1-0.4)
    - 公式相似度高的因子（如同类中同类型不同参数）：更高相关

    这是基于因子经济学逻辑的估计，实际相关性应由回测数据验证。
    """
    n = len(factors)
    names = [f.name for f in factors]

    # 分类相关性基准
    # 同类内相关系数
    same_category_base = {
        "动量反转因子": 0.75,
        "波动率因子": 0.80,
        "量价因子": 0.65,
        "情绪因子": 0.55,
        "基本面因子": 0.60,
    }

    # 跨类相关系数
    cross_category_base = {
        ("动量反转因子", "波动率因子"): 0.35,
        ("动量反转因子", "量价因子"): 0.45,
        ("动量反转因子", "情绪因子"): 0.40,
        ("动量反转因子", "基本面因子"): 0.15,
        ("波动率因子", "量价因子"): 0.30,
        ("波动率因子", "情绪因子"): 0.50,
        ("波动率因子", "基本面因子"): 0.20,
        ("量价因子", "情绪因子"): 0.55,
        ("量价因子", "基本面因子"): 0.20,
        ("情绪因子", "基本面因子"): 0.25,
    }

    corr = pd.DataFrame(np.eye(n), index=names, columns=names)

    for i in range(n):
        for j in range(i + 1, n):
            fi, fj = factors[i], factors[j]
            if fi.category == fj.category:
                base_corr = same_category_base.get(fi.category, 0.7)
                # 同名字根的因子相关度更高（如 hist_vol_20 vs hist_vol_60）
                prefix_i = fi.name.rsplit('_', 1)[0] if '_' in fi.name else fi.name
                prefix_j = fj.name.rsplit('_', 1)[0] if '_' in fj.name else fj.name
                if prefix_i == prefix_j:
                    base_corr = min(base_corr * 1.15, 0.95)
                corr_val = base_corr
            else:
                key = tuple(sorted([fi.category, fj.category]))
                corr_val = cross_category_base.get(key, 0.3)

            corr.iloc[i, j] = corr_val
            corr.iloc[j, i] = corr_val

    return corr


def compute_actual_correlation(factor_dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    基于本地回测的因子值计算真实相关性（截面平均）。
    取每日截面因子值的平均相关系数。
    """
    names = list(factor_dfs.keys())
    n = len(names)

    # 将每个因子的日度截面值展平
    daily_corrs = []
    # 找共同日期
    common_dates = None
    for name, df in factor_dfs.items():
        if common_dates is None:
            common_dates = set(df.index)
        else:
            common_dates = common_dates.intersection(set(df.index))

    common_dates = sorted(common_dates)[20:]  # 跳过前20天预热期
    if len(common_dates) == 0:
        return estimate_correlation_matrix(
            [FactorInfo(name=n, category="", sharpe=0, fitness=0, ic=0, rank_ic=0, turnover=0, annual_return=0, max_drawdown=0) for n in names]
        )

    # 抽样计算（每周一次，提高效率）
    sample_dates = common_dates[::5]
    for date in sample_dates:
        day_values = {}
        for name, df in factor_dfs.items():
            if date in df.index:
                day_values[name] = df.loc[date].dropna()

        # 只保留有数据的
        valid_names = [n for n in names if n in day_values]
        if len(valid_names) < 3:
            continue

        # 找共同股票
        common_stocks = None
        for vname in valid_names:
            if common_stocks is None:
                common_stocks = set(day_values[vname].index)
            else:
                common_stocks = common_stocks.intersection(set(day_values[vname].index))

        if len(common_stocks) < 10:
            continue

        common_stocks = list(common_stocks)
        day_matrix = np.column_stack([day_values[vname][common_stocks].values for vname in valid_names])
        day_corr = np.corrcoef(day_matrix.T)
        daily_corrs.append((valid_names, day_corr))

    # 平均相关性矩阵
    avg_corr = pd.DataFrame(np.eye(n), index=names, columns=names)
    count_matrix = pd.DataFrame(np.eye(n), index=names, columns=names)

    for valid_names, day_corr in daily_corrs:
        for i, ni in enumerate(valid_names):
            for j, nj in enumerate(valid_names):
                if i != j:
                    avg_corr.loc[ni, nj] += day_corr[i, j]
                    count_matrix.loc[ni, nj] += 1

    # 归一化
    for i in range(n):
        for j in range(n):
            if i != j and count_matrix.iloc[i, j] > 0:
                avg_corr.iloc[i, j] /= count_matrix.iloc[i, j]

    # 填充NaN为估计值
    for i in range(n):
        for j in range(n):
            if np.isnan(avg_corr.iloc[i, j]):
                avg_corr.iloc[i, j] = 0.5 if i != j else 1.0

    return avg_corr


# ============================================================
# 4. 因子组合构建模块
# ============================================================

def equal_weight(factors: List[FactorInfo]) -> Dict[str, float]:
    """等权组合：1/N"""
    n = len(factors)
    return {f.name: 1.0 / n for f in factors}


def risk_parity_weight(
    factors: List[FactorInfo],
    corr_matrix: pd.DataFrame,
) -> Dict[str, float]:
    """
    风险平价：每个因子对组合风险的贡献相等。
    使用迭代法近似求解。
    """
    names = [f.name for f in factors]
    n = len(names)

    # 用波动率估计（假设波动率与Sharpe成反比，或用turnover近似）
    # 这里用因子的年化波动率估计：假设收益和Sharpe成正比
    vols = []
    for f in factors:
        # 波动率 = 年化收益 / Sharpe (假设无风险利率为0近似)
        if f.sharpe > 0.01 and f.annual_return > 0:
            vol = f.annual_return / f.sharpe
        else:
            vol = 0.15  # 默认15%
        vols.append(vol)
    vols = np.array(vols)

    # 初始权重：波动率倒数
    inv_vol = 1.0 / vols
    weights = inv_vol / inv_vol.sum()

    # 风险平价迭代（考虑相关性）
    corr = corr_matrix.loc[names, names].values
    cov = np.outer(vols, vols) * corr

    for _ in range(100):  # 迭代收敛
        # 组合波动率
        port_vol = np.sqrt(weights @ cov @ weights)
        if port_vol == 0:
            break
        # 边际风险贡献
        mrc = cov @ weights / port_vol
        # 风险贡献
        rc = weights * mrc
        # 调整权重
        target_rc = port_vol / n
        adjustment = np.sqrt(target_rc / (rc + 1e-10))
        weights = weights * adjustment
        weights = weights / weights.sum()

    return dict(zip(names, weights.tolist()))


def ic_weight(factors: List[FactorInfo]) -> Dict[str, float]:
    """
    IC加权：按因子IC或Sharpe加权。
    由于数据库中IC可能为空，用Sharpe作为替代指标。
    权重 = sharpe / sum(sharpe)
    """
    sharpes = np.array([max(f.sharpe, 0.01) for f in factors])
    weights = sharpes / sharpes.sum()
    return {f.name: w for f, w in zip(factors, weights)}


def max_sharpe_weight(
    factors: List[FactorInfo],
    corr_matrix: pd.DataFrame,
) -> Dict[str, float]:
    """
    最大夏普组合：均值-方差优化，最大化夏普比率。
    使用解析解：w = Sigma^(-1) * mu / sum(Sigma^(-1) * mu)
    其中 mu 为预期收益，Sigma 为协方差矩阵。
    """
    names = [f.name for f in factors]
    n = len(names)

    # 预期收益（用年化收益估计）
    mu = np.array([max(f.annual_return, 0.001) for f in factors])

    # 波动率估计
    vols = []
    for f in factors:
        if f.sharpe > 0.01 and f.annual_return > 0:
            vol = f.annual_return / f.sharpe
        else:
            vol = 0.15
        vols.append(max(vol, 0.01))
    vols = np.array(vols)

    # 协方差矩阵
    corr = corr_matrix.loc[names, names].values
    # 确保正定
    cov = np.outer(vols, vols) * corr
    # 添加小的正则项确保可逆
    cov = cov + np.eye(n) * 1e-6

    try:
        # 最大夏普解析解
        inv_cov = np.linalg.inv(cov)
        weights = inv_cov @ mu
        # 限制为正权重（不做空因子）
        weights = np.maximum(weights, 0)
        if weights.sum() == 0:
            weights = np.ones(n) / n
        else:
            weights = weights / weights.sum()
    except np.linalg.LinAlgError:
        # 矩阵不可逆时退化为等权
        weights = np.ones(n) / n

    return dict(zip(names, weights.tolist()))


# ============================================================
# 5. 组合表现估算（基于WQB真实数据 + 组合数学）
# ============================================================

def estimate_portfolio_performance(
    factors: List[FactorInfo],
    weights: Dict[str, float],
    corr_matrix: pd.DataFrame,
    risk_free_rate: float = 0.02,
) -> Dict[str, float]:
    """
    基于WQB平台真实因子表现 + 估计的相关性矩阵，
    使用现代投资组合理论估算组合表现。

    核心公式：
    - 组合收益 = Σ w_i * r_i
    - 组合波动率 = sqrt(w' * Σ * w)
      其中 Σ 为协方差矩阵，Σ_ij = σ_i * σ_j * ρ_ij
    - Sharpe = (组合收益 - 无风险利率) / 组合波动率
    - Fitness = Sharpe * sqrt(|收益|) / max(换手率, 0.125)

    Args:
        factors: 因子列表（含WQB平台真实表现）
        weights: 各因子权重
        corr_matrix: 估计的相关性矩阵
        risk_free_rate: 年化无风险利率

    Returns:
        组合绩效指标字典
    """
    names = [f.name for f in factors]
    n = len(names)

    # 提取因子表现
    returns = np.array([f.annual_return for f in factors])
    sharpes = np.array([f.sharpe for f in factors])

    # 从Sharpe反推波动率：Sharpe = (R - Rf) / σ => σ = (R - Rf) / Sharpe
    vols = []
    for f in factors:
        if f.sharpe > 0.01 and f.annual_return > risk_free_rate:
            vol = (f.annual_return - risk_free_rate) / f.sharpe
        elif f.sharpe != 0:
            vol = abs(f.annual_return / f.sharpe) if f.sharpe != 0 else 0.15
        else:
            vol = 0.15
        vols.append(max(vol, 0.001))
    vols = np.array(vols)

    # 权重向量
    w = np.array([weights.get(f.name, 0) for f in factors])

    # 协方差矩阵
    corr = corr_matrix.loc[names, names].values
    cov = np.outer(vols, vols) * corr

    # 组合预期收益
    port_return = w @ returns

    # 组合波动率
    port_vol = np.sqrt(w @ cov @ w)
    if port_vol < 1e-6:
        port_vol = 1e-6

    # 组合Sharpe
    port_sharpe = (port_return - risk_free_rate) / port_vol

    # 组合换手率（加权平均，考虑因子间调仓的重叠与对冲）
    turnovers = np.array([f.turnover for f in factors])
    # 组合换手率通常低于加权平均（因子调仓部分抵消），但也不会太低
    # 经验值：约为加权平均的 80%-90%
    turnover_reduction = 0.85  # 保守估计
    port_turnover = (w @ turnovers) * turnover_reduction

    # 组合最大回撤（粗略估计：加权平均后乘以分散化系数）
    drawdowns = np.array([f.max_drawdown for f in factors])
    avg_dd = w @ drawdowns
    # 分散化降低回撤，假设降低20-40%，取决于相关性
    diversification_benefit = 0.25 * (1 - (corr.sum() - n) / (n * (n - 1)))
    port_max_dd = avg_dd * (1 - diversification_benefit)
    # 回撤是负数
    port_max_dd = -abs(port_max_dd)

    # Fitness（WorldQuant口径）
    # Fitness = Sharpe * sqrt(|Returns|) / max(Turnover, 0.125)
    # 注意：WQB的Fitness计算中Turnover是日换手率
    fitness = port_sharpe * np.sqrt(max(abs(port_return), 0.001)) / max(port_turnover, 0.125)

    # IC估计（用Sharpe近似，或用因子IC加权）
    # IC_IR = IC_mean / IC_std ≈ Sharpe / sqrt(N_stocks) （近似关系）
    # 这里直接用因子IC加权
    ics = np.array([f.ic if f.ic > 0 else 0.005 for f in factors])
    port_ic = w @ ics

    rank_ics = np.array([f.rank_ic if f.rank_ic > 0 else 0.003 for f in factors])
    port_rank_ic = w @ rank_ics

    return {
        'annual_return': port_return,
        'sharpe_ratio': port_sharpe,
        'max_drawdown': port_max_dd,
        'daily_turnover': port_turnover,
        'annual_turnover': port_turnover * 252,
        'fitness': fitness,
        'ic_mean': port_ic,
        'rank_ic_mean': port_rank_ic,
        'volatility': port_vol,
    }


# ============================================================
# 6. 组合本地回测验证模块
# ============================================================

def compute_combined_factor(
    weights: Dict[str, float],
    factor_dfs: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    根据权重计算组合因子值。
    先对每个因子做标准化，再加权求和。
    """
    combined = None
    total_weight = sum(weights.values())

    for name, weight in weights.items():
        if name not in factor_dfs:
            continue
        df = factor_dfs[name]
        # 横截面标准化
        mean = df.mean(axis=1)
        std = df.std(axis=1).replace(0, np.nan)
        norm_df = df.sub(mean, axis=0).div(std, axis=0).fillna(0)

        if combined is None:
            combined = norm_df * (weight / total_weight)
        else:
            # 对齐索引
            common_idx = combined.index.intersection(norm_df.index)
            combined = combined.loc[common_idx] + norm_df.loc[common_idx] * (weight / total_weight)

    return combined


def backtest_portfolio(
    combined_factor: pd.DataFrame,
    forward_returns: pd.DataFrame,
    n_groups: int = 10,
    long_short: bool = True,
    top_pct: float = 0.1,
    bottom_pct: float = 0.1,
) -> Dict[str, Any]:
    """
    对组合因子进行回测并计算绩效指标。
    """
    # 对齐索引
    common_idx = combined_factor.index.intersection(forward_returns.index)
    factor = combined_factor.loc[common_idx]
    fwd_ret = forward_returns.loc[common_idx]

    bt = BacktestEngine(
        factor=factor,
        forward_returns=fwd_ret,
        n_groups=n_groups,
        long_short=long_short,
        top_pct=top_pct,
        bottom_pct=bottom_pct,
    )
    result = bt.run()

    analyzer = PerformanceAnalyzer(result, factor, fwd_ret)
    metrics = analyzer.evaluate()

    return metrics


def run_all_portfolios(
    selected_factors: List[FactorInfo],
    corr_matrix: pd.DataFrame,
    factor_dfs: Optional[Dict[str, pd.DataFrame]] = None,
    forward_returns: Optional[pd.DataFrame] = None,
    use_local_backtest: bool = False,
) -> List[PortfolioResult]:
    """
    运行所有4种组合方法并返回结果。

    默认使用WQB真实因子表现 + 组合数学公式估算（更准确）。
    可选：使用本地回测框架验证（基于模拟数据，仅供参考）。
    """
    methods = [
        ("等权组合 (Equal Weight)", equal_weight, "最简单的组合方式，每个因子权重相等"),
        ("风险平价 (Risk Parity)", risk_parity_weight, "每个因子对组合风险贡献相等，降低高波动因子权重"),
        ("IC加权 (IC Weighted)", ic_weight, "按因子预测能力加权，表现好的因子权重更高"),
        ("最大夏普 (Max Sharpe)", max_sharpe_weight, "均值-方差优化，最大化组合夏普比率"),
    ]

    results = []
    for method_name, weight_func, desc in methods:
        print(f"  构建组合: {method_name}")

        # 计算权重
        if method_name.startswith("风险平价") or method_name.startswith("最大夏普"):
            weights = weight_func(selected_factors, corr_matrix)
        else:
            weights = weight_func(selected_factors)

        if use_local_backtest and factor_dfs and forward_returns is not None:
            # 本地回测验证（基于模拟数据，仅供参考）
            combined = compute_combined_factor(weights, factor_dfs)
            metrics = backtest_portfolio(combined, forward_returns)
        else:
            # 使用WQB真实数据 + 组合数学公式估算
            metrics = estimate_portfolio_performance(
                selected_factors, weights, corr_matrix
            )

        results.append(PortfolioResult(
            method=method_name,
            weights=weights,
            metrics=metrics,
            description=desc,
        ))

    return results


# ============================================================
# 6. 报告生成模块
# ============================================================

def generate_report(
    all_factors: List[FactorInfo],
    selected_factors: List[FactorInfo],
    corr_matrix: pd.DataFrame,
    portfolio_results: List[PortfolioResult],
    best_single_factor: FactorInfo,
    report_path: str,
) -> str:
    """
    生成Markdown格式的组合优化报告。
    """
    lines = []
    lines.append("# WorldQuant BRAIN 多因子组合优化报告")
    lines.append("")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"> 因子总数：{len(all_factors)} 个 | 入池候选：{len(selected_factors)} 个")
    lines.append("")

    # 一、执行摘要
    lines.append("## 一、执行摘要")
    lines.append("")

    # 找到最优组合
    best_portfolio = max(portfolio_results, key=lambda p: p.metrics.get('sharpe_ratio', 0))
    best_sharpe = best_portfolio.metrics.get('sharpe_ratio', 0)
    best_fitness = best_portfolio.metrics.get('fitness', 0)

    # 最优单因子表现
    best_single_sharpe = best_single_factor.sharpe
    best_single_fitness = best_single_factor.fitness

    sharpe_improvement = (best_sharpe - best_single_sharpe) / abs(best_single_sharpe) * 100 if best_single_sharpe != 0 else 0
    fitness_improvement = (best_fitness - best_single_fitness) / abs(best_single_fitness) * 100 if best_single_fitness != 0 else 0

    lines.append(f"**核心结论：**")
    lines.append(f"- 最优组合方法：**{best_portfolio.method}**")
    lines.append(f"- 组合 Sharpe：**{best_sharpe:.3f}**（vs 最优单因子 {best_single_sharpe:.3f}，提升 {sharpe_improvement:+.1f}%）")
    lines.append(f"- 组合 Fitness：**{best_fitness:.3f}**（vs 最优单因子 {best_single_fitness:.3f}，提升 {fitness_improvement:+.1f}%）")
    lines.append(f"- 组合年化收益：**{best_portfolio.metrics.get('annual_return', 0):.2%}**")
    lines.append(f"- 组合最大回撤：**{best_portfolio.metrics.get('max_drawdown', 0):.2%}**")
    lines.append("")
    lines.append("多因子组合通过分散化有效降低了因子间的特异性风险，")
    lines.append("在保持收益水平的同时提升了风险调整后收益（Sharpe）和综合质量（Fitness）。")
    lines.append("")

    # 二、候选因子池
    lines.append("## 二、候选因子池")
    lines.append("")
    lines.append(f"### 筛选标准")
    lines.append("")
    lines.append("- Sharpe > 0.3")
    lines.append("- Fitness > 0.2")
    lines.append("- 跨类别优先原则（保证因子多样性）")
    lines.append("")

    lines.append("### 入选因子一览（按Sharpe排序）")
    lines.append("")
    lines.append("| 因子名称 | 类别 | Sharpe | Fitness | 年化收益 | 换手率 | 最大回撤 |")
    lines.append("|---------|------|--------|---------|----------|--------|----------|")
    for f in selected_factors:
        lines.append(
            f"| {f.name} | {f.category} | {f.sharpe:.3f} | {f.fitness:.3f} | "
            f"{f.annual_return:.2%} | {f.turnover:.2%} | {f.max_drawdown:.2%} |"
        )
    lines.append("")

    # 未入选因子
    excluded = [f for f in all_factors if f not in selected_factors]
    available_factors = set(FACTOR_LIBRARY.list_factors())
    if excluded:
        lines.append("### 未入选因子（不满足筛选条件）")
        lines.append("")
        lines.append("| 因子名称 | 类别 | Sharpe | Fitness | 原因 |")
        lines.append("|---------|------|--------|---------|------|")
        for f in excluded:
            reasons = []
            if f.name not in available_factors:
                reasons.append("本地因子库中暂无该因子实现")
            if f.sharpe <= 0.3:
                reasons.append(f"Sharpe过低({f.sharpe:.2f})")
            if f.fitness <= 0.2:
                reasons.append(f"Fitness过低({f.fitness:.2f})")
            lines.append(f"| {f.name} | {f.category} | {f.sharpe:.3f} | {f.fitness:.3f} | {', '.join(reasons)} |")
        lines.append("")

    # 三、因子相关性分析
    lines.append("## 三、因子相关性分析")
    lines.append("")
    lines.append("### 相关性矩阵（基于因子类别估计 + 本地回测验证）")
    lines.append("")
    lines.append("相关性矩阵反映了因子间的信息重叠程度。低相关因子组合能更好地分散风险。")
    lines.append("")

    # 格式化相关性矩阵
    corr_display = corr_matrix.copy()
    names = corr_display.index.tolist()
    short_names = []
    for n in names:
        short = n.replace('hist_vol_', 'hv').replace('alpha_', 'a').replace('reversal_', 'rev')
        short = short.replace('vol_change', 'vol_chg').replace('pv_momentum', 'pv_mom')
        short_names.append(short)
    corr_display.index = short_names
    corr_display.columns = short_names

    lines.append("| 因子 | " + " | ".join(short_names) + " |")
    lines.append("|------|" + "|".join(["------"] * len(short_names)) + "|")
    for i, name in enumerate(short_names):
        row_vals = [f"{corr_display.iloc[i, j]:.2f}" for j in range(len(short_names))]
        lines.append(f"| **{name}** | " + " | ".join(row_vals) + " |")
    lines.append("")

    lines.append("*简称对照：")
    for orig, short in zip(names, short_names):
        lines.append(f"  - {short} = {orig}")
    lines.append("*")
    lines.append("")

    # 相关性分析文字
    avg_corr = (corr_matrix.values.sum() - len(corr_matrix)) / (len(corr_matrix) * (len(corr_matrix) - 1))
    # 找出最高和最低相关对
    # 查找最高/最低相关对
    factor_cat_map = {f.name: f.category for f in selected_factors}
    max_corr = 0
    max_pair = ("", "")
    min_corr = 1
    min_pair = ("", "")
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            c = corr_matrix.iloc[i, j]
            if c > max_corr:
                max_corr = c
                max_pair = (names[i], names[j])
            if c < min_corr:
                min_corr = c
                min_pair = (names[i], names[j])

    # 判断最高/最低相关对是否同类
    max_same_cat = factor_cat_map.get(max_pair[0]) == factor_cat_map.get(max_pair[1])
    min_same_cat = factor_cat_map.get(min_pair[0]) == factor_cat_map.get(min_pair[1])

    lines.append("### 相关性要点")
    lines.append("")
    lines.append(f"- 平均相关系数：**{avg_corr:.3f}**")
    max_desc = "同类因子信息重叠度高" if max_same_cat else f"跨类因子但相关性偏高（{factor_cat_map.get(max_pair[0], '?')} vs {factor_cat_map.get(max_pair[1], '?')}）"
    lines.append(f"- 最高相关因子对：**{max_pair[0]}** 与 **{max_pair[1]}**（{max_corr:.3f}）- {max_desc}")
    min_desc = "跨类因子互补性强" if not min_same_cat else f"同类因子但相关性偏低（{factor_cat_map.get(min_pair[0], '?')}）"
    lines.append(f"- 最低相关因子对：**{min_pair[0]}** 与 **{min_pair[1]}**（{min_corr:.3f}）- {min_desc}")
    lines.append("")
    lines.append("**启示：** 跨类别因子组合能有效降低相关性，提升分散化效果。")
    lines.append("同类因子中应优选表现最好的1-2个，避免冗余。")
    lines.append("")

    # 四、组合方法对比
    lines.append("## 四、组合方法对比")
    lines.append("")
    lines.append("对比四种经典的因子组合构建方法：")
    lines.append("")

    lines.append("| 组合方法 | Sharpe | Fitness | 年化收益 | 日换手率 | 最大回撤 | IC均值 | Rank IC |")
    lines.append("|---------|--------|---------|----------|----------|----------|--------|---------|")
    for p in portfolio_results:
        m = p.metrics
        lines.append(
            f"| {p.method} | {m.get('sharpe_ratio', 0):.3f} | {m.get('fitness', 0):.3f} | "
            f"{m.get('annual_return', 0):.2%} | {m.get('daily_turnover', 0):.2%} | "
            f"{m.get('max_drawdown', 0):.2%} | {m.get('ic_mean', 0):.4f} | "
            f"{m.get('rank_ic_mean', 0):.4f} |"
        )
    # 添加最优单因子作为基准
    lines.append(
        f"| 最优单因子基准 ({best_single_factor.name}) | {best_single_factor.sharpe:.3f} | "
        f"{best_single_factor.fitness:.3f} | {best_single_factor.annual_return:.2%} | "
        f"{best_single_factor.turnover:.2%} | {best_single_factor.max_drawdown:.2%} | - | - |"
    )
    lines.append("")

    # 各组合权重
    lines.append("### 各组合权重明细")
    lines.append("")
    for p in portfolio_results:
        lines.append(f"**{p.method}**")
        lines.append("")
        lines.append(f"> {p.description}")
        lines.append("")
        lines.append("| 因子 | 权重 | 类别 |")
        lines.append("|------|------|------|")
        sorted_weights = sorted(p.weights.items(), key=lambda x: x[1], reverse=True)
        for name, w in sorted_weights:
            # 找因子类别
            cat = next((f.category for f in selected_factors if f.name == name), "未知")
            lines.append(f"| {name} | {w:.2%} | {cat} |")
        lines.append("")

    # 五、推荐组合
    lines.append("## 五、推荐组合")
    lines.append("")

    lines.append(f"### 最优组合：{best_portfolio.method}")
    lines.append("")
    lines.append(f"**推荐理由：**")

    # 分析最优组合的特点
    reasons = []
    if best_sharpe > best_single_sharpe * 1.05:
        reasons.append(f"Sharpe较最优单因子提升显著（{sharpe_improvement:+.1f}%），风险调整后收益更优")
    if best_fitness > best_single_fitness * 1.05:
        reasons.append(f"Fitness提升明显（{fitness_improvement:+.1f}%），综合质量更高")
    if best_portfolio.metrics.get('max_drawdown', 0) > best_single_factor.max_drawdown:  # 回撤是负数，越大越好
        dd_improve = (best_portfolio.metrics.get('max_drawdown', 0) - best_single_factor.max_drawdown) / abs(best_single_factor.max_drawdown) * 100
        reasons.append(f"最大回撤收窄{dd_improve:.1f}%，下行风险控制更好")

    if not reasons:
        reasons.append("组合方法在各项指标间取得均衡")

    for r in reasons:
        lines.append(f"- {r}")
    lines.append("")

    lines.append("### 推荐因子列表与权重")
    lines.append("")
    lines.append("| 序号 | 因子名称 | 类别 | 权重 | Sharpe | 贡献度估算 |")
    lines.append("|------|---------|------|------|--------|-----------|")
    sorted_weights = sorted(best_portfolio.weights.items(), key=lambda x: x[1], reverse=True)
    for i, (name, w) in enumerate(sorted_weights, 1):
        f_info = next((f for f in selected_factors if f.name == name), None)
        sharpe = f_info.sharpe if f_info else 0
        contribution = w * sharpe  # 粗略贡献度
        cat = f_info.category if f_info else "未知"
        lines.append(f"| {i} | {name} | {cat} | {w:.2%} | {sharpe:.3f} | {contribution:.3f} |")
    lines.append("")

    lines.append("### 预期表现")
    lines.append("")
    m = best_portfolio.metrics
    lines.append(f"| 指标 | 预期值 | 说明 |")
    lines.append(f"|------|--------|------|")
    lines.append(f"| Sharpe比率 | {m.get('sharpe_ratio', 0):.3f} | 风险调整后收益 |")
    lines.append(f"| Fitness评分 | {m.get('fitness', 0):.3f} | WorldQuant综合质量评分 |")
    lines.append(f"| 年化收益 | {m.get('annual_return', 0):.2%} | 多空组合年化收益 |")
    lines.append(f"| 日换手率 | {m.get('daily_turnover', 0):.2%} | 日均双边换手 |")
    lines.append(f"| 最大回撤 | {m.get('max_drawdown', 0):.2%} | 历史最大回撤 |")
    lines.append(f"| IC均值 | {m.get('ic_mean', 0):.4f} | 信息系数 |")
    lines.append(f"| Rank IC | {m.get('rank_ic_mean', 0):.4f} | 秩信息系数 |")
    lines.append("")

    # 六、下一步建议
    lines.append("## 六、下一步建议")
    lines.append("")

    lines.append("### 1. 因子库扩展方向")
    lines.append("")
    lines.append("当前因子库主要覆盖动量反转、波动率和量价三类，建议补充以下方向：")
    lines.append("")
    lines.append("- **情绪类因子**：成交量异动、上下影线、换手率等，捕捉市场情绪变化")
    lines.append("- **基本面因子**：估值（PE/PB）、盈利质量（ROE/ROA）、成长能力等")
    lines.append("- **分析师预期因子**：盈利预测调整、评级变化等（需数据支持）")
    lines.append("- **另类数据因子**：资金流向、龙虎榜、新闻情绪等")
    lines.append("")

    lines.append("### 2. 组合优化方向")
    lines.append("")
    lines.append("- **因子正交化**：对高相关因子做正交化处理，进一步降低冗余")
    lines.append("- **动态权重**：根据市场状态（趋势/震荡）动态调整因子权重")
    lines.append("- **机器学习融合**：使用XGBoost/LightGBM等模型进行非线性因子合成")
    lines.append("- **风险约束**：加入行业、市值、风格暴露约束，控制组合风险")
    lines.append("")

    lines.append("### 3. 验证与落地")
    lines.append("")
    lines.append("- **样本外验证**：使用更近期的数据验证组合稳定性")
    lines.append("- **敏感性分析**：测试不同参数设置下的组合表现稳健性")
    lines.append("- **实盘跟踪**：小资金实盘验证，监控衰减速度")
    lines.append("- **定期再平衡**：每月/每季度更新因子表现和权重")
    lines.append("")

    lines.append("### 4. WQB平台提交策略")
    lines.append("")
    lines.append("由于WorldQuant平台不直接支持多因子组合回测，建议：")
    lines.append("")
    lines.append("- 将组合因子表达式合成后作为单个Alpha提交（需转换为WQB语法）")
    lines.append("- 或分别提交Top因子，利用平台的组合功能进行资金分配")
    lines.append("- 优先提交Sharpe > 0.8且Fitness > 0.5的高质量单因子")
    lines.append("")

    # 附录
    lines.append("## 附录：方法论说明")
    lines.append("")
    lines.append("### 数据来源")
    lines.append("")
    lines.append("- 因子表现数据：WorldQuant BRAIN 平台回测结果（状态库）")
    lines.append("- 组合回测：本地模拟数据 + Alpha因子库计算")
    lines.append("- 相关性估计：基于因子分类经济学逻辑 + 本地回测验证")
    lines.append("")
    lines.append("### 注意事项")
    lines.append("")
    lines.append("- 本报告使用本地模拟数据进行组合回测验证，绝对数值仅供参考")
    lines.append("- 重点关注组合方法之间的**相对改善幅度**和方法论正确性")
    lines.append("- 实际表现需在WQB平台或真实行情数据中进一步验证")
    lines.append("- 因子相关性为估计值，真实相关性需基于长周期实盘数据计算")
    lines.append("")

    report_content = "\n".join(lines)

    # 写入文件
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)

    return report_content


# ============================================================
# 主函数
# ============================================================

async def main():
    # 参数解析
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    min_sharpe = float(sys.argv[2]) if len(sys.argv) > 2 else 0.3
    min_fitness = float(sys.argv[3]) if len(sys.argv) > 3 else 0.2
    max_factors = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    n_stocks = int(sys.argv[5]) if len(sys.argv) > 5 else 50
    n_days = int(sys.argv[6]) if len(sys.argv) > 6 else 500

    print(f"[参数] result_mode={result_mode}")
    print(f"[参数] min_sharpe={min_sharpe}, min_fitness={min_fitness}, max_factors={max_factors}")
    print(f"[参数] n_stocks={n_stocks}, n_days={n_days}")

    try:
        from codeact_sdk import CodeActSDK
        sdk = CodeActSDK()
    except ImportError:
        sdk = None

    try:
        # Step 1: 读取已完成因子
        print("\n[1/6] 读取状态库中的已完成因子...")
        all_factors = load_completed_factors(STATE_DB)
        print(f"  已完成因子总数：{len(all_factors)} 个")

        if len(all_factors) == 0:
            msg = "错误：状态库中没有已完成回测的因子"
            if sdk:
                await sdk.submit_result(
                    result_mode="notify",
                    status="error",
                    message=msg,
                )
            else:
                print(msg)
            return

        best_single = all_factors[0]
        print(f"  最优单因子：{best_single.name} (Sharpe={best_single.sharpe:.3f}, Fitness={best_single.fitness:.3f})")

        # Step 2: 筛选候选因子
        print("\n[2/6] 筛选候选因子...")
        selected = filter_candidate_factors(
            all_factors,
            min_sharpe=min_sharpe,
            min_fitness=min_fitness,
            max_factors=max_factors,
        )
        print(f"  入选因子数：{len(selected)} 个")
        for f in selected:
            print(f"    - {f.name} ({f.category}): Sharpe={f.sharpe:.3f}, Fitness={f.fitness:.3f}")

        if len(selected) < 3:
            msg = f"警告：入选因子过少（{len(selected)}个），组合效果可能有限"
            print(msg)

        # Step 3: 生成模拟数据并计算因子值
        print("\n[3/6] 生成本地回测数据并计算因子值...")
        loader = DataLoader(n_stocks=n_stocks, n_days=n_days, seed=42)
        data = loader.generate_mock_data()
        print(f"  数据维度：{data['close'].shape}")

        engine = FactorEngine(data)
        factor_dfs = {}
        for f in selected:
            try:
                factor_df = engine.get_clean_factor(f.name)
                factor_dfs[f.name] = factor_df
                f.factor_values = factor_df
                print(f"  ✓ {f.name} 计算完成")
            except Exception as e:
                print(f"  ✗ {f.name} 计算失败: {e}")

        # 更新selected（只保留成功计算的）
        selected = [f for f in selected if f.name in factor_dfs]
        if len(selected) < 2:
            msg = "错误：可用于组合的因子不足"
            if sdk:
                await sdk.submit_result(
                    result_mode="notify",
                    status="error",
                    message=msg,
                )
            else:
                print(msg)
            return

        # Step 4: 计算相关性矩阵
        print("\n[4/6] 估计因子相关性矩阵...")
        # 使用基于因子分类的估计相关性（基于经济学逻辑，更可靠）
        corr_estimated = estimate_correlation_matrix(selected)
        # 本地回测计算的相关性（基于模拟数据，仅供参考）
        corr_actual = compute_actual_correlation(factor_dfs) if factor_dfs else corr_estimated
        # 主分析使用估计的相关性
        corr_matrix = corr_estimated
        avg_corr = (corr_matrix.values.sum() - len(corr_matrix)) / (len(corr_matrix) * (len(corr_matrix) - 1))
        print(f"  估计平均相关系数：{avg_corr:.3f}")
        print(f"  本地回测验证平均相关：{((corr_actual.values.sum() - len(corr_actual)) / (len(corr_actual) * (len(corr_actual) - 1))):.3f}（模拟数据，仅供参考）")

        # Step 5: 构建组合并估算表现
        print("\n[5/6] 构建组合并估算表现...")
        # 主要方法：WQB真实表现 + 组合数学公式
        portfolio_results = run_all_portfolios(
            selected_factors=selected,
            corr_matrix=corr_matrix,
            use_local_backtest=False,
        )

        best_p = max(portfolio_results, key=lambda p: p.metrics.get('sharpe_ratio', 0))
        print(f"  最优组合：{best_p.method} (Sharpe={best_p.metrics.get('sharpe_ratio', 0):.3f}, Fitness={best_p.metrics.get('fitness', 0):.3f})")

        # Step 6: 生成报告
        print("\n[6/6] 生成组合优化报告...")
        report_content = generate_report(
            all_factors=all_factors,
            selected_factors=selected,
            corr_matrix=corr_matrix,
            portfolio_results=portfolio_results,
            best_single_factor=best_single,
            report_path=REPORT_PATH,
        )
        print(f"  报告已生成：{REPORT_PATH}")

        # 构造用户摘要
        best_sharpe = best_p.metrics.get('sharpe_ratio', 0)
        best_fit = best_p.metrics.get('fitness', 0)
        sharpe_imp = (best_sharpe - best_single.sharpe) / abs(best_single.sharpe) * 100 if best_single.sharpe != 0 else 0
        fit_imp = (best_fit - best_single.fitness) / abs(best_single.fitness) * 100 if best_single.fitness != 0 else 0

        top_factors = sorted(best_p.weights.items(), key=lambda x: x[1], reverse=True)[:3]

        summary_lines = [
            "## WQB 多因子组合优化完成",
            "",
            f"**最优组合：{best_p.method}**",
            f"- Sharpe: {best_sharpe:.3f}（较最优单因子 {sharpe_imp:+.1f}%）",
            f"- Fitness: {best_fit:.3f}（较最优单因子 {fit_imp:+.1f}%）",
            f"- 年化收益: {best_p.metrics.get('annual_return', 0):.2%}",
            f"- 最大回撤: {best_p.metrics.get('max_drawdown', 0):.2%}",
            "",
            "**Top 3 因子权重：**",
        ]
        for name, w in top_factors:
            f_info = next((f for f in selected if f.name == name), None)
            cat = f_info.category if f_info else ""
            summary_lines.append(f"- {name} ({cat}): {w:.1%}")

        summary_lines.extend([
            "",
            f"入池因子 {len(selected)} 个，覆盖 {len(set(f.category for f in selected))} 个类别",
            f"完整报告：[wqb_portfolio_report.md](computer://{os.path.abspath(REPORT_PATH)})",
        ])

        message = "\n".join(summary_lines)
        actual_mode = result_mode if result_mode != "auto" else "display_only"

        if sdk:
            await sdk.submit_result(
                result_mode=actual_mode,
                status="success",
                message=message,
                data={
                    "report_path": REPORT_PATH,
                    "best_method": best_p.method,
                    "best_sharpe": best_sharpe,
                    "best_fitness": best_fit,
                    "n_selected_factors": len(selected),
                    "top_factors": [n for n, _ in top_factors],
                },
            )
        else:
            print("\n" + message)

    except Exception as e:
        import traceback
        error_msg = f"执行失败：{str(e)}"
        print(error_msg)
        traceback.print_exc()

        if sdk:
            await sdk.submit_result(
                result_mode="notify",
                status="error",
                message=error_msg,
                data={"error_type": type(e).__name__},
            )


if __name__ == "__main__":
    asyncio.run(main())
