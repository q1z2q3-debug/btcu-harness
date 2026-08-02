"""
Alpha因子库 - 对标 WorldQuant 101 Alphas 经典因子体系
====================================================

因子分类：
  1. 量价因子 (Price-Volume Factors)
  2. 动量反转因子 (Momentum & Reversal Factors)
  3. 波动率因子 (Volatility Factors)
  4. 基本面类因子 (Fundamental Factors)
  5. 情绪类因子 (Sentiment Factors)

每个因子包含：
  - name: 因子名称
  - category: 因子类别
  - description: 逻辑说明
  - formula: 公式表达式（参考 WorldQuant 语法）
  - function: 计算函数 (pandas DataFrame 输入，返回因子值 Series/DataFrame)

数据约定：
  输入 DataFrame 列：open, high, low, close, volume, vwap, returns
  索引：MultiIndex (date, symbol) 或 单级 date 索引（多股票按列组织）
  本库支持两种数据格式：
    1. 宽表格式：index=date, columns=symbols, values=价格/成交量
    2. 长表格式：MultiIndex (date, symbol), columns=各字段
"""

import numpy as np
import pandas as pd
from typing import Callable, Dict, List, Optional, Tuple


# ============================================================
# 工具函数
# ============================================================

def _ts_rank(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """时间序列排名：每个时点对过去window天的值排名（百分位0-1）"""
    return df.rolling(window=window, min_periods=max(1, window // 2)).rank(pct=True)


def _rank(df: pd.DataFrame) -> pd.DataFrame:
    """横截面排名：每个日期对所有股票排名（百分位0-1）"""
    if isinstance(df.index, pd.MultiIndex):
        return df.groupby(level='date').rank(pct=True)
    else:
        return df.rank(axis=1, pct=True)


def _ts_corr(x: pd.DataFrame, y: pd.DataFrame, window: int) -> pd.DataFrame:
    """滚动时间序列相关系数"""
    return x.rolling(window=window, min_periods=max(1, window // 2)).corr(y)


def _ts_cov(x: pd.DataFrame, y: pd.DataFrame, window: int) -> pd.DataFrame:
    """滚动时间序列协方差"""
    return x.rolling(window=window, min_periods=max(1, window // 2)).cov(y)


def _ts_std(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """滚动标准差"""
    return df.rolling(window=window, min_periods=max(1, window // 2)).std()


def _ts_mean(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """滚动均值"""
    return df.rolling(window=window, min_periods=max(1, window // 2)).mean()


def _ts_sum(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """滚动求和"""
    return df.rolling(window=window, min_periods=max(1, window // 2)).sum()


def _ts_min(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """滚动最小值"""
    return df.rolling(window=window, min_periods=max(1, window // 2)).min()


def _ts_max(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """滚动最大值"""
    return df.rolling(window=window, min_periods=max(1, window // 2)).max()


def _delay(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """滞后n期"""
    return df.shift(n)


def _delta(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """n期差分"""
    return df.diff(n)


def _sign(df: pd.DataFrame) -> pd.DataFrame:
    """符号函数"""
    return np.sign(df)


def _scale(df: pd.DataFrame) -> pd.DataFrame:
    """横截面标准化（除以绝对值之和，使总和为1）"""
    if isinstance(df.index, pd.MultiIndex):
        abs_sum = df.abs().groupby(level='date').transform('sum')
    else:
        abs_sum = df.abs().sum(axis=1).to_frame().reindex(df.index)
        abs_sum = abs_sum.reindex(columns=df.columns, method='ffill')
    result = df / abs_sum.replace(0, np.nan)
    return result.fillna(0)


def _signedpower(df: pd.DataFrame, power: float) -> pd.DataFrame:
    """带符号的幂运算"""
    return np.sign(df) * (np.abs(df) ** power)


def _decay_linear(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """线性衰减加权移动平均"""
    weights = np.arange(1, window + 1)  # 越新权重越大
    weights = weights / weights.sum()
    return df.rolling(window=window, min_periods=max(1, window // 2)).apply(
        lambda x: np.nansum(x * weights[-len(x):]) if np.sum(~np.isnan(x)) > 0 else np.nan,
        raw=True
    )


# ============================================================
# 因子注册器
# ============================================================

class AlphaFactor:
    """单因子定义"""
    def __init__(self, name: str, category: str, description: str,
                 formula: str, func: Callable):
        self.name = name
        self.category = category
        self.description = description
        self.formula = formula
        self.func = func

    def __call__(self, data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        return self.func(data)

    def __repr__(self):
        return f"AlphaFactor({self.name}, {self.category})"


class AlphaLibrary:
    """Alpha因子库 - 注册与管理"""

    def __init__(self):
        self._factors: Dict[str, AlphaFactor] = {}
        self._register_all()

    def register(self, name: str, category: str, description: str,
                 formula: str, func: Callable):
        """注册一个因子"""
        self._factors[name] = AlphaFactor(name, category, description, formula, func)

    def get(self, name: str) -> AlphaFactor:
        """获取指定因子"""
        if name not in self._factors:
            raise KeyError(f"因子 {name} 不存在，可用因子: {list(self._factors.keys())}")
        return self._factors[name]

    def list_factors(self, category: Optional[str] = None) -> List[str]:
        """列出所有因子名称，可按类别筛选"""
        if category:
            return [n for n, f in self._factors.items() if f.category == category]
        return list(self._factors.keys())

    @property
    def categories(self) -> List[str]:
        """所有因子类别"""
        return sorted(set(f.category for f in self._factors.values()))

    def factor_info(self, name: str) -> Dict:
        """获取因子详细信息"""
        f = self.get(name)
        return {
            'name': f.name,
            'category': f.category,
            'description': f.description,
            'formula': f.formula,
        }

    def all_info(self) -> List[Dict]:
        """获取所有因子信息"""
        return [self.factor_info(n) for n in self._factors]

    # ============================================================
    # 注册所有因子
    # ============================================================
    def _register_all(self):
        self._register_price_volume()
        self._register_momentum_reversal()
        self._register_volatility()
        self._register_fundamental()
        self._register_sentiment()

    # ----------------------------------------------------------
    # 1. 量价因子 (Price-Volume Factors)
    # ----------------------------------------------------------
    def _register_price_volume(self):
        """量价类因子：捕捉价格与成交量的关系"""

        # Alpha#3: 开盘价秩与成交量秩的10日滚动相关系数（负值）
        def alpha_003(data):
            open_r = _rank(data['open'])
            vol_r = _rank(data['volume'])
            return -1 * _ts_corr(open_r, vol_r, 10)
        self.register('alpha_003', '量价因子',
            '过去10天开盘价秩与成交量秩的滚动相关系数，取负值。量价背离时做多，量价同向时做空。',
            '-1 * ts_corr(rank(open), rank(volume), 10)',
            alpha_003)

        # Alpha#6: 开盘价与成交量的10日相关系数（负值）
        def alpha_006(data):
            return -1 * _ts_corr(data['open'], data['volume'], 10)
        self.register('alpha_006', '量价因子',
            '过去10天开盘价与成交量的相关系数，取负值。价量背离是反转信号。',
            '-1 * correlation(open, volume, 10)',
            alpha_006)

        # Alpha#12: 成交量变化方向 × 价格变化方向（反向）
        def alpha_012(data):
            vol_sign = _sign(_delta(data['volume'], 1))
            price_delta = _delta(data['close'], 1)
            return vol_sign * (-1 * price_delta)
        self.register('alpha_012', '量价因子',
            '成交量变化方向乘以价格变化的负值。放量上涨/缩量下跌预示反转；缩量上涨/放量下跌则顺势。',
            'sign(delta(volume, 1)) * (-1 * delta(close, 1))',
            alpha_012)

        # Alpha#13: 收盘价秩与成交量秩的5日协方差（负值 + 排名）
        def alpha_013(data):
            close_r = _rank(data['close'])
            vol_r = _rank(data['volume'])
            return -1 * _rank(_ts_cov(close_r, vol_r, 5))
        self.register('alpha_013', '量价因子',
            '收盘价秩与成交量秩的5日滚动协方差，取负后排名。量价负相关度越高越值得投资。',
            '-1 * rank(covariance(rank(close), rank(volume), 5))',
            alpha_013)

        # Alpha#15: 最高价秩与成交量秩的3日相关系数排名的3日求和（负值）
        def alpha_015(data):
            high_r = _rank(data['high'])
            vol_r = _rank(data['volume'])
            corr = _ts_corr(high_r, vol_r, 3)
            corr_r = _rank(corr)
            return -1 * _ts_sum(corr_r, 3)
        self.register('alpha_015', '量价因子',
            '滚动计算最高价秩与成交量秩的3日相关系数并排名，再对3天求和取负。捕捉量价背离的持续性。',
            '-1 * sum(rank(correlation(rank(high), rank(volume), 3)), 3)',
            alpha_015)

        # 量价齐升因子（自定义）
        def pv_momentum(data):
            """量价趋势共振因子"""
            price_mom = _delta(data['close'], 5) / _delay(data['close'], 5)
            vol_mom = _delta(data['volume'], 5) / _delay(data['volume'], 5).replace(0, np.nan)
            return _rank(price_mom) * _rank(vol_mom)
        self.register('pv_momentum', '量价因子',
            '5日价格动量与5日成交量动量的排名乘积。量价齐升的股票排名靠前。',
            'rank(close_ret_5d) * rank(volume_ret_5d)',
            pv_momentum)

    # ----------------------------------------------------------
    # 2. 动量反转因子 (Momentum & Reversal Factors)
    # ----------------------------------------------------------
    def _register_momentum_reversal(self):
        """动量与反转类因子"""

        # Alpha#1 (简化版): 条件波动率/价格信号
        def alpha_001(data):
            returns = data['returns']
            down_vol = _ts_std(returns.where(returns < 0, data['close']), 20)
            sig = _signedpower(down_vol, 2)
            argmax_pos = _ts_rank(sig, 5)
            return _rank(argmax_pos) - 0.5
        self.register('alpha_001', '动量反转因子',
            '条件波动率信号的横截面排名中心化。下跌时关注波动率（恐慌见底信号），上涨时关注价格水平。',
            'rank(ts_argmax(signedpower(returns<0 ? std(returns,20) : close, 2), 5)) - 0.5',
            alpha_001)

        # Alpha#9: 趋势/反转切换因子
        def alpha_009(data):
            delta_c = _delta(data['close'], 1)
            min_delta = _ts_min(delta_c, 5)
            max_delta = _ts_max(delta_c, 5)
            # 全涨或全跌（趋势市）用动量排名，否则用反转
            trend = (min_delta > 0) | (max_delta < 0)
            result = pd.DataFrame(0.0, index=data['close'].index, columns=data['close'].columns)
            result[trend] = _ts_rank(delta_c, 5)[trend]
            result[~trend] = (-1 * delta_c)[~trend]
            return result
        self.register('alpha_009', '动量反转因子',
            '趋势市（5日单调涨跌）用动量信号，震荡市用短期反转信号。自适应切换动量与反转。',
            'if ts_min(delta(close,1),5)>0 or ts_max(delta(close,1),5)<0: ts_rank(delta(close,1),5) else -delta(close,1)',
            alpha_009)

        # Alpha#10: 同Alpha#9但4天窗口 + 横截面排名
        def alpha_010(data):
            delta_c = _delta(data['close'], 1)
            min_delta = _ts_min(delta_c, 4)
            max_delta = _ts_max(delta_c, 4)
            trend = (min_delta > 0) | (max_delta < 0)
            result = pd.DataFrame(0.0, index=data['close'].index, columns=data['close'].columns)
            result[trend] = _ts_rank(delta_c, 4)[trend]
            result[~trend] = (-1 * delta_c)[~trend]
            return _rank(result)
        self.register('alpha_010', '动量反转因子',
            '4天窗口的趋势/反转切换因子，结果做横截面排名。更短窗口捕捉更短期的状态切换。',
            'rank(if ts_min(delta(close,1),4)>0 or ts_max(delta(close,1),4)<0: delta(close,1) else -delta(close,1))',
            alpha_010)

        # 20日动量因子
        def mom_20(data):
            close = data['close']
            return (close - _delay(close, 20)) / _delay(close, 20)
        self.register('mom_20', '动量反转因子',
            '过去20日收益率。中期动量效应：强者恒强。',
            '(close - delay(close, 20)) / delay(close, 20)',
            mom_20)

        # 5日反转因子
        def reversal_5(data):
            close = data['close']
            return -1 * (close - _delay(close, 5)) / _delay(close, 5)
        self.register('reversal_5', '动量反转因子',
            '过去5日收益率取反。短期反转效应：涨多了会跌，跌多了会涨。',
            '-1 * (close - delay(close, 5)) / delay(close, 5)',
            reversal_5)

        # Alpha#19: 7日动量 + 长期动量调制
        def alpha_019(data):
            close = data['close']
            returns = data['returns']
            # 7日价格变化的方向一致性
            delta7 = _delta(close, 7)
            # 长期动量（250日累计收益）排名调制
            long_mom_rank = _rank(1 + _ts_sum(returns, 250))
            return (-1 * _sign(delta7 + _delta(close, 7))) * (1 + long_mom_rank)
        self.register('alpha_019', '动量反转因子',
            '短期反转信号乘以长期动量调制。长期涨势中的短期回调是买入机会。',
            '(-1 * sign((close - delay(close,7)) + delta(close,7))) * (1 + rank(1 + sum(returns, 250)))',
            alpha_019)

    # ----------------------------------------------------------
    # 3. 波动率因子 (Volatility Factors)
    # ----------------------------------------------------------
    def _register_volatility(self):
        """波动率类因子"""

        # 20日历史波动率（取反，低波异象）
        def hist_vol_20(data):
            returns = data['returns']
            vol = _ts_std(returns, 20)
            return -1 * vol  # 低波动率异象：低波动股票长期表现更好
        self.register('hist_vol_20', '波动率因子',
            '20日历史波动率取负。低波动率异象：低波动股票长期跑赢高波动股票。',
            '-1 * std(returns, 20)',
            hist_vol_20)

        # 60日历史波动率（取反）
        def hist_vol_60(data):
            returns = data['returns']
            return -1 * _ts_std(returns, 60)
        self.register('hist_vol_60', '波动率因子',
            '60日历史波动率取负。长期低波异象更稳定。',
            '-1 * std(returns, 60)',
            hist_vol_60)

        # Alpha#11: 波动率 × 成交量变化
        def alpha_011(data):
            close = data['close']
            vwap = data['vwap'] if 'vwap' in data else (data['high'] + data['low'] + data['close']) / 3
            volume = data['volume']
            spread = vwap - close
            # 过去3天价差最大值排名 + 最小值排名
            high_spread_rank = _rank(_ts_max(spread, 3))
            low_spread_rank = _rank(_ts_min(spread, 3))
            # 3日成交量变化排名
            vol_delta_rank = _rank(_delta(volume, 3))
            return (high_spread_rank + low_spread_rank) * vol_delta_rank
        self.register('alpha_011', '波动率因子',
            '价格波动率（VWAP与收盘价差）排名乘以成交量变化排名。高波动+放量是上涨信号。',
            '(rank(ts_max(vwap-close, 3)) + rank(ts_min(vwap-close, 3))) * rank(delta(volume, 3))',
            alpha_011)

        # 波动率变化率因子
        def vol_change(data):
            returns = data['returns']
            vol_short = _ts_std(returns, 5)
            vol_long = _ts_std(returns, 20)
            return vol_short / vol_long.replace(0, np.nan) - 1
        self.register('vol_change', '波动率因子',
            '短期波动率相对长期波动率的变化率。波动率突然放大往往伴随新信息到来。',
            'std(returns, 5) / std(returns, 20) - 1',
            vol_change)

        # 高低波比因子
        def high_low_vol(data):
            high = data['high']
            low = data['low']
            close = data['close']
            # 真实波幅简化版
            tr = (high - low) / close
            return -1 * _ts_mean(tr, 10)
        self.register('high_low_vol', '波动率因子',
            '基于日内高低点的波动率取负。日内波动越大，短期越可能反转。',
            '-1 * mean((high - low) / close, 10)',
            high_low_vol)

    # ----------------------------------------------------------
    # 4. 基本面类因子 (Fundamental Factors)
    # ----------------------------------------------------------
    def _register_fundamental(self):
        """基本面类因子 - 基于模拟/简化财务数据，也可对接真实数据"""

        # 模拟PE因子（低PE价值因子）
        def value_pe(data):
            # 若有真实pe数据则使用，否则用价格代理（简化版）
            if 'pe' in data:
                return -1 * data['pe']  # 低PE得分高
            # 无数据时用价格倒数近似（简化，真实场景需用盈利数据）
            return -1 * data['close'] / _ts_mean(data['close'], 252)
        self.register('value_pe', '基本面因子',
            '市盈率（PE）取负。价值因子：低估值股票长期跑赢高估值股票。无财务数据时用相对价格近似。',
            '-1 * PE  (value factor: low PE outperforms high PE)',
            value_pe)

        # 模拟PB因子（低PB价值因子）
        def value_pb(data):
            if 'pb' in data:
                return -1 * data['pb']
            # 简化：用价格与250日均价的比值作为估值代理
            return -1 * (data['close'] / _ts_mean(data['close'], 252))
        self.register('value_pb', '基本面因子',
            '市净率（PB）取负。账面市值比效应：低PB股票长期收益更高。',
            '-1 * PB  (book-to-market effect)',
            value_pb)

        # 质量因子 - ROE（简化版：用价格趋势代理盈利能力）
        def quality_roe(data):
            if 'roe' in data:
                return data['roe']
            # 简化：用60日收益率作为盈利动量的代理
            close = data['close']
            return (close - _delay(close, 60)) / _delay(close, 60)
        self.register('quality_roe', '基本面因子',
            '净资产收益率（ROE）。质量因子：高盈利公司长期表现更优。无数据时用中期动量近似。',
            'ROE  (quality factor: profitable firms outperform)',
            quality_roe)

        # 规模因子（小市值异象）
        def size_factor(data):
            if 'market_cap' in data:
                return -1 * np.log(data['market_cap'])
            # 简化：用成交量对数作为市值代理（高度相关）
            return -1 * np.log(data['volume'].rolling(20).mean().replace(0, np.nan))
        self.register('size_factor', '基本面因子',
            '市值对数取负。规模因子：小市值股票长期存在流动性溢价。无数据时用平均成交量近似。',
            '-1 * log(market_cap)  (size factor: small cap premium)',
            size_factor)

        # 盈利动量因子
        def earnings_momentum(data):
            if 'earnings' in data:
                earn = data['earnings']
                return (earn - _delay(earn, 60)) / _delay(earn, 60).abs().replace(0, np.nan)
            # 简化：用价格动量替代（盈利往往伴随价格变动）
            close = data['close']
            return (close - _delay(close, 20)) / _delay(close, 20)
        self.register('earnings_momentum', '基本面因子',
            '盈利增长率。盈利动量因子：盈利加速增长的公司股价表现更好。',
            'delta(earnings, 60) / |delay(earnings, 60)|',
            earnings_momentum)

    # ----------------------------------------------------------
    # 5. 情绪类因子 (Sentiment Factors)
    # ----------------------------------------------------------
    def _register_sentiment(self):
        """情绪类因子 - 基于量价行为推断市场情绪"""

        # 成交量异动因子（情绪热度）
        def volume_surge(data):
            volume = data['volume']
            avg_vol = _ts_mean(volume, 20)
            return volume / avg_vol.replace(0, np.nan) - 1
        self.register('volume_surge', '情绪因子',
            '当日成交量相对20日均量的放大倍数。成交量异动代表市场情绪升温。',
            'volume / mean(volume, 20) - 1',
            volume_surge)

        # 换手率因子（情绪活跃度，取反）
        def turnover_factor(data):
            if 'turnover' in data:
                return -1 * data['turnover']  # 低换手率：低情绪，往往是价值股
            # 简化：用成交量/价格比作为换手率代理
            vol_price = data['volume'] / data['close'].replace(0, np.nan)
            return -1 * _ts_mean(vol_price, 20)
        self.register('turnover_factor', '情绪因子',
            '换手率取负。低换手率代表低关注度/低情绪，长期反而表现好（冷门股效应）。',
            '-1 * turnover  (low attention outperforms)',
            turnover_factor)

        # 上影线因子（抛压情绪）
        def upper_shadow(data):
            high = data['high']
            close = data['close']
            open_ = data['open']
            # 计算实体顶部（使用 where 避免只读问题）
            body_top = close.where(close >= open_, open_)
            shadow = (high - body_top) / body_top.replace(0, np.nan)
            return -1 * shadow  # 上影线越长，抛压越大，越不看好
        self.register('upper_shadow', '情绪因子',
            '上影线长度占比取负。上影线代表上方抛压重，是短期负面情绪信号。',
            '-1 * (high - max(close, open)) / max(close, open)',
            upper_shadow)

        # 下影线因子（支撑情绪）
        def lower_shadow(data):
            low = data['low']
            close = data['close']
            open_ = data['open']
            # 计算实体底部（使用 where 避免只读问题）
            body_bottom = close.where(close <= open_, open_)
            shadow = (body_bottom - low) / body_bottom.replace(0, np.nan)
            return shadow  # 下影线越长，支撑越强，越看好
        self.register('lower_shadow', '情绪因子',
            '下影线长度占比。下影线代表下方支撑强，是短期正面情绪信号。',
            '(min(close, open) - low) / min(close, open)',
            lower_shadow)

        # 涨跌停情绪因子（简化版：用收益率极值）
        def extreme_return_sentiment(data):
            returns = data['returns']
            # 当日绝对收益率排名（越高越情绪化），取反（低情绪=更好的长期收益）
            return -1 * _rank(np.abs(returns))
        self.register('extreme_sentiment', '情绪因子',
            '当日绝对收益率排名取负。极端收益代表高情绪/高关注度，长期反而收益差（博傻效应）。',
            '-1 * rank(|returns|)  (low sentiment = better long-term return)',
            extreme_return_sentiment)


# ============================================================
# 全局实例
# ============================================================

FACTOR_LIBRARY = AlphaLibrary()


def compute_factor(factor_name: str, data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """便捷函数：计算单个因子值"""
    factor = FACTOR_LIBRARY.get(factor_name)
    return factor(data)


def compute_all_factors(data: Dict[str, pd.DataFrame],
                        categories: Optional[List[str]] = None) -> Dict[str, pd.DataFrame]:
    """批量计算所有因子（或指定类别）"""
    results = {}
    for name in FACTOR_LIBRARY.list_factors():
        factor = FACTOR_LIBRARY.get(name)
        if categories and factor.category not in categories:
            continue
        try:
            results[name] = factor(data)
        except Exception as e:
            print(f"[警告] 因子 {name} 计算失败: {e}")
    return results


if __name__ == '__main__':
    # 快速测试：打印因子库信息
    lib = AlphaLibrary()
    print(f"因子总数: {len(lib.list_factors())}")
    print(f"因子类别: {lib.categories}")
    print()
    for cat in lib.categories:
        factors = lib.list_factors(cat)
        print(f"【{cat}】 ({len(factors)}个)")
        for name in factors:
            info = lib.factor_info(name)
            print(f"  - {name}: {info['description'][:50]}...")
        print()
