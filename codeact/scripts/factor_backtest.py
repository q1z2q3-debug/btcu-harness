"""
因子回测框架 - factor_backtest.py
==================================

模块化架构：
  1. DataLoader      - 数据获取（模拟数据 + akshare真实数据接口）
  2. FactorEngine    - 因子计算与预处理（去极值、标准化）
  3. BacktestEngine  - 向量化回测引擎（分层回测、多空组合）
  4. PerformanceAnalyzer - 绩效评估（8大核心指标）

数据格式约定：
  宽表格式：DataFrame with index=date, columns=symbol, values=price/volume
  支持字段：open, high, low, close, volume, vwap, returns
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# 1. 数据获取模块
# ============================================================

class DataLoader:
    """
    数据加载器
    - 支持模拟数据生成（默认，确保框架可运行）
    - 支持 akshare 获取A股真实数据（可选，需安装akshare）
    - 支持 tushare 接口（预留）
    """

    def __init__(self, n_stocks: int = 50, n_days: int = 500, seed: int = 42):
        self.n_stocks = n_stocks
        self.n_days = n_days
        self.seed = seed

    def generate_mock_data(self) -> Dict[str, pd.DataFrame]:
        """
        生成模拟股票数据（几何布朗运动 + 个股异质波动）

        Returns:
            Dict with keys: open, high, low, close, volume, vwap, returns
            每个值为 DataFrame(index=date, columns=symbol)
        """
        np.random.seed(self.seed)

        # 生成日期
        dates = pd.bdate_range(end=pd.Timestamp.today(), periods=self.n_days)

        # 生成股票代码
        symbols = [f'STOCK_{i:03d}' for i in range(self.n_stocks)]

        # 初始价格
        init_prices = np.random.uniform(10, 100, self.n_stocks)

        # 个股漂移率和波动率
        mu = np.random.uniform(-0.0005, 0.0015, self.n_stocks)  # 日漂移
        sigma = np.random.uniform(0.01, 0.03, self.n_stocks)    # 日波动

        # 市场因子（增强相关性，更真实）
        market_ret = np.random.normal(0.0002, 0.01, self.n_days)
        market_beta = np.random.uniform(0.5, 1.5, self.n_stocks)

        # 生成收益率
        returns = np.zeros((self.n_days, self.n_stocks))
        for i in range(self.n_stocks):
            # 市场收益 + 个股特质收益
            returns[:, i] = market_ret * market_beta[i] + \
                           np.random.normal(mu[i], sigma[i], self.n_days)

        # 生成收盘价
        close = np.zeros((self.n_days, self.n_stocks))
        close[0] = init_prices
        for t in range(1, self.n_days):
            close[t] = close[t-1] * (1 + returns[t])

        close_df = pd.DataFrame(close, index=dates, columns=symbols)
        returns_df = pd.DataFrame(returns, index=dates, columns=symbols)

        # 生成开盘价（昨收 * 小跳空）
        gap = np.random.normal(0, 0.005, (self.n_days, self.n_stocks))
        open_ = np.zeros((self.n_days, self.n_stocks))
        open_[0] = close[0] * (1 + gap[0])
        for t in range(1, self.n_days):
            open_[t] = close[t-1] * (1 + gap[t])
        open_df = pd.DataFrame(open_, index=dates, columns=symbols)

        # 生成最高价和最低价
        intraday_range = np.random.uniform(0.005, 0.03, (self.n_days, self.n_stocks))
        high = np.maximum(open_, close) * (1 + intraday_range * np.random.random((self.n_days, self.n_stocks)))
        low = np.minimum(open_, close) * (1 - intraday_range * np.random.random((self.n_days, self.n_stocks)))
        high_df = pd.DataFrame(high, index=dates, columns=symbols)
        low_df = pd.DataFrame(low, index=dates, columns=symbols)

        # 生成成交量（对数正态分布，带趋势和自相关）
        base_vol = np.random.lognormal(15, 1, self.n_stocks)  # 基础成交量
        volume = np.zeros((self.n_days, self.n_stocks))
        vol_shock = np.random.normal(0, 0.1, (self.n_days, self.n_stocks))
        volume[0] = base_vol
        for t in range(1, self.n_days):
            volume[t] = volume[t-1] * 0.9 + base_vol * 0.1
            volume[t] *= np.exp(vol_shock[t])
        volume_df = pd.DataFrame(volume, index=dates, columns=symbols)

        # VWAP (成交量加权平均价，用(H+L+C)/3 近似)
        vwap = (high + low + close) / 3
        vwap_df = pd.DataFrame(vwap, index=dates, columns=symbols)

        return {
            'open': open_df,
            'high': high_df,
            'low': low_df,
            'close': close_df,
            'volume': volume_df,
            'vwap': vwap_df,
            'returns': returns_df,
        }

    def fetch_akshare_data(self, symbols: Optional[List[str]] = None,
                           start_date: Optional[str] = None,
                           end_date: Optional[str] = None) -> Dict[str, pd.DataFrame]:
        """
        使用 akshare 获取A股真实日行情数据

        Args:
            symbols: 股票代码列表，如 ['000001', '600000']
            start_date: 开始日期 'YYYYMMDD'
            end_date: 结束日期 'YYYYMMDD'

        Returns:
            同 generate_mock_data 格式
        """
        try:
            import akshare as ak
        except ImportError:
            raise ImportError("请先安装 akshare: pip install akshare")

        # 默认获取沪深300成分股
        if symbols is None:
            try:
                hs300 = ak.index_stock_cons_csindex(symbol="000300")
                symbols = hs300['成分券代码'].tolist()[:self.n_stocks]
            except Exception:
                symbols = ['000001', '000002', '600000', '600036', '600519']

        if end_date is None:
            end_date = pd.Timestamp.today().strftime('%Y%m%d')
        if start_date is None:
            start_date = (pd.Timestamp.today() - pd.Timedelta(days=self.n_days * 1.5)).strftime('%Y%m%d')

        all_data = {}
        for sym in symbols:
            try:
                df = ak.stock_zh_a_hist(symbol=sym, period="daily",
                                        start_date=start_date, end_date=end_date,
                                        adjust="qfq")
                df = df.rename(columns={
                    '日期': 'date', '开盘': 'open', '收盘': 'close',
                    '最高': 'high', '最低': 'low', '成交量': 'volume',
                    '成交额': 'amount', '涨跌幅': 'pct_chg'
                })
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date').sort_index()
                all_data[sym] = df
            except Exception as e:
                print(f"[警告] 获取 {sym} 数据失败: {e}")

        if not all_data:
            raise ValueError("未获取到任何股票数据，使用模拟数据代替")

        # 整理成宽表格式
        dates = sorted(set(d for df in all_data.values() for d in df.index))
        result = {}
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df_out = pd.DataFrame(index=pd.to_datetime(dates))
            for sym, df_sym in all_data.items():
                df_out[sym] = df_sym[col]
            result[col] = df_out

        # 计算 VWAP 和 收益率
        result['vwap'] = (result['high'] + result['low'] + result['close']) / 3
        result['returns'] = result['close'].pct_change()

        return result

    def load(self, use_real_data: bool = False, **kwargs) -> Dict[str, pd.DataFrame]:
        """统一加载接口"""
        if use_real_data:
            try:
                return self.fetch_akshare_data(**kwargs)
            except Exception as e:
                print(f"[警告] 真实数据获取失败({e})，回退到模拟数据")
        return self.generate_mock_data()


# ============================================================
# 2. 因子计算引擎
# ============================================================

class FactorEngine:
    """
    因子计算与预处理引擎
    - 从 alpha_library 获取因子函数
    - 因子预处理：去极值（MAD）、标准化（Z-score）
    - 支持中性化（可选）
    """

    def __init__(self, data: Dict[str, pd.DataFrame]):
        self.data = data
        self._factors = {}  # 缓存已计算的因子

    def compute(self, factor_name: str) -> pd.DataFrame:
        """计算单个因子（带缓存）"""
        if factor_name in self._factors:
            return self._factors[factor_name]

        from alpha_library import FACTOR_LIBRARY
        factor_func = FACTOR_LIBRARY.get(factor_name).func
        result = factor_func(self.data)
        self._factors[factor_name] = result
        return result

    def compute_batch(self, factor_names: List[str]) -> Dict[str, pd.DataFrame]:
        """批量计算因子"""
        return {name: self.compute(name) for name in factor_names}

    @staticmethod
    def winsorize(factor: pd.DataFrame, n_mad: float = 3.0) -> pd.DataFrame:
        """MAD去极值：超过n倍MAD的值截断"""
        result = factor.copy()
        for idx in factor.index:
            row = factor.loc[idx].dropna()
            if len(row) == 0:
                continue
            median = row.median()
            mad = (row - median).abs().median()
            if mad == 0:
                continue
            upper = median + n_mad * mad
            lower = median - n_mad * mad
            result.loc[idx] = row.clip(lower, upper).reindex(factor.columns)
        return result

    @staticmethod
    def standardize(factor: pd.DataFrame) -> pd.DataFrame:
        """横截面Z-score标准化"""
        result = factor.copy()
        mean = factor.mean(axis=1)
        std = factor.std(axis=1)
        std = std.replace(0, np.nan)
        result = factor.sub(mean, axis=0).div(std, axis=0)
        return result.fillna(0)

    def get_clean_factor(self, factor_name: str,
                         do_winsorize: bool = True,
                         do_standardize: bool = True) -> pd.DataFrame:
        """获取清洗后的因子值"""
        factor = self.compute(factor_name)
        if do_winsorize:
            factor = self.winsorize(factor)
        if do_standardize:
            factor = self.standardize(factor)
        return factor


# ============================================================
# 3. 回测引擎
# ============================================================

class BacktestEngine:
    """
    向量化因子回测引擎

    回测方法：
    - 分层回测：按因子值分为N组，等权持有，每日调仓
    - 多空组合：做多 Top quantile，做空 Bottom quantile
    - 多头组合：只做多 Top quantile

    输出：
    - 每日组合收益率
    - 每日持仓权重
    - 换手数据
    """

    def __init__(self, factor: pd.DataFrame, forward_returns: pd.DataFrame,
                 n_groups: int = 10, long_short: bool = True,
                 top_pct: float = 0.1, bottom_pct: float = 0.1):
        """
        Args:
            factor: 因子值 DataFrame(index=date, columns=symbol)
            forward_returns: 未来收益率（用于回测，默认shift(1)即T+1收益）
            n_groups: 分层层数
            long_short: 是否多空
            top_pct: 多头比例
            bottom_pct: 空头比例
        """
        self.factor = factor
        self.forward_returns = forward_returns
        self.n_groups = n_groups
        self.long_short = long_short
        self.top_pct = top_pct
        self.bottom_pct = bottom_pct

        # 对齐索引
        common_idx = factor.index.intersection(forward_returns.index)
        self.factor = factor.loc[common_idx]
        self.forward_returns = forward_returns.loc[common_idx]

    def _get_group_labels(self) -> pd.DataFrame:
        """获取每日分组标签（1=最低因子值组，n_groups=最高因子值组）"""
        groups = pd.DataFrame(index=self.factor.index, columns=self.factor.columns)
        for date in self.factor.index:
            row = self.factor.loc[date].dropna()
            if len(row) == 0:
                continue
            # 按因子值排序分组
            ranks = row.rank(pct=True)
            labels = (ranks * self.n_groups).apply(np.ceil).clip(1, self.n_groups)
            groups.loc[date, labels.index] = labels.values
        return groups.astype(float)

    def run_group_backtest(self) -> Dict:
        """
        分层回测

        Returns:
            Dict: {
                'group_returns': DataFrame(index=date, columns=group_id),
                'group_cum_returns': DataFrame,
                'group_weights': Dict of DataFrame,
            }
        """
        groups = self._get_group_labels()
        group_returns = pd.DataFrame(index=self.factor.index,
                                     columns=range(1, self.n_groups + 1),
                                     dtype=float)

        for g in range(1, self.n_groups + 1):
            # 该组的持仓权重（等权）
            mask = (groups == g).astype(float)
            # 每日持仓数
            n_hold = mask.sum(axis=1).replace(0, np.nan)
            # 等权权重
            weights = mask.div(n_hold, axis=0).fillna(0)
            # 组合收益 = 权重 × 未来收益
            ret = (weights * self.forward_returns).sum(axis=1)
            group_returns[g] = ret

        group_cum = (1 + group_returns).cumprod()

        return {
            'group_returns': group_returns,
            'group_cum_returns': group_cum,
        }

    def run_long_short_backtest(self) -> Dict:
        """
        多空组合回测（因子值排名前10%做多，后10%做空）

        Returns:
            Dict: {
                'ls_returns': Series (多空组合日收益),
                'ls_cum_returns': Series,
                'long_returns': Series,
                'short_returns': Series,
                'turnover': Series (日换手率),
                'long_weights': DataFrame,
                'short_weights': DataFrame,
            }
        """
        # 每日因子排名
        ranks = self.factor.rank(axis=1, pct=True)

        # 多头：因子值最高的 top_pct
        long_mask = (ranks >= (1 - self.top_pct)).astype(float)
        # 空头：因子值最低的 bottom_pct
        short_mask = (ranks <= self.bottom_pct).astype(float)

        # 等权权重
        n_long = long_mask.sum(axis=1).replace(0, np.nan)
        n_short = short_mask.sum(axis=1).replace(0, np.nan)
        long_weights = long_mask.div(n_long, axis=0).fillna(0)
        short_weights = short_mask.div(n_short, axis=0).fillna(0)

        # 组合收益
        long_ret = (long_weights * self.forward_returns).sum(axis=1)
        short_ret = (short_weights * self.forward_returns).sum(axis=1)

        if self.long_short:
            ls_ret = long_ret - short_ret  # 多空等权
        else:
            ls_ret = long_ret  # 只做多

        ls_cum = (1 + ls_ret).cumprod()

        # 计算换手率（多头 + 空头）
        turnover = self._calc_turnover(long_weights, short_weights)

        return {
            'ls_returns': ls_ret,
            'ls_cum_returns': ls_cum,
            'long_returns': long_ret,
            'short_returns': short_ret,
            'turnover': turnover,
            'long_weights': long_weights,
            'short_weights': short_weights,
        }

    def _calc_turnover(self, long_weights: pd.DataFrame,
                       short_weights: pd.DataFrame) -> pd.Series:
        """
        计算日换手率
        换手率 = sum(|w_t - w_{t-1}|) / 2
        多空组合总换手 = 多头换手 + 空头换手
        """
        # 多头换手
        long_diff = long_weights.diff().abs().sum(axis=1)
        # 空头换手
        short_diff = short_weights.diff().abs().sum(axis=1)

        turnover = (long_diff + short_diff) / 2  # 双边换手 / 2 = 单边
        turnover.iloc[0] = (long_weights.iloc[0].sum() + short_weights.iloc[0].sum()) / 2

        return turnover

    def run(self) -> Dict:
        """执行完整回测"""
        group_result = self.run_group_backtest()
        ls_result = self.run_long_short_backtest()
        return {
            'group': group_result,
            'long_short': ls_result,
        }


# ============================================================
# 4. 绩效评估模块
# ============================================================

class PerformanceAnalyzer:
    """
    绩效评估器 - 8大核心指标

    指标列表：
    1. 年化收益 (Annual Return)
    2. 夏普比率 (Sharpe Ratio)
    3. 信息比率 (Information Ratio, IR) - 基于IC
    4. IC (信息系数)
    5. Rank IC (秩信息系数)
    6. 换手率 (Turnover)
    7. 最大回撤 (Max Drawdown)
    8. Fitness评分
    """

    def __init__(self, backtest_result: Dict, factor: pd.DataFrame,
                 forward_returns: pd.DataFrame, risk_free_rate: float = 0.02):
        """
        Args:
            backtest_result: BacktestEngine.run() 返回值
            factor: 因子值 DataFrame
            forward_returns: 未来收益率
            risk_free_rate: 年化无风险利率
        """
        self.result = backtest_result
        self.factor = factor
        self.forward_returns = forward_returns
        self.risk_free_rate = risk_free_rate
        self.days_per_year = 252  # 年化系数

    # ---- 收益指标 ----

    def calc_annual_return(self, returns: pd.Series) -> float:
        """年化收益率（复利）"""
        total_return = (1 + returns).prod() - 1
        n_years = len(returns) / self.days_per_year
        if n_years <= 0 or total_return <= -1:
            return 0.0
        return (1 + total_return) ** (1 / n_years) - 1

    def calc_sharpe(self, returns: pd.Series) -> float:
        """夏普比率 = (年化收益 - 无风险利率) / 年化波动率"""
        mean_daily = returns.mean()
        std_daily = returns.std()
        if std_daily == 0 or np.isnan(std_daily):
            return 0.0
        annual_return = mean_daily * self.days_per_year
        annual_vol = std_daily * np.sqrt(self.days_per_year)
        return (annual_return - self.risk_free_rate) / annual_vol

    def calc_max_drawdown(self, returns: pd.Series) -> float:
        """最大回撤 = (峰值 - 谷值) / 峰值"""
        cum = (1 + returns).cumprod()
        running_max = cum.cummax()
        drawdown = (cum - running_max) / running_max
        return drawdown.min()  # 负值，越小表示回撤越大

    def calc_daily_turnover(self, turnover: pd.Series) -> float:
        """平均日换手率（小数形式，如0.25表示25%）"""
        return turnover.mean()

    def calc_annual_turnover(self, turnover: pd.Series) -> float:
        """年化换手率（小数形式）"""
        return turnover.mean() * self.days_per_year

    # ---- IC相关指标 ----

    def calc_ic_series(self, method: str = 'pearson') -> pd.Series:
        """
        计算每日IC序列

        Args:
            method: 'pearson' for IC, 'spearman' for Rank IC
        """
        ic_values = {}
        for date in self.factor.index:
            f = self.factor.loc[date]
            r = self.forward_returns.loc[date]
            # 对齐有效数据
            valid = f.dropna().index.intersection(r.dropna().index)
            if len(valid) < 5:
                continue
            if method == 'spearman':
                # Rank IC：对两者分别排名后计算相关系数
                f_ranked = f[valid].rank()
                r_ranked = r[valid].rank()
                ic_values[date] = f_ranked.corr(r_ranked)
            else:
                ic_values[date] = f[valid].corr(r[valid])
        return pd.Series(ic_values)

    def calc_ic_mean(self, method: str = 'pearson') -> float:
        """IC均值"""
        ic = self.calc_ic_series(method)
        return ic.mean() if len(ic) > 0 else 0.0

    def calc_ic_ir(self, method: str = 'pearson') -> float:
        """信息比率 IR = IC均值 / IC标准差"""
        ic = self.calc_ic_series(method)
        if len(ic) < 2:
            return 0.0
        std = ic.std()
        if std == 0 or np.isnan(std):
            return 0.0
        return ic.mean() / std

    def calc_icir_annual(self, method: str = 'pearson') -> float:
        """年化ICIR"""
        return self.calc_ic_ir(method) * np.sqrt(self.days_per_year)

    # ---- Fitness评分 ----

    def calc_fitness(self, sharpe: float, annual_return: float,
                     annual_turnover: float) -> float:
        """
        WorldQuant Fitness评分
        Fitness = Sharpe × sqrt(|Returns|) / max(Turnover, 0.125)

        Turnover下限0.125防止低换手策略评分虚高
        """
        turnover = max(annual_turnover, 0.125)
        ret_abs = abs(annual_return)
        if turnover == 0 or ret_abs == 0:
            return 0.0
        return sharpe * np.sqrt(ret_abs) / turnover

    # ---- 综合评估 ----

    def evaluate(self) -> Dict[str, Any]:
        """
        完整绩效评估

        Returns:
            Dict with all metrics
        """
        ls_returns = self.result['long_short']['ls_returns']
        turnover = self.result['long_short']['turnover']

        # 基础收益指标
        annual_return = self.calc_annual_return(ls_returns)
        sharpe = self.calc_sharpe(ls_returns)
        max_dd = self.calc_max_drawdown(ls_returns)
        daily_turnover = self.calc_daily_turnover(turnover)
        annual_turnover = self.calc_annual_turnover(turnover)

        # IC指标
        ic_mean = self.calc_ic_mean('pearson')
        rank_ic_mean = self.calc_ic_mean('spearman')
        ic_ir_annual = self.calc_icir_annual('pearson')
        rank_ic_ir_annual = self.calc_icir_annual('spearman')

        # Fitness评分（使用日换手率，与WorldQuant口径一致）
        fitness = self.calc_fitness(sharpe, annual_return, daily_turnover)

        # 分组收益（单调性检验）
        group_cum = self.result['group']['group_cum_returns']
        group_final = group_cum.iloc[-1] if len(group_cum) > 0 else pd.Series()
        # 计算多空对冲收益的分组单调性
        group_returns = self.result['group']['group_returns']
        group_annual = {}
        for g in group_returns.columns:
            group_annual[f'group_{g}'] = self.calc_annual_return(group_returns[g])

        return {
            # 核心指标
            'annual_return': annual_return,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'daily_turnover': daily_turnover,
            'annual_turnover': annual_turnover,
            'fitness': fitness,
            # IC指标
            'ic_mean': ic_mean,
            'ic_ir_annual': ic_ir_annual,
            'rank_ic_mean': rank_ic_mean,
            'rank_ic_ir_annual': rank_ic_ir_annual,
            # 分组收益
            'group_annual_returns': group_annual,
            # 每日数据（用于绘图和详细分析）
            'daily': {
                'ls_returns': ls_returns.to_dict(),
                'ls_cum_returns': self.result['long_short']['ls_cum_returns'].to_dict(),
                'long_returns': self.result['long_short']['long_returns'].to_dict(),
                'short_returns': self.result['long_short']['short_returns'].to_dict(),
                'turnover': turnover.to_dict(),
            },
            # 统计信息
            'stats': {
                'n_days': len(ls_returns),
                'n_stocks': self.factor.shape[1],
                'win_rate': (ls_returns > 0).mean(),
                'profit_loss_ratio': abs(ls_returns[ls_returns > 0].mean() /
                                        ls_returns[ls_returns < 0].mean()) if (ls_returns < 0).any() else 0,
            },
        }


# ============================================================
# 便捷函数
# ============================================================

def run_single_factor_backtest(factor_name: str,
                               data: Dict[str, pd.DataFrame],
                               forward_shift: int = 1,
                               **backtest_kwargs) -> Dict:
    """
    便捷函数：运行单因子完整回测

    Args:
        factor_name: 因子名称
        data: 行情数据
        forward_shift: 未来收益滞后期数（默认1，即T日因子预测T+1收益）
        **backtest_kwargs: BacktestEngine 参数

    Returns:
        完整的评估结果字典
    """
    # 计算因子
    engine = FactorEngine(data)
    factor = engine.get_clean_factor(factor_name)

    # 构造未来收益
    forward_returns = data['returns'].shift(-forward_shift)

    # 回测
    bt = BacktestEngine(factor, forward_returns, **backtest_kwargs)
    result = bt.run()

    # 评估
    analyzer = PerformanceAnalyzer(result, factor, forward_returns)
    metrics = analyzer.evaluate()

    # 添加因子信息
    from alpha_library import FACTOR_LIBRARY
    info = FACTOR_LIBRARY.factor_info(factor_name)

    return {
        'factor_name': factor_name,
        'factor_info': info,
        'metrics': metrics,
    }


if __name__ == '__main__':
    # 快速测试
    print("生成模拟数据...")
    loader = DataLoader(n_stocks=30, n_days=300)
    data = loader.generate_mock_data()
    print(f"数据维度: {data['close'].shape}")

    print("\n计算因子 alpha_003 ...")
    engine = FactorEngine(data)
    factor = engine.get_clean_factor('alpha_003')
    print(f"因子维度: {factor.shape}")

    print("\n运行回测...")
    forward_ret = data['returns'].shift(-1)
    bt = BacktestEngine(factor, forward_ret)
    result = bt.run()

    print("\n绩效评估...")
    analyzer = PerformanceAnalyzer(result, factor, forward_ret)
    metrics = analyzer.evaluate()

    print("\n===== 核心指标 =====")
    print(f"年化收益: {metrics['annual_return']:.2%}")
    print(f"夏普比率: {metrics['sharpe_ratio']:.3f}")
    print(f"最大回撤: {metrics['max_drawdown']:.2%}")
    print(f"日换手率: {metrics['daily_turnover']:.2%}")
    print(f"年化换手: {metrics['annual_turnover']:.2%}")
    print(f"IC均值:   {metrics['ic_mean']:.4f}")
    print(f"Rank IC:  {metrics['rank_ic_mean']:.4f}")
    print(f"年化ICIR: {metrics['ic_ir_annual']:.3f}")
    print(f"Fitness:  {metrics['fitness']:.3f}")
