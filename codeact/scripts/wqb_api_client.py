"""
WorldQuant BRAIN API 客户端封装 - wqb_api_client.py
====================================================

功能：
  1. 认证与会话管理（基于 autobrain-sim 增强）
  2. Alpha 模拟提交与结果查询
  3. 运算符 / 数据字段元数据查询
  4. 频率限制与指数退避重试
  5. 因子表达式 FASTEXPR 语法适配转换
  6. SQLite 持久化（避免重复提交）

FASTEXPR 运算符对照表（平台真实支持的 66 个运算符）：
  时间序列: ts_sum, ts_mean, ts_std_dev, ts_rank, ts_corr, ts_covariance,
            ts_delta, ts_delay, ts_decay_linear, ts_arg_max, ts_arg_min,
            ts_zscore, ts_scale, ts_quantile, ts_regression, ts_product,
            ts_backfill, ts_av_diff, ts_step, kth_element, hump,
            last_diff_value, days_from_last_change, ts_count_nans
  横截面:   rank, scale, zscore, winsorize, normalize, quantile
  算术:     add, subtract, multiply, divide, power, signed_power, sqrt,
            log, abs, sign, reverse, inverse, min, max, densify
  逻辑:     and, or, not, equal, not_equal, greater, greater_equal,
            less, less_equal, if_else, is_nan
  分组:     group_scale, group_neutralize, group_zscore, group_backfill,
            group_mean, group_rank
  变换:     bucket, trade_when
  向量:     vec_sum, vec_avg

默认回测设置：
  region=USA, universe=TOP3000, delay=1, decay=15,
  neutralization=SUBINDUSTRY, truncation=0.08, testPeriod=P1Y6M
"""

import json
import time
import sqlite3
import hashlib
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from contextlib import contextmanager

import requests


# ============================================================
# 常量
# ============================================================

BASE_URL = "https://api.worldquantbrain.com"

DEFAULT_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 15,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "maxTrade": "ON",
    "pasteurization": "ON",
    "testPeriod": "P1Y6M",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
}

# 因子库函数名 -> FASTEXPR 运算符名 的映射
FASTEXPR_OPERATOR_MAP = {
    # 时间序列
    "ts_mean": "ts_mean",
    "ts_sum": "ts_sum",
    "ts_std": "ts_std_dev",       # 库中是 ts_std，平台是 ts_std_dev
    "ts_stddev": "ts_std_dev",    # 兼容写法
    "ts_std_dev": "ts_std_dev",
    "ts_rank": "ts_rank",
    "ts_corr": "ts_corr",
    "ts_cov": "ts_covariance",    # 库中是 ts_cov，平台是 ts_covariance
    "ts_covariance": "ts_covariance",
    "ts_delta": "ts_delta",
    "ts_delay": "ts_delay",
    "delay": "ts_delay",          # 库中直接用 delay
    "delta": "ts_delta",          # 库中直接用 delta
    "ts_decay_linear": "ts_decay_linear",
    "decay_linear": "ts_decay_linear",
    "ts_min": "kth_element",      # 平台用 kth_element 实现 ts_min（第一个元素）
    "ts_max": "kth_element",      # 平台用 kth_element 实现 ts_max（最后一个元素）
    "ts_argmax": "ts_arg_max",
    "ts_argmin": "ts_arg_min",
    "ts_zscore": "ts_zscore",
    "ts_scale": "ts_scale",
    "ts_product": "ts_product",
    "ts_backfill": "ts_backfill",

    # 横截面
    "rank": "rank",
    "scale": "scale",
    "zscore": "zscore",
    "winsorize": "winsorize",
    "normalize": "normalize",
    "quantile": "quantile",

    # 算术
    "abs": "abs",
    "sign": "sign",
    "signedpower": "signed_power",   # 库中是 signedpower，平台是 signed_power
    "signed_power": "signed_power",
    "sqrt": "sqrt",
    "log": "log",
    "power": "power",
    "inverse": "inverse",
    "reverse": "reverse",            # 取反 = -x
    "min": "min",
    "max": "max",
    "add": "add",
    "subtract": "subtract",
    "multiply": "multiply",
    "divide": "divide",

    # 逻辑
    "if_else": "if_else",
    "and": "and",
    "or": "or",
    "not": "not",
    "greater": "greater",
    "less": "less",
    "greater_equal": "greater_equal",
    "less_equal": "less_equal",
    "equal": "equal",
    "not_equal": "not_equal",
    "is_nan": "is_nan",

    # 分组
    "group_rank": "group_rank",
    "group_neutralize": "group_neutralize",
    "group_zscore": "group_zscore",
    "group_scale": "group_scale",
}

# 量价类数据字段（平台支持）
PRICE_VOLUME_FIELDS = [
    "open", "high", "low", "close", "volume", "vwap", "returns",
]


# ============================================================
# 频率限制重试装饰器
# ============================================================

def retry_with_backoff(max_retries: int = 5, base_delay: float = 2.0,
                       backoff_factor: float = 2.0, status_codes: tuple = (429, 500, 502, 503, 504)):
    """
    指数退避重试装饰器，用于处理 API 频率限制和服务器错误。
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except requests.HTTPError as e:
                    if e.response.status_code in status_codes:
                        last_exception = e
                        # 优先使用 Retry-After header
                        retry_after = e.response.headers.get("Retry-After")
                        if retry_after:
                            wait = float(retry_after)
                        else:
                            wait = delay * (backoff_factor ** attempt)
                        print(f"  [重试 {attempt+1}/{max_retries}] 状态码 {e.response.status_code}, "
                              f"等待 {wait:.1f}s 后重试...")
                        time.sleep(wait)
                    else:
                        raise
            raise last_exception
        return wrapper
    return decorator


# ============================================================
# WQB API 客户端
# ============================================================

class WQBApiClient:
    """
    WorldQuant BRAIN API 客户端
    
    增强功能：
    - 频率限制自动重试（指数退避）
    - 运算符/字段元数据查询
    - 表达式 FASTEXPR 语法适配
    - SQLite 持久化去重
    """

    def __init__(self, email: str, password: str,
                 db_path: str = "./codeact/output/wqb_state.db"):
        """
        Args:
            email: BRAIN 平台账号邮箱
            password: BRAIN 平台密码
            db_path: SQLite 状态库路径
        """
        self.email = email
        self._session = requests.Session()
        self._session.auth = (email, password)
        self._authenticated = False
        self._operators_cache = None
        self.db_path = db_path
        self._init_db()

    # ---- 认证 ----

    def authenticate(self) -> dict:
        """登录并获取会话"""
        response = self._session.post(f"{BASE_URL}/authentication")
        response.raise_for_status()
        self._authenticated = True
        user_info = response.json()
        print(f"[WQB] 登录成功: {user_info.get('user', {}).get('id', 'unknown')}")
        return user_info

    @classmethod
    def login(cls, email: str, password: str, **kwargs) -> "WQBApiClient":
        """一步登录"""
        client = cls(email, password, **kwargs)
        client.authenticate()
        return client

    # ---- 元数据查询 ----

    @retry_with_backoff(max_retries=3)
    def get_operators(self) -> List[dict]:
        """获取所有可用运算符"""
        if self._operators_cache is not None:
            return self._operators_cache
        response = self._session.get(f"{BASE_URL}/operators")
        response.raise_for_status()
        self._operators_cache = response.json()
        return self._operators_cache

    def list_operators_by_category(self) -> Dict[str, List[str]]:
        """按类别列出所有运算符名称"""
        ops = self.get_operators()
        categories = {}
        for op in ops:
            cat = op.get("category", "unknown")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(op["name"])
        return categories

    # ---- 模拟提交 ----

    @retry_with_backoff(max_retries=5, base_delay=3.0)
    def _submit_simulation(self, payload: dict) -> str:
        """提交模拟（内部方法，带重试）"""
        response = self._session.post(f"{BASE_URL}/simulations", json=payload)
        response.raise_for_status()
        return response.headers.get("Location")

    def simulate(self, expression: str, settings: dict = None) -> "WQBSimulation":
        """
        提交 Alpha 表达式进行模拟

        Args:
            expression: FASTEXPR 表达式
            settings: 回测设置（覆盖默认设置）

        Returns:
            WQBSimulation 对象，可轮询结果
        """
        sim_settings = dict(DEFAULT_SETTINGS)
        if settings:
            sim_settings.update(settings)

        payload = {
            "type": "REGULAR",
            "settings": sim_settings,
            "regular": expression,
        }

        progress_url = self._submit_simulation(payload)
        return WQBSimulation(self, progress_url, expression, sim_settings)

    def simulate_batch(self, expressions: List[str], settings: dict = None,
                       submit_interval: float = 15.0, poll_interval: float = 5.0) -> List["WQBSimulation"]:
        """
        批量提交模拟（串行提交，控制速率避免触发限流）

        Args:
            expressions: 表达式列表
            settings: 共用的回测设置
            submit_interval: 提交间隔（秒），默认 15s 避免 429
            poll_interval: 轮询间隔（秒）

        Returns:
            WQBSimulation 列表
        """
        simulations = []
        for i, expr in enumerate(expressions):
            print(f"[WQB] 提交第 {i+1}/{len(expressions)} 个因子...")
            try:
                sim = self.simulate(expr, settings)
                simulations.append(sim)
            except Exception as e:
                print(f"  [错误] 提交失败: {e}")
                sim = WQBSimulation(self, None, expr, settings or DEFAULT_SETTINGS)
                sim.status = "FAILED"
                sim.error = str(e)
                simulations.append(sim)
            # 提交间隔，避免触发限流（WQB 限制较严，默认 10s）
            if i < len(expressions) - 1:
                time.sleep(submit_interval)

        return simulations

    # ---- Alpha 查询 ----

    @retry_with_backoff(max_retries=3)
    def get_alpha(self, alpha_id: str) -> dict:
        """获取 Alpha 详情"""
        response = self._session.get(f"{BASE_URL}/alphas/{alpha_id}")
        response.raise_for_status()
        return response.json()

    @retry_with_backoff(max_retries=3)
    def get_pnl(self, alpha_id: str) -> dict:
        """获取 PnL 记录集"""
        url = f"{BASE_URL}/alphas/{alpha_id}/recordsets/pnl"
        while True:
            response = self._session.get(url)
            retry_after = float(response.headers.get("Retry-After", 0))
            if retry_after == 0:
                response.raise_for_status()
                return response.json()
            time.sleep(retry_after)

    def get_yearly(self, alpha_id: str) -> List[dict]:
        """获取按年分组的 PnL"""
        from collections import defaultdict
        import math

        pnl_data = self.get_pnl(alpha_id)
        records = pnl_data.get("records", [])

        grouped = defaultdict(list)
        for r in records:
            year = str(r[0])[:4]
            if year.isdigit():
                grouped[year].append(float(r[1]))

        result = []
        for year in sorted(grouped.keys()):
            daily_pnls = grouped[year]
            n = len(daily_pnls)
            total_pnl = sum(daily_pnls)

            if n > 1:
                mean = total_pnl / n
                variance = sum((x - mean) ** 2 for x in daily_pnls) / (n - 1)
                std = math.sqrt(variance) if variance > 0 else 0
                sharpe = round(mean / std * math.sqrt(252) / 100, 4) if std > 0 else None
            else:
                sharpe = None

            result.append({
                "year": int(year),
                "pnl": round(total_pnl, 2),
                "sharpe": sharpe,
                "days": n,
            })

        return result

    # ---- SQLite 持久化 ----

    def _init_db(self):
        """初始化数据库"""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alphas (
                expr_hash TEXT PRIMARY KEY,
                expression TEXT NOT NULL,
                factor_name TEXT,
                category TEXT,
                settings_json TEXT NOT NULL,
                alpha_id TEXT,
                progress_url TEXT,
                status TEXT DEFAULT 'PENDING',
                sharpe REAL,
                fitness REAL,
                ic REAL,
                rank_ic REAL,
                turnover REAL,
                annual_return REAL,
                max_drawdown REAL,
                is_summary TEXT,
                yearly_json TEXT,
                submitted_at TEXT,
                completed_at TEXT,
                error TEXT
            )
        """)
        # 兼容旧数据库：添加 progress_url 列（如果不存在）
        try:
            conn.execute("ALTER TABLE alphas ADD COLUMN progress_url TEXT")
        except sqlite3.OperationalError:
            pass  # 列已存在
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_alphas_status ON alphas(status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_alphas_factor ON alphas(factor_name)
        """)
        conn.commit()
        conn.close()

    @contextmanager
    def _db_conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _expr_hash(expression: str, settings: dict) -> str:
        """计算表达式+设置的哈希，用于去重"""
        key = json.dumps({"expr": expression, "settings": settings}, sort_keys=True)
        return hashlib.md5(key.encode()).hexdigest()

    def get_cached_alpha(self, expression: str, settings: dict) -> Optional[dict]:
        """从缓存中查找已提交的因子"""
        expr_hash = self._expr_hash(expression, settings)
        with self._db_conn() as conn:
            row = conn.execute(
                "SELECT * FROM alphas WHERE expr_hash = ?", (expr_hash,)
            ).fetchone()
            if row:
                columns = [desc[0] for desc in conn.execute("SELECT * FROM alphas LIMIT 0").description]
                return dict(zip(columns, row))
        return None

    def save_alpha_result(self, expression: str, settings: dict,
                          factor_name: str = None, category: str = None,
                          alpha_id: str = None, progress_url: str = None,
                          status: str = "COMPLETED",
                          metrics: dict = None, is_summary: dict = None,
                          yearly: List[dict] = None, error: str = None):
        """保存因子回测结果到数据库"""
        expr_hash = self._expr_hash(expression, settings)
        now = datetime.now().isoformat(timespec="seconds")

        metrics = metrics or {}
        with self._db_conn() as conn:
            # 检查是否已存在
            existing = conn.execute(
                "SELECT expr_hash FROM alphas WHERE expr_hash = ?", (expr_hash,)
            ).fetchone()

            if existing:
                # 更新
                conn.execute("""
                    UPDATE alphas SET
                        alpha_id = COALESCE(?, alpha_id),
                        progress_url = COALESCE(?, progress_url),
                        status = COALESCE(?, status),
                        sharpe = COALESCE(?, sharpe),
                        fitness = COALESCE(?, fitness),
                        ic = COALESCE(?, ic),
                        rank_ic = COALESCE(?, rank_ic),
                        turnover = COALESCE(?, turnover),
                        annual_return = COALESCE(?, annual_return),
                        max_drawdown = COALESCE(?, max_drawdown),
                        is_summary = COALESCE(?, is_summary),
                        yearly_json = COALESCE(?, yearly_json),
                        completed_at = ?,
                        error = COALESCE(?, error)
                    WHERE expr_hash = ?
                """, (
                    alpha_id, progress_url, status,
                    metrics.get("sharpe"), metrics.get("fitness"),
                    metrics.get("ic"), metrics.get("rank_ic"),
                    metrics.get("turnover"), metrics.get("annual_return"),
                    metrics.get("max_drawdown"),
                    json.dumps(is_summary) if is_summary else None,
                    json.dumps(yearly) if yearly else None,
                    now, error, expr_hash
                ))
            else:
                # 插入
                conn.execute("""
                    INSERT INTO alphas (
                        expr_hash, expression, factor_name, category, settings_json,
                        alpha_id, progress_url, status, sharpe, fitness, ic, rank_ic,
                        turnover, annual_return, max_drawdown,
                        is_summary, yearly_json, submitted_at, completed_at, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    expr_hash, expression, factor_name, category,
                    json.dumps(settings, sort_keys=True),
                    alpha_id, progress_url, status,
                    metrics.get("sharpe"), metrics.get("fitness"),
                    metrics.get("ic"), metrics.get("rank_ic"),
                    metrics.get("turnover"), metrics.get("annual_return"),
                    metrics.get("max_drawdown"),
                    json.dumps(is_summary) if is_summary else None,
                    json.dumps(yearly) if yearly else None,
                    now, now if status == "COMPLETED" else None, error
                ))

    def list_all_results(self, status: str = None) -> List[dict]:
        """列出所有已保存的因子结果"""
        with self._db_conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM alphas WHERE status = ? ORDER BY sharpe DESC",
                    (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM alphas ORDER BY sharpe DESC"
                ).fetchall()
            columns = [desc[0] for desc in conn.execute("SELECT * FROM alphas LIMIT 0").description]
            return [dict(zip(columns, row)) for row in rows]

    # ---- 表达式转换 ----

    @staticmethod
    def _find_matching_paren(s: str, start: int) -> int:
        """找到与 start 位置左括号匹配的右括号位置"""
        depth = 0
        for i in range(start, len(s)):
            if s[i] == '(':
                depth += 1
            elif s[i] == ')':
                depth -= 1
                if depth == 0:
                    return i
        return -1

    @staticmethod
    def _replace_func_names(expr: str) -> str:
        """替换独立的函数名（处理嵌套括号）"""
        import re

        func_map = {
            "ts_std": "ts_std_dev",
            "ts_stddev": "ts_std_dev",
            "ts_cov": "ts_covariance",
            "signedpower": "signed_power",
            "delta": "ts_delta",
            "delay": "ts_delay",
            "decay_linear": "ts_decay_linear",
            "ts_argmax": "ts_arg_max",
            "ts_argmin": "ts_arg_min",
            "ts_min": "kth_element",  # kth_element(x, 1, window) 类似 ts_min
            "ts_max": "kth_element",  # kth_element(x, window, window) 类似 ts_max
        }

        result = []
        i = 0
        while i < len(expr):
            # 尝试匹配函数名（前面不是字母数字下划线）
            match = re.match(r'(?<![a-zA-Z0-9_])([a-zA-Z_][a-zA-Z0-9_]*)\(', expr[i:])
            if match:
                name = match.group(1)
                if name in func_map:
                    new_name = func_map[name]
                    result.append(new_name + '(')
                    i += len(name) + 1  # 跳过函数名和左括号
                    # 递归处理函数参数
                    paren_end = WQBApiClient._find_matching_paren(expr, i - 1)
                    if paren_end > 0:
                        inner = expr[i:paren_end]
                        result.append(WQBApiClient._replace_func_names(inner))
                        result.append(')')
                        i = paren_end + 1
                    else:
                        # 没找到匹配的右括号，原样追加剩余部分
                        result.append(expr[i:])
                        i = len(expr)
                else:
                    # 函数名不需要替换，但需要递归处理参数
                    result.append(name + '(')
                    i += len(name) + 1
                    paren_end = WQBApiClient._find_matching_paren(expr, i - 1)
                    if paren_end > 0:
                        inner = expr[i:paren_end]
                        result.append(WQBApiClient._replace_func_names(inner))
                        result.append(')')
                        i = paren_end + 1
                    else:
                        result.append(expr[i:])
                        i = len(expr)
            else:
                result.append(expr[i])
                i += 1

        return ''.join(result)

    @staticmethod
    def _wrap_reverse(expr: str) -> str:
        """
        处理表达式开头的 -1 * 或 - 模式
        将整个表达式包裹在 reverse() 中如果它以 -1 * 或 - 开头
        """
        import re

        # 模式1: 以 -1 * 开头
        m = re.match(r'^(-1\s*\*)\s*(.+)$', expr.strip())
        if m:
            inner = m.group(2).strip()
            return f"reverse({inner})"

        # 模式2: 以负号开头且后面跟着函数调用
        m = re.match(r'^(-\s*)([a-zA-Z_][a-zA-Z0-9_]*\(.+)$', expr.strip())
        if m:
            inner = m.group(2).strip()
            return f"reverse({inner})"

        return expr

    @staticmethod
    def convert_to_fastexpr(formula: str) -> str:
        """
        将因子库中的公式表达式转换为 WQB 平台的 FASTEXPR 语法

        主要转换：
        - 函数名适配（ts_std -> ts_std_dev, ts_cov -> ts_covariance 等）
        - -1 * x -> reverse(x)
        - 特殊模式处理

        Args:
            formula: 原始表达式字符串

        Returns:
            FASTEXPR 格式的表达式字符串
        """
        expr = formula.strip()

        # 1. 替换函数名（递归处理嵌套）
        expr = WQBApiClient._replace_func_names(expr)

        # 2. 处理开头的负号 / -1 * 模式
        expr = WQBApiClient._wrap_reverse(expr)

        return expr


# ============================================================
# 模拟任务对象
# ============================================================

class WQBSimulation:
    """
    Alpha 模拟任务对象，用于轮询和获取结果
    """

    def __init__(self, client: WQBApiClient, progress_url: str,
                 expression: str, settings: dict):
        self.client = client
        self.progress_url = progress_url
        self.expression = expression
        self.settings = settings
        self.alpha_id: Optional[str] = None
        self.status: str = "PENDING"  # PENDING, COMPLETED, FAILED
        self.error: Optional[str] = None
        self._alpha_data: Optional[dict] = None

    def wait(self, verbose: bool = True, poll_interval: float = 5.0) -> bool:
        """
        等待模拟完成

        Returns:
            True 表示成功，False 表示失败
        """
        if not self.progress_url:
            self.status = "FAILED"
            self.error = self.error or "无进度URL（提交失败）"
            return False

        while True:
            try:
                response = self.client._session.get(self.progress_url)
                retry_after = float(response.headers.get("Retry-After", 0))

                if retry_after == 0:
                    response.raise_for_status()
                    result = response.json()
                    self.alpha_id = result.get("alpha")
                    self.status = "COMPLETED"
                    if verbose:
                        print(f"  ✓ 模拟完成 Alpha ID: {self.alpha_id}")
                    return True

                if verbose:
                    print(f"  ⏳ 模拟中... 等待 {retry_after:.0f}s")
                time.sleep(retry_after)

            except Exception as e:
                self.status = "FAILED"
                self.error = str(e)
                if verbose:
                    print(f"  ✗ 模拟失败: {e}")
                return False

    def get_alpha(self) -> dict:
        """获取完整 Alpha 详情"""
        if self.status != "COMPLETED" or not self.alpha_id:
            raise RuntimeError(f"模拟未完成或失败 (status={self.status})")
        if self._alpha_data is None:
            self._alpha_data = self.client.get_alpha(self.alpha_id)
        return self._alpha_data

    def get_metrics(self) -> dict:
        """
        获取核心指标

        Returns:
            dict with keys: sharpe, fitness, turnover, annual_return,
                           max_drawdown, pnl, etc.
        """
        alpha = self.get_alpha()
        is_data = alpha.get("is", {})  # in-sample
        train_data = alpha.get("train", {})
        test_data = alpha.get("test", {})

        return {
            # IS (In-Sample) 核心指标
            "sharpe": is_data.get("sharpe"),
            "fitness": is_data.get("fitness"),
            "turnover": is_data.get("turnover"),
            "annual_return": is_data.get("returns"),
            "max_drawdown": is_data.get("drawdown"),
            "pnl": is_data.get("pnl"),
            "margin": is_data.get("margin"),
            "long_count": is_data.get("longCount"),
            "short_count": is_data.get("shortCount"),
            # 分阶段指标
            "train_sharpe": train_data.get("sharpe"),
            "train_fitness": train_data.get("fitness"),
            "test_sharpe": test_data.get("sharpe"),
            "test_fitness": test_data.get("fitness"),
            # Alpha 元信息
            "grade": alpha.get("grade"),
            "stage": alpha.get("stage"),
            "is_summary": is_data,
        }

    def get_yearly(self) -> List[dict]:
        """获取按年分组的 PnL"""
        if not self.alpha_id:
            return []
        return self.client.get_yearly(self.alpha_id)


# ============================================================
# 便捷函数
# ============================================================

def test_login(email: str, password: str) -> Tuple[bool, str]:
    """
    测试登录是否成功

    Returns:
        (success: bool, message: str)
    """
    try:
        client = WQBApiClient(email, password)
        info = client.authenticate()
        user_id = info.get("user", {}).get("id", "unknown")
        return True, f"登录成功，用户ID: {user_id}"
    except requests.HTTPError as e:
        return False, f"HTTP 错误 {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return False, f"登录失败: {type(e).__name__}: {e}"


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":
    # 测试登录
    print("测试 WorldQuant BRAIN 登录...")
    success, msg = test_login("q1z2q3@126.com", "W2025zq0118")
    print(f"结果: {msg}")

    if success:
        client = WQBApiClient.login("q1z2q3@126.com", "W2025zq0118")

        # 测试运算符查询
        print("\n=== 运算符类别 ===")
        cats = client.list_operators_by_category()
        for cat, ops in sorted(cats.items()):
            print(f"  [{cat}]: {len(ops)} 个")

        # 测试表达式转换
        print("\n=== 表达式转换测试 ===")
        test_exprs = [
            "ts_corr(rank(open), rank(volume), 10)",
            "ts_std(returns, 20)",
            "delta(close, 5)",
            "signedpower(x, 2)",
            "-1 * rank(ts_cov(rank(close), rank(volume), 5))",
        ]
        for expr in test_exprs:
            converted = WQBApiClient.convert_to_fastexpr(expr)
            print(f"  原: {expr}")
            print(f"  转: {converted}")
            print()
