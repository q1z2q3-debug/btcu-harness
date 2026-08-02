#!/usr/bin/env python3
"""
WorldQuant BRAIN 因子批量回测脚本 - wqb_factor_runner.py
=======================================================

功能：
  1. 从因子映射表读取因子（FASTEXPR 精确表达式）
  2. 提交到 WorldQuant BRAIN 平台进行真实回测
  3. 收集 Sharpe / Fitness / IC 等核心指标
  4. SQLite 持久化，避免重复提交，失败自动重试
  5. 参数扫描：对 Top 因子做多周期参数测试
  6. 输出详细 Markdown 报告

用法：
  python wqb_factor_runner.py [result_mode] [mode] [max_factors]

参数：
  result_mode: display_only / notify / auto (默认: display_only)
  mode:        all / new / rescan / scan_params / matrix (默认: all)
               - all: 提交所有映射表中未完成的因子
               - new: 只提交新增的 v2 因子
               - rescan: 只重试失败/pending 的因子
               - scan_params: 只运行参数扫描
               - matrix: 参数方案矩阵测试（Top因子 × 4套方案）
  max_factors: 最大提交数量 (默认: 50)
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
from wqb_api_client import WQBApiClient, WQBSimulation


# ============================================================
# 工具 Schema 版本常量
# ============================================================
TOOL_SCHEMA_VERSIONS = {
    "codeact_search_web": "v1_5ac1b0eba8c26f2a",
    "codeact_fetch_web": "v1_2c8d0580b3f93a58",
    "file_to_url": "v1_fe3416acf3d7b53b",
}


# ============================================================
# 因子 FASTEXPR 精确映射
# ============================================================
# 手动定义每个因子的准确 FASTEXPR 表达式
# 所有因子使用基础价量数据：close / open / high / low / volume / vwap / returns

FACTOR_FASTEXPR_MAP = {
    # ================================================================
    # 第一组：量价因子
    # ================================================================
    "alpha_003": {
        "category": "量价因子",
        "description": "过去10天开盘价秩与成交量秩的滚动相关系数，取负值",
        "fastexpr": "reverse(ts_corr(rank(open), rank(volume), 10))",
        "version": "v1",
    },
    "alpha_006": {
        "category": "量价因子",
        "description": "过去10天开盘价与成交量的相关系数，取负值",
        "fastexpr": "reverse(ts_corr(open, volume, 10))",
        "version": "v1",
    },
    "alpha_012": {
        "category": "量价因子",
        "description": "成交量变化方向乘以价格变化的负值（1日）",
        "fastexpr": "sign(ts_delta(volume, 1)) * reverse(ts_delta(close, 1))",
        "version": "v1",
    },
    "alpha_013": {
        "category": "量价因子",
        "description": "收盘价秩与成交量秩的5日滚动协方差，取负后排名",
        "fastexpr": "reverse(rank(ts_covariance(rank(close), rank(volume), 5)))",
        "version": "v1",
    },
    "alpha_015": {
        "category": "量价因子",
        "description": "最高价秩与成交量秩的3日相关系数排名的3日求和，取负",
        "fastexpr": "reverse(ts_sum(rank(ts_corr(rank(high), rank(volume), 3)), 3))",
        "version": "v1",
    },
    "pv_momentum": {
        "category": "量价因子",
        "description": "5日价格动量与5日成交量动量的排名乘积",
        "fastexpr": "rank(divide(ts_delta(close, 5), ts_delay(close, 5))) * rank(divide(ts_delta(volume, 5), ts_delay(volume, 5)))",
        "version": "v1",
    },

    # ================================================================
    # 第二组：动量反转因子
    # ================================================================
    "mom_20": {
        "category": "动量反转因子",
        "description": "过去20日收益率（动量）— 已知失效，用于对比",
        "fastexpr": "divide(ts_delta(close, 20), ts_delay(close, 20))",
        "version": "v1",
    },
    "reversal_5": {
        "category": "动量反转因子",
        "description": "过去5日收益率取反（短期反转）",
        "fastexpr": "reverse(divide(ts_delta(close, 5), ts_delay(close, 5)))",
        "version": "v1",
    },
    "alpha_010": {
        "category": "动量反转因子",
        "description": "4天窗口趋势/反转切换因子，横截面排名",
        "fastexpr": "rank(if_else(greater(kth_element(ts_delta(close, 1), 4, k=1), 0), ts_delta(close, 1), reverse(ts_delta(close, 1))))",
        "version": "v1",
    },
    "alpha_019": {
        "category": "动量反转因子",
        "description": "短期反转信号乘以长期动量调制",
        "fastexpr": "reverse(sign(add(ts_delta(close, 7), ts_delta(close, 7))))) * add(1.0, rank(add(1.0, ts_sum(returns, 250))))",
        "version": "v1",
    },

    # ================================================================
    # 第三组：波动率因子
    # ================================================================
    "hist_vol_20": {
        "category": "波动率因子",
        "description": "20日历史波动率取负（低波异象）",
        "fastexpr": "reverse(ts_std_dev(returns, 20))",
        "version": "v1",
    },
    "hist_vol_60": {
        "category": "波动率因子",
        "description": "60日历史波动率取负（长期低波异象）",
        "fastexpr": "reverse(ts_std_dev(returns, 60))",
        "version": "v1",
    },
    "vol_change": {
        "category": "波动率因子",
        "description": "短期波动率相对长期波动率的变化率",
        "fastexpr": "subtract(divide(ts_std_dev(returns, 5), ts_std_dev(returns, 20)), 1.0)",
        "version": "v1",
    },
    "high_low_vol": {
        "category": "波动率因子",
        "description": "日内高低波幅取负（10日均）",
        "fastexpr": "reverse(ts_mean(divide(subtract(high, low), close), 10))",
        "version": "v1",
    },

    # ================================================================
    # 第四组：情绪因子
    # ================================================================
    "volume_surge": {
        "category": "情绪因子",
        "description": "当日成交量相对20日均量的放大倍数",
        "fastexpr": "subtract(divide(volume, ts_mean(volume, 20)), 1.0)",
        "version": "v1",
    },
    "upper_shadow": {
        "category": "情绪因子",
        "description": "上影线长度占比取负（抛压信号）",
        "fastexpr": "reverse(divide(subtract(high, max(close, open)), max(close, open)))",
        "version": "v1",
    },
    "lower_shadow": {
        "category": "情绪因子",
        "description": "下影线长度占比（支撑信号）",
        "fastexpr": "divide(subtract(min(close, open), low), min(close, open))",
        "version": "v1",
    },

    # ================================================================
    # 第五组：波动率类变体（v2 新增）
    # ================================================================
    "hist_vol_5": {
        "category": "波动率因子",
        "description": "5日历史波动率取负（超短期低波）",
        "fastexpr": "reverse(ts_std_dev(returns, 5))",
        "version": "v2",
    },
    "hist_vol_10": {
        "category": "波动率因子",
        "description": "10日历史波动率取负（短期低波）",
        "fastexpr": "reverse(ts_std_dev(returns, 10))",
        "version": "v2",
    },
    "hist_vol_30": {
        "category": "波动率因子",
        "description": "30日历史波动率取负（中期低波）",
        "fastexpr": "reverse(ts_std_dev(returns, 30))",
        "version": "v2",
    },
    "hist_vol_120": {
        "category": "波动率因子",
        "description": "120日历史波动率取负（长期低波）",
        "fastexpr": "reverse(ts_std_dev(returns, 120))",
        "version": "v2",
    },
    "vol_zscore_60": {
        "category": "波动率因子",
        "description": "20日波动率的60日Z-Score取负（波动率异常高的做空）",
        "fastexpr": "reverse(ts_zscore(ts_std_dev(returns, 20), 60))",
        "version": "v2",
    },
    "vol_rank_120": {
        "category": "波动率因子",
        "description": "20日波动率的120日时序排名取反",
        "fastexpr": "reverse(ts_rank(ts_std_dev(returns, 20), 120))",
        "version": "v2",
    },
    "vol_of_vol": {
        "category": "波动率因子",
        "description": "波动率的波动率取负（5日波动率的20日标准差）",
        "fastexpr": "reverse(ts_std_dev(ts_std_dev(returns, 5), 20))",
        "version": "v2",
    },
    "hl_vol_rank_20": {
        "category": "波动率因子",
        "description": "20日日内波幅均值的横截面排名取反",
        "fastexpr": "reverse(rank(ts_mean(divide(subtract(high, low), close), 20)))",
        "version": "v2",
    },

    # ================================================================
    # 第六组：反转类变体（v2 新增）
    # ================================================================
    "reversal_1": {
        "category": "动量反转因子",
        "description": "1日收益率取反（超短期反转）",
        "fastexpr": "reverse(divide(ts_delta(close, 1), ts_delay(close, 1)))",
        "version": "v2",
    },
    "reversal_3": {
        "category": "动量反转因子",
        "description": "3日收益率取反（短期反转）",
        "fastexpr": "reverse(divide(ts_delta(close, 3), ts_delay(close, 3)))",
        "version": "v2",
    },
    "reversal_10": {
        "category": "动量反转因子",
        "description": "10日收益率取反（中期反转）",
        "fastexpr": "reverse(divide(ts_delta(close, 10), ts_delay(close, 10)))",
        "version": "v2",
    },
    "reversal_20": {
        "category": "动量反转因子",
        "description": "20日收益率取反（长期反转）",
        "fastexpr": "reverse(divide(ts_delta(close, 20), ts_delay(close, 20)))",
        "version": "v2",
    },
    "decay_reversal_10": {
        "category": "动量反转因子",
        "description": "10日线性衰减加权反转（近期权重更高）",
        "fastexpr": "reverse(ts_decay_linear(divide(ts_delta(close, 1), ts_delay(close, 1)), 10))",
        "version": "v2",
    },
    "vwap_reversal": {
        "category": "动量反转因子",
        "description": "价格相对VWAP偏离取反（均值回归）",
        "fastexpr": "reverse(divide(subtract(close, vwap), vwap))",
        "version": "v2",
    },

    # ================================================================
    # 第七组：经典 Alpha101 因子（v2 新增）
    # ================================================================
    "alpha_001": {
        "category": "Alpha101因子",
        "description": "Alpha#001: 波动率条件下收益幂的最大值排名减0.5",
        "fastexpr": "subtract(rank(ts_arg_max(signed_power(if_else(less(returns, 0), ts_std_dev(returns, 20), close), 2.0), 5)), 0.5)",
        "version": "v2",
    },
    "alpha_002": {
        "category": "Alpha101因子",
        "description": "Alpha#002: 量变排名与价变排名的6日相关取负",
        "fastexpr": "reverse(ts_corr(rank(ts_delta(log(volume), 2)), rank(divide(subtract(close, open), open)), 6))",
        "version": "v2",
    },
    "alpha_004": {
        "category": "Alpha101因子",
        "description": "Alpha#004: 最低价横截面排名的9日时序排名取反",
        "fastexpr": "reverse(ts_rank(rank(low), 9))",
        "version": "v2",
    },
    "alpha_007": {
        "category": "Alpha101因子",
        "description": "Alpha#007: 价格在近6日高低点中的相对位置",
        "fastexpr": "divide(subtract(close, kth_element(low, 6, k=1)), subtract(kth_element(high, 6, k=6), kth_element(low, 6, k=1)))",
        "version": "v2",
    },
    "alpha_008": {
        "category": "Alpha101因子",
        "description": "Alpha#008: 2日收益变化排名乘2日量变化排名取负",
        "fastexpr": "reverse(multiply(rank(ts_delta(returns, 2)), rank(ts_delta(volume, 2))))",
        "version": "v2",
    },
    "alpha_026": {
        "category": "Alpha101因子",
        "description": "Alpha#026: 最高价与成交量的5日相关取负",
        "fastexpr": "reverse(ts_corr(high, volume, 5))",
        "version": "v2",
    },
    "alpha_044": {
        "category": "Alpha101因子",
        "description": "Alpha#044: 近10日最高价出现位置的横截面排名取反",
        "fastexpr": "reverse(rank(ts_arg_max(high, 10)))",
        "version": "v2",
    },
    "alpha_057": {
        "category": "Alpha101因子",
        "description": "Alpha#057: 量比（成交量/20日均量）的5日时序排名取反",
        "fastexpr": "reverse(ts_rank(divide(volume, ts_mean(volume, 20)), 5))",
        "version": "v2",
    },
    "alpha_060": {
        "category": "Alpha101因子",
        "description": "Alpha#060: 当日涨跌幅的横截面排名",
        "fastexpr": "rank(divide(subtract(close, open), open))",
        "version": "v2",
    },
    "alpha_088": {
        "category": "Alpha101因子",
        "description": "Alpha#088: 收盘价相对VWAP偏离的横截面排名",
        "fastexpr": "rank(divide(subtract(close, vwap), vwap))",
        "version": "v2",
    },

    # ================================================================
    # 第八组：参数扫描因子（Top3 因子多周期）
    # ================================================================
    "alpha_012_d5": {
        "category": "参数扫描",
        "description": "alpha_012 5日周期版：量变方向乘价变取反",
        "fastexpr": "sign(ts_delta(volume, 5)) * reverse(ts_delta(close, 5))",
        "version": "scan",
        "base_factor": "alpha_012",
        "param_name": "周期",
        "param_value": 5,
    },
    "alpha_012_d10": {
        "category": "参数扫描",
        "description": "alpha_012 10日周期版：量变方向乘价变取反",
        "fastexpr": "sign(ts_delta(volume, 10)) * reverse(ts_delta(close, 10))",
        "version": "scan",
        "base_factor": "alpha_012",
        "param_name": "周期",
        "param_value": 10,
    },
    "alpha_012_d20": {
        "category": "参数扫描",
        "description": "alpha_012 20日周期版：量变方向乘价变取反",
        "fastexpr": "sign(ts_delta(volume, 20)) * reverse(ts_delta(close, 20))",
        "version": "scan",
        "base_factor": "alpha_012",
        "param_name": "周期",
        "param_value": 20,
    },

    # ================================================================
    # 第九组：组合因子（v3 新增）
    # ================================================================
    "combo_weighted_3f": {
        "category": "组合因子",
        "description": "加权三因子：alpha_012(50%) + reversal_5(30%) + hist_vol_20(20%)，先rank再加权",
        "fastexpr": "add(multiply(0.5, rank(sign(ts_delta(volume, 1)) * reverse(ts_delta(close, 1)))), add(multiply(0.3, rank(reverse(divide(ts_delta(close, 5), ts_delay(close, 5))))), multiply(0.2, rank(reverse(ts_std_dev(returns, 20))))))",
        "version": "v3",
        "components": {"alpha_012": 0.5, "reversal_5": 0.3, "hist_vol_20": 0.2},
        "combo_type": "weighted",
    },
    "combo_equal_3f": {
        "category": "组合因子",
        "description": "等权三因子：alpha_012 + reversal_5 + hist_vol_20，先rank再等权",
        "fastexpr": "divide(add(rank(sign(ts_delta(volume, 1)) * reverse(ts_delta(close, 1))), add(rank(reverse(divide(ts_delta(close, 5), ts_delay(close, 5)))), rank(reverse(ts_std_dev(returns, 20))))), 3.0)",
        "version": "v3",
        "components": {"alpha_012": 1/3, "reversal_5": 1/3, "hist_vol_20": 1/3},
        "combo_type": "equal_weight",
    },
    "combo_rev_vol": {
        "category": "组合因子",
        "description": "反转+波动率双因子：reversal_5(60%) + hist_vol_120(40%)，先rank再加权",
        "fastexpr": "add(multiply(0.6, rank(reverse(divide(ts_delta(close, 5), ts_delay(close, 5))))), multiply(0.4, rank(reverse(ts_std_dev(returns, 120)))))",
        "version": "v3",
        "components": {"reversal_5": 0.6, "hist_vol_120": 0.4},
        "combo_type": "weighted",
    },
    "combo_5f_equal": {
        "category": "组合因子",
        "description": "五因子等权：alpha_012 + reversal_5 + hist_vol_20 + alpha_006 + hist_vol_120，先rank再等权",
        "fastexpr": "divide(add(add(rank(sign(ts_delta(volume, 1)) * reverse(ts_delta(close, 1))), rank(reverse(divide(ts_delta(close, 5), ts_delay(close, 5))))), add(add(rank(reverse(ts_std_dev(returns, 20))), rank(reverse(ts_corr(open, volume, 10)))), rank(reverse(ts_std_dev(returns, 120))))), 5.0)",
        "version": "v3",
        "components": {"alpha_012": 0.2, "reversal_5": 0.2, "hist_vol_20": 0.2, "alpha_006": 0.2, "hist_vol_120": 0.2},
        "combo_type": "equal_weight",
    },

    # ================================================================
    # 第十组：情绪类因子（v3 新增）
    # ================================================================
    "volume_spike_5d": {
        "category": "情绪因子",
        "description": "5日量能突变：成交量/20日均量的5日均值排名取反（量能异常放大看空）",
        "fastexpr": "reverse(rank(ts_mean(divide(volume, ts_mean(volume, 20)), 5)))",
        "version": "v3",
    },
    "turnover_rank": {
        "category": "情绪因子",
        "description": "换手率横截面排名（成交量/20日均量排名作为代理）",
        "fastexpr": "rank(divide(volume, ts_mean(volume, 20)))",
        "version": "v3",
    },
    "upper_shadow_ratio": {
        "category": "情绪因子",
        "description": "上影线比例横截面排名（抛压信号）",
        "fastexpr": "rank(divide(subtract(high, max(close, open)), max(close, open)))",
        "version": "v3",
    },
    "lower_shadow_ratio": {
        "category": "情绪因子",
        "description": "下影线比例横截面排名（支撑信号）",
        "fastexpr": "rank(divide(subtract(min(close, open), low), min(close, open)))",
        "version": "v3",
    },
    "open_gap": {
        "category": "情绪因子",
        "description": "开盘缺口（跳空幅度）排名取反（缺口反转因子）",
        "fastexpr": "reverse(rank(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1))))",
        "version": "v3",
    },
    "high_break_20": {
        "category": "情绪因子",
        "description": "20日新高位置比例排名（收盘价/20日最高价）",
        "fastexpr": "rank(divide(close, kth_element(high, 20, k=20)))",
        "version": "v3",
    },
    "volume_price_diverge": {
        "category": "情绪因子",
        "description": "量价背离：价涨量缩/价跌量增（5日周期）",
        "fastexpr": "sign(ts_delta(close, 5)) * reverse(sign(ts_delta(volume, 5)))",
        "version": "v3",
    },
    "amihud_illiq": {
        "category": "情绪因子",
        "description": "Amihud非流动性指标（20日|收益率|/成交量均值）排名取反",
        "fastexpr": "reverse(rank(ts_mean(divide(abs(returns), volume), 20)))",
        "version": "v3",
    },

    # ================================================================
    # 第十一组：更多 Alpha101 因子（v3 新增）
    # ================================================================
    "alpha_005": {
        "category": "Alpha101因子",
        "description": "Alpha#005: 交易量加权波动率（20日成交量加权绝对收益）取反",
        "fastexpr": "reverse(divide(ts_sum(multiply(abs(returns), volume), 20), ts_sum(volume, 20)))",
        "version": "v3",
    },
    "alpha_009": {
        "category": "Alpha101因子",
        "description": "Alpha#009: 6日最小最低价横截面排名的9日时序排名",
        "fastexpr": "ts_rank(rank(kth_element(low, 6, k=1)), 9)",
        "version": "v3",
    },
    "alpha_014": {
        "category": "Alpha101因子",
        "description": "Alpha#014: 成交量排名与1日滞后成交量排名的10日相关系数",
        "fastexpr": "ts_corr(rank(volume), rank(ts_delay(volume, 1)), 10)",
        "version": "v3",
    },
    "alpha_017": {
        "category": "Alpha101因子",
        "description": "Alpha#017: VWAP对收盘价的20日回归截距（量价关系截距）",
        "fastexpr": "ts_regression(vwap, close, 20)",
        "version": "v3",
    },
    "alpha_021": {
        "category": "Alpha101因子",
        "description": "Alpha#021: 隔夜收益减去日内收益的横截面排名",
        "fastexpr": "rank(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)))",
        "version": "v3",
    },
    "alpha_022": {
        "category": "Alpha101因子",
        "description": "Alpha#022: 6日量价相关系数排名乘5日反转",
        "fastexpr": "multiply(rank(ts_corr(close, volume, 6)), reverse(divide(ts_delta(close, 5), ts_delay(close, 5))))",
        "version": "v3",
    },
    "alpha_030": {
        "category": "Alpha101因子",
        "description": "Alpha#030: 10日收益率符号之和（趋势持续性）",
        "fastexpr": "ts_sum(sign(returns), 10)",
        "version": "v3",
    },
    "alpha_031": {
        "category": "Alpha101因子",
        "description": "Alpha#031: 5日成交量排名乘5日收益波动排名取反",
        "fastexpr": "reverse(multiply(ts_rank(volume, 5), ts_rank(abs(returns), 5)))",
        "version": "v3",
    },
    "alpha_032": {
        "category": "Alpha101因子",
        "description": "Alpha#032: 15日价变绝对值100日排名乘价变方向取反",
        "fastexpr": "reverse(multiply(ts_rank(abs(ts_delta(close, 15)), 100), sign(ts_delta(close, 15))))",
        "version": "v3",
    },
    "alpha_035": {
        "category": "Alpha101因子",
        "description": "Alpha#035: 收盘价/成交量/最高价10日时序排名乘积取反",
        "fastexpr": "reverse(multiply(multiply(ts_rank(close, 10), ts_rank(volume, 10)), ts_rank(high, 10)))",
        "version": "v3",
    },
}

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
# 参数方案矩阵（四套配置）
# ============================================================

PARAM_SCHEMES = {
    "standard": {
        "name": "标准稳健版",
        "description": "中大盘、行业中性、中等衰减，5年周期验证",
        "settings": {
            "region": "USA",
            "universe": "TOP2000",
            "delay": 1,
            "neutralization": "INDUSTRY",
            "decay": 6,
            "truncation": 0.10,
            "pasteurization": "ON",
            "unitHandling": "VERIFY",
            "testPeriod": "P5Y0M",
        },
    },
    "aggressive": {
        "name": "高灵敏进攻版",
        "description": "大盘股、板块中性、快衰减，2年短周期捕捉机会",
        "settings": {
            "region": "USA",
            "universe": "TOP1000",
            "delay": 1,
            "neutralization": "SECTOR",
            "decay": 2,
            "truncation": 0.05,
            "pasteurization": "ON",
            "unitHandling": "VERIFY",
            "testPeriod": "P2Y0M",
        },
    },
    "low_turnover": {
        "name": "低换手长线版",
        "description": "全市场、市场中性、慢衰减，6年长周期低换手",
        "settings": {
            "region": "USA",
            "universe": "TOP3000",
            "delay": 1,
            "neutralization": "MARKET",
            "decay": 12,
            "truncation": 0.12,
            "pasteurization": "ON",
            "unitHandling": "VERIFY",
            "testPeriod": "P6Y0M",
        },
    },
    "drawdown_control": {
        "name": "异常修复稳回撤版",
        "description": "中大盘、细分行业中性、中慢衰减，6年周期控回撤",
        "settings": {
            "region": "USA",
            "universe": "TOP2000",
            "delay": 1,
            "neutralization": "SUBINDUSTRY",
            "decay": 8,
            "truncation": 0.15,
            "pasteurization": "ON",
            "unitHandling": "VERIFY",
            "testPeriod": "P6Y0M",
        },
    },
}

# 参与矩阵测试的 Top 因子（按 Sharpe 排名）
TOP_FACTORS_MATRIX = [
    "reversal_5",      # Sharpe 1.16 - 动量反转因子
    "alpha_012",       # Sharpe 1.00 - 量价因子
    "hist_vol_120",    # Sharpe 0.93 - 波动率因子
    "hist_vol_20",     # Sharpe 0.86 - 波动率因子
    "alpha_006",       # Sharpe 0.85 - 量价因子
]

# Baseline 配置标签
BASELINE_LABEL = "baseline"

# 提交间隔（秒）- 保守限流（WQB 免费版限流严格，40秒较安全）
SUBMIT_INTERVAL = 40.0


# ============================================================
# 报告生成
# ============================================================

def generate_report(results: List[dict], output_path: str) -> str:
    """
    生成 Markdown 格式的回测报告

    Args:
        results: 因子回测结果列表
        output_path: 报告输出路径

    Returns:
        报告文件路径
    """
    # 按 Sharpe 排序
    completed = [r for r in results if r.get("status") == "COMPLETED"]
    failed = [r for r in results if r.get("status") == "FAILED"]
    pending = [r for r in results if r.get("status") == "PENDING"]
    completed.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)

    lines = []
    lines.append("# WorldQuant BRAIN 因子回测报告")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**回测设置**: USA / TOP3000 / delay=1 / decay=15 / SUBINDUSTRY / P1Y6M")
    lines.append(f"**成功**: {len(completed)} 个 | **失败**: {len(failed)} 个 | **进行中**: {len(pending)} 个")
    lines.append("")

    # ---- 核心指标汇总表 ----
    lines.append("## 核心指标汇总（按 Sharpe 排名）")
    lines.append("")
    lines.append("| 排名 | 因子名称 | 类别 | 版本 | Sharpe | Fitness | 年化收益 | 换手率 | 等级 |")
    lines.append("|------|----------|------|------|--------|---------|----------|--------|------|")

    for i, r in enumerate(completed):
        sharpe = f"{r.get('sharpe', 0):.3f}" if r.get("sharpe") is not None else "N/A"
        fitness = f"{r.get('fitness', 0):.3f}" if r.get("fitness") is not None else "N/A"
        annual_ret = f"{r.get('annual_return', 0):.2%}" if r.get("annual_return") is not None else "N/A"
        turnover = f"{r.get('turnover', 0):.2%}" if r.get("turnover") is not None else "N/A"
        grade = r.get("grade", "N/A") or "N/A"
        version = r.get("version", "v1") or "v1"
        lines.append(
            f"| {i+1} | {r.get('factor_name', '?')} | {r.get('category', '?')} | "
            f"{version} | {sharpe} | {fitness} | {annual_ret} | {turnover} | {grade} |"
        )

    lines.append("")

    # ---- 按类别统计 ----
    lines.append("## 按类别统计")
    lines.append("")

    category_stats = defaultdict(list)
    for r in completed:
        cat = r.get("category", "未知")
        category_stats[cat].append(r)

    for cat, items in sorted(category_stats.items()):
        items.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
        avg_sharpe = sum(x.get("sharpe", 0) or 0 for x in items) / len(items) if items else 0
        avg_fitness = sum(x.get("fitness", 0) or 0 for x in items) / len(items) if items else 0
        best = items[0]
        lines.append(
            f"- **{cat}**: {len(items)} 个因子, "
            f"平均 Sharpe={avg_sharpe:.3f}, 平均 Fitness={avg_fitness:.3f}, "
            f"最佳={best.get('factor_name')} (Sharpe={best.get('sharpe', 0):.3f})"
        )

    lines.append("")

    # ---- 参数扫描分析 ----
    scan_results = [r for r in completed if r.get("category") == "参数扫描"]
    if scan_results:
        lines.append("## 参数扫描分析")
        lines.append("")

        # 按基础因子分组
        base_groups = defaultdict(list)
        for r in scan_results:
            base = r.get("factor_name", "")
            # 从因子名提取基础因子
            for bf in ["alpha_012"]:
                if base.startswith(bf + "_"):
                    base_groups[bf].append(r)
                    break

        for base_f, items in base_groups.items():
            items.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)
            lines.append(f"### {base_f} 周期参数扫描")
            lines.append("")
            lines.append("| 参数值 | Sharpe | Fitness | 换手率 |")
            lines.append("|--------|--------|---------|--------|")
            for r in items:
                # 从因子名提取参数值
                fname = r.get("factor_name", "")
                parts = fname.split("_d")
                param_val = parts[-1] if len(parts) > 1 else "?"
                sharpe = f"{r.get('sharpe', 0):.3f}" if r.get("sharpe") is not None else "N/A"
                fitness = f"{r.get('fitness', 0):.3f}" if r.get("fitness") is not None else "N/A"
                turnover = f"{r.get('turnover', 0):.2%}" if r.get("turnover") is not None else "N/A"
                lines.append(f"| {param_val}日 | {sharpe} | {fitness} | {turnover} |")
            lines.append("")

        # 波动率周期扫描（hist_vol 系列）
        vol_items = [r for r in completed if r.get("factor_name", "").startswith("hist_vol_")]
        if vol_items:
            vol_items.sort(key=lambda x: int(x.get("factor_name", "").split("_")[-1]) if x.get("factor_name", "").split("_")[-1].isdigit() else 0)
            lines.append("### hist_vol 波动率周期扫描")
            lines.append("")
            lines.append("| 周期 | Sharpe | Fitness | 换手率 | 年化收益 |")
            lines.append("|------|--------|---------|--------|----------|")
            for r in vol_items:
                fname = r.get("factor_name", "")
                period = fname.split("_")[-1]
                sharpe = f"{r.get('sharpe', 0):.3f}" if r.get("sharpe") is not None else "N/A"
                fitness = f"{r.get('fitness', 0):.3f}" if r.get("fitness") is not None else "N/A"
                turnover = f"{r.get('turnover', 0):.2%}" if r.get("turnover") is not None else "N/A"
                ann = f"{r.get('annual_return', 0):.2%}" if r.get("annual_return") is not None else "N/A"
                lines.append(f"| {period}日 | {sharpe} | {fitness} | {turnover} | {ann} |")
            lines.append("")

        # 反转周期扫描（reversal 系列）
        rev_items = [r for r in completed if r.get("factor_name", "").startswith("reversal_")]
        if rev_items:
            rev_items.sort(key=lambda x: int(x.get("factor_name", "").split("_")[-1]) if x.get("factor_name", "").split("_")[-1].isdigit() else 0)
            lines.append("### reversal 反转周期扫描")
            lines.append("")
            lines.append("| 周期 | Sharpe | Fitness | 换手率 | 年化收益 |")
            lines.append("|------|--------|---------|--------|----------|")
            for r in rev_items:
                fname = r.get("factor_name", "")
                period = fname.split("_")[-1]
                sharpe = f"{r.get('sharpe', 0):.3f}" if r.get("sharpe") is not None else "N/A"
                fitness = f"{r.get('fitness', 0):.3f}" if r.get("fitness") is not None else "N/A"
                turnover = f"{r.get('turnover', 0):.2%}" if r.get("turnover") is not None else "N/A"
                ann = f"{r.get('annual_return', 0):.2%}" if r.get("annual_return") is not None else "N/A"
                lines.append(f"| {period}日 | {sharpe} | {fitness} | {turnover} | {ann} |")
            lines.append("")

    # ---- 失败因子 ----
    if failed:
        lines.append("## 失败因子")
        lines.append("")
        for r in failed:
            err = r.get("error", "未知错误")
            # 截断错误信息
            if len(err) > 100:
                err = err[:100] + "..."
            lines.append(f"- **{r.get('factor_name', '?')}** ({r.get('category', '?')}): {err}")
        lines.append("")

    # ---- 进行中因子 ----
    if pending:
        lines.append("## 进行中的因子")
        lines.append("")
        for r in pending:
            lines.append(f"- **{r.get('factor_name', '?')}** ({r.get('category', '?')})")
        lines.append("")

    # ---- Top 因子详情 ----
    lines.append("## Top 因子详情")
    lines.append("")

    top_n = min(10, len(completed))
    for r in completed[:top_n]:
        lines.append(f"### {r.get('factor_name', '?')}")
        lines.append("")
        lines.append(f"- **类别**: {r.get('category', '?')}")
        lines.append(f"- **版本**: {r.get('version', 'v1')}")
        lines.append(f"- **Alpha ID**: `{r.get('alpha_id', 'N/A')}`")
        lines.append(f"- **表达式**: `{r.get('expression', 'N/A')}`")
        lines.append(f"- **描述**: {r.get('description', 'N/A')}")
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        metrics = [
            ("Sharpe (IS)", f"{r.get('sharpe', 0):.4f}" if r.get('sharpe') is not None else "N/A"),
            ("Fitness", f"{r.get('fitness', 0):.4f}" if r.get('fitness') is not None else "N/A"),
            ("年化收益", f"{r.get('annual_return', 0):.2%}" if r.get('annual_return') is not None else "N/A"),
            ("换手率", f"{r.get('turnover', 0):.2%}" if r.get('turnover') is not None else "N/A"),
            ("最大回撤", f"{r.get('max_drawdown', 0):.2%}" if r.get('max_drawdown') is not None else "N/A"),
            ("Sharpe (Train)", f"{r.get('train_sharpe', 0):.4f}" if r.get('train_sharpe') is not None else "N/A"),
            ("Sharpe (Test)", f"{r.get('test_sharpe', 0):.4f}" if r.get('test_sharpe') is not None else "N/A"),
            ("质量等级", r.get('grade', 'N/A') or 'N/A'),
        ]
        for name, val in metrics:
            lines.append(f"| {name} | {val} |")
        lines.append("")

        # 年度表现
        yearly = r.get("yearly_data")
        if yearly:
            lines.append("**年度表现**:")
            lines.append("")
            lines.append("| 年份 | PnL | Sharpe | 天数 |")
            lines.append("|------|-----|--------|------|")
            for y in yearly:
                pnl = f"{y.get('pnl', 0):.2f}"
                sharpe_y = f"{y.get('sharpe', 0):.3f}" if y.get('sharpe') is not None else "N/A"
                lines.append(f"| {y.get('year')} | {pnl} | {sharpe_y} | {y.get('days', 0)} |")
            lines.append("")

    report_content = "\n".join(lines)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    return output_path


# ============================================================
# 参数矩阵对比报告生成
# ============================================================

def generate_param_matrix_report(matrix_results: List[dict], output_path: str) -> str:
    """
    生成参数矩阵对比报告

    Args:
        matrix_results: 矩阵测试结果列表，每个元素包含：
            factor_name, scheme_key, scheme_name, category,
            sharpe, fitness, annual_return, turnover, max_drawdown, status
        output_path: 报告输出路径

    Returns:
        报告文件路径
    """
    lines = []
    lines.append("# WorldQuant BRAIN 参数矩阵对比报告")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**测试因子**: {len(TOP_FACTORS_MATRIX)} 个 Top 因子")
    lines.append(f"**参数方案**: {len(PARAM_SCHEMES)} 套 + 1 套 Baseline")
    lines.append("")

    # 统计完成情况
    completed = [r for r in matrix_results if r.get("status") == "COMPLETED"]
    failed = [r for r in matrix_results if r.get("status") == "FAILED"]
    pending = [r for r in matrix_results if r.get("status") == "PENDING"]

    lines.append(f"**完成情况**: 成功 {len(completed)} / 失败 {len(failed)} / 进行中 {len(pending)}")
    lines.append("")

    # ---- 四套方案概览 ----
    lines.append("## 一、参数方案概览")
    lines.append("")
    lines.append("| 方案代号 | 方案名称 | Universe | 中性化 | Decay | 截断 | 测试周期 | 特点 |")
    lines.append("|----------|----------|----------|--------|-------|------|----------|------|")
    for key, scheme in PARAM_SCHEMES.items():
        s = scheme["settings"]
        lines.append(
            f"| {key} | {scheme['name']} | {s['universe']} | {s['neutralization']} | "
            f"{s['decay']} | {s['truncation']:.0%} | {s['testPeriod']} | {scheme['description']} |"
        )
    # Baseline
    bl = DEFAULT_SIM_SETTINGS
    lines.append(
        f"| baseline | 基准配置 | {bl['universe']} | {bl['neutralization']} | "
        f"{bl['decay']} | {bl['truncation']:.0%} | {bl['testPeriod']} | 当前默认配置 |"
    )
    lines.append("")

    # ---- 每个因子的对比表 ----
    lines.append("## 二、各因子参数方案对比")
    lines.append("")

    # 按因子分组
    factor_groups = defaultdict(list)
    for r in matrix_results:
        factor_groups[r["factor_name"]].append(r)

    for factor_name in TOP_FACTORS_MATRIX:
        items = factor_groups.get(factor_name, [])
        if not items:
            continue

        # 获取因子信息
        factor_info = FACTOR_FASTEXPR_MAP.get(factor_name, {})
        category = factor_info.get("category", "未知")
        description = factor_info.get("description", "")

        lines.append(f"### {factor_name}（{category}）")
        lines.append("")
        lines.append(f"> {description}")
        lines.append("")
        lines.append("| 方案 | Sharpe | Fitness | 年化收益 | 换手率 | 最大回撤 | 状态 |")
        lines.append("|------|--------|---------|----------|--------|----------|------|")

        # 按方案排序展示
        scheme_order = ["baseline"] + list(PARAM_SCHEMES.keys())
        for scheme_key in scheme_order:
            item = next((r for r in items if r.get("scheme_key") == scheme_key), None)
            if not item:
                continue

            status = item.get("status", "UNKNOWN")
            if status == "COMPLETED":
                sharpe = f"{item.get('sharpe', 0):.3f}" if item.get('sharpe') is not None else "N/A"
                fitness = f"{item.get('fitness', 0):.3f}" if item.get('fitness') is not None else "N/A"
                ann = f"{item.get('annual_return', 0):.2%}" if item.get('annual_return') is not None else "N/A"
                turnover = f"{item.get('turnover', 0):.2%}" if item.get('turnover') is not None else "N/A"
                mdd = f"{item.get('max_drawdown', 0):.2%}" if item.get('max_drawdown') is not None else "N/A"
                scheme_display = PARAM_SCHEMES.get(scheme_key, {}).get("name", scheme_key)
                if scheme_key == "baseline":
                    scheme_display = "基准 (baseline)"
                lines.append(f"| {scheme_display} | {sharpe} | {fitness} | {ann} | {turnover} | {mdd} | ✅ |")
            elif status == "PENDING":
                scheme_display = PARAM_SCHEMES.get(scheme_key, {}).get("name", scheme_key)
                if scheme_key == "baseline":
                    scheme_display = "基准 (baseline)"
                lines.append(f"| {scheme_display} | - | - | - | - | - | ⏳ 进行中 |")
            else:
                scheme_display = PARAM_SCHEMES.get(scheme_key, {}).get("name", scheme_key)
                if scheme_key == "baseline":
                    scheme_display = "基准 (baseline)"
                err = item.get("error", "失败")[:30]
                lines.append(f"| {scheme_display} | - | - | - | - | - | ❌ {err} |")

        # 找出该因子的最优方案（按 Sharpe）
        completed_items = [r for r in items if r.get("status") == "COMPLETED" and r.get("sharpe") is not None]
        if completed_items:
            best = max(completed_items, key=lambda x: x["sharpe"])
            best_scheme = best["scheme_key"]
            best_scheme_name = PARAM_SCHEMES.get(best_scheme, {}).get("name", best_scheme)
            if best_scheme == "baseline":
                best_scheme_name = "基准配置"
            lines.append("")
            lines.append(
                f"**最优方案**: {best_scheme_name} (Sharpe={best['sharpe']:.3f}, "
                f"Fitness={best.get('fitness', 0):.3f})"
            )

            # 相对于 baseline 的提升
            baseline_item = next((r for r in items if r.get("scheme_key") == "baseline" and r.get("status") == "COMPLETED"), None)
            if baseline_item and best_scheme != "baseline" and baseline_item.get("sharpe"):
                improvement = best["sharpe"] - baseline_item["sharpe"]
                improvement_pct = improvement / baseline_item["sharpe"] * 100 if baseline_item["sharpe"] != 0 else 0
                lines.append(
                    f"  - 相对基准 Sharpe 提升: +{improvement:.3f} (+{improvement_pct:.1f}%)"
                )

        lines.append("")

    # ---- 每类因子的最优方案推荐 ----
    lines.append("## 三、各类因子最优方案推荐")
    lines.append("")

    # 按类别分组
    category_results = defaultdict(list)
    for r in completed:
        factor_info = FACTOR_FASTEXPR_MAP.get(r["factor_name"], {})
        cat = factor_info.get("category", "未知")
        category_results[cat].append(r)

    for cat, items in sorted(category_results.items()):
        if not items:
            continue
        # 找出该类别下 Sharpe 最高的组合
        best = max(items, key=lambda x: x.get("sharpe") or -999)
        best_scheme = best["scheme_key"]
        best_scheme_name = PARAM_SCHEMES.get(best_scheme, {}).get("name", best_scheme)
        if best_scheme == "baseline":
            best_scheme_name = "基准配置"

        # 统计该类别下各方案的平均表现
        scheme_avg = defaultdict(list)
        for r in items:
            scheme_avg[r["scheme_key"]].append(r.get("sharpe") or 0)

        avg_by_scheme = {k: sum(v)/len(v) for k, v in scheme_avg.items() if v}
        best_avg_scheme = max(avg_by_scheme, key=avg_by_scheme.get) if avg_by_scheme else None
        best_avg_name = PARAM_SCHEMES.get(best_avg_scheme, {}).get("name", best_avg_scheme) if best_avg_scheme else "N/A"
        if best_avg_scheme == "baseline":
            best_avg_name = "基准配置"

        lines.append(f"### {cat}")
        lines.append("")
        lines.append(f"- **单因子最优**: {best['factor_name']} × {best_scheme_name} (Sharpe={best.get('sharpe', 0):.3f})")
        lines.append(f"- **平均最优方案**: {best_avg_name} (平均 Sharpe={avg_by_scheme.get(best_avg_scheme, 0):.3f})")
        lines.append("")

        # 该类别各方案平均表现表
        lines.append("| 方案 | 平均 Sharpe | 平均 Fitness | 样本数 |")
        lines.append("|------|------------|-------------|--------|")
        scheme_order = ["baseline"] + list(PARAM_SCHEMES.keys())
        for sk in scheme_order:
            if sk not in scheme_avg:
                continue
            sk_items = [r for r in items if r["scheme_key"] == sk]
            avg_sharpe = sum(r.get("sharpe", 0) or 0 for r in sk_items) / len(sk_items) if sk_items else 0
            avg_fitness = sum(r.get("fitness", 0) or 0 for r in sk_items) / len(sk_items) if sk_items else 0
            sk_name = PARAM_SCHEMES.get(sk, {}).get("name", sk)
            if sk == "baseline":
                sk_name = "基准配置"
            lines.append(f"| {sk_name} | {avg_sharpe:.3f} | {avg_fitness:.3f} | {len(sk_items)} |")
        lines.append("")

    # ---- 交叉分析 ----
    lines.append("## 四、参数交叉分析")
    lines.append("")

    if completed:
        # 1. Decay 影响分析
        lines.append("### 4.1 Decay（衰减周期）对表现的影响")
        lines.append("")

        decay_groups = defaultdict(list)
        for r in completed:
            scheme_key = r.get("scheme_key", "")
            if scheme_key in PARAM_SCHEMES:
                decay = PARAM_SCHEMES[scheme_key]["settings"]["decay"]
                decay_groups[decay].append(r.get("sharpe") or 0)

        if decay_groups:
            lines.append("| Decay 周期 | 平均 Sharpe | 组合数 |")
            lines.append("|-----------|------------|--------|")
            for decay in sorted(decay_groups.keys()):
                vals = decay_groups[decay]
                avg = sum(vals) / len(vals) if vals else 0
                lines.append(f"| {decay} 日 | {avg:.3f} | {len(vals)} |")
            lines.append("")

            # 趋势判断
            sorted_decays = sorted(decay_groups.keys())
            if len(sorted_decays) >= 2:
                first_avg = sum(decay_groups[sorted_decays[0]]) / len(decay_groups[sorted_decays[0]])
                last_avg = sum(decay_groups[sorted_decays[-1]]) / len(decay_groups[sorted_decays[-1]])
                trend = "上升" if last_avg > first_avg else "下降"
                lines.append(f"**趋势**: 从 decay={sorted_decays[0]} 到 decay={sorted_decays[-1]}，Sharpe 呈{trend}趋势 "
                             f"({first_avg:.3f} → {last_avg:.3f})")
                lines.append("")

        # 2. 中性化方式影响
        lines.append("### 4.2 中性化方式对表现的影响")
        lines.append("")

        neut_groups = defaultdict(list)
        for r in completed:
            scheme_key = r.get("scheme_key", "")
            if scheme_key in PARAM_SCHEMES:
                neut = PARAM_SCHEMES[scheme_key]["settings"]["neutralization"]
                neut_groups[neut].append(r.get("sharpe") or 0)

        if neut_groups:
            lines.append("| 中性化方式 | 平均 Sharpe | 组合数 |")
            lines.append("|-----------|------------|--------|")
            for neut in sorted(neut_groups.keys(), key=lambda x: -sum(neut_groups[x])/len(neut_groups[x]) if neut_groups[x] else 0):
                vals = neut_groups[neut]
                avg = sum(vals) / len(vals) if vals else 0
                lines.append(f"| {neut} | {avg:.3f} | {len(vals)} |")
            lines.append("")

        # 3. 样本池（Universe）影响
        lines.append("### 4.3 样本池（Universe）对表现的影响")
        lines.append("")

        univ_groups = defaultdict(list)
        for r in completed:
            scheme_key = r.get("scheme_key", "")
            if scheme_key in PARAM_SCHEMES:
                univ = PARAM_SCHEMES[scheme_key]["settings"]["universe"]
                univ_groups[univ].append(r.get("sharpe") or 0)

        if univ_groups:
            lines.append("| 样本池 | 平均 Sharpe | 组合数 |")
            lines.append("|--------|------------|--------|")
            for univ in sorted(univ_groups.keys()):
                vals = univ_groups[univ]
                avg = sum(vals) / len(vals) if vals else 0
                lines.append(f"| {univ} | {avg:.3f} | {len(vals)} |")
            lines.append("")

    # ---- 综合排名 ----
    lines.append("## 五、综合排名（所有组合）")
    lines.append("")

    # 按 Sharpe 排名
    completed_sorted = sorted(completed, key=lambda x: x.get("sharpe") or -999, reverse=True)

    lines.append("### 5.1 按 Sharpe 排名")
    lines.append("")
    lines.append("| 排名 | 因子 | 方案 | Sharpe | Fitness | 年化收益 | 换手率 | 最大回撤 |")
    lines.append("|------|------|------|--------|---------|----------|--------|----------|")

    for i, r in enumerate(completed_sorted[:20]):
        scheme_key = r.get("scheme_key", "")
        scheme_name = PARAM_SCHEMES.get(scheme_key, {}).get("name", scheme_key)
        if scheme_key == "baseline":
            scheme_name = "基准"
        factor_info = FACTOR_FASTEXPR_MAP.get(r["factor_name"], {})
        sharpe = f"{r.get('sharpe', 0):.3f}" if r.get('sharpe') is not None else "N/A"
        fitness = f"{r.get('fitness', 0):.3f}" if r.get('fitness') is not None else "N/A"
        ann = f"{r.get('annual_return', 0):.2%}" if r.get('annual_return') is not None else "N/A"
        turnover = f"{r.get('turnover', 0):.2%}" if r.get('turnover') is not None else "N/A"
        mdd = f"{r.get('max_drawdown', 0):.2%}" if r.get('max_drawdown') is not None else "N/A"
        lines.append(f"| {i+1} | {r['factor_name']} | {scheme_name} | {sharpe} | {fitness} | {ann} | {turnover} | {mdd} |")

    lines.append("")

    # 按 Fitness 排名
    fitness_sorted = sorted(completed, key=lambda x: x.get("fitness") or -999, reverse=True)

    lines.append("### 5.2 按 Fitness 排名")
    lines.append("")
    lines.append("| 排名 | 因子 | 方案 | Fitness | Sharpe | 年化收益 | 换手率 |")
    lines.append("|------|------|------|---------|--------|----------|--------|")

    for i, r in enumerate(fitness_sorted[:20]):
        scheme_key = r.get("scheme_key", "")
        scheme_name = PARAM_SCHEMES.get(scheme_key, {}).get("name", scheme_key)
        if scheme_key == "baseline":
            scheme_name = "基准"
        sharpe = f"{r.get('sharpe', 0):.3f}" if r.get('sharpe') is not None else "N/A"
        fitness = f"{r.get('fitness', 0):.3f}" if r.get('fitness') is not None else "N/A"
        ann = f"{r.get('annual_return', 0):.2%}" if r.get('annual_return') is not None else "N/A"
        turnover = f"{r.get('turnover', 0):.2%}" if r.get('turnover') is not None else "N/A"
        lines.append(f"| {i+1} | {r['factor_name']} | {scheme_name} | {fitness} | {sharpe} | {ann} | {turnover} |")

    lines.append("")

    # ---- 结论与建议 ----
    lines.append("## 六、结论与建议")
    lines.append("")

    if completed_sorted:
        top_sharpe = completed_sorted[0]
        top_scheme = top_sharpe["scheme_key"]
        top_scheme_name = PARAM_SCHEMES.get(top_scheme, {}).get("name", top_scheme)
        if top_scheme == "baseline":
            top_scheme_name = "基准配置"

        lines.append(f"1. **Sharpe 最优组合**: {top_sharpe['factor_name']} × {top_scheme_name} "
                     f"(Sharpe={top_sharpe.get('sharpe', 0):.3f})")

        top_fitness = fitness_sorted[0] if fitness_sorted else top_sharpe
        top_f_scheme = top_fitness["scheme_key"]
        top_f_name = PARAM_SCHEMES.get(top_f_scheme, {}).get("name", top_f_scheme)
        if top_f_scheme == "baseline":
            top_f_name = "基准配置"
        lines.append(f"2. **Fitness 最优组合**: {top_fitness['factor_name']} × {top_f_name} "
                     f"(Fitness={top_fitness.get('fitness', 0):.3f})")

        # 找出综合最优方案（Sharpe 和 Fitness 都在前 50%）
        n = len(completed_sorted)
        top_half_sharpe = set(r["factor_name"] + "|" + r["scheme_key"] for r in completed_sorted[:max(1, n//2)])
        top_half_fitness = set(r["factor_name"] + "|" + r["scheme_key"] for r in fitness_sorted[:max(1, n//2)])
        overlap = top_half_sharpe & top_half_fitness
        if overlap:
            lines.append(f"3. **双优组合**（Sharpe 和 Fitness 均在前 50%）: {len(overlap)} 个")
            lines.append("")
            for combo in list(overlap)[:5]:
                fname, skey = combo.split("|")
                sname = PARAM_SCHEMES.get(skey, {}).get("name", skey)
                if skey == "baseline":
                    sname = "基准"
                lines.append(f"   - {fname} × {sname}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append(f"*数据来源: WorldQuant BRAIN 平台 API*")

    report_content = "\n".join(lines)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    return output_path


# ============================================================
# 因子提交与结果收集（批量提交 + 批量等待，提高效率）
# ============================================================

async def batch_submit(client: WQBApiClient, to_submit: List[tuple],
                       sim_settings: dict) -> List[WQBSimulation]:
    """
    批量提交因子（串行提交，控制间隔避免限流）

    Args:
        to_submit: [(factor_name, expression, info), ...]
        sim_settings: 回测设置

    Returns:
        WQBSimulation 列表
    """
    simulations = []

    for i, (factor_name, expression, info) in enumerate(to_submit):
        category = info.get("category", "未知")

        # 标记为 PENDING
        client.save_alpha_result(
            expression=expression,
            settings=sim_settings,
            factor_name=factor_name,
            category=category,
            status="PENDING",
        )

        try:
            sim = client.simulate(expression, sim_settings)
            sim.factor_name = factor_name
            sim.category = category
            sim.description = info.get("description", "")
            sim.version = info.get("version", "v1")
            sim._submitted = True
            simulations.append(sim)
            # 提交成功后保存 progress_url
            client.save_alpha_result(
                expression=expression,
                settings=sim_settings,
                factor_name=factor_name,
                category=category,
                progress_url=sim.progress_url,
                status="PENDING",
            )
            print(f"  [{i+1}/{len(to_submit)}] ✓ 提交 {factor_name}")
        except Exception as e:
            error_str = str(e)
            print(f"  [{i+1}/{len(to_submit)}] ✗ 提交失败 {factor_name}: {error_str[:80]}")
            # 保存失败状态
            client.save_alpha_result(
                expression=expression,
                settings=sim_settings,
                factor_name=factor_name,
                category=category,
                status="FAILED",
                error=error_str,
            )
            sim_obj = WQBSimulation(client, None, expression, sim_settings)
            sim_obj.factor_name = factor_name
            sim_obj.category = category
            sim_obj.description = info.get("description", "")
            sim_obj.version = info.get("version", "v1")
            sim_obj.status = "FAILED"
            sim_obj.error = error_str
            sim_obj._submitted = False
            simulations.append(sim_obj)

        # 提交间隔（保守限流）
        if i < len(to_submit) - 1:
            await asyncio.sleep(SUBMIT_INTERVAL)

    return simulations


async def batch_wait_and_collect(client: WQBApiClient, simulations: List[WQBSimulation],
                                 sim_settings: dict, poll_interval: float = 5.0,
                                 max_wait: float = 300.0) -> List[dict]:
    """
    批量等待模拟完成并收集结果

    Args:
        simulations: 模拟任务列表
        sim_settings: 回测设置
        poll_interval: 轮询间隔（秒）
        max_wait: 最大等待时间（秒）

    Returns:
        结果字典列表
    """
    results = []
    pending_sims = [s for s in simulations if s.status == "PENDING" and getattr(s, '_submitted', False)]
    completed_count = 0
    failed_count = 0
    start_time = asyncio.get_event_loop().time()

    print(f"\n[等待] {len(pending_sims)} 个模拟进行中，最多等待 {max_wait}s...")

    while pending_sims and (asyncio.get_event_loop().time() - start_time) < max_wait:
        still_pending = []

        for sim in pending_sims:
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
                            "expression": sim.expression,
                            "description": sim.description,
                            "alpha_id": sim.alpha_id,
                            "status": "COMPLETED",
                            "version": getattr(sim, 'version', 'v1'),
                            **metrics,
                            "yearly_data": yearly,
                        })
                        print(f"  ✓ [{completed_count}/{len(pending_sims)}] {sim.factor_name}: "
                              f"Sharpe={metrics.get('sharpe', 'N/A')}")
                    except Exception as e:
                        print(f"  ✗ 获取结果失败 {sim.factor_name}: {e}")
                        client.save_alpha_result(
                            expression=sim.expression,
                            settings=sim_settings,
                            factor_name=sim.factor_name,
                            category=sim.category,
                            status="FAILED",
                            error=f"结果获取失败: {e}",
                        )
                        results.append({
                            "factor_name": sim.factor_name,
                            "category": sim.category,
                            "expression": sim.expression,
                            "description": sim.description,
                            "status": "FAILED",
                            "version": getattr(sim, 'version', 'v1'),
                            "error": f"结果获取失败: {e}",
                        })
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
                    settings=sim_settings,
                    factor_name=sim.factor_name,
                    category=sim.category,
                    status="FAILED",
                    error=str(e),
                )
                results.append({
                    "factor_name": sim.factor_name,
                    "category": sim.category,
                    "expression": sim.expression,
                    "description": sim.description,
                    "status": "FAILED",
                    "version": getattr(sim, 'version', 'v1'),
                    "error": str(e),
                })

        pending_sims = still_pending
        if pending_sims:
            # 等待一小段时间再轮询
            await asyncio.sleep(min(poll_interval, 3.0))

    # 处理超时仍在 pending 的模拟
    for sim in pending_sims:
        print(f"  ⏳ {sim.factor_name} 超时，保持 PENDING 状态（下次运行自动重试）")
        results.append({
            "factor_name": sim.factor_name,
            "category": sim.category,
            "expression": sim.expression,
            "description": sim.description,
            "status": "PENDING",
            "version": getattr(sim, 'version', 'v1'),
        })

    # 加上提交失败的
    for sim in simulations:
        if not getattr(sim, '_submitted', False) and sim.status == "FAILED":
            results.append({
                "factor_name": sim.factor_name,
                "category": sim.category,
                "expression": sim.expression,
                "description": sim.description,
                "status": "FAILED",
                "version": getattr(sim, 'version', 'v1'),
                "error": sim.error or "提交失败",
            })

    return results


# ============================================================
# 组合因子验证报告生成
# ============================================================

def generate_combination_report(all_results: List[dict], output_path: str) -> str:
    """
    生成组合因子与单因子对比验证报告

    Args:
        all_results: 所有因子回测结果列表
        output_path: 报告输出路径

    Returns:
        报告文件路径
    """
    # 筛选组合因子和其成分因子
    combo_factors = [r for r in all_results
                     if r.get("category") == "组合因子" and r.get("status") == "COMPLETED"]
    combo_factors.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)

    # 所有已完成的因子（用于对比）
    completed_all = [r for r in all_results if r.get("status") == "COMPLETED"]
    completed_all.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)

    # 成分因子字典
    component_map = {}
    for fname, info in FACTOR_FASTEXPR_MAP.items():
        if info.get("category") == "组合因子" and "components" in info:
            component_map[fname] = info["components"]

    lines = []
    lines.append("# WorldQuant BRAIN 组合因子验证报告")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**回测设置**: USA / TOP3000 / delay=1 / decay=15 / SUBINDUSTRY / P1Y6M")
    lines.append(f"**组合因子**: {len(combo_factors)} 个 | **对比基准**: {len(completed_all)} 个单因子")
    lines.append("")

    # ---- 一、组合因子排名 ----
    lines.append("## 一、组合因子表现排名")
    lines.append("")
    lines.append("| 排名 | 组合名称 | 类型 | Sharpe | Fitness | 年化收益 | 换手率 | 相对最佳单因子提升 |")
    lines.append("|------|----------|------|--------|---------|----------|--------|--------------------|")

    for i, combo in enumerate(combo_factors):
        fname = combo.get("factor_name", "?")
        combo_type = FACTOR_FASTEXPR_MAP.get(fname, {}).get("combo_type", "?")
        type_map = {"weighted": "加权", "equal_weight": "等权"}
        type_display = type_map.get(combo_type, combo_type)

        sharpe = f"{combo.get('sharpe', 0):.3f}" if combo.get('sharpe') is not None else "N/A"
        fitness = f"{combo.get('fitness', 0):.3f}" if combo.get('fitness') is not None else "N/A"
        ann = f"{combo.get('annual_return', 0):.2%}" if combo.get('annual_return') is not None else "N/A"
        turnover = f"{combo.get('turnover', 0):.2%}" if combo.get('turnover') is not None else "N/A"

        # 计算相对最佳成分因子的提升
        components = component_map.get(fname, {})
        best_comp_sharpe = 0
        best_comp_name = ""
        for comp_name in components:
            comp_result = next((r for r in completed_all if r.get("factor_name") == comp_name), None)
            if comp_result and comp_result.get("sharpe", 0) > best_comp_sharpe:
                best_comp_sharpe = comp_result.get("sharpe", 0)
                best_comp_name = comp_name

        combo_sharpe = combo.get("sharpe", 0) or 0
        if best_comp_sharpe > 0:
            improvement = combo_sharpe - best_comp_sharpe
            improvement_pct = improvement / best_comp_sharpe * 100 if best_comp_sharpe != 0 else 0
            improvement_str = f"{improvement:+.3f} ({improvement_pct:+.1f}%) vs {best_comp_name}"
        else:
            improvement_str = "N/A"

        lines.append(f"| {i+1} | {fname} | {type_display} | {sharpe} | {fitness} | {ann} | {turnover} | {improvement_str} |")

    lines.append("")

    # ---- 二、各组合因子详细对比 ----
    lines.append("## 二、各组合因子 vs 成分因子详细对比")
    lines.append("")

    for combo in combo_factors:
        fname = combo.get("factor_name", "?")
        combo_info = FACTOR_FASTEXPR_MAP.get(fname, {})
        components = component_map.get(fname, {})
        combo_type = combo_info.get("combo_type", "?")
        type_display = {"weighted": "加权组合", "equal_weight": "等权组合"}.get(combo_type, combo_type)

        lines.append(f"### {fname}（{type_display}）")
        lines.append("")
        lines.append(f"> {combo_info.get('description', '')}")
        lines.append("")

        lines.append("| 因子 | 权重 | Sharpe | Fitness | 年化收益 | 换手率 | 最大回撤 |")
        lines.append("|------|------|--------|---------|----------|--------|----------|")

        # 组合自身
        combo_sharpe = f"{combo.get('sharpe', 0):.3f}" if combo.get('sharpe') is not None else "N/A"
        combo_fitness = f"{combo.get('fitness', 0):.3f}" if combo.get('fitness') is not None else "N/A"
        combo_ann = f"{combo.get('annual_return', 0):.2%}" if combo.get('annual_return') is not None else "N/A"
        combo_to = f"{combo.get('turnover', 0):.2%}" if combo.get('turnover') is not None else "N/A"
        combo_mdd = f"{combo.get('max_drawdown', 0):.2%}" if combo.get('max_drawdown') is not None else "N/A"
        lines.append(f"| **{fname} (组合)** | **100%** | **{combo_sharpe}** | **{combo_fitness}** | **{combo_ann}** | **{combo_to}** | **{combo_mdd}** |")

        # 成分因子
        for comp_name, weight in sorted(components.items(), key=lambda x: -x[1]):
            comp_result = next((r for r in completed_all if r.get("factor_name") == comp_name), None)
            weight_pct = f"{weight*100:.1f}%"
            if comp_result:
                c_sharpe = f"{comp_result.get('sharpe', 0):.3f}" if comp_result.get('sharpe') is not None else "N/A"
                c_fitness = f"{comp_result.get('fitness', 0):.3f}" if comp_result.get('fitness') is not None else "N/A"
                c_ann = f"{comp_result.get('annual_return', 0):.2%}" if comp_result.get('annual_return') is not None else "N/A"
                c_to = f"{comp_result.get('turnover', 0):.2%}" if comp_result.get('turnover') is not None else "N/A"
                c_mdd = f"{comp_result.get('max_drawdown', 0):.2%}" if comp_result.get('max_drawdown') is not None else "N/A"
                lines.append(f"| {comp_name} | {weight_pct} | {c_sharpe} | {c_fitness} | {c_ann} | {c_to} | {c_mdd} |")
            else:
                lines.append(f"| {comp_name} | {weight_pct} | - | - | - | - | - | ⏳ 进行中 |")

        lines.append("")

        # 分析结论
        combo_s = combo.get("sharpe", 0) or 0
        if components and combo_s > 0:
            avg_comp_sharpe = 0
            comp_count = 0
            for comp_name in components:
                comp_result = next((r for r in completed_all if r.get("factor_name") == comp_name), None)
                if comp_result and comp_result.get("sharpe"):
                    avg_comp_sharpe += comp_result.get("sharpe", 0)
                    comp_count += 1

            if comp_count > 0:
                avg_comp_sharpe /= comp_count
                if combo_s > avg_comp_sharpe:
                    gain = combo_s - avg_comp_sharpe
                    gain_pct = gain / avg_comp_sharpe * 100 if avg_comp_sharpe != 0 else 0
                    lines.append(f"**结论**: 组合 Sharpe ({combo_s:.3f}) 优于成分因子平均 ({avg_comp_sharpe:.3f})，提升 +{gain:.3f} (+{gain_pct:.1f}%) ✅")
                else:
                    loss = avg_comp_sharpe - combo_s
                    loss_pct = loss / avg_comp_sharpe * 100 if avg_comp_sharpe != 0 else 0
                    lines.append(f"**结论**: 组合 Sharpe ({combo_s:.3f}) 低于成分因子平均 ({avg_comp_sharpe:.3f})，降低 -{loss:.3f} (-{loss_pct:.1f}%) ⚠️")
                lines.append("")

    # ---- 三、全因子总排名（含组合） ----
    lines.append("## 三、全因子总排名 Top 20（含组合因子）")
    lines.append("")
    lines.append("| 排名 | 因子名称 | 类别 | Sharpe | Fitness | 年化收益 | 换手率 |")
    lines.append("|------|----------|------|--------|---------|----------|--------|")

    for i, r in enumerate(completed_all[:20]):
        sharpe = f"{r.get('sharpe', 0):.3f}" if r.get('sharpe') is not None else "N/A"
        fitness = f"{r.get('fitness', 0):.3f}" if r.get('fitness') is not None else "N/A"
        ann = f"{r.get('annual_return', 0):.2%}" if r.get('annual_return') is not None else "N/A"
        turnover = f"{r.get('turnover', 0):.2%}" if r.get('turnover') is not None else "N/A"
        cat = r.get("category", "?")
        name = r.get("factor_name", "?")
        # 标记组合因子
        if cat == "组合因子":
            name = f"⭐ {name}"
        lines.append(f"| {i+1} | {name} | {cat} | {sharpe} | {fitness} | {ann} | {turnover} |")

    lines.append("")

    # ---- 四、按类别平均表现 ----
    lines.append("## 四、各类别平均表现对比")
    lines.append("")

    category_stats = defaultdict(list)
    for r in completed_all:
        cat = r.get("category", "未知")
        category_stats[cat].append(r)

    lines.append("| 类别 | 因子数 | 平均 Sharpe | 平均 Fitness | 最佳因子 | 最佳 Sharpe |")
    lines.append("|------|--------|------------|-------------|----------|-------------|")

    for cat, items in sorted(category_stats.items(),
                             key=lambda x: -sum(r.get("sharpe", 0) or 0 for r in x[1]) / len(x[1]) if x[1] else 0):
        avg_sharpe = sum(r.get("sharpe", 0) or 0 for r in items) / len(items) if items else 0
        avg_fitness = sum(r.get("fitness", 0) or 0 for r in items) / len(items) if items else 0
        best = max(items, key=lambda x: x.get("sharpe", 0) or 0)
        lines.append(
            f"| {cat} | {len(items)} | {avg_sharpe:.3f} | {avg_fitness:.3f} | "
            f"{best.get('factor_name')} | {best.get('sharpe', 0):.3f} |"
        )

    lines.append("")

    # ---- 五、失败/进行中的因子 ----
    failed = [r for r in all_results if r.get("status") == "FAILED"
              and FACTOR_FASTEXPR_MAP.get(r.get("factor_name", ""), {}).get("version") == "v3"]
    pending = [r for r in all_results if r.get("status") == "PENDING"
               and FACTOR_FASTEXPR_MAP.get(r.get("factor_name", ""), {}).get("version") == "v3"]

    if failed:
        lines.append("## 五、v3 新因子失败列表")
        lines.append("")
        for r in failed:
            err = (r.get("error", "") or "")[:100]
            lines.append(f"- **{r.get('factor_name', '?')}**: {err}")
        lines.append("")

    if pending:
        lines.append("## 六、v3 新因子进行中")
        lines.append("")
        for r in pending:
            lines.append(f"- **{r.get('factor_name', '?')}** ({r.get('category', '?')})")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append(f"*数据来源: WorldQuant BRAIN 平台 API*")

    report_content = "\n".join(lines)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    return output_path


# ============================================================
# 参数矩阵测试模式
# ============================================================

async def run_param_matrix(client: WQBApiClient, sdk: CodeActSDK,
                           output_dir: str) -> Tuple[str, List[dict]]:
    """
    运行参数矩阵测试：对 Top 因子分别跑 4 套参数方案

    Args:
        client: WQB API 客户端
        sdk: CodeAct SDK 实例
        output_dir: 输出目录

    Returns:
        (report_path, matrix_results)
    """
    print(f"\n{'='*60}")
    print(f"[矩阵模式] 对 {len(TOP_FACTORS_MATRIX)} 个 Top 因子进行 {len(PARAM_SCHEMES)} 套参数方案测试")
    print(f"{'='*60}")

    matrix_results = []  # 最终所有组合的结果

    # ---- 1. 构建所有测试组合 ----
    all_combos = []  # [(factor_name, scheme_key, settings, info)]

    # Baseline 组合
    for factor_name in TOP_FACTORS_MATRIX:
        if factor_name not in FACTOR_FASTEXPR_MAP:
            print(f"  [跳过] 因子 {factor_name} 不在映射表中")
            continue
        info = FACTOR_FASTEXPR_MAP[factor_name]
        all_combos.append((factor_name, BASELINE_LABEL, dict(DEFAULT_SIM_SETTINGS), info))

    # 四套参数方案组合
    for factor_name in TOP_FACTORS_MATRIX:
        if factor_name not in FACTOR_FASTEXPR_MAP:
            continue
        info = FACTOR_FASTEXPR_MAP[factor_name]
        for scheme_key, scheme in PARAM_SCHEMES.items():
            all_combos.append((factor_name, scheme_key, dict(scheme["settings"]), info))

    total = len(all_combos)
    print(f"[矩阵] 共 {total} 个组合（{len(TOP_FACTORS_MATRIX)} 因子 × {len(PARAM_SCHEMES)+1} 方案）")

    # ---- 2. 检查缓存，筛选需要提交的组合 ----
    to_submit = []  # 需要提交的组合
    cached_count = 0

    for factor_name, scheme_key, settings, info in all_combos:
        expression = info["fastexpr"]
        cached = client.get_cached_alpha(expression, settings)

        if cached and cached.get("status") == "COMPLETED":
            cached_count += 1
            scheme_name = PARAM_SCHEMES.get(scheme_key, {}).get("name", scheme_key)
            if scheme_key == BASELINE_LABEL:
                scheme_name = "基准配置"
            sharpe_val = cached.get("sharpe", 0) or 0
            print(f"  [缓存] {factor_name} × {scheme_name}: Sharpe={sharpe_val:.3f}")
            matrix_results.append({
                "factor_name": factor_name,
                "scheme_key": scheme_key,
                "scheme_name": scheme_name,
                "category": info.get("category", "未知"),
                "status": "COMPLETED",
                "sharpe": cached.get("sharpe"),
                "fitness": cached.get("fitness"),
                "annual_return": cached.get("annual_return"),
                "turnover": cached.get("turnover"),
                "max_drawdown": cached.get("max_drawdown"),
                "alpha_id": cached.get("alpha_id"),
            })
        elif cached and cached.get("status") == "PENDING":
            # PENDING 状态，加入待等待列表
            scheme_name = PARAM_SCHEMES.get(scheme_key, {}).get("name", scheme_key)
            if scheme_key == BASELINE_LABEL:
                scheme_name = "基准配置"
            progress_url = cached.get("progress_url")
            alpha_id = cached.get("alpha_id")
            
            if progress_url or alpha_id:
                print(f"  [进行中] {factor_name} × {scheme_name}: PENDING（恢复等待）")
                # 构造一个 WQBSimulation 对象用于等待
                sim = WQBSimulation(client, progress_url, expression, settings)
                sim.factor_name = factor_name
                sim.category = info.get("category", "未知")
                sim.description = info.get("description", "")
                sim.version = info.get("version", "v1")
                sim.scheme_key = scheme_key
                sim.scheme_name = scheme_name
                sim._submitted = True
                if alpha_id:
                    sim.alpha_id = alpha_id
                    # 已有 alpha_id 说明已完成但没存指标，标记为 COMPLETED 待获取
                    sim.status = "COMPLETED"
                else:
                    sim.status = "PENDING"
                to_submit.append((factor_name, expression, info, scheme_key, settings, sim))
            else:
                # 没有 progress_url 也没有 alpha_id，无法恢复，需要重新提交
                print(f"  [重提交] {factor_name} × {scheme_name}: PENDING 但无 progress_url，重新提交")
                to_submit.append((factor_name, expression, info, scheme_key, settings, None))
        else:
            # 需要新提交
            scheme_name = PARAM_SCHEMES.get(scheme_key, {}).get("name", scheme_key)
            if scheme_key == BASELINE_LABEL:
                scheme_name = "基准配置"
            to_submit.append((factor_name, expression, info, scheme_key, settings, None))

    print(f"\n[矩阵] 缓存命中 {cached_count} 个，需处理 {len(to_submit)} 个")

    # ---- 3. 提交新的模拟（串行提交，控制限流）----
    simulations = []
    new_submit_count = 0
    pending_wait_count = 0

    for i, (factor_name, expression, info, scheme_key, settings, existing_sim) in enumerate(to_submit):
        scheme_name = PARAM_SCHEMES.get(scheme_key, {}).get("name", scheme_key)
        if scheme_key == BASELINE_LABEL:
            scheme_name = "基准配置"

        if existing_sim is not None and existing_sim.status == "PENDING":
            # 已存在的 PENDING 任务，加入等待列表
            simulations.append(existing_sim)
            pending_wait_count += 1
            continue

        if existing_sim is not None and existing_sim.status == "COMPLETED":
            # 已有 alpha_id，直接获取指标
            try:
                metrics = existing_sim.get_metrics()
                is_summary = metrics.pop("is_summary", None)
                yearly = existing_sim.get_yearly()

                client.save_alpha_result(
                    expression=expression,
                    settings=settings,
                    factor_name=factor_name,
                    category=info.get("category", "未知"),
                    alpha_id=existing_sim.alpha_id,
                    status="COMPLETED",
                    metrics=metrics,
                    is_summary=is_summary,
                    yearly=yearly,
                )

                matrix_results.append({
                    "factor_name": factor_name,
                    "scheme_key": scheme_key,
                    "scheme_name": scheme_name,
                    "category": info.get("category", "未知"),
                    "status": "COMPLETED",
                    "sharpe": metrics.get("sharpe"),
                    "fitness": metrics.get("fitness"),
                    "annual_return": metrics.get("annual_return"),
                    "turnover": metrics.get("turnover"),
                    "max_drawdown": metrics.get("max_drawdown"),
                    "alpha_id": existing_sim.alpha_id,
                })
                print(f"  [补全] {factor_name} × {scheme_name}: Sharpe={metrics.get('sharpe', 'N/A')}")
            except Exception as e:
                print(f"  [错误] 获取指标失败 {factor_name} × {scheme_name}: {e}")
            continue

        # 新提交
        # 标记为 PENDING
        client.save_alpha_result(
            expression=expression,
            settings=settings,
            factor_name=factor_name,
            category=info.get("category", "未知"),
            status="PENDING",
        )

        try:
            sim = client.simulate(expression, settings)
            sim.factor_name = factor_name
            sim.category = info.get("category", "未知")
            sim.description = info.get("description", "")
            sim.version = info.get("version", "v1")
            sim.scheme_key = scheme_key
            sim.scheme_name = scheme_name
            sim._submitted = True
            simulations.append(sim)
            new_submit_count += 1
            # 提交成功后保存 progress_url
            client.save_alpha_result(
                expression=expression,
                settings=settings,
                factor_name=factor_name,
                category=info.get("category", "未知"),
                progress_url=sim.progress_url,
                status="PENDING",
            )
            print(f"  [{i+1}/{len(to_submit)}] ✓ 提交 {factor_name} × {scheme_name}")
        except Exception as e:
            error_str = str(e)
            print(f"  [{i+1}/{len(to_submit)}] ✗ 提交失败 {factor_name} × {scheme_name}: {error_str[:80]}")
            client.save_alpha_result(
                expression=expression,
                settings=settings,
                factor_name=factor_name,
                category=info.get("category", "未知"),
                status="FAILED",
                error=error_str,
            )
            matrix_results.append({
                "factor_name": factor_name,
                "scheme_key": scheme_key,
                "scheme_name": scheme_name,
                "category": info.get("category", "未知"),
                "status": "FAILED",
                "error": error_str,
            })

        # 提交间隔（保守限流）
        if i < len(to_submit) - 1:
            await asyncio.sleep(SUBMIT_INTERVAL)

    print(f"\n[提交] 新提交 {new_submit_count} 个，待等待 {pending_wait_count} 个")

    # ---- 4. 批量等待结果 ----
    if simulations:
        submitted_sims = [s for s in simulations if s.status == "PENDING" and getattr(s, '_submitted', False)]
        if submitted_sims:
            print(f"\n[等待] {len(submitted_sims)} 个模拟进行中...")

            # 估算最大等待时间（每个约 30-60 秒，但并行等待）
            max_wait = 600.0  # 最多等 10 分钟
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

                                scheme_key = getattr(sim, 'scheme_key', 'unknown')
                                scheme_name = getattr(sim, 'scheme_name', scheme_key)
                                matrix_results.append({
                                    "factor_name": sim.factor_name,
                                    "scheme_key": scheme_key,
                                    "scheme_name": scheme_name,
                                    "category": sim.category,
                                    "status": "COMPLETED",
                                    "sharpe": metrics.get("sharpe"),
                                    "fitness": metrics.get("fitness"),
                                    "annual_return": metrics.get("annual_return"),
                                    "turnover": metrics.get("turnover"),
                                    "max_drawdown": metrics.get("max_drawdown"),
                                    "alpha_id": sim.alpha_id,
                                })
                                print(f"  ✓ [{completed_count}] {sim.factor_name} × {scheme_name}: "
                                      f"Sharpe={metrics.get('sharpe', 'N/A')}")
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
                                scheme_key = getattr(sim, 'scheme_key', 'unknown')
                                scheme_name = getattr(sim, 'scheme_name', scheme_key)
                                matrix_results.append({
                                    "factor_name": sim.factor_name,
                                    "scheme_key": scheme_key,
                                    "scheme_name": scheme_name,
                                    "category": sim.category,
                                    "status": "FAILED",
                                    "error": f"结果获取失败: {e}",
                                })
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
                        scheme_key = getattr(sim, 'scheme_key', 'unknown')
                        scheme_name = getattr(sim, 'scheme_name', scheme_key)
                        matrix_results.append({
                            "factor_name": sim.factor_name,
                            "scheme_key": scheme_key,
                            "scheme_name": scheme_name,
                            "category": sim.category,
                            "status": "FAILED",
                            "error": str(e),
                        })

                submitted_sims = still_pending
                if submitted_sims:
                    await asyncio.sleep(5.0)

            # 处理超时仍在 pending 的模拟
            for sim in submitted_sims:
                scheme_key = getattr(sim, 'scheme_key', 'unknown')
                scheme_name = getattr(sim, 'scheme_name', scheme_key)
                print(f"  ⏳ {sim.factor_name} × {scheme_name} 超时，保持 PENDING")
                matrix_results.append({
                    "factor_name": sim.factor_name,
                    "scheme_key": scheme_key,
                    "scheme_name": scheme_name,
                    "category": sim.category,
                    "status": "PENDING",
                })

    # ---- 5. 生成矩阵对比报告 ----
    report_path = os.path.join(output_dir, "wqb_param_matrix_report.md")
    report_path = generate_param_matrix_report(matrix_results, report_path)
    print(f"\n[报告] 参数矩阵对比报告已生成: {report_path}")

    return report_path, matrix_results


# ============================================================
# 主逻辑
# ============================================================

async def main():
    # ---- 参数解析 ----
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    mode = sys.argv[2] if len(sys.argv) > 2 else "all"
    max_factors = int(sys.argv[3]) if len(sys.argv) > 3 else 50

    # 账号配置
    email = "q1z2q3@126.com"
    password = "W2025zq0118"

    # 使用脚本所在目录的相对路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.normpath(os.path.join(script_dir, "..", "output"))
    os.makedirs(output_dir, exist_ok=True)

    db_path = os.path.join(output_dir, "wqb_state.db")
    report_path = os.path.join(output_dir, "wqb_backtest_report.md")

    actual_mode = result_mode if result_mode != "auto" else "display_only"

    print(f"[参数] result_mode={actual_mode}, mode={mode}, max_factors={max_factors}")
    print(f"[路径] 数据库: {db_path}")
    print(f"[路径] 报告: {report_path}")
    print(f"[限流] 提交间隔: {SUBMIT_INTERVAL}s")

    sdk = CodeActSDK()

    try:
        # ---- 1. 选择要跑的因子 ----
        if mode == "all":
            # 所有映射表中的因子
            selected_factors = list(FACTOR_FASTEXPR_MAP.keys())
        elif mode == "new":
            # 只跑 v2 版本的新因子
            selected_factors = [
                name for name, info in FACTOR_FASTEXPR_MAP.items()
                if info.get("version") == "v2"
            ]
        elif mode == "v3":
            # 只跑 v3 版本的新因子（组合+情绪+新Alpha101）
            selected_factors = [
                name for name, info in FACTOR_FASTEXPR_MAP.items()
                if info.get("version") == "v3"
            ]
        elif mode == "combos":
            # 只跑组合因子
            selected_factors = [
                name for name, info in FACTOR_FASTEXPR_MAP.items()
                if info.get("category") == "组合因子"
            ]
        elif mode == "rescan":
            # 只重试失败和 pending 的因子（从数据库读取）
            selected_factors = []  # 后面单独处理
        elif mode == "scan_params":
            # 只跑参数扫描因子
            selected_factors = [
                name for name, info in FACTOR_FASTEXPR_MAP.items()
                if info.get("version") == "scan"
            ]
        else:
            selected_factors = list(FACTOR_FASTEXPR_MAP.keys())

        # 限制数量
        selected_factors = selected_factors[:max_factors]

        print(f"[信息] 模式 '{mode}' 选定 {len(selected_factors)} 个因子")

        # ---- 2. 登录 API ----
        print("[WQB] 正在登录...")
        client = WQBApiClient.login(email, password, db_path=db_path)

        # ---- 2.5 matrix 模式：参数矩阵测试 ----
        if mode == "matrix":
            report_path, matrix_results = await run_param_matrix(client, sdk, output_dir)
            abs_report_path = os.path.abspath(report_path)

            # 统计结果
            completed = [r for r in matrix_results if r.get("status") == "COMPLETED"]
            failed = [r for r in matrix_results if r.get("status") == "FAILED"]
            pending = [r for r in matrix_results if r.get("status") == "PENDING"]
            completed.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)

            summary_lines = [
                f"WorldQuant BRAIN 参数矩阵测试完成！",
                f"测试范围：{len(TOP_FACTORS_MATRIX)} 个 Top 因子 × {len(PARAM_SCHEMES)} 套方案 + Baseline",
                f"结果：成功 {len(completed)} / 失败 {len(failed)} / 进行中 {len(pending)}",
            ]

            if completed:
                top = completed[0]
                top_scheme = top.get("scheme_name", "?")
                summary_lines.append(
                    f"最优组合：{top.get('factor_name')} × {top_scheme} "
                    f"(Sharpe={top.get('sharpe', 0):.3f}, Fitness={top.get('fitness', 0):.3f})"
                )

                # Top 5 组合
                summary_lines.append("\nTop 5 组合排名（按 Sharpe）：")
                for i, r in enumerate(completed[:5]):
                    sharpe = f"{r.get('sharpe', 0):.3f}" if r.get('sharpe') is not None else "N/A"
                    fitness = f"{r.get('fitness', 0):.3f}" if r.get('fitness') is not None else "N/A"
                    scheme = r.get("scheme_name", "?")
                    summary_lines.append(
                        f"  {i+1}. {r.get('factor_name')} × {scheme}: Sharpe={sharpe}, Fitness={fitness}"
                    )

            summary_lines.append(f"\n📊 详细报告：[参数矩阵对比报告](computer://{abs_report_path})")
            summary_lines.append(f"💾 状态数据库：./codeact/output/wqb_state.db")

            summary_message = "\n".join(summary_lines)

            await sdk.submit_result(
                result_mode=actual_mode,
                status="success",
                message=summary_message,
                data={
                    "total_combos": len(matrix_results),
                    "completed": len(completed),
                    "failed": len(failed),
                    "pending": len(pending),
                    "report_path": report_path,
                    "top_combo_factor": completed[0].get("factor_name") if completed else None,
                    "top_combo_scheme": completed[0].get("scheme_name") if completed else None,
                    "top_sharpe": completed[0].get("sharpe") if completed else None,
                    "top_fitness": completed[0].get("fitness") if completed else None,
                    "mode": "matrix",
                },
            )
            return

        # ---- 3. rescan 模式：从数据库读取失败/pending的因子 ----
        if mode == "rescan":
            all_db = client.list_all_results()
            retry_names = []
            for r in all_db:
                if r.get("status") in ("FAILED", "PENDING"):
                    fname = r.get("factor_name", "")
                    if fname and fname in FACTOR_FASTEXPR_MAP:
                        retry_names.append(fname)
            # 去重并限制数量
            selected_factors = list(dict.fromkeys(retry_names))[:max_factors]
            print(f"[信息] 需重试 {len(selected_factors)} 个因子: {selected_factors}")

        # ---- 4. 检查缓存，过滤已完成的因子 ----
        sim_settings = dict(DEFAULT_SIM_SETTINGS)
        to_submit = []
        cached_results = []

        for factor_name in selected_factors:
            if factor_name not in FACTOR_FASTEXPR_MAP:
                continue
            info = FACTOR_FASTEXPR_MAP[factor_name]
            expression = info["fastexpr"]

            cached = client.get_cached_alpha(expression, sim_settings)
            if cached and cached.get("status") == "COMPLETED":
                print(f"  [缓存] {factor_name}: Sharpe={cached.get('sharpe', 'N/A')}")
                cached["description"] = info.get("description", "")
                cached["version"] = info.get("version", "v1")
                cached_results.append(cached)
            else:
                to_submit.append((factor_name, expression, info))

        print(f"[信息] 缓存命中 {len(cached_results)} 个，需提交 {len(to_submit)} 个")

        # ---- 5. 批量提交 + 批量等待（提高效率）----
        new_results = []
        if to_submit:
            print(f"\n[WQB] 批量提交 {len(to_submit)} 个因子 (间隔 {SUBMIT_INTERVAL}s)...")

            # 第一步：批量提交
            simulations = await batch_submit(client, to_submit, sim_settings)

            submitted_count = sum(1 for s in simulations if getattr(s, '_submitted', False))
            failed_submit = len(simulations) - submitted_count
            print(f"\n[提交] 成功 {submitted_count} 个, 失败 {failed_submit} 个")

            # 第二步：批量等待结果
            if submitted_count > 0:
                # 计算剩余可用时间（留 60 秒给报告生成和收尾）
                elapsed = 0  # 粗略估计，实际用 wall clock
                max_wait_time = 300.0  # 最多等待 5 分钟
                new_results = await batch_wait_and_collect(
                    client, simulations, sim_settings,
                    poll_interval=5.0, max_wait=max_wait_time
                )
            else:
                # 全部提交失败，收集失败结果
                for sim in simulations:
                    new_results.append({
                        "factor_name": sim.factor_name,
                        "category": sim.category,
                        "expression": sim.expression,
                        "description": getattr(sim, 'description', ''),
                        "status": "FAILED",
                        "version": getattr(sim, 'version', 'v1'),
                        "error": sim.error or "提交失败",
                    })

        # ---- 6. 从数据库读取所有历史结果（生成完整报告）----
        all_results = client.list_all_results()

        # 补充描述和版本信息
        for r in all_results:
            fname = r.get("factor_name", "")
            if fname in FACTOR_FASTEXPR_MAP:
                if not r.get("description"):
                    r["description"] = FACTOR_FASTEXPR_MAP[fname]["description"]
                if not r.get("version"):
                    r["version"] = FACTOR_FASTEXPR_MAP[fname].get("version", "v1")
            if "yearly_data" not in r and r.get("yearly_json"):
                try:
                    r["yearly_data"] = json.loads(r["yearly_json"])
                except Exception:
                    pass

        # ---- 7. 生成报告 ----
        report_path = generate_report(all_results, report_path)
        abs_report_path = os.path.abspath(report_path)

        # ---- 7.5 生成组合因子验证报告（如果有组合因子数据）----
        combo_report_path = os.path.join(output_dir, "wqb_combination_test_report.md")
        combo_completed = [r for r in all_results
                           if r.get("category") == "组合因子" and r.get("status") == "COMPLETED"]
        if combo_completed:
            combo_report_path = generate_combination_report(all_results, combo_report_path)
            abs_combo_report_path = os.path.abspath(combo_report_path)
            print(f"[报告] 组合因子验证报告已生成: {combo_report_path}")
        else:
            combo_report_path = None
            abs_combo_report_path = None

        # ---- 8. 输出摘要 ----
        completed = [r for r in all_results if r.get("status") == "COMPLETED"]
        failed = [r for r in all_results if r.get("status") == "FAILED"]
        pending = [r for r in all_results if r.get("status") == "PENDING"]
        completed.sort(key=lambda x: x.get("sharpe") or -999, reverse=True)

        # 本次新增的数量
        new_completed = len([r for r in new_results if r.get("status") == "COMPLETED"])
        new_failed = len([r for r in new_results if r.get("status") == "FAILED"])

        if completed:
            top = completed[0]
            summary_lines = [
                f"WorldQuant BRAIN 因子扩展回测完成！",
                f"本次运行：新增 {new_completed} 成功 / {new_failed} 失败 / {len(pending)} 进行中",
                f"累计：成功 {len(completed)} 个，失败 {len(failed)} 个",
                f"最佳因子：{top.get('factor_name')} (Sharpe={top.get('sharpe', 0):.3f}, Fitness={top.get('fitness', 0):.3f})",
            ]

            # Top 5 简表
            summary_lines.append("\nTop 5 因子排名：")
            for i, r in enumerate(completed[:5]):
                sharpe = f"{r.get('sharpe', 0):.3f}" if r.get('sharpe') is not None else "N/A"
                fitness = f"{r.get('fitness', 0):.3f}" if r.get('fitness') is not None else "N/A"
                turnover = f"{r.get('turnover', 0):.1%}" if r.get('turnover') is not None else "N/A"
                cat = r.get('category', '?')
                summary_lines.append(
                    f"  {i+1}. {r.get('factor_name')} [{cat}]: Sharpe={sharpe}, Fitness={fitness}, 换手={turnover}"
                )

            # 按类别统计简表
            category_stats = defaultdict(list)
            for r in completed:
                cat = r.get("category", "未知")
                category_stats[cat].append(r)
            summary_lines.append("\n各类别表现：")
            for cat, items in sorted(category_stats.items()):
                avg_sharpe = sum(x.get("sharpe", 0) or 0 for x in items) / len(items) if items else 0
                best = max(items, key=lambda x: x.get("sharpe") or -999)
                summary_lines.append(
                    f"  - {cat}: {len(items)}个, 平均Sharpe={avg_sharpe:.3f}, "
                    f"最佳={best.get('factor_name')}({best.get('sharpe', 0):.3f})"
                )
        else:
            summary_lines = [f"回测全部失败 ({len(failed)} 个因子)"]

        summary_lines.append(f"\n📊 详细报告：[回测报告](computer://{abs_report_path})")
        if abs_combo_report_path:
            summary_lines.append(f"📊 组合验证：[组合因子验证报告](computer://{abs_combo_report_path})")
        summary_lines.append(f"💾 状态数据库：./codeact/output/wqb_state.db")

        summary_message = "\n".join(summary_lines)

        submit_data = {
            "total_factors": len(all_results),
            "completed": len(completed),
            "failed": len(failed),
            "pending": len(pending),
            "new_completed": new_completed,
            "new_failed": new_failed,
            "report_path": report_path,
            "combo_report_path": combo_report_path,
            "top_factor": completed[0].get("factor_name") if completed else None,
            "top_sharpe": completed[0].get("sharpe") if completed else None,
            "mode": mode,
        }

        # 如果有组合因子，加上组合因子的信息
        if combo_completed:
            combo_completed_sorted = sorted(combo_completed,
                                            key=lambda x: x.get("sharpe") or -999, reverse=True)
            top_combo = combo_completed_sorted[0]
            submit_data["top_combo_factor"] = top_combo.get("factor_name")
            submit_data["top_combo_sharpe"] = top_combo.get("sharpe")
            submit_data["top_combo_fitness"] = top_combo.get("fitness")

        await sdk.submit_result(
            result_mode=actual_mode,
            status="success",
            message=summary_message,
            data=submit_data,
        )

    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {e}"
        print(f"[错误] {error_msg}")
        traceback.print_exc()

        await sdk.submit_result(
            result_mode="notify",
            status="error",
            message=f"WorldQuant BRAIN 回测脚本执行失败: {error_msg}",
            data={"error_type": type(e).__name__},
        )


if __name__ == "__main__":
    asyncio.run(main())
