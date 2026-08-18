"""
量化因子数据加载器 —— 从共享数据库加载WQB因子并转化为FactorInstance
"""

from __future__ import annotations
import json
import re
import os
from typing import List, Dict

from .adapter import FactorInstance, FACTOR_DIMENSIONS


class WQBDataLoader:
    """从WQB数据文件加载因子实例"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def load_all_factors(self) -> List[FactorInstance]:
        factors = []
        factors.extend(self._load_active())
        factors.extend(self._load_batch("tri_sc_batch2_results.json"))
        factors.extend(self._load_batch("tri_sc_batch3_results.json"))
        factors.extend(self._load_seeds("low_sc_seed_details.json"))
        factors.extend(self._load_seeds("low_sc_seed_batch2.json"))
        
        seen = set()
        unique = []
        for f in factors:
            if f.alpha_id not in seen and f.alpha_id and f.alpha_id != "unknown":
                seen.add(f.alpha_id)
                unique.append(f)
        return unique

    def _load_active(self) -> List[FactorInstance]:
        path = os.path.join(self.db_path, "alpha_database", "active_alphas_20260814.json")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            data = json.load(f)
        
        factors = []
        for item in data:
            regular = item.get("regular", "")
            if isinstance(regular, dict):
                expr = regular.get("code", "")
            else:
                expr = str(regular or item.get("expression", ""))
            is_data = item.get("is", {}) or {}
            dims = self._infer_dimensions(expr)
            
            factors.append(FactorInstance(
                alpha_id=item.get("id", ""),
                name=item.get("name", ""),
                expression=expr,
                fitness=float(is_data.get("fitness") or 0),
                sharpe=float(is_data.get("sharpe") or 0),
                drawdown=float(is_data.get("drawdown") or 0),
                self_correlation=float(is_data.get("selfCorrelation") or 0),
                grade=item.get("grade", "UNKNOWN"),
                stage=item.get("stage", "IS"),
                data_sources=self._detect_sources(expr),
                dim_values=dims,
            ))
        return factors

    def _load_batch(self, filename: str) -> List[FactorInstance]:
        path = os.path.join(self.db_path, filename)
        if not os.path.exists(path):
            return []
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        
        factors = []
        for item in data:
            if item.get("status") not in ("COMPLETE", "SUBMITTED"):
                continue
            aid = item.get("alpha_id") or item.get("id")
            if not aid:
                continue
            expr = item.get("expr", "")
            dims = self._infer_dimensions(expr)
            
            factors.append(FactorInstance(
                alpha_id=aid,
                name=item.get("name", aid),
                expression=expr,
                fitness=float(item.get("fitness") or 0),
                sharpe=float(item.get("sharpe") or 0),
                drawdown=float(item.get("drawdown") or 0),
                self_correlation=float(item.get("self_correlation", item.get("sc", 0)) or 0),
                grade=item.get("grade", "UNKNOWN"),
                stage=item.get("stage", "IS"),
                data_sources=self._detect_sources(expr),
                dim_values=dims,
            ))
        return factors

    def _load_seeds(self, filename: str) -> List[FactorInstance]:
        path = os.path.join(self.db_path, "alpha_database", filename)
        if not os.path.exists(path):
            return []
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        
        factors = []
        for item in data:
            if not isinstance(item, dict):
                continue
            aid = item.get("id")
            if not aid:
                continue
            expr = str(item.get("expr") or item.get("expression") or item.get("regular", ""))
            if isinstance(expr, dict):
                expr = expr.get("code", "")
            dims = self._infer_dimensions(expr)
            
            factors.append(FactorInstance(
                alpha_id=aid,
                name=item.get("name") or item.get("note", aid),
                expression=str(expr),
                fitness=float(item.get("fitness") or 0),
                sharpe=float(item.get("sharpe") or 0),
                drawdown=float(item.get("drawdown") or 0),
                self_correlation=float(item.get("sc", item.get("self_correlation", 0)) or 0),
                grade=item.get("grade", "UNKNOWN"),
                stage=item.get("stage", "IS"),
                data_sources=self._detect_sources(expr),
                dim_values=dims,
            ))
        return factors

    def _infer_dimensions(self, expression: str) -> Dict[str, float]:
        """
        从因子表达式推断九维特征向量 (-1 ~ 1)
        
        核心判断逻辑：
        - 价格类：returns + 方向前缀判断动量/反转
        - 基本面：估值比率(阴) vs 成长(阳)
        - 质量：ROE/ROA等(阳) vs 债务(阴)
        - 波动率：-vol(阳=低波) vs +vol(阴=高波)
        - 等等
        """
        expr = str(expression).lower()
        dims = {d: 0.0 for d in FACTOR_DIMENSIONS}
        
        # ========== 1. 价格动量 ==========
        # 核心：看returns前面的符号和函数
        # 动量：ts_momentum, ts_delta(close), returns被正向使用
        # 反转：-returns, ts_reverse, rank(-returns)
        price_signal = 0
        if "ts_momentum" in expr:
            price_signal += 0.8
        if "ts_reverse" in expr or "reversal" in expr or "mean_reversion" in expr:
            price_signal -= 0.8
        
        # 检测returns的使用方向
        returns_patterns = [
            (r"-returns", -0.5),      # -returns = 反转
            (r"rank\(-returns", -0.6),
            (r"rank\(returns", 0.4),
            (r"ts_rank\(returns", 0.4),
            (r"ts_zscore\(returns", 0.3),
            (r"ts_delta\(", 0.5),
            (r"ts_return", 0.6),
        ]
        for pat, score in returns_patterns:
            if re.search(pat, expr):
                price_signal += score
        
        # 纯粹的open/close/high/low是价格信号但非动量
        has_price_vars = any(k in expr for k in ["close", "open", "high", "low"])
        has_volume = "volume" in expr
        
        # 量价协方差=量价齐升=动量
        if "ts_covariance(close, volume" in expr or "ts_correlation(close, volume" in expr:
            price_signal += 0.4
        
        # 价格振幅类 (high-low)/close 等——非动量，归为波动率
        # 只有returns/delta/momentum才是动量维度
        
        if price_signal > 1.0:
            price_signal = 1.0
        elif price_signal < -1.0:
            price_signal = -1.0
        
        # 有returns但信号弱的给基础值
        if "returns" in expr and abs(price_signal) < 0.2:
            price_signal = 0.2
        
        dims["price_momentum"] = price_signal
        
        # ========== 2. 基本面价值 ==========
        # 价值(阴)=低估值比率如book/price, earnings/price
        # 成长(阳)=增长指标
        value_signal = 0
        
        # 估值比率 = 价值因子 = 阴
        if any(k in expr for k in [
            "book_to_price", "earnings_yield", "earnings_per_share/close",
            "div_mean/close", "ebit / cap", "ebit / market",
            "operating_income / cap", "sales / price",
        ]):
            value_signal -= 0.6
        
        # 显式的pe/pb
        if "pe_" in expr or "pb_" in expr or "bp_" in expr or "ep_" in expr:
            value_signal -= 0.5
        
        # 增长类 = 成长 = 阳
        if any(k in expr for k in ["sales_growth", "revenue_growth", "earnings_growth", "ts_delta.*earn"]):
            value_signal += 0.7
        
        # 有基本面但方向不明——给弱阳（因为通常是做多优质）
        has_fundamental = any(k in expr for k in [
            "operating_income", "revenue", "sales", "earnings", "net_income",
            "ebit", "ebitda", "equity", "book_value", "assets", "cap",
            "earnings_per_share", "div_mean",
        ])
        if has_fundamental and value_signal == 0:
            value_signal = 0.3  # 中性偏阳
        
        dims["fundamental_value"] = max(-1.0, min(1.0, value_signal))
        
        # ========== 3. 质量因子 ==========
        quality_signal = 0
        if any(k in expr for k in ["roe", "roa", "roic", "return_equity", "gross_margin", "profit_margin"]):
            quality_signal += 0.8
        if any(k in expr for k in ["debt", "leverage", "default", "debt_st"]):
            # 债务比率通常做多低债务公司=高质量
            if "rank(-" in expr or "-ts_zscore(debt" in expr or "debt / " in expr:
                quality_signal -= 0.5  # 债务比=质量因子(负号表示做多低债务=阳)
            else:
                quality_signal -= 0.3
        
        dims["quality_score"] = max(-1.0, min(1.0, quality_signal))
        
        # ========== 4. 波动率 ==========
        vol_signal = 0
        # 波动率因子通常做空高波=低波异象=阳
        if any(k in expr for k in ["volatility", "stddev", "ts_std", "std_dev", "realized_vol"]):
            if "-ts_std" in expr or "-ts_zscore(ts_std" in expr or "rank(-" in expr and "std" in expr:
                vol_signal += 0.7  # -vol = 做多低波 = 阳
            else:
                vol_signal -= 0.5  # 直接用vol，方向不明确，先标阴
        
        # (high-low)/close 这种振幅类也算波动率维度
        if "(high-low)" in expr or "(close-low)" in expr or "(high-close)" in expr:
            if vol_signal == 0:
                vol_signal -= 0.3  # 振幅通常作为反向指标(低振幅=好)
        
        if "low_vol" in expr or "low_beta" in expr:
            vol_signal = 0.8
        
        dims["volatility_regime"] = max(-1.0, min(1.0, vol_signal))
        
        # ========== 5. 流动性 ==========
        liq_signal = 0
        if "volume" in expr or "turnover" in expr or "dollar_volume" in expr:
            liq_signal = 0.5
        dims["liquidity_flow"] = liq_signal
        
        # ========== 6. 规模 ==========
        size_signal = 0
        if any(k in expr for k in ["cap", "market_cap", "size", "enterprise_value"]):
            # cap做分母通常是小盘效应=阴
            if "/ cap" in expr or "/market_cap" in expr:
                size_signal -= 0.4  # 隐含小盘偏好
            else:
                size_signal = 0.3
        dims["size_exposure"] = size_signal
        
        # ========== 7. 情绪 ==========
        sent_signal = 0
        if any(k in expr for k in ["sentiment", "tone", "news", "social", "media"]):
            sent_signal = 0.5
        dims["sentiment_score"] = sent_signal
        
        # ========== 8. 分析师 ==========
        analyst_signal = 0
        if any(k in expr for k in [
            "anl4_", "analyst", "eps_estimate", "consensus",
            "recommendation", "epsr", "afv4",
        ]):
            analyst_signal = 0.6
        dims["analyst_momentum"] = analyst_signal
        
        # ========== 9. 期权 ==========
        opt_signal = 0
        if any(k in expr for k in [
            "implied_volatility", "option_", "put_call", "breakeven",
            "option_volume", "iv_skew", "iv_mean",
        ]):
            opt_signal = 0.7
        dims["options_signal"] = opt_signal
        
        return dims

    def _detect_sources(self, expression: str) -> List[str]:
        """检测因子使用的数据源类别"""
        expr = str(expression).lower()
        sources = []
        
        if any(k in expr for k in ["close", "open", "high", "low", "volume", "returns"]):
            sources.append("price_volume")
        if any(k in expr for k in [
            "operating_income", "revenue", "earnings", "book_value", "assets",
            "cap", "equity", "ebitda", "ebit", "debt", "div_mean",
            "earnings_per_share", "sales", "net_income",
        ]):
            sources.append("fundamental")
        if any(k in expr for k in ["anl4_", "analyst", "eps_estimate", "consensus", "epsr", "afv4"]):
            sources.append("analyst")
        if any(k in expr for k in ["implied_volatility", "option_", "put_call", "breakeven"]):
            sources.append("options")
        if any(k in expr for k in ["news", "sentiment", "social", "tone"]):
            sources.append("news_sentiment")
        
        if not sources:
            sources.append("other")
        return sources
