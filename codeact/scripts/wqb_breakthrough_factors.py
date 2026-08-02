#!/usr/bin/env python3
"""
WorldQuant BRAIN 跃迁因子研究脚本 - wqb_breakthrough_factors.py
============================================================

目标：从因子逻辑本质出发，设计并验证一批全新的 Alpha 因子，
目标是同时通过 WQB 所有提交检查：
  Sharpe ≥ 1.25, Fitness ≥ 1.0, SELF_CORRELATION ≤ 0.7,
  换手率 0.01-0.7, 集中度通过, 子样本夏普通过。

核心原则：不做现有因子的加权微调，从因子逻辑层面创新。

六个逻辑方向：
  方向一：变化率因子（动量的加速度）
  方向二：条件/事件驱动因子
  方向三：横截面相对变化率（排名加速度）
  方向四：多因子非线性组合
  方向五：隔夜/日内结构的高阶变体
  方向六：量价背离的变化率

用法：
  python wqb_breakthrough_factors.py [result_mode] [max_factors] [submit_check]

参数：
  result_mode:   display_only / notify / auto (默认: display_only)
  max_factors:   最大提交数量 (默认: 40, 即全部36个)
  submit_check:  1=对合格因子做提交检查, 0=只回测 (默认: 1)
"""

import asyncio
import sys
import os
import json
import time
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

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

# 提交间隔（严格限流）- 免费账号限流严，50秒更稳妥
SUBMIT_INTERVAL = 50.0
# 提交检查间隔
CHECK_INTERVAL = 20.0

# 合格阈值
SHARPE_THRESHOLD = 1.25
FITNESS_THRESHOLD = 1.0


# ============================================================
# 跃迁因子 FASTEXPR 映射表（6个方向，36个因子）
# ============================================================

BREAKTHROUGH_FACTORS = {
    # ================================================================
    # 方向一：变化率因子（动量的加速度）
    # 逻辑：不是买强者，是买"变强速度最快的"。价格动量的一阶导数。
    # 自相关天然低于纯动量。
    # ================================================================
    "mom_accel_5d3": {
        "category": "变化率因子",
        "direction": "方向一：变化率因子",
        "description": "5日收益的3日变化量排名（动量加速度，短周期）",
        "logic": "动量一阶导数：收益变化越快，动量加速度越大",
        "fastexpr": "rank(ts_delta(divide(ts_delta(close, 5), ts_delay(close, 5)), 3))",
        "version": "breakthrough_v1",
    },
    "mom_accel_10d5": {
        "category": "变化率因子",
        "direction": "方向一：变化率因子",
        "description": "10日收益的5日变化量排名（动量加速度，中周期）",
        "logic": "动量一阶导数：中期收益变化速度",
        "fastexpr": "rank(ts_delta(divide(ts_delta(close, 10), ts_delay(close, 10)), 5))",
        "version": "breakthrough_v1",
    },
    "mom_accel_20d10": {
        "category": "变化率因子",
        "direction": "方向一：变化率因子",
        "description": "20日收益的10日变化量排名（动量加速度，长周期）",
        "logic": "动量一阶导数：长期收益变化速度",
        "fastexpr": "rank(ts_delta(divide(ts_delta(close, 20), ts_delay(close, 20)), 10))",
        "version": "breakthrough_v1",
    },
    "volume_accel_5d3": {
        "category": "变化率因子",
        "direction": "方向一：变化率因子",
        "description": "成交量5日变化率的3日加速度排名",
        "logic": "成交量加速度：量能变化越快，信号越强",
        "fastexpr": "rank(ts_delta(divide(ts_delta(volume, 5), ts_delay(volume, 5)), 3))",
        "version": "breakthrough_v1",
    },
    "vol_accel_5d5": {
        "category": "变化率因子",
        "direction": "方向一：变化率因子",
        "description": "20日波动率的5日变化率排名（波动率加速度）",
        "logic": "波动率加速度：波动快速上升的股票",
        "fastexpr": "rank(ts_delta(ts_std_dev(returns, 20), 5))",
        "version": "breakthrough_v1",
    },
    "price_vol_accel": {
        "category": "变化率因子",
        "direction": "方向一：变化率因子",
        "description": "价加速度×量排名变化（量价齐升的加速度）",
        "logic": "量价加速度共振：价格加速上涨且量排名上升",
        "fastexpr": "rank(multiply(ts_delta(divide(ts_delta(close, 5), ts_delay(close, 5)), 2), ts_delta(ts_rank(volume, 20), 2)))",
        "version": "breakthrough_v1",
    },

    # ================================================================
    # 方向二：条件/事件驱动因子
    # 逻辑：只在极端条件下出信号，大部分时间中性。
    # 天然低自相关（因为经常变）。
    # ================================================================
    "extreme_gap_reversal": {
        "category": "事件驱动因子",
        "direction": "方向二：条件/事件驱动因子",
        "description": "极端缺口日的反转信号（缺口越大，反转越强）",
        "logic": "事件驱动：缺口越极端，反转概率越高",
        "fastexpr": "multiply(ts_rank(abs(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1))), 20), reverse(rank(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)))))",
        "version": "breakthrough_v1",
    },
    "vol_breakout_short": {
        "category": "事件驱动因子",
        "direction": "方向二：条件/事件驱动因子",
        "description": "波动率突然上升时做空放量的股票",
        "logic": "波动率突破事件：放量+波动率跳升=看空",
        "fastexpr": "multiply(rank(ts_delta(ts_std_dev(returns, 20), 5)), reverse(rank(volume)))",
        "version": "breakthrough_v1",
    },
    "extreme_rev_weighted": {
        "category": "事件驱动因子",
        "direction": "方向二：条件/事件驱动因子",
        "description": "极端涨跌幅日的反转加权（涨跌幅越极端，反转信号越强）",
        "logic": "极端日反转：涨跌幅越极端，次日反转概率越高",
        "fastexpr": "multiply(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), reverse(rank(divide(ts_delta(close, 1), ts_delay(close, 1)))))",
        "version": "breakthrough_v1",
    },
    "vol_spike_reversal": {
        "category": "事件驱动因子",
        "direction": "方向二：条件/事件驱动因子",
        "description": "放量日的反转信号更强（量比60日排名×日度反转）",
        "logic": "放量反转：异常放量日的反转信号更可靠",
        "fastexpr": "multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(rank(divide(ts_delta(close, 1), ts_delay(close, 1)))))",
        "version": "breakthrough_v1",
    },
    "cond_vol_regime": {
        "category": "事件驱动因子",
        "direction": "方向二：条件/事件驱动因子",
        "description": "高波动市买低波，低波动市买动量（波动率状态切换）",
        "logic": "波动率状态切换：不同市况下使用不同因子",
        "fastexpr": "if_else(greater(ts_std_dev(returns, 20), ts_mean(ts_std_dev(returns, 60), 20)), reverse(rank(ts_std_dev(returns, 20))), rank(divide(ts_delta(close, 10), ts_delay(close, 10))))",
        "version": "breakthrough_v1",
    },
    "new_high_momentum": {
        "category": "事件驱动因子",
        "direction": "方向二：条件/事件驱动因子",
        "description": "突破20日新高的幅度×日内涨幅（突破确认动量）",
        "logic": "突破事件：创新高且日内强势=动量确认",
        "fastexpr": "multiply(rank(divide(subtract(close, kth_element(high, 20, k=20)), kth_element(high, 20, k=20))), rank(divide(subtract(close, open), open)))",
        "version": "breakthrough_v1",
    },

    # ================================================================
    # 方向三：横截面相对变化率（排名加速度）
    # 逻辑：截面排名的变化率。截面动量的加速度。
    # ================================================================
    "rank_mom_10d5": {
        "category": "排名变化率",
        "direction": "方向三：横截面相对变化率",
        "description": "10日收益排名的5日变化量（排名动量）",
        "logic": "截面排名动量：收益排名上升最快的股票",
        "fastexpr": "ts_delta(rank(divide(ts_delta(close, 10), ts_delay(close, 10))), 5)",
        "version": "breakthrough_v1",
    },
    "rank_accel_close": {
        "category": "排名变化率",
        "direction": "方向三：横截面相对变化率",
        "description": "收盘价排名的加速度（二阶导数）",
        "logic": "截面排名加速度：排名上升速度越来越快",
        "fastexpr": "ts_delta(ts_delta(rank(close), 5), 3)",
        "version": "breakthrough_v1",
    },
    "vol_rank_change_3d": {
        "category": "排名变化率",
        "direction": "方向三：横截面相对变化率",
        "description": "成交量排名的3日变化量",
        "logic": "量能排名变化：成交量排名快速上升的股票",
        "fastexpr": "ts_delta(rank(volume), 3)",
        "version": "breakthrough_v1",
    },
    "vol_rank_mom_5d": {
        "category": "排名变化率",
        "direction": "方向三：横截面相对变化率",
        "description": "波动率排名的5日变化量",
        "logic": "波动率排名变化：波动率排名快速变化的股票",
        "fastexpr": "ts_delta(rank(ts_std_dev(returns, 20)), 5)",
        "version": "breakthrough_v1",
    },
    "rank_of_rank_change": {
        "category": "排名变化率",
        "direction": "方向三：横截面相对变化率",
        "description": "排名变化量的横截面排名（排名变化率的排名）",
        "logic": "排名变化的相对强度：排名上升幅度在全市场的排位",
        "fastexpr": "rank(ts_delta(rank(close), 5))",
        "version": "breakthrough_v1",
    },
    "vwap_rank_change": {
        "category": "排名变化率",
        "direction": "方向三：横截面相对变化率",
        "description": "价格相对VWAP偏离的排名变化率",
        "logic": "强弱变化：价格相对VWAP的排名变化速度",
        "fastexpr": "ts_delta(rank(divide(subtract(close, vwap), vwap)), 3)",
        "version": "breakthrough_v1",
    },

    # ================================================================
    # 方向四：多因子非线性组合
    # 逻辑：不是加权求和，是乘法、条件选择等非线性组合，
    # 降低与各成分的相关性。
    # ================================================================
    "rank_mul_mom_vol": {
        "category": "非线性组合",
        "direction": "方向四：多因子非线性组合",
        "description": "价格动量×量能时序排名的横截面排名",
        "logic": "动量×量能的非线性组合：放量动量更强",
        "fastexpr": "rank(multiply(divide(ts_delta(close, 5), ts_delay(close, 5)), ts_rank(volume, 20)))",
        "version": "breakthrough_v1",
    },
    "mom_minus_vol_rank": {
        "category": "非线性组合",
        "direction": "方向四：多因子非线性组合",
        "description": "动量排名-波动率排名（做多动量做空低波的多空组合排名）",
        "logic": "多空组合排名：寻找高动量且低波动的股票",
        "fastexpr": "subtract(rank(divide(ts_delta(close, 10), ts_delay(close, 10))), rank(ts_std_dev(returns, 20)))",
        "version": "breakthrough_v1",
    },
    "low_vol_momentum": {
        "category": "非线性组合",
        "direction": "方向四：多因子非线性组合",
        "description": "动量排名×低波排名（低波动动量因子）",
        "logic": "低波动量：在低波动股票中找动量强的",
        "fastexpr": "multiply(rank(divide(ts_delta(close, 5), ts_delay(close, 5))), reverse(rank(ts_std_dev(returns, 20))))",
        "version": "breakthrough_v1",
    },
    "sign_mul_rank": {
        "category": "非线性组合",
        "direction": "方向四：多因子非线性组合",
        "description": "动量方向×动量幅度排名（有方向的动量强度排名）",
        "logic": "方向×强度：只在动量方向上做强度排名",
        "fastexpr": "multiply(sign(divide(ts_delta(close, 10), ts_delay(close, 10))), rank(abs(divide(ts_delta(close, 10), ts_delay(close, 10)))))",
        "version": "breakthrough_v1",
    },
    "cond_rev_mom": {
        "category": "非线性组合",
        "direction": "方向四：多因子非线性组合",
        "description": "极端日反转，非极端日动量（条件切换因子）",
        "logic": "自适应切换：极端日反转，平日动量",
        "fastexpr": "if_else(greater(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), 0.8), reverse(rank(divide(ts_delta(close, 1), ts_delay(close, 1)))), rank(divide(ts_delta(close, 10), ts_delay(close, 10))))",
        "version": "breakthrough_v1",
    },
    "vol_weighted_mom": {
        "category": "非线性组合",
        "direction": "方向四：多因子非线性组合",
        "description": "动量×量比排名的横截面排名（放量动量排名）",
        "logic": "放量动量：成交量放大的动量更可靠",
        "fastexpr": "rank(multiply(divide(ts_delta(close, 10), ts_delay(close, 10)), ts_rank(divide(volume, ts_mean(volume, 20)), 20)))",
        "version": "breakthrough_v1",
    },

    # ================================================================
    # 方向五：隔夜/日内结构的高阶变体
    # 逻辑：alpha_021 的核心逻辑是隔夜vs日内的分化。
    # 做更灵敏的变化率版本，降低自相关。
    # ================================================================
    "overnight_change_3d": {
        "category": "隔夜日内变体",
        "direction": "方向五：隔夜/日内结构的高阶变体",
        "description": "隔夜收益的3日变化率排名（隔夜动量加速度）",
        "logic": "隔夜收益变化率：隔夜动量的加速度",
        "fastexpr": "rank(ts_delta(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), 3))",
        "version": "breakthrough_v1",
    },
    "intraday_change_3d": {
        "category": "隔夜日内变体",
        "direction": "方向五：隔夜/日内结构的高阶变体",
        "description": "日内收益的3日变化率排名",
        "logic": "日内收益变化率：日内动量的加速度",
        "fastexpr": "rank(ts_delta(divide(subtract(close, open), open), 3))",
        "version": "breakthrough_v1",
    },
    "oi_divergence_change": {
        "category": "隔夜日内变体",
        "direction": "方向五：隔夜/日内结构的高阶变体",
        "description": "隔夜vs日内分化的变化率排名（比alpha_021更灵敏）",
        "logic": "分化加速度：隔夜与日内收益差的变化率",
        "fastexpr": "rank(subtract(ts_delta(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), 3), ts_delta(divide(subtract(close, open), open), 3)))",
        "version": "breakthrough_v1",
    },
    "overnight_momentum": {
        "category": "隔夜日内变体",
        "direction": "方向五：隔夜/日内结构的高阶变体",
        "description": "隔夜收益×隔夜收益排名（强者恒强的隔夜动量）",
        "logic": "隔夜动量增强：隔夜收益高且排名高的更强",
        "fastexpr": "rank(multiply(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), ts_rank(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), 20)))",
        "version": "breakthrough_v1",
    },
    "overnight_accel": {
        "category": "隔夜日内变体",
        "direction": "方向五：隔夜/日内结构的高阶变体",
        "description": "隔夜收益排名的3日变化率（隔夜动量加速度）",
        "logic": "隔夜排名加速度：隔夜收益排名上升最快的",
        "fastexpr": "rank(ts_delta(ts_rank(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), 20), 3))",
        "version": "breakthrough_v1",
    },
    "oi_corr_10d": {
        "category": "隔夜日内变体",
        "direction": "方向五：隔夜/日内结构的高阶变体",
        "description": "隔夜与日内收益的10日相关系数取负（分化越大越有效）",
        "logic": "隔夜日内分化：相关性越低，分化越严重，alpha_021逻辑越强",
        "fastexpr": "reverse(ts_corr(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open), 10))",
        "version": "breakthrough_v1",
    },

    # ================================================================
    # 方向六：量价背离的变化率
    # 逻辑：量价背离已经有效，但自相关可能也高。
    # 做变化率版本降低自相关。
    # ================================================================
    "vpd_change_5d": {
        "category": "量价背离变体",
        "direction": "方向六：量价背离的变化率",
        "description": "量价背离的5日变化率排名",
        "logic": "背离加速度：量价背离程度的变化率",
        "fastexpr": "rank(ts_delta(subtract(rank(volume), rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))))), 5))",
        "version": "breakthrough_v1",
    },
    "vpd_rank_change_3d": {
        "category": "量价背离变体",
        "direction": "方向六：量价背离的变化率",
        "description": "量价背离排名的3日变化量",
        "logic": "背离排名变化：背离程度排名的变化速度",
        "fastexpr": "ts_delta(rank(subtract(rank(volume), rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1)))))), 3)",
        "version": "breakthrough_v1",
    },
    "vpd_accel": {
        "category": "量价背离变体",
        "direction": "方向六：量价背离的变化率",
        "description": "量价背离的加速度（二阶导数）",
        "logic": "背离加速度：背离变化率的变化率",
        "fastexpr": "ts_delta(ts_delta(subtract(rank(volume), rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))))), 5), 3)",
        "version": "breakthrough_v1",
    },
    "pv_diverge_mom": {
        "category": "量价背离变体",
        "direction": "方向六：量价背离的变化率",
        "description": "量价背离×中期动量方向",
        "logic": "背离+动量方向：背离方向与中期动量一致时更强",
        "fastexpr": "multiply(subtract(rank(volume), rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))))), sign(divide(ts_delta(close, 5), ts_delay(close, 5))))",
        "version": "breakthrough_v1",
    },
    "vpd_weighted_rev": {
        "category": "量价背离变体",
        "direction": "方向六：量价背离的变化率",
        "description": "量价背离加权的日度反转排名",
        "logic": "背离增强反转：量价背离越大，反转信号越强",
        "fastexpr": "rank(multiply(subtract(rank(volume), rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))))), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))",
        "version": "breakthrough_v1",
    },
    "pv_corr_change_5d": {
        "category": "量价背离变体",
        "direction": "方向六：量价背离的变化率",
        "description": "量价相关性的5日变化率排名",
        "logic": "相关性变化：量价关系快速变化的股票",
        "fastexpr": "rank(ts_delta(ts_corr(close, volume, 10), 5))",
        "version": "breakthrough_v1",
    },

    # ================================================================
    # 方向七：oi_divergence 优化变体（降低换手、提高Fitness）
    # 逻辑：oi_divergence_change Sharpe=1.31 但换手0.8超标
    # 通过平滑、衰减、延长周期来降低换手率
    # ================================================================
    "oi_div_smooth_3d": {
        "category": "隔夜日内优化",
        "direction": "方向七：oi_divergence优化变体",
        "description": "隔夜vs日内分化变化率的3日平滑（降低换手）",
        "logic": "对oi_divergence_change做3日均值平滑，降低换手率",
        "fastexpr": "rank(ts_mean(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 3))",
        "version": "breakthrough_v2",
    },
    "oi_div_decay5": {
        "category": "隔夜日内优化",
        "direction": "方向七：oi_divergence优化变体",
        "description": "隔夜vs日内分化变化率的5日线性衰减（降低换手）",
        "logic": "对oi_divergence_change做5日线性衰减，降低换手率",
        "fastexpr": "rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5))",
        "version": "breakthrough_v2",
    },
    "oi_div_5d": {
        "category": "隔夜日内优化",
        "direction": "方向七：oi_divergence优化变体",
        "description": "隔夜vs日内分化的5日变化率（更长周期，更低换手）",
        "logic": "更长周期的分化变化率，换手率更低",
        "fastexpr": "rank(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 5))",
        "version": "breakthrough_v2",
    },
    "oi_div_10d": {
        "category": "隔夜日内优化",
        "direction": "方向七：oi_divergence优化变体",
        "description": "隔夜vs日内分化的10日变化率（长周期，低换手）",
        "logic": "10日长周期的分化变化率，换手率最低",
        "fastexpr": "rank(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 10))",
        "version": "breakthrough_v2",
    },

    # ================================================================
    # 方向八：反转类优化变体（提高Sharpe和Fitness）
    # 逻辑：vol_spike_reversal Sharpe=1.18, extreme_rev_weighted Sharpe=1.05
    # 尝试更多变体突破1.25
    # ================================================================
    "vsr_3d_rev": {
        "category": "反转优化",
        "direction": "方向八：反转类优化变体",
        "description": "放量加权的3日反转（更长周期的反转）",
        "logic": "放量加权的3日反转，可能更稳定",
        "fastexpr": "multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(rank(divide(ts_delta(close, 3), ts_delay(close, 3)))))",
        "version": "breakthrough_v2",
    },
    "rev_hl_weighted": {
        "category": "反转优化",
        "direction": "方向八：反转类优化变体",
        "description": "日内波幅加权的日度反转（波动越大反转越强）",
        "logic": "日内波幅大的股票，日度反转信号更强",
        "fastexpr": "multiply(rank(divide(subtract(high, low), close)), reverse(rank(divide(ts_delta(close, 1), ts_delay(close, 1)))))",
        "version": "breakthrough_v2",
    },
    "rev_5d_spike": {
        "category": "反转优化",
        "direction": "方向八：反转类优化变体",
        "description": "放量加权的5日反转（中期反转+放量确认）",
        "logic": "5日反转叠加放量加权，捕捉中期反转",
        "fastexpr": "multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(rank(divide(ts_delta(close, 5), ts_delay(close, 5)))))",
        "version": "breakthrough_v2",
    },

    # ================================================================
    # 方向九：组合因子（提高Fitness和稳定性）
    # 逻辑：多个弱因子组合，分散化提高Fitness
    # ================================================================
    "combo_oi_vsr": {
        "category": "组合因子v2",
        "direction": "方向九：组合因子（提高Fitness）",
        "description": "oi_divergence + vol_spike_reversal 等权组合",
        "logic": "两个弱因子等权组合，分散化提高Fitness",
        "fastexpr": "divide(add(rank(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3)), rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), 2.0)",
        "version": "breakthrough_v2",
        "components": {"oi_divergence_change": 0.5, "vol_spike_reversal": 0.5},
    },
    "combo_3f_v2": {
        "category": "组合因子v2",
        "direction": "方向九：组合因子（提高Fitness）",
        "description": "三因子等权组合：oi_div + vsr + low_vol",
        "logic": "三个不同逻辑因子等权组合，最大化分散化",
        "fastexpr": "divide(add(add(rank(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3)), rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), reverse(rank(ts_std_dev(returns, 20)))), 3.0)",
        "version": "breakthrough_v2",
        "components": {"oi_divergence_change": 0.33, "vol_spike_reversal": 0.33, "low_vol": 0.34},
    },
    "combo_rev_lowvol": {
        "category": "组合因子v2",
        "direction": "方向九：组合因子（提高Fitness）",
        "description": "extreme_rev + low_vol 等权组合（反转+低波）",
        "logic": "反转因子+低波因子，互补性强",
        "fastexpr": "divide(add(rank(multiply(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), reverse(divide(ts_delta(close, 1), ts_delay(close, 1))))), reverse(rank(ts_std_dev(returns, 20)))), 2.0)",
        "version": "breakthrough_v2",
        "components": {"extreme_rev_weighted": 0.5, "low_vol": 0.5},
    },

    # ================================================================
    # 方向十：Fitness深度优化（第三批）
    # 逻辑：基于前两批发现的有效因子，通过组合、加权、衰减提高Fitness
    # 目标：Fitness ≥ 1.0
    # ================================================================
    "combo_oi_vsr_decay5": {
        "category": "Fitness优化",
        "direction": "方向十：Fitness深度优化",
        "description": "combo_oi_vsr的5日线性衰减版（降换手提Fitness）",
        "logic": "最佳组合因子加衰减，降低换手率提高稳定性",
        "fastexpr": "rank(ts_decay_linear(divide(add(rank(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3)), rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), 2.0), 5))",
        "version": "breakthrough_v3",
    },
    "combo_3f_weighted": {
        "category": "Fitness优化",
        "direction": "方向十：Fitness深度优化",
        "description": "三因子加权组合：oi_div_decay5(50%) + vsr(30%) + low_vol(20%)",
        "logic": "按表现加权，表现好的因子权重更高",
        "fastexpr": "add(multiply(0.5, rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5))), add(multiply(0.3, rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), multiply(0.2, reverse(rank(ts_std_dev(returns, 20))))))",
        "version": "breakthrough_v3",
        "components": {"oi_div_decay5": 0.5, "vol_spike_reversal": 0.3, "low_vol": 0.2},
    },
    "combo_oi_vsr_ext": {
        "category": "Fitness优化",
        "direction": "方向十：Fitness深度优化",
        "description": "oi_div_decay5 + vsr + extreme_rev 三因子等权",
        "logic": "三个不同反转/分化逻辑的因子组合，分散化",
        "fastexpr": "divide(add(add(rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5)), rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), rank(multiply(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), 3.0)",
        "version": "breakthrough_v3",
        "components": {"oi_div_decay5": 0.33, "vsr": 0.33, "extreme_rev": 0.34},
    },
    "oi_div_5d_decay5": {
        "category": "Fitness优化",
        "direction": "方向十：Fitness深度优化",
        "description": "oi_div_5d再加5日线性衰减（更平滑）",
        "logic": "5日变化率+5日衰减，双重平滑提高稳定性",
        "fastexpr": "rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 5), 5))",
        "version": "breakthrough_v3",
    },
    "combo_multi_period": {
        "category": "Fitness优化",
        "direction": "方向十：Fitness深度优化",
        "description": "oi_div多周期组合：3日+5日+10日变化率等权",
        "logic": "多周期组合分散单一周期风险，提高稳定性",
        "fastexpr": "divide(add(add(rank(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3)), rank(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 5))), rank(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 10))), 3.0)",
        "version": "breakthrough_v3",
    },
    "vsr_decay5": {
        "category": "Fitness优化",
        "direction": "方向十：Fitness深度优化",
        "description": "vol_spike_reversal的5日衰减版",
        "logic": "放量反转因子加衰减，降低换手率提高Fitness",
        "fastexpr": "rank(ts_decay_linear(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))), 5))",
        "version": "breakthrough_v3",
    },
    "combo_4f_balanced": {
        "category": "Fitness优化",
        "direction": "方向十：Fitness深度优化",
        "description": "四因子平衡组合：oi_div(40%)+vsr(25%)+ext_rev(20%)+low_vol(15%)",
        "logic": "四个不同逻辑因子按表现加权，最大化分散化",
        "fastexpr": "add(multiply(0.4, rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5))), add(multiply(0.25, rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), add(multiply(0.2, rank(multiply(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), multiply(0.15, reverse(rank(ts_std_dev(returns, 20)))))))",
        "version": "breakthrough_v3",
    },
    "oi_div_cond_lowvol": {
        "category": "Fitness优化",
        "direction": "方向十：Fitness深度优化",
        "description": "oi_div条件版：只在低波动环境下出信号",
        "logic": "波动率低时oi_div更有效，高波动时中性",
        "fastexpr": "if_else(less(ts_std_dev(returns, 20), ts_mean(ts_std_dev(returns, 60), 20)), rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5)), 0.0)",
        "version": "breakthrough_v3",
    },

    # ================================================================
    # 方向十一：冲击Fitness≥1.0（第四批）
    # 逻辑：5因子+等权组合，最大化分散化提升Fitness
    # ================================================================
    "combo_5f_equal": {
        "category": "冲击Fitness",
        "direction": "方向十一：冲击Fitness≥1.0",
        "description": "五因子等权组合：oi_div+vsr+ext_rev+low_vol+rev_5d_spike",
        "logic": "5个不同逻辑因子等权，最大化分散化提升Fitness",
        "fastexpr": "divide(add(add(add(add(rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5)), rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), rank(multiply(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), reverse(rank(ts_std_dev(returns, 20)))), rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 5), ts_delay(close, 5)))))), 5.0)",
        "version": "breakthrough_v4",
        "components": {"oi_div_decay5": 0.2, "vsr": 0.2, "ext_rev": 0.2, "low_vol": 0.2, "rev_5d_spike": 0.2},
    },
    "combo_5f_weighted": {
        "category": "冲击Fitness",
        "direction": "方向十一：冲击Fitness≥1.0",
        "description": "五因子加权组合：oi_div(30%)+vsr(25%)+ext_rev(20%)+low_vol(15%)+rev5d(10%)",
        "logic": "按表现加权，强因子权重更高",
        "fastexpr": "add(multiply(0.3, rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5))), add(multiply(0.25, rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), add(multiply(0.2, rank(multiply(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), add(multiply(0.15, reverse(rank(ts_std_dev(returns, 20)))), multiply(0.1, rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 5), ts_delay(close, 5))))))))))",
        "version": "breakthrough_v4",
    },
    "combo_oi_vsr_ext_decay": {
        "category": "冲击Fitness",
        "direction": "方向十一：冲击Fitness≥1.0",
        "description": "combo_oi_vsr_ext再加5日衰减（更平滑）",
        "logic": "三因子组合+衰减，双重提升Fitness",
        "fastexpr": "rank(ts_decay_linear(divide(add(add(rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5)), rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), rank(multiply(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), 3.0), 5))",
        "version": "breakthrough_v4",
    },
    "combo_4f_decay5": {
        "category": "冲击Fitness",
        "direction": "方向十一：冲击Fitness≥1.0",
        "description": "四因子平衡组合加5日衰减",
        "logic": "四因子组合+衰减，进一步提高稳定性",
        "fastexpr": "rank(ts_decay_linear(add(multiply(0.4, rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5))), add(multiply(0.25, rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), add(multiply(0.2, rank(multiply(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), multiply(0.15, reverse(rank(ts_std_dev(returns, 20))))))), 5))",
        "version": "breakthrough_v4",
    },
    "combo_6f_diverse": {
        "category": "冲击Fitness",
        "direction": "方向十一：冲击Fitness≥1.0",
        "description": "六因子多样化等权：oi_div+vsr+ext_rev+low_vol+rev5d+pv_diverge",
        "logic": "6个不同逻辑因子等权，极致分散化",
        "fastexpr": "divide(add(add(add(add(add(rank(ts_decay_linear(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3), 5)), rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), rank(multiply(ts_rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))), 20), reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))))), reverse(rank(ts_std_dev(returns, 20)))), rank(multiply(ts_rank(divide(volume, ts_mean(volume, 20)), 60), reverse(divide(ts_delta(close, 5), ts_delay(close, 5)))))), rank(multiply(subtract(rank(volume), rank(abs(divide(ts_delta(close, 1), ts_delay(close, 1))))), sign(divide(ts_delta(close, 5), ts_delay(close, 5)))))), 6.0)",
        "version": "breakthrough_v4",
    },
}

# 默认回测设置（基准设置）
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
# 提交检查相关方法（扩展 WQBApiClient）
# ============================================================

def submit_alpha_for_check(client: WQBApiClient, alpha_id: str) -> Optional[str]:
    """
    提交 Alpha 进行检查（POST /alphas/{alpha_id}/submit）
    
    Returns:
        检查进度URL，如果失败返回None
    """
    url = f"{client._session.auth[1] if False else ''}"  # dummy
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/submit"
    
    try:
        # 使用带重试的请求
        @retry_with_backoff(max_retries=3, base_delay=5.0)
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


def get_submit_check_result(client: WQBApiClient, alpha_id: str, 
                            max_wait: float = 300.0) -> Optional[dict]:
    """
    获取提交检查结果（GET /alphas/{alpha_id} 查看 status 和 checks）
    
    Returns:
        检查结果字典，包含各个检查项的状态
    """
    start = time.time()
    
    while time.time() - start < max_wait:
        try:
            alpha_data = client.get_alpha(alpha_id)
            stage = alpha_data.get("stage", "")
            grade = alpha_data.get("grade", "")
            status = alpha_data.get("status", "")
            
            # 如果已经到了某个提交阶段，返回详细信息
            if stage and stage != "IS":
                # 提取各项检查
                checks = {
                    "stage": stage,
                    "grade": grade,
                    "status": status,
                    "is_sharpe": alpha_data.get("is", {}).get("sharpe"),
                    "is_fitness": alpha_data.get("is", {}).get("fitness"),
                    "is_turnover": alpha_data.get("is", {}).get("turnover"),
                }
                
                # 尝试获取提交检查详情
                check_details = alpha_data.get("checks", {})
                if check_details:
                    checks["checks"] = check_details
                
                return checks
            
            # 还在IS阶段，检查是否有提交相关信息
            # 可能提交还在处理中，等一下再查
            time.sleep(10.0)
            
        except Exception as e:
            print(f"  [查询检查结果异常] {alpha_id}: {e}")
            time.sleep(10.0)
    
    return None


def get_detailed_checks(client: WQBApiClient, alpha_id: str) -> dict:
    """
    获取详细的提交检查项（通过 recordsets 或 alpha 详情）
    
    检查项包括：
    - Sharpe (In-Sample)
    - Fitness
    - Self-Correlation (自相关)
    - Turnover (换手率)
    - Concentration (集中度)
    - Sub-Sample Sharpe (子样本夏普)
    """
    try:
        alpha_data = client.get_alpha(alpha_id)
        is_data = alpha_data.get("is", {})
        
        # 基础指标
        result = {
            "alpha_id": alpha_id,
            "sharpe": is_data.get("sharpe"),
            "fitness": is_data.get("fitness"),
            "turnover": is_data.get("turnover"),
            "drawdown": is_data.get("drawdown"),
            "returns": is_data.get("returns"),
            "grade": alpha_data.get("grade"),
            "stage": alpha_data.get("stage"),
            "status": alpha_data.get("status"),
        }
        
        # 尝试获取 self-correlation（可能在不同字段中）
        # WQB 中自相关检查可能叫 self_correlation 或 autocorrelation
        for key in ["self_correlation", "autocorrelation", "selfCorrelation", "autoCorrelation"]:
            if key in alpha_data:
                result["self_correlation"] = alpha_data[key]
                break
            if key in is_data:
                result["self_correlation"] = is_data[key]
                break
        
        # 尝试获取更多检查项
        extra = alpha_data.get("checks", {})
        if extra:
            result["checks_detail"] = extra
        
        # 子样本：train / test
        train_data = alpha_data.get("train", {})
        test_data = alpha_data.get("test", {})
        if train_data:
            result["train_sharpe"] = train_data.get("sharpe")
            result["train_fitness"] = train_data.get("fitness")
        if test_data:
            result["test_sharpe"] = test_data.get("sharpe")
            result["test_fitness"] = test_data.get("fitness")
        
        return result
        
    except Exception as e:
        print(f"  [获取详细检查失败] {alpha_id}: {e}")
        return {"alpha_id": alpha_id, "error": str(e)}


def estimate_self_correlation(client: WQBApiClient, alpha_id: str) -> Optional[float]:
    """
    估算自相关系数：通过获取 PnL 数据计算相邻日的自相关
    
    注意：WQB 的 SELF_CORRELATION 检查可能指的是因子暴露的自相关，
    这里用 PnL 自相关作为近似参考。
    """
    try:
        pnl_data = client.get_pnl(alpha_id)
        records = pnl_data.get("records", [])
        
        if len(records) < 30:
            return None
        
        pnls = [float(r[1]) for r in records if r[1] is not None]
        
        if len(pnls) < 30:
            return None
        
        # 计算一阶自相关
        n = len(pnls)
        mean_val = sum(pnls) / n
        var_val = sum((x - mean_val) ** 2 for x in pnls) / n
        
        if var_val == 0:
            return None
        
        # 一阶自相关系数
        autocov = sum((pnls[i] - mean_val) * (pnls[i+1] - mean_val) for i in range(n-1)) / (n-1)
        autocorr = autocov / var_val
        
        return round(autocorr, 4)
        
    except Exception as e:
        print(f"  [自相关计算失败] {alpha_id}: {e}")
        return None


# ============================================================
# 批量提交与等待
# ============================================================

async def batch_submit(client: WQBApiClient, to_submit: List[tuple],
                        sim_settings: dict) -> List[WQBSimulation]:
    """
    批量提交模拟（控制提交间隔为 40s，缓存命中不等待）
    """
    simulations = []
    submitted_count = 0  # 实际提交的数量（用于计算等待）
    
    for i, (factor_name, expression, info) in enumerate(to_submit):
        # 先检查是否已存在
        cached = client.get_cached_alpha(expression, sim_settings)
        if cached and cached.get("status") == "COMPLETED":
            print(f"  [{i+1}/{len(to_submit)}] [缓存] {factor_name}: Sharpe={cached.get('sharpe', 'N/A')}")
            sim = WQBSimulation(client, None, expression, sim_settings)
            sim.factor_name = factor_name
            sim.category = info.get("category", "未知")
            sim.description = info.get("description", "")
            sim.direction = info.get("direction", "")
            sim.logic = info.get("logic", "")
            sim.version = info.get("version", "v1")
            sim.alpha_id = cached.get("alpha_id")
            sim.status = "COMPLETED"
            sim._from_cache = True
            simulations.append(sim)
            continue
        
        # 标记 PENDING
        client.save_alpha_result(
            expression=expression,
            settings=sim_settings,
            factor_name=factor_name,
            category=info.get("category", "未知"),
            status="PENDING",
        )
        
        # 提交前等待（如果不是第一个提交的）
        if submitted_count > 0:
            await asyncio.sleep(SUBMIT_INTERVAL)
        
        try:
            sim = client.simulate(expression, sim_settings)
            sim.factor_name = factor_name
            sim.category = info.get("category", "未知")
            sim.description = info.get("description", "")
            sim.direction = info.get("direction", "")
            sim.logic = info.get("logic", "")
            sim.version = info.get("version", "v1")
            sim._submitted = True
            simulations.append(sim)
            submitted_count += 1
            
            # 保存 progress_url
            client.save_alpha_result(
                expression=expression,
                settings=sim_settings,
                factor_name=factor_name,
                category=info.get("category", "未知"),
                progress_url=sim.progress_url,
                status="PENDING",
            )
            print(f"  [{i+1}/{len(to_submit)}] ✓ 提交 {factor_name}")
        except Exception as e:
            error_str = str(e)
            print(f"  [{i+1}/{len(to_submit)}] ✗ 提交失败 {factor_name}: {error_str[:100]}")
            client.save_alpha_result(
                expression=expression,
                settings=sim_settings,
                factor_name=factor_name,
                category=info.get("category", "未知"),
                status="FAILED",
                error=error_str,
            )
            sim = WQBSimulation(client, None, expression, sim_settings)
            sim.factor_name = factor_name
            sim.category = info.get("category", "未知")
            sim.status = "FAILED"
            sim.error = error_str
            simulations.append(sim)
            submitted_count += 1
    
    return simulations


async def batch_wait_and_collect(client: WQBApiClient, simulations: List[WQBSimulation],
                                  sim_settings: dict, poll_interval: float = 5.0,
                                  max_wait: float = 600.0) -> List[dict]:
    """
    批量等待模拟完成并收集结果
    """
    results = []
    submitted = [s for s in simulations if s.status == "PENDING" and getattr(s, '_submitted', False)]
    cached = [s for s in simulations if getattr(s, '_from_cache', False)]
    failed = [s for s in simulations if s.status == "FAILED"]
    
    print(f"\n[等待] 新提交 {len(submitted)} 个, 缓存命中 {len(cached)} 个, 失败 {len(failed)} 个")
    
    # 先处理缓存的
    for sim in cached:
        try:
            metrics = sim.get_metrics() if sim.alpha_id else {}
            is_summary = metrics.pop("is_summary", None)
            results.append({
                "factor_name": sim.factor_name,
                "category": sim.category,
                "direction": getattr(sim, 'direction', ''),
                "logic": getattr(sim, 'logic', ''),
                "description": sim.description,
                "expression": sim.expression,
                "status": "COMPLETED",
                "alpha_id": sim.alpha_id,
                "sharpe": metrics.get("sharpe"),
                "fitness": metrics.get("fitness"),
                "turnover": metrics.get("turnover"),
                "annual_return": metrics.get("annual_return"),
                "max_drawdown": metrics.get("max_drawdown"),
                "from_cache": True,
            })
        except Exception as e:
            print(f"  [缓存数据异常] {sim.factor_name}: {e}")
    
    # 处理失败的
    for sim in failed:
        results.append({
            "factor_name": sim.factor_name,
            "category": sim.category,
            "direction": getattr(sim, 'direction', ''),
            "description": getattr(sim, 'description', ''),
            "expression": sim.expression,
            "status": "FAILED",
            "error": sim.error,
        })
    
    # 等待新提交的
    start_time = time.time()
    completed_count = 0
    failed_count = 0
    
    while submitted and (time.time() - start_time) < max_wait:
        still_pending = []
        
        for sim in submitted:
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
                            settings=sim_settings,
                            factor_name=sim.factor_name,
                            category=sim.category,
                            alpha_id=sim.alpha_id,
                            status="COMPLETED",
                            metrics=metrics,
                            is_summary=is_summary,
                            yearly=yearly,
                        )
                        
                        results.append({
                            "factor_name": sim.factor_name,
                            "category": sim.category,
                            "direction": getattr(sim, 'direction', ''),
                            "logic": getattr(sim, 'logic', ''),
                            "description": sim.description,
                            "expression": sim.expression,
                            "status": "COMPLETED",
                            "alpha_id": sim.alpha_id,
                            "sharpe": metrics.get("sharpe"),
                            "fitness": metrics.get("fitness"),
                            "turnover": metrics.get("turnover"),
                            "annual_return": metrics.get("annual_return"),
                            "max_drawdown": metrics.get("max_drawdown"),
                            "from_cache": False,
                        })
                        print(f"  ✓ [{completed_count}] {sim.factor_name}: Sharpe={metrics.get('sharpe', 'N/A')}, Fitness={metrics.get('fitness', 'N/A')}")
                    except Exception as e:
                        print(f"  ✗ 获取结果失败 {sim.factor_name}: {e}")
                        failed_count += 1
                        results.append({
                            "factor_name": sim.factor_name,
                            "category": sim.category,
                            "direction": getattr(sim, 'direction', ''),
                            "description": sim.description,
                            "expression": sim.expression,
                            "status": "FAILED",
                            "error": f"结果获取失败: {e}",
                        })
                else:
                    still_pending.append(sim)
            except Exception as e:
                sim.status = "FAILED"
                sim.error = str(e)
                failed_count += 1
                print(f"  ✗ {sim.factor_name} 失败: {str(e)[:80]}")
                client.save_alpha_result(
                    expression=sim.expression,
                    settings=sim_settings,
                    factor_name=sim.factor_name,
                    category=sim.category,
                    status="FAILED",
                    error=str(e),
                )
                results.append({
                    "factor_name": sim.factor_name,
                    "category": sim.category,
                    "direction": getattr(sim, 'direction', ''),
                    "description": sim.description,
                    "expression": sim.expression,
                    "status": "FAILED",
                    "error": str(e),
                })
        
        submitted = still_pending
        if submitted:
            await asyncio.sleep(poll_interval)
    
    # 处理超时仍在 pending 的
    for sim in submitted:
        print(f"  ⏳ {sim.factor_name} 超时，保持 PENDING")
        results.append({
            "factor_name": sim.factor_name,
            "category": sim.category,
            "direction": getattr(sim, 'direction', ''),
            "description": sim.description,
            "expression": sim.expression,
            "status": "PENDING",
            "alpha_id": sim.alpha_id,
        })
    
    return results


# ============================================================
# 报告生成
# ============================================================

def generate_breakthrough_report(all_results: List[dict], 
                                  check_results: List[dict],
                                  output_path: str,
                                  sim_settings: dict) -> str:
    """
    生成跃迁因子研究报告
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 筛选
    completed = [r for r in all_results if r.get("status") == "COMPLETED"]
    failed = [r for r in all_results if r.get("status") == "FAILED"]
    pending = [r for r in all_results if r.get("status") == "PENDING"]
    
    # 按 Sharpe 排序
    completed.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
    
    # 合格因子（Sharpe≥1.25 且 Fitness≥1.0）
    qualified = [r for r in completed 
                  if r.get("sharpe", 0) is not None and r.get("sharpe", 0) >= SHARPE_THRESHOLD
                  and r.get("fitness", 0) is not None and r.get("fitness", 0) >= FITNESS_THRESHOLD]
    
    # 按方向分组
    by_direction = defaultdict(list)
    for r in completed:
        direction = r.get("direction", "未知方向")
        by_direction[direction].append(r)
    
    # ---- 构建报告 ----
    lines = []
    
    lines.append("# 跃迁因子研究报告")
    lines.append("")
    lines.append(f"**生成时间：** {now}")
    lines.append("")
    lines.append("## 研究目标")
    lines.append("")
    lines.append("从因子逻辑本质出发，设计并验证一批全新的 Alpha 因子，目标是同时通过 WQB 所有提交检查：")
    lines.append("- Sharpe ≥ 1.25")
    lines.append("- Fitness ≥ 1.0")
    lines.append("- SELF_CORRELATION ≤ 0.7")
    lines.append("- 换手率 0.01 - 0.7")
    lines.append("- 集中度通过")
    lines.append("- 子样本夏普通过")
    lines.append("")
    lines.append("**核心原则：** 不做现有因子的加权微调，从因子逻辑层面创新。")
    lines.append("")
    
    lines.append("## 回测设置")
    lines.append("")
    lines.append(f"| 参数 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 地区 | {sim_settings.get('region', 'USA')} |")
    lines.append(f"| 股票池 | {sim_settings.get('universe', 'TOP3000')} |")
    lines.append(f"| 延迟 | {sim_settings.get('delay', 1)} 天 |")
    lines.append(f"| 衰减 | {sim_settings.get('decay', 15)} 天 |")
    lines.append(f"| 中性化 | {sim_settings.get('neutralization', 'SUBINDUSTRY')} |")
    lines.append(f"| 截断 | {sim_settings.get('truncation', 0.08)} |")
    lines.append(f"| 回测周期 | {sim_settings.get('testPeriod', 'P1Y6M')} |")
    lines.append("")
    
    # 总体概览
    lines.append("## 总体概览")
    lines.append("")
    lines.append(f"| 指标 | 数量 |")
    lines.append(f"|------|------|")
    lines.append(f"| 总因子数 | {len(all_results)} |")
    lines.append(f"| 成功完成 | {len(completed)} |")
    lines.append(f"| 提交失败 | {len(failed)} |")
    lines.append(f"| 进行中 | {len(pending)} |")
    lines.append(f"| **Sharpe≥{SHARPE_THRESHOLD} 且 Fitness≥{FITNESS_THRESHOLD}** | **{len(qualified)}** |")
    lines.append("")
    
    if completed:
        top = completed[0]
        lines.append(f"**最佳因子：** {top['factor_name']}")
        lines.append(f"- Sharpe: {top.get('sharpe', 'N/A')}")
        lines.append(f"- Fitness: {top.get('fitness', 'N/A')}")
        lines.append(f"- 换手率: {top.get('turnover', 'N/A')}")
        lines.append(f"- 方向: {top.get('direction', 'N/A')}")
        lines.append(f"- 逻辑: {top.get('logic', 'N/A')}")
        lines.append("")
    
    # 各方向表现
    lines.append("## 各方向表现统计")
    lines.append("")
    lines.append("| 方向 | 因子数 | 平均Sharpe | 最佳Sharpe | 最佳因子 | 平均Fitness |")
    lines.append("|------|--------|-----------|-----------|----------|------------|")
    
    for direction in sorted(by_direction.keys()):
        items = by_direction[direction]
        avg_sharpe = sum(x.get("sharpe", 0) or 0 for x in items) / len(items) if items else 0
        best = max(items, key=lambda x: x.get("sharpe") or -999)
        avg_fitness = sum(x.get("fitness", 0) or 0 for x in items) / len(items) if items else 0
        lines.append(
            f"| {direction} | {len(items)} | {avg_sharpe:.3f} | "
            f"{best.get('sharpe', 0):.3f} | {best['factor_name']} | {avg_fitness:.3f} |"
        )
    lines.append("")
    
    # 合格因子
    lines.append(f"## 合格因子（Sharpe≥{SHARPE_THRESHOLD} 且 Fitness≥{FITNESS_THRESHOLD}）")
    lines.append("")
    
    if qualified:
        lines.append("| 排名 | 因子名称 | 方向 | Sharpe | Fitness | 换手率 | 年化收益 | 最大回撤 |")
        lines.append("|------|---------|------|--------|---------|--------|---------|---------|")
        
        for i, r in enumerate(qualified):
            sharpe = f"{r.get('sharpe', 0):.3f}"
            fitness = f"{r.get('fitness', 0):.3f}"
            turnover = f"{r.get('turnover', 0):.3f}" if r.get('turnover') is not None else "N/A"
            annual = f"{r.get('annual_return', 0):.2%}" if r.get('annual_return') is not None else "N/A"
            mdd = f"{r.get('max_drawdown', 0):.2%}" if r.get('max_drawdown') is not None else "N/A"
            lines.append(
                f"| {i+1} | {r['factor_name']} | {r.get('direction', '')} | "
                f"{sharpe} | {fitness} | {turnover} | {annual} | {mdd} |"
            )
        lines.append("")
    else:
        lines.append("暂无同时满足 Sharpe≥1.25 且 Fitness≥1.0 的因子。")
        lines.append("")
    
    # 提交检查结果
    if check_results:
        lines.append("## 提交检查结果")
        lines.append("")
        lines.append("| 因子名称 | Alpha ID | Sharpe | Fitness | 换手率 | Stage | Grade | Status |")
        lines.append("|---------|----------|--------|---------|--------|-------|-------|--------|")
        
        for cr in check_results:
            sharpe = f"{cr.get('sharpe', 0):.3f}" if cr.get('sharpe') is not None else "N/A"
            fitness = f"{cr.get('fitness', 0):.3f}" if cr.get('fitness') is not None else "N/A"
            turnover = f"{cr.get('turnover', 0):.3f}" if cr.get('turnover') is not None else "N/A"
            lines.append(
                f"| {cr.get('factor_name', '')} | {cr.get('alpha_id', '')} | "
                f"{sharpe} | {fitness} | {turnover} | "
                f"{cr.get('stage', '')} | {cr.get('grade', '')} | {cr.get('status', '')} |"
            )
        lines.append("")
    
    # 所有因子详细排名
    lines.append("## 所有因子详细排名（按Sharpe降序）")
    lines.append("")
    lines.append("| 排名 | 因子名称 | 方向 | Sharpe | Fitness | 换手率 | 年化收益 | 最大回撤 | 状态 |")
    lines.append("|------|---------|------|--------|---------|--------|---------|---------|------|")
    
    for i, r in enumerate(completed):
        sharpe = f"{r.get('sharpe', 0):.3f}"
        fitness = f"{r.get('fitness', 0):.3f}" if r.get('fitness') is not None else "N/A"
        turnover = f"{r.get('turnover', 0):.3f}" if r.get('turnover') is not None else "N/A"
        annual = f"{r.get('annual_return', 0):.2%}" if r.get('annual_return') is not None else "N/A"
        mdd = f"{r.get('max_drawdown', 0):.2%}" if r.get('max_drawdown') is not None else "N/A"
        status = "✓缓存" if r.get("from_cache") else "✓新测"
        lines.append(
            f"| {i+1} | {r['factor_name']} | {r.get('direction', '')} | "
            f"{sharpe} | {fitness} | {turnover} | {annual} | {mdd} | {status} |"
        )
    
    # 失败的因子
    if failed:
        lines.append("")
        lines.append("### 失败因子")
        lines.append("")
        for r in failed:
            lines.append(f"- **{r['factor_name']}**: {r.get('error', '未知错误')[:100]}")
    lines.append("")
    
    # 因子表达式详情
    lines.append("## 因子表达式详情")
    lines.append("")
    
    for direction in sorted(by_direction.keys()):
        lines.append(f"### {direction}")
        lines.append("")
        items = by_direction[direction]
        items.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
        
        for r in items:
            sharpe = r.get('sharpe', 0)
            sharpe_str = f"{sharpe:.3f}" if sharpe is not None else "N/A"
            lines.append(f"#### {r['factor_name']} (Sharpe: {sharpe_str})")
            lines.append("")
            lines.append(f"- **描述：** {r.get('description', '')}")
            lines.append(f"- **逻辑：** {r.get('logic', '')}")
            lines.append(f"- **表达式：**")
            lines.append("```")
            lines.append(r.get('expression', ''))
            lines.append("```")
            lines.append("")
    
    lines.append("---")
    lines.append(f"*报告生成时间：{now}*")
    
    # 写入文件
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    return output_path


def generate_full_ranking_report(client: WQBApiClient, output_path: str) -> str:
    """
    生成全因子排名报告（包括历史所有因子）
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    all_results = client.list_all_results()
    completed = [r for r in all_results if r.get("status") == "COMPLETED"]
    completed.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
    
    # 补充描述信息
    for r in completed:
        fname = r.get("factor_name", "")
        if fname in BREAKTHROUGH_FACTORS:
            if not r.get("description"):
                r["description"] = BREAKTHROUGH_FACTORS[fname]["description"]
            if not r.get("category"):
                r["category"] = BREAKTHROUGH_FACTORS[fname]["category"]
    
    lines = []
    lines.append("# WQB 全因子排名报告")
    lines.append("")
    lines.append(f"**生成时间：** {now}")
    lines.append(f"**总因子数：** {len(all_results)}（已完成 {len(completed)} 个）")
    lines.append("")
    
    lines.append("## Top 30 因子排名（按Sharpe降序）")
    lines.append("")
    lines.append("| 排名 | 因子名称 | 类别 | Sharpe | Fitness | 换手率 | 年化收益 |")
    lines.append("|------|---------|------|--------|---------|--------|---------|")
    
    for i, r in enumerate(completed[:30]):
        sharpe = f"{r.get('sharpe', 0):.3f}" if r.get('sharpe') is not None else "N/A"
        fitness = f"{r.get('fitness', 0):.3f}" if r.get('fitness') is not None else "N/A"
        turnover = f"{r.get('turnover', 0):.3f}" if r.get('turnover') is not None else "N/A"
        annual = f"{r.get('annual_return', 0):.2%}" if r.get('annual_return') is not None else "N/A"
        cat = r.get('category', '未知')
        # 标记本次新增的跃迁因子
        name = r.get('factor_name', '')
        if r.get('factor_name', '') in BREAKTHROUGH_FACTORS:
            name = f"**{name}** ⭐"
        lines.append(
            f"| {i+1} | {name} | {cat} | {sharpe} | {fitness} | {turnover} | {annual} |"
        )
    lines.append("")
    
    # 按类别统计
    by_category = defaultdict(list)
    for r in completed:
        cat = r.get("category", "未知")
        by_category[cat].append(r)
    
    lines.append("## 各类别统计")
    lines.append("")
    lines.append("| 类别 | 因子数 | 平均Sharpe | 最佳Sharpe | 最佳因子 |")
    lines.append("|------|--------|-----------|-----------|----------|")
    
    for cat in sorted(by_category.keys()):
        items = by_category[cat]
        avg_sharpe = sum(x.get("sharpe", 0) or 0 for x in items) / len(items) if items else 0
        best = max(items, key=lambda x: x.get("sharpe") or -999)
        lines.append(
            f"| {cat} | {len(items)} | {avg_sharpe:.3f} | "
            f"{best.get('sharpe', 0):.3f} | {best.get('factor_name', '')} |"
        )
    lines.append("")
    
    lines.append("---")
    lines.append(f"*报告生成时间：{now}*")
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    return output_path


# ============================================================
# 主逻辑
# ============================================================

async def main():
    # ---- 参数解析 ----
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    max_factors = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    do_submit_check = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    
    # 账号配置
    email = "q1z2q3@126.com"
    password = "W2025zq0118"
    
    # 路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.normpath(os.path.join(script_dir, "..", "output"))
    os.makedirs(output_dir, exist_ok=True)
    
    db_path = os.path.join(output_dir, "wqb_state.db")
    report_path = os.path.join(output_dir, "wqb_breakthrough_report.md")
    full_ranking_path = os.path.join(output_dir, "wqb_full_ranking_report.md")
    
    actual_mode = result_mode if result_mode != "auto" else "display_only"
    
    print(f"[参数] result_mode={actual_mode}, max_factors={max_factors}, do_submit_check={do_submit_check}")
    print(f"[路径] 数据库: {db_path}")
    print(f"[路径] 报告: {report_path}")
    print(f"[限流] 提交间隔: {SUBMIT_INTERVAL}s")
    
    sdk = CodeActSDK()
    
    try:
        # ---- 1. 选择要跑的因子 ----
        selected_factors = list(BREAKTHROUGH_FACTORS.keys())[:max_factors]
        print(f"[信息] 选定 {len(selected_factors)} 个跃迁因子")
        
        # ---- 2. 登录 API ----
        print("[WQB] 正在登录...")
        client = WQBApiClient.login(email, password, db_path=db_path)
        
        # ---- 3. 准备提交列表（检查缓存） ----
        sim_settings = dict(DEFAULT_SIM_SETTINGS)
        to_submit = []
        cached_count = 0
        
        for factor_name in selected_factors:
            info = BREAKTHROUGH_FACTORS[factor_name]
            expression = info["fastexpr"]
            
            cached = client.get_cached_alpha(expression, sim_settings)
            if cached and cached.get("status") == "COMPLETED":
                cached_count += 1
            to_submit.append((factor_name, expression, info))
        
        print(f"[信息] 缓存命中 {cached_count} 个，待提交 {len(to_submit) - cached_count} 个")
        
        # ---- 4. 批量提交 + 等待 ----
        print(f"\n[WQB] 批量提交 {len(to_submit)} 个跃迁因子...")
        simulations = await batch_submit(client, to_submit, sim_settings)
        
        new_results = await batch_wait_and_collect(
            client, simulations, sim_settings,
            poll_interval=5.0, max_wait=600.0
        )
        
        # 重新从数据库读取最新结果，确保完整
        all_results = []
        for factor_name in selected_factors:
            info = BREAKTHROUGH_FACTORS[factor_name]
            expression = info["fastexpr"]
            cached = client.get_cached_alpha(expression, sim_settings)
            if cached:
                cached["direction"] = info.get("direction", "")
                cached["logic"] = info.get("logic", "")
                cached["description"] = info.get("description", "")
                all_results.append(cached)
            else:
                all_results.append({
                    "factor_name": factor_name,
                    "status": "UNKNOWN",
                    "direction": info.get("direction", ""),
                    "description": info.get("description", ""),
                    "expression": expression,
                })
        
        # 按 Sharpe 排序
        completed_all = [r for r in all_results if r.get("status") == "COMPLETED"]
        completed_all.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
        
        # ---- 5. 筛选合格因子 ----
        qualified = [r for r in completed_all
                      if r.get("sharpe", 0) is not None and r.get("sharpe", 0) >= SHARPE_THRESHOLD
                      and r.get("fitness", 0) is not None and r.get("fitness", 0) >= FITNESS_THRESHOLD]
        
        print(f"\n[筛选] Sharpe≥{SHARPE_THRESHOLD} 且 Fitness≥{FITNESS_THRESHOLD} 的因子: {len(qualified)} 个")
        for r in qualified:
            print(f"  - {r['factor_name']}: Sharpe={r.get('sharpe', 0):.3f}, Fitness={r.get('fitness', 0):.3f}")
        
        # ---- 6. 提交检查 ----
        check_results = []
        submitted_count = 0
        
        if do_submit_check and qualified:
            print(f"\n[提交检查] 对 {len(qualified)} 个合格因子进行提交检查...")
            
            for i, r in enumerate(qualified):
                alpha_id = r.get("alpha_id")
                if not alpha_id:
                    continue
                
                factor_name = r["factor_name"]
                print(f"\n  [{i+1}/{len(qualified)}] 检查 {factor_name} (ID: {alpha_id})")
                
                # 获取详细检查
                detail = get_detailed_checks(client, alpha_id)
                detail["factor_name"] = factor_name
                check_results.append(detail)
                
                print(f"    Stage: {detail.get('stage', 'N/A')}, Grade: {detail.get('grade', 'N/A')}")
                print(f"    Sharpe: {detail.get('sharpe', 'N/A')}, Fitness: {detail.get('fitness', 'N/A')}")
                print(f"    Turnover: {detail.get('turnover', 'N/A')}")
                
                # 尝试提交（POST submit）
                if detail.get('stage') == 'IS' or not detail.get('stage'):
                    # 还在 IS 阶段，尝试提交
                    print(f"    → 尝试提交到下一个阶段...")
                    submit_url = submit_alpha_for_check(client, alpha_id)
                    
                    if submit_url:
                        submitted_count += 1
                        # 等一会儿再查状态
                        print(f"    → 已提交，等待处理...")
                        time.sleep(CHECK_INTERVAL)
                        
                        # 重新获取状态
                        detail2 = get_detailed_checks(client, alpha_id)
                        detail2["factor_name"] = factor_name
                        check_results[-1] = detail2
                        print(f"    → 新状态: Stage={detail2.get('stage', 'N/A')}, Grade={detail2.get('grade', 'N/A')}")
                
                # 检查间隔
                if i < len(qualified) - 1:
                    await asyncio.sleep(CHECK_INTERVAL)
        
        # ---- 7. 生成报告 ----
        print(f"\n[报告] 生成跃迁因子研究报告...")
        report_path = generate_breakthrough_report(all_results, check_results, report_path, sim_settings)
        abs_report_path = os.path.abspath(report_path)
        
        print(f"[报告] 生成全因子排名报告...")
        full_ranking_path = generate_full_ranking_report(client, full_ranking_path)
        abs_full_ranking_path = os.path.abspath(full_ranking_path)
        
        # ---- 8. 输出摘要 ----
        total_completed = len(completed_all)
        total_failed = len([r for r in all_results if r.get("status") == "FAILED"])
        
        summary_lines = [
            f"跃迁因子研究完成！",
            f"测试因子：{len(selected_factors)} 个（6个逻辑方向）",
            f"结果：成功 {total_completed} / 失败 {total_failed} / 进行中 {len(all_results)-total_completed-total_failed}",
            f"合格因子（Sharpe≥{SHARPE_THRESHOLD} 且 Fitness≥{FITNESS_THRESHOLD}）：{len(qualified)} 个",
        ]
        
        if submitted_count > 0:
            summary_lines.append(f"已提交检查：{submitted_count} 个因子")
        
        if completed_all:
            top = completed_all[0]
            summary_lines.append(
                f"最佳因子：{top['factor_name']} "
                f"(Sharpe={top.get('sharpe', 0):.3f}, Fitness={top.get('fitness', 0):.3f})"
            )
            
            # Top 5
            summary_lines.append("\nTop 5 跃迁因子：")
            for i, r in enumerate(completed_all[:5]):
                sharpe = f"{r.get('sharpe', 0):.3f}"
                fitness = f"{r.get('fitness', 0):.3f}" if r.get('fitness') is not None else "N/A"
                direction = r.get('direction', '')
                summary_lines.append(f"  {i+1}. {r['factor_name']} [{direction}]: Sharpe={sharpe}, Fitness={fitness}")
        
        summary_lines.append(f"\n📊 跃迁报告：[跃迁因子研究报告](computer://{abs_report_path})")
        summary_lines.append(f"📊 全排名：[全因子排名报告](computer://{abs_full_ranking_path})")
        summary_lines.append(f"💾 状态数据库：./codeact/output/wqb_state.db")
        
        summary_message = "\n".join(summary_lines)
        
        await sdk.submit_result(
            result_mode=actual_mode,
            status="success",
            message=summary_message,
            data={
                "total_factors": len(selected_factors),
                "completed": total_completed,
                "failed": total_failed,
                "qualified": len(qualified),
                "submitted_check": submitted_count,
                "check_results": [
                    {
                        "factor_name": cr.get("factor_name", ""),
                        "alpha_id": cr.get("alpha_id", ""),
                        "sharpe": cr.get("sharpe"),
                        "fitness": cr.get("fitness"),
                        "stage": cr.get("stage"),
                        "grade": cr.get("grade"),
                    }
                    for cr in check_results
                ],
                "report_path": report_path,
                "full_ranking_path": full_ranking_path,
                "top_factor": completed_all[0].get("factor_name") if completed_all else None,
                "top_sharpe": completed_all[0].get("sharpe") if completed_all else None,
                "top_fitness": completed_all[0].get("fitness") if completed_all else None,
                "directions": len(set(r.get('direction', '') for r in completed_all if r.get('direction'))),
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
            message=f"跃迁因子研究脚本执行失败: {error_msg}",
            data={"error_type": type(e).__name__},
        )


if __name__ == "__main__":
    asyncio.run(main())
