#!/usr/bin/env python3
"""
alpha_021_d5 自相关深度诊断与突破脚本 - wqb_d5_selfcorr_breakthrough.py
=========================================================================

功能：
  1. 诊断 alpha_021_d5 (O0xZv69J) 提交检查失败原因，获取完整8项检查结果
  2. 获取 d1/d3/d5 自相关性详细数据，对比分析反常现象
  3. 设计 d5 附近精细调整因子（不同decay、衰减方式、波动率加权组合）
  4. 批量回测新因子，对 Sharpe≥1.25 且 Fitness≥1.0 的执行提交检查
  5. 生成完整诊断与突破报告

用法：
  python wqb_d5_selfcorr_breakthrough.py [result_mode] [email] [password] [db_path] [report_path]

参数：
  result_mode: display_only / notify / auto (默认: display_only)
  email:       BRAIN 账号邮箱 (默认: 从环境变量 BRAIN_CREDENTIAL_EMAIL 读取)
  password:    BRAIN 账号密码 (默认: 从环境变量 BRAIN_CREDENTIAL_PASSWORD 读取)
  db_path:     状态库路径 (默认: ../output/wqb_state.db)
  report_path: 报告输出路径 (默认: ../output/wqb_d5_selfcorr_breakthrough_report.md)
"""

import asyncio
import sys
import os
import json
import time
import sqlite3
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# ============================================================
# 路径配置
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ACE库路径
ACE_LIB_DIR = os.path.join(SCRIPT_DIR, "ace_lib")
sys.path.insert(0, ACE_LIB_DIR)
sys.path.insert(0, SCRIPT_DIR)

from codeact_sdk import CodeActSDK

# ============================================================
# 工具 Schema 版本常量
# ============================================================

TOOL_SCHEMA_VERSIONS = {
    "codeact_search_web": "v1_5ac1b0eba8c26f2a",
    "codeact_fetch_web": "v1_2c8d0580b3f93a58",
    "file_to_url": "v1_fe3416acf3d7b53b",
}

# ============================================================
# 提交间隔（严格限流，40秒以上避免429）
# ============================================================

SUBMIT_INTERVAL = 45.0

# ============================================================
# 8项提交检查阈值
# ============================================================

SUBMISSION_THRESHOLDS = {
    "LOW_SHARPE": 1.25,
    "LOW_FITNESS": 1.0,
    "LOW_TURNOVER": 0.01,
    "HIGH_TURNOVER": 0.7,
    "CONCENTRATED_WEIGHT": None,
    "LOW_SUB_UNIVERSE_SHARPE": None,
    "SELF_CORRELATION": 0.7,
    "MATCHES_COMPETITION": None,
}


# ============================================================
# 默认设置
# ============================================================

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


def normalize_settings(settings: Dict) -> Dict:
    """规范化设置，确保与DEFAULT_SETTINGS合并后哈希一致"""
    full = dict(DEFAULT_SETTINGS)
    full.update(settings)
    return full


def expr_hash(expr: str, settings: Dict) -> str:
    """计算表达式+设置的哈希值，用于去重"""
    norm = normalize_settings(settings)
    key = expr + "|" + json.dumps(norm, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()[:16]


# ============================================================
# 数据库操作
# ============================================================

def init_db(db_path: str):
    """初始化数据库表"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # alphas 表（已存在，确保字段完整）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alphas (
            expr_hash TEXT PRIMARY KEY,
            expression TEXT NOT NULL,
            factor_name TEXT,
            category TEXT,
            settings_json TEXT NOT NULL,
            alpha_id TEXT,
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
    
    # check_results 表（存储提交检查结果）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS check_results (
            alpha_id TEXT NOT NULL,
            factor_name TEXT,
            check_name TEXT NOT NULL,
            check_result TEXT,
            check_value REAL,
            check_limit REAL,
            checked_at TEXT NOT NULL,
            PRIMARY KEY (alpha_id, check_name, checked_at)
        )
    """)
    
    # self_corr 表（存储自相关详细数据）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS self_corr (
            alpha_id TEXT NOT NULL,
            factor_name TEXT,
            lag_period TEXT,
            correlation REAL,
            max_self_corr REAL,
            min_self_corr REAL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (alpha_id, lag_period, fetched_at)
        )
    """)
    
    conn.commit()
    return conn


def get_alpha_by_id(conn, alpha_id: str) -> Optional[Dict]:
    """从数据库获取alpha信息"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alphas WHERE alpha_id = ?", (alpha_id,))
    row = cursor.fetchone()
    if row:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    return None


def get_alpha_by_name(conn, factor_name: str) -> Optional[Dict]:
    """从数据库按名称获取alpha"""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alphas WHERE factor_name = ? ORDER BY completed_at DESC LIMIT 1", (factor_name,))
    row = cursor.fetchone()
    if row:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    return None


def save_check_results(conn, alpha_id: str, factor_name: str, checks_df, checked_at: str):
    """保存提交检查结果到数据库"""
    cursor = conn.cursor()
    for _, row in checks_df.iterrows():
        cursor.execute("""
            INSERT OR REPLACE INTO check_results 
            (alpha_id, factor_name, check_name, check_result, check_value, check_limit, checked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            alpha_id,
            factor_name,
            row.get("check", row.get("name", "")),
            row.get("result", ""),
            row.get("value", None),
            row.get("limit", None),
            checked_at
        ))
    conn.commit()


def save_self_corr(conn, alpha_id: str, factor_name: str, self_corr_df, fetched_at: str):
    """保存自相关数据到数据库"""
    cursor = conn.cursor()
    max_corr = self_corr_df["alpha_max_self_corr"].iloc[0] if not self_corr_df.empty and "alpha_max_self_corr" in self_corr_df.columns else None
    min_corr = self_corr_df["alpha_min_self_corr"].iloc[0] if not self_corr_df.empty and "alpha_min_self_corr" in self_corr_df.columns else None
    
    for _, row in self_corr_df.iterrows():
        lag = str(row.get("period", row.get("lag", "")))
        corr = row.get("correlation", None)
        cursor.execute("""
            INSERT OR REPLACE INTO self_corr
            (alpha_id, factor_name, lag_period, correlation, max_self_corr, min_self_corr, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (alpha_id, factor_name, lag, corr, max_corr, min_corr, fetched_at))
    conn.commit()


def alpha_exists(conn, expr: str, settings: Dict) -> Optional[Dict]:
    """检查alpha是否已存在于数据库"""
    h = expr_hash(expr, settings)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alphas WHERE expr_hash = ?", (h,))
    row = cursor.fetchone()
    if row:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    return None


def save_alpha_result(conn, expr: str, settings: Dict, factor_name: str, 
                      alpha_id: Optional[str], status: str, stats: Dict = None,
                      error: str = None):
    """保存或更新alpha结果到数据库"""
    h = expr_hash(expr, settings)
    settings_json = json.dumps(normalize_settings(settings), sort_keys=True)
    now = datetime.now().isoformat()
    
    cursor = conn.cursor()
    
    existing = alpha_exists(conn, expr, settings)
    
    if existing:
        # 更新
        updates = []
        params = []
        if alpha_id:
            updates.append("alpha_id = ?")
            params.append(alpha_id)
        if status:
            updates.append("status = ?")
            params.append(status)
        if stats:
            if "sharpe" in stats:
                updates.append("sharpe = ?")
                params.append(stats["sharpe"])
            if "fitness" in stats:
                updates.append("fitness = ?")
                params.append(stats["fitness"])
            if "turnover" in stats:
                updates.append("turnover = ?")
                params.append(stats["turnover"])
            if "ic" in stats:
                updates.append("ic = ?")
                params.append(stats["ic"])
            if "rank_ic" in stats:
                updates.append("rank_ic = ?")
                params.append(stats["rank_ic"])
        if error:
            updates.append("error = ?")
            params.append(error)
        updates.append("completed_at = ?")
        params.append(now)
        params.append(h)
        
        if updates:
            cursor.execute(f"UPDATE alphas SET {', '.join(updates)} WHERE expr_hash = ?", params)
    else:
        # 插入
        cursor.execute("""
            INSERT INTO alphas 
            (expr_hash, expression, factor_name, settings_json, alpha_id, status, 
             sharpe, fitness, turnover, ic, rank_ic, submitted_at, completed_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            h, expr, factor_name, settings_json, alpha_id, status,
            stats.get("sharpe") if stats else None,
            stats.get("fitness") if stats else None,
            stats.get("turnover") if stats else None,
            stats.get("ic") if stats else None,
            stats.get("rank_ic") if stats else None,
            now, now if status in ("COMPLETED", "FAILED") else None,
            error
        ))
    
    conn.commit()
    return h


# ============================================================
# ACE 库会话管理
# ============================================================

def create_session(email: str, password: str):
    """创建并认证 WQB 会话（使用 ACE 库）"""
    import ace_lib
    
    # 设置环境变量（ACE库通过环境变量读取凭证）
    os.environ["BRAIN_CREDENTIAL_EMAIL"] = email
    os.environ["BRAIN_CREDENTIAL_PASSWORD"] = password
    
    # 使用ACE库的start_session进行认证
    # 注意：SingleSession是单例模式，每次返回同一实例
    # 需要先重置实例以避免旧会话干扰
    if hasattr(ace_lib.SingleSession, '_instance'):
        ace_lib.SingleSession._instance = None
        ace_lib.SingleSession._initialized = False
    
    s = ace_lib.start_session()
    return s


# ============================================================
# 因子定义
# ============================================================

# alpha_021 基础信号（未decay版本的原始信号）
# open/ts_delay(close,1) - close/open
ALPHA021_SIGNAL = "subtract(divide(open, ts_delay(close, 1)), divide(close, open))"

# 波动率因子表达式
VOL20_EXPR = "multiply(ts_std_dev(log(divide(close, ts_delay(close, 1))), 20), sqrt(252))"
VOL5_EXPR = "multiply(ts_std_dev(log(divide(close, ts_delay(close, 1))), 5), sqrt(252))"

# d5 基准表达式
ALPHA021_D5_EXPR = f"ts_decay_linear({ALPHA021_SIGNAL}, 5)"


def build_new_factors() -> List[Dict]:
    """
    构建新因子列表
    策略：利用d5自相关低的特性，精细调整寻找最优平衡点
    """
    factors = []
    
    # 基础设置
    base_settings = normalize_settings({
        "decay": 0,  # 表达式内含decay，设置decay=0避免双重衰减
        "neutralization": "SUBINDUSTRY",
    })
    
    # 1. d4 - 线性衰减4天
    factors.append({
        "name": "alpha_021_d4",
        "expression": f"ts_decay_linear({ALPHA021_SIGNAL}, 4)",
        "settings": base_settings,
        "category": "decay_variants",
        "description": "线性衰减4天，探索d5附近自相关低谷"
    })
    
    # 2. d6 - 线性衰减6天
    factors.append({
        "name": "alpha_021_d6",
        "expression": f"ts_decay_linear({ALPHA021_SIGNAL}, 6)",
        "settings": base_settings,
        "category": "decay_variants",
        "description": "线性衰减6天，探索d5附近自相关低谷"
    })
    
    # 3. d7 - 线性衰减7天
    factors.append({
        "name": "alpha_021_d7",
        "expression": f"ts_decay_linear({ALPHA021_SIGNAL}, 7)",
        "settings": base_settings,
        "category": "decay_variants",
        "description": "线性衰减7天，探索d5附近自相关低谷"
    })
    
    # 4. d5 指数衰减
    factors.append({
        "name": "alpha_021_d5_exp",
        "expression": f"ts_decay_exp_window({ALPHA021_SIGNAL}, 5)",
        "settings": base_settings,
        "category": "decay_type",
        "description": "指数衰减5天，对比线性衰减的自相关差异"
    })
    
    # 5. d5 + vol20 组合 97:3
    factors.append({
        "name": "combo_d5_vol20_w9703",
        "expression": f"add(multiply({ALPHA021_D5_EXPR}, 0.97), multiply({VOL20_EXPR}, -0.03))",
        "settings": base_settings,
        "category": "vol_combo",
        "description": "d5与vol20加权组合(97:3)，用低自相关vol提升Fitness"
    })
    
    # 6. d5 + vol20 组合 98:2
    factors.append({
        "name": "combo_d5_vol20_w9802",
        "expression": f"add(multiply({ALPHA021_D5_EXPR}, 0.98), multiply({VOL20_EXPR}, -0.02))",
        "settings": base_settings,
        "category": "vol_combo",
        "description": "d5与vol20加权组合(98:2)，用低自相关vol提升Fitness"
    })
    
    # 7. d5 + vol20 组合 99:1
    factors.append({
        "name": "combo_d5_vol20_w9901",
        "expression": f"add(multiply({ALPHA021_D5_EXPR}, 0.99), multiply({VOL20_EXPR}, -0.01))",
        "settings": base_settings,
        "category": "vol_combo",
        "description": "d5与vol20加权组合(99:1)，用低自相关vol提升Fitness"
    })
    
    # 8. d5 + vol5 组合 95:5（短周期vol自相关更低）
    factors.append({
        "name": "combo_d5_vol5_w9505",
        "expression": f"add(multiply({ALPHA021_D5_EXPR}, 0.95), multiply({VOL5_EXPR}, -0.05))",
        "settings": base_settings,
        "category": "vol_combo",
        "description": "d5与vol5加权组合(95:5)，短周期vol自相关更低"
    })
    
    # 9. d5 + vol5 组合 97:3
    factors.append({
        "name": "combo_d5_vol5_w9703",
        "expression": f"add(multiply({ALPHA021_D5_EXPR}, 0.97), multiply({VOL5_EXPR}, -0.03))",
        "settings": base_settings,
        "category": "vol_combo",
        "description": "d5与vol5加权组合(97:3)，短周期vol自相关更低"
    })
    
    # 10. d5 无中性化版本（高Fitness低自相关候选）
    factors.append({
        "name": "alpha_021_d5_neut_none",
        "expression": ALPHA021_D5_EXPR,
        "settings": normalize_settings({
            "decay": 0,
            "neutralization": "NONE",
        }),
        "category": "neutralization",
        "description": "d5无中性化版本，参考neut_none的高Fitness特性"
    })
    
    # 11. d5 行业中性化（对比当前subindustry）
    factors.append({
        "name": "alpha_021_d5_neut_industry",
        "expression": ALPHA021_D5_EXPR,
        "settings": normalize_settings({
            "decay": 0,
            "neutralization": "INDUSTRY",
        }),
        "category": "neutralization",
        "description": "d5行业中性化，对比subindustry的Fitness/自相关平衡"
    })
    
    return factors


# ============================================================
# 核心功能函数
# ============================================================

def fetch_check_submission(s, alpha_id: str, factor_name: str, conn) -> Dict:
    """获取并保存提交检查结果"""
    import ace_lib
    import pandas as pd
    
    print(f"  获取提交检查结果: {factor_name} ({alpha_id})")
    
    try:
        checks_df = ace_lib.get_check_submission(s, alpha_id)
        checked_at = datetime.now().isoformat()
        
        if checks_df.empty:
            print(f"  ⚠ 检查结果为空，可能需要等待或alpha不存在")
            return {"alpha_id": alpha_id, "factor_name": factor_name, "checks": [], "empty": True}
        
        # 保存到数据库
        save_check_results(conn, alpha_id, factor_name, checks_df, checked_at)
        
        # 解析结果
        results = []
        all_pass = True
        for _, row in checks_df.iterrows():
            check_name = row.get("name", row.get("check", "UNKNOWN"))
            check_result = row.get("result", "")
            check_value = row.get("value", None)
            check_limit = row.get("limit", None)
            
            if check_result and "FAIL" in str(check_result).upper():
                all_pass = False
            
            results.append({
                "name": check_name,
                "result": check_result,
                "value": check_value,
                "limit": check_limit
            })
        
        return {
            "alpha_id": alpha_id,
            "factor_name": factor_name,
            "checks": results,
            "all_pass": all_pass,
            "empty": False
        }
        
    except Exception as e:
        print(f"  ❌ 获取检查结果失败: {e}")
        return {"alpha_id": alpha_id, "factor_name": factor_name, "checks": [], "error": str(e)}


def fetch_self_correlation(s, alpha_id: str, factor_name: str, conn) -> Dict:
    """获取并保存自相关性详细数据"""
    import ace_lib
    
    print(f"  获取自相关数据: {factor_name} ({alpha_id})")
    
    try:
        self_corr_df = ace_lib.get_self_corr(s, alpha_id)
        fetched_at = datetime.now().isoformat()
        
        if self_corr_df.empty:
            print(f"  ⚠ 自相关数据为空")
            return {"alpha_id": alpha_id, "factor_name": factor_name, "data": [], "empty": True}
        
        # 调试：打印列名
        print(f"  自相关数据列: {list(self_corr_df.columns)}")
        print(f"  自相关数据行数: {len(self_corr_df)}")
        if len(self_corr_df) > 0:
            print(f"  前3行:\n{self_corr_df.head(3).to_string()}")
        
        # 保存到数据库
        save_self_corr(conn, alpha_id, factor_name, self_corr_df, fetched_at)
        
        # 解析数据 - 自动检测列名
        data = []
        max_corr = self_corr_df["alpha_max_self_corr"].iloc[0] if "alpha_max_self_corr" in self_corr_df.columns else None
        min_corr = self_corr_df["alpha_min_self_corr"].iloc[0] if "alpha_min_self_corr" in self_corr_df.columns else None
        
        # 检测lag列和correlation列
        lag_col = None
        corr_col = None
        for col in self_corr_df.columns:
            if col in ("period", "lag", "lag_period", "shift", "delay"):
                lag_col = col
            elif col == "correlation":
                corr_col = col
            elif col in ("corr", "value") and corr_col is None:
                corr_col = col
        
        # 如果没找到correlation列，且只有alpha_max_self_corr，尝试从records提取
        if corr_col is None and max_corr is not None:
            # 可能只有一个最大值记录
            for col in self_corr_df.columns:
                if col not in ("alpha_max_self_corr", "alpha_min_self_corr", "alpha_id"):
                    # 尝试数值列
                    try:
                        val = float(self_corr_df.iloc[0][col])
                        if 0 <= val <= 1:
                            corr_col = col
                            break
                    except:
                        pass
        
        for idx, row in self_corr_df.iterrows():
            lag = str(row[lag_col]) if lag_col else str(idx)
            corr = row[corr_col] if corr_col else None
            if corr is not None:
                try:
                    corr = float(corr)
                except:
                    pass
            data.append({"lag": lag, "correlation": corr})
        
        return {
            "alpha_id": alpha_id,
            "factor_name": factor_name,
            "data": data,
            "max_correlation": max_corr,
            "min_correlation": min_corr,
            "empty": False
        }
        
    except Exception as e:
        import traceback
        print(f"  ❌ 获取自相关数据失败: {e}")
        print(f"  {traceback.format_exc()}")
        return {"alpha_id": alpha_id, "factor_name": factor_name, "data": [], "error": str(e)}


def submit_and_simulate(s, factors: List[Dict], conn) -> List[Dict]:
    """
    批量提交因子回测（使用ACE库simulate_alpha_list_multi，支持多因子同时模拟）
    返回模拟结果列表
    """
    import ace_lib
    
    results = []
    new_factors = []  # 需要新提交的因子
    
    # 第一步：筛选需要新提交的因子
    for i, factor in enumerate(factors):
        name = factor["name"]
        expr = factor["expression"]
        settings = factor["settings"]
        
        # 检查是否已存在
        existing = alpha_exists(conn, expr, settings)
        if existing and existing.get("status") == "COMPLETED" and existing.get("alpha_id"):
            print(f"  [{i+1}/{len(factors)}] {name}: 已存在 (alpha_id={existing['alpha_id']}, "
                  f"sharpe={existing.get('sharpe', 'N/A')}, fitness={existing.get('fitness', 'N/A')})")
            results.append({
                "factor": factor,
                "alpha_id": existing["alpha_id"],
                "status": "COMPLETED",
                "sharpe": existing.get("sharpe"),
                "fitness": existing.get("fitness"),
                "turnover": existing.get("turnover"),
                "existing": True
            })
            continue
        
        if existing and existing.get("status") in ("PENDING", "RUNNING") and existing.get("alpha_id"):
            print(f"  [{i+1}/{len(factors)}] {name}: 已提交，状态={existing.get('status')}, "
                  f"alpha_id={existing.get('alpha_id')}")
            # 对于已有alpha_id的PENDING，尝试查询结果
            try:
                stats_result = ace_lib.get_specified_alpha_stats(s, existing["alpha_id"], 
                    {"type": "REGULAR", "settings": settings, "regular": expr})
                if stats_result.get("is_stats") is not None and not stats_result["is_stats"].empty:
                    row = stats_result["is_stats"].iloc[0]
                    stats = {
                        "sharpe": row.get("sharpe"),
                        "fitness": row.get("fitness"),
                        "turnover": row.get("turnover"),
                        "ic": row.get("ic"),
                        "rank_ic": row.get("rank_ic"),
                    }
                    save_alpha_result(conn, expr, settings, name, existing["alpha_id"], "COMPLETED", stats)
                    results.append({
                        "factor": factor,
                        "alpha_id": existing["alpha_id"],
                        "status": "COMPLETED",
                        "sharpe": stats.get("sharpe"),
                        "fitness": stats.get("fitness"),
                        "turnover": stats.get("turnover"),
                        "existing": True
                    })
                    continue
            except Exception as e:
                print(f"    查询状态失败: {e}")
            
            results.append({
                "factor": factor,
                "alpha_id": existing.get("alpha_id"),
                "status": existing.get("status"),
                "existing": True
            })
            continue
        
        # 需要新提交
        print(f"  [{i+1}/{len(factors)}] 待提交: {name}")
        new_factors.append(factor)
    
    if not new_factors:
        print("\n  所有因子已存在，无需新提交")
        return results
    
    print(f"\n  需要新提交 {len(new_factors)} 个因子，使用批量模拟...")
    
    # 第二步：构建alpha_list格式，用于simulate_alpha_list_multi
    alpha_list = []
    for factor in new_factors:
        expr = factor["expression"]
        settings = factor["settings"]
        name = factor["name"]
        
        # 先记录为PENDING
        save_alpha_result(conn, expr, settings, name, None, "PENDING")
        
        simulate_data = {
            "type": "REGULAR",
            "settings": settings,
            "regular": expr,
        }
        alpha_list.append(simulate_data)
    
    # 第三步：逐个提交模拟（因multi-simulate 403权限问题，改用单因子提交）
    print(f"  单因子逐个提交: 共{len(new_factors)}个因子, 间隔{SUBMIT_INTERVAL}秒")
    print(f"  (预期时间: 约{(len(new_factors) * SUBMIT_INTERVAL + len(new_factors) * 60) / 60:.0f}分钟)\n")
    
    results_from_submit = []
    for i, factor in enumerate(new_factors):
        name = factor["name"]
        expr = factor["expression"]
        settings = factor["settings"]
        
        print(f"  [{i+1}/{len(new_factors)}] 提交: {name}")
        
        try:
            simulate_data = {
                "type": "REGULAR",
                "settings": settings,
                "regular": expr,
            }
            
            result = ace_lib.simulate_single_alpha(s, simulate_data)
            alpha_id = result.get("alpha_id")
            
            if alpha_id:
                # 获取详细统计
                stats = {}
                try:
                    stats_result = ace_lib.get_specified_alpha_stats(s, alpha_id, simulate_data)
                    if stats_result.get("is_stats") is not None and not stats_result["is_stats"].empty:
                        row = stats_result["is_stats"].iloc[0]
                        stats["sharpe"] = row.get("sharpe")
                        stats["fitness"] = row.get("fitness")
                        stats["turnover"] = row.get("turnover")
                        stats["ic"] = row.get("ic")
                        stats["rank_ic"] = row.get("rank_ic")
                except Exception as e:
                    print(f"    ⚠ 获取统计失败: {e}")
                
                save_alpha_result(conn, expr, settings, name, alpha_id, "COMPLETED", stats)
                print(f"    ✅ 完成: alpha_id={alpha_id}, sharpe={stats.get('sharpe')}, "
                      f"fitness={stats.get('fitness')}, turnover={stats.get('turnover')}")
                
                results_from_submit.append({
                    "factor": factor,
                    "alpha_id": alpha_id,
                    "status": "COMPLETED",
                    "sharpe": stats.get("sharpe"),
                    "fitness": stats.get("fitness"),
                    "turnover": stats.get("turnover"),
                    "existing": False
                })
            else:
                error_msg = result.get("error", "Unknown error")
                save_alpha_result(conn, expr, settings, name, None, "FAILED", error=error_msg)
                print(f"    ❌ 失败: {error_msg}")
                results_from_submit.append({
                    "factor": factor,
                    "alpha_id": None,
                    "status": "FAILED",
                    "error": error_msg,
                    "existing": False
                })
                
        except Exception as e:
            import traceback
            save_alpha_result(conn, expr, settings, name, None, "FAILED", error=str(e))
            print(f"    ❌ 异常: {e}")
            print(f"    {traceback.format_exc()}")
            results_from_submit.append({
                "factor": factor,
                "alpha_id": None,
                "status": "FAILED",
                "error": str(e),
                "existing": False
            })
        
        # 限流等待（最后一个不用等）
        if i < len(new_factors) - 1:
            print(f"    等待 {SUBMIT_INTERVAL} 秒...")
            time.sleep(SUBMIT_INTERVAL)
    
    results.extend(results_from_submit)
    return results


# ============================================================
# 报告生成
# ============================================================

def generate_report(d5_check: Dict, self_corr_results: List[Dict], 
                    new_factor_results: List[Dict], new_check_results: List[Dict],
                    report_path: str):
    """生成完整的诊断与突破报告"""
    
    lines = []
    lines.append("# alpha_021_d5 自相关深度诊断与突破报告\n")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # ========================================
    # 第一部分：d5 提交检查结果
    # ========================================
    lines.append("## 一、alpha_021_d5 提交检查结果\n")
    lines.append(f"- **Alpha ID**: `{d5_check.get('alpha_id', 'N/A')}`")
    lines.append(f"- **因子名称**: {d5_check.get('factor_name', 'N/A')}\n")
    
    if d5_check.get("empty"):
        lines.append("> ⚠️ 检查结果为空，可能需要手动触发检查或alpha不存在\n")
    elif d5_check.get("error"):
        lines.append(f"> ❌ 获取检查结果失败: {d5_check['error']}\n")
    else:
        # 统计通过情况
        checks = d5_check.get("checks", [])
        passed = sum(1 for c in checks if c.get("result", "").upper() == "PASS")
        failed = sum(1 for c in checks if c.get("result", "").upper() == "FAIL")
        
        lines.append(f"**总检查项**: {len(checks)} | ✅ 通过: {passed} | ❌ 失败: {failed}\n")
        
        lines.append("| 检查项 | 结果 | 数值 | 阈值 |")
        lines.append("|--------|------|------|------|")
        for c in checks:
            name = c.get("name", "")
            result = c.get("result", "")
            value = c.get("value", "N/A")
            limit = c.get("limit", "N/A")
            emoji = "✅" if result.upper() == "PASS" else "❌"
            lines.append(f"| {name} | {emoji} {result} | {value} | {limit} |")
        
        lines.append("")
        
        # 失败项分析
        failed_checks = [c for c in checks if c.get("result", "").upper() == "FAIL"]
        if failed_checks:
            lines.append("### 失败项分析\n")
            for c in failed_checks:
                lines.append(f"- **{c.get('name')}**: 值={c.get('value')}, 阈值={c.get('limit')}")
            lines.append("")
    
    # ========================================
    # 第二部分：d1/d3/d5 自相关对比
    # ========================================
    lines.append("## 二、d1/d3/d5 自相关性对比分析\n")
    
    # 构建对比表
    sc_by_name = {sc["factor_name"]: sc for sc in self_corr_results}
    
    # 找到公共的lag周期
    all_lags = set()
    for sc in self_corr_results:
        for d in sc.get("data", []):
            all_lags.add(d["lag"])
    
    if all_lags:
        # 按数值排序lag
        def lag_sort_key(lag):
            try:
                # 尝试提取数字
                num = ''.join(filter(str.isdigit, lag))
                return int(num) if num else 999
            except:
                return 999
        
        sorted_lags = sorted(all_lags, key=lag_sort_key)
        
        lines.append("### 2.1 各滞后期相关系数对比\n")
        lines.append("| 滞后期 | " + " | ".join(sc["factor_name"] for sc in self_corr_results) + " |")
        lines.append("|" + "------|" * (len(self_corr_results) + 1))
        
        for lag in sorted_lags:
            row = [lag]
            for sc in self_corr_results:
                corr = next((d["correlation"] for d in sc.get("data", []) if d["lag"] == lag), "N/A")
                if isinstance(corr, float):
                    row.append(f"{corr:.4f}")
                else:
                    row.append(str(corr))
            lines.append("| " + " | ".join(row) + " |")
        
        lines.append("")
    
    # 最大自相关对比
    lines.append("### 2.2 最大自相关系数对比\n")
    lines.append("| 因子 | Alpha ID | 最大自相关 | 是否超标(0.7) | Sharpe | Fitness | 换手率 |")
    lines.append("|------|----------|------------|---------------|--------|---------|--------|")
    
    for sc in self_corr_results:
        name = sc["factor_name"]
        alpha_id = sc["alpha_id"]
        max_corr = sc.get("max_correlation", "N/A")
        
        # 从数据库获取sharpe等数据
        conn = sqlite3.connect(os.path.join(OUTPUT_DIR, "wqb_state.db"))
        alpha_info = get_alpha_by_id(conn, alpha_id)
        conn.close()
        
        sharpe = alpha_info.get("sharpe", "N/A") if alpha_info else "N/A"
        fitness = alpha_info.get("fitness", "N/A") if alpha_info else "N/A"
        turnover = alpha_info.get("turnover", "N/A") if alpha_info else "N/A"
        
        if isinstance(max_corr, float):
            status = "❌ 超标" if max_corr >= 0.7 else "✅ 达标"
            max_corr_str = f"{max_corr:.4f}"
        else:
            status = "N/A"
            max_corr_str = str(max_corr)
        
        lines.append(f"| {name} | `{alpha_id}` | {max_corr_str} | {status} | {sharpe} | {fitness} | {turnover} |")
    
    lines.append("")
    
    # 反常现象分析
    lines.append("### 2.3 反常现象深度分析\n")
    lines.append("**现象**: d5（5天线性衰减）的自相关性反而低于 d3 和 d1，这与直觉相悖——")
    lines.append("通常衰减窗口越大，信号越平滑，自相关性应该越高。\n")
    
    lines.append("**可能原因分析**:\n")
    lines.append("1. **周度周期共振效应**: 5天刚好是一个完整交易周，可能与市场的周度周期形成共振抵消，")
    lines.append("   导致相邻两天的信号重叠度反而降低。d1和d3没有完整覆盖周度模式。\n")
    
    lines.append("2. **衰减权重分布差异**: 线性衰减下，d5的权重分布为 [5,4,3,2,1]/15，")
    lines.append("   最近一天权重仅33%；而d3的权重为 [3,2,1]/6，最近一天权重50%。")
    lines.append("   d5信号对单日变化的敏感度更低，可能恰好使得日度变化的自相关降低。\n")
    
    lines.append("3. **信号本身的反转特性**: alpha_021 基于隔夜-日内反转，")
    lines.append("   5天窗口可能刚好捕捉到一个完整的反转-回归周期，")
    lines.append("   使得T日和T+1日的信号在5日尺度上呈现低相关性。\n")
    
    lines.append("4. **数值稳定性**: d5换手率仅0.226，远低于d1的0.403和d3的0.272，")
    lines.append("   说明信号变化更平缓，但自相关反而更低——这暗示信号的变化方向更随机，")
    lines.append("   而不是简单的平滑。\n")
    
    lines.append("**验证方法**: 测试d4, d6, d7，观察自相关是否在d5附近形成低谷。\n")
    
    # ========================================
    # 第三部分：新因子回测结果
    # ========================================
    lines.append("## 三、新因子批量回测结果\n")
    
    if not new_factor_results:
        lines.append("> 暂无新因子回测数据\n")
    else:
        # 按类别分组
        by_category = defaultdict(list)
        for r in new_factor_results:
            cat = r["factor"].get("category", "unknown")
            by_category[cat].append(r)
        
        for cat, results in sorted(by_category.items()):
            lines.append(f"### 3.{list(by_category.keys()).index(cat)+1} {cat} 类别\n")
            lines.append("| 因子名称 | Sharpe | Fitness | 换手率 | 状态 | Alpha ID |")
            lines.append("|----------|--------|---------|--------|------|----------|")
            
            for r in sorted(results, key=lambda x: x.get("fitness") or 0, reverse=True):
                name = r["factor"]["name"]
                sharpe = r.get("sharpe", "N/A")
                fitness = r.get("fitness", "N/A")
                turnover = r.get("turnover", "N/A")
                status = r.get("status", "N/A")
                alpha_id = r.get("alpha_id", "N/A")
                
                sharpe_str = f"{sharpe:.2f}" if isinstance(sharpe, float) else str(sharpe)
                fitness_str = f"{fitness:.2f}" if isinstance(fitness, float) else str(fitness)
                turnover_str = f"{turnover:.4f}" if isinstance(turnover, float) else str(turnover)
                
                # 达标标记
                marks = []
                if isinstance(sharpe, float) and sharpe >= 1.25:
                    marks.append("📈")
                if isinstance(fitness, float) and fitness >= 1.0:
                    marks.append("💪")
                mark_str = " " + "".join(marks) if marks else ""
                
                lines.append(f"| {name}{mark_str} | {sharpe_str} | {fitness_str} | {turnover_str} | {status} | `{alpha_id}` |")
            
            lines.append("")
        
        # 达标因子汇总
        qualifying = [r for r in new_factor_results 
                     if isinstance(r.get("sharpe"), float) and r["sharpe"] >= 1.25
                     and isinstance(r.get("fitness"), float) and r["fitness"] >= 1.0]
        
        lines.append(f"### 3.X 达标因子汇总 (Sharpe≥1.25 且 Fitness≥1.0)\n")
        if qualifying:
            lines.append(f"共 **{len(qualifying)}** 个因子达到初筛标准：\n")
            for r in sorted(qualifying, key=lambda x: x.get("fitness", 0), reverse=True):
                lines.append(f"- **{r['factor']['name']}**: Sharpe={r['sharpe']:.2f}, "
                           f"Fitness={r['fitness']:.2f}, Turnover={r.get('turnover', 'N/A')}")
        else:
            lines.append("> 暂无因子同时满足 Sharpe≥1.25 和 Fitness≥1.0\n")
        lines.append("")
    
    # ========================================
    # 第四部分：新因子提交检查结果
    # ========================================
    lines.append("## 四、新因子提交检查结果\n")
    
    if not new_check_results:
        lines.append("> 暂无提交检查数据\n")
    else:
        for cr in new_check_results:
            name = cr.get("factor_name", "Unknown")
            alpha_id = cr.get("alpha_id", "N/A")
            checks = cr.get("checks", [])
            
            lines.append(f"### {name}\n")
            lines.append(f"- **Alpha ID**: `{alpha_id}`")
            
            if cr.get("empty"):
                lines.append("- ⚠️ 检查结果为空\n")
                continue
            if cr.get("error"):
                lines.append(f"- ❌ 检查失败: {cr['error']}\n")
                continue
            
            all_pass = cr.get("all_pass", False)
            passed = sum(1 for c in checks if c.get("result", "").upper() == "PASS")
            failed = sum(1 for c in checks if c.get("result", "").upper() == "FAIL")
            
            status_emoji = "🎉" if all_pass else "⚠️"
            lines.append(f"- **状态**: {status_emoji} {'全部通过' if all_pass else '存在失败项'} "
                       f"({passed}/{len(checks)} 通过)\n")
            
            lines.append("| 检查项 | 结果 | 数值 | 阈值 |")
            lines.append("|--------|------|------|------|")
            for c in checks:
                cname = c.get("name", "")
                cresult = c.get("result", "")
                cvalue = c.get("value", "N/A")
                climit = c.get("limit", "N/A")
                emoji = "✅" if cresult.upper() == "PASS" else "❌"
                lines.append(f"| {cname} | {emoji} {cresult} | {cvalue} | {climit} |")
            lines.append("")
    
    # ========================================
    # 第五部分：结论与建议
    # ========================================
    lines.append("## 五、结论与建议\n")
    
    # 从数据中提取结论
    d5_max_corr = None
    for sc in self_corr_results:
        if "d5" in sc["factor_name"]:
            d5_max_corr = sc.get("max_correlation")
            break
    
    if d5_max_corr is not None:
        if d5_max_corr < 0.7:
            lines.append("### ✅ 核心发现\n")
            lines.append(f"alpha_021_d5 的最大自相关系数为 **{d5_max_corr:.4f}**，低于0.7阈值！\n")
            lines.append("这意味着 d5 版本本身可能已经满足自相关要求，之前的提交失败可能是由于其他原因。\n")
        else:
            lines.append("### ❌ 核心发现\n")
            lines.append(f"alpha_021_d5 的最大自相关系数为 **{d5_max_corr:.4f}**，超过0.7阈值。\n")
    
    lines.append("### 策略建议\n")
    lines.append("1. **如果d5自相关已达标**: 重点优化 Fitness 和 Sharpe，考虑：")
    lines.append("   - 降低中性化强度（NONE > SECTOR > INDUSTRY > SUBINDUSTRY）")
    lines.append("   - 加入小比例波动率因子提升Fitness")
    lines.append("   - 调整truncation参数\n")
    
    lines.append("2. **如果d5自相关未达标**: 利用d5自相关低谷特性，做精细调整：")
    lines.append("   - 测试d4-d7之间的所有整数窗口")
    lines.append("   - 尝试指数衰减vs线性衰减")
    lines.append("   - 组合极低自相关的因子（如vol类）拉低整体自相关\n")
    
    lines.append("3. **组合因子方向**: 利用d5较低的自相关作为基底，")
    lines.append("   加入1-5%的负波动率因子，预期可以：")
    lines.append("   - 略微提升Fitness（波动率因子Fitness通常很高）")
    lines.append("   - 保持或进一步降低自相关（vol因子自相关特性不同）")
    lines.append("   - 维持Sharpe在可接受范围\n")
    
    # 写入文件
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    print(f"\n✅ 报告已生成: {report_path}")
    return report_path


# ============================================================
# 主函数
# ============================================================

async def main():
    # 解析参数
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    email = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("BRAIN_CREDENTIAL_EMAIL", "q1z2q3@126.com")
    password = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("BRAIN_CREDENTIAL_PASSWORD", "W2025zq0118")
    db_path = sys.argv[4] if len(sys.argv) > 4 else os.path.join(OUTPUT_DIR, "wqb_state.db")
    report_path = sys.argv[5] if len(sys.argv) > 5 else os.path.join(OUTPUT_DIR, "wqb_d5_selfcorr_breakthrough_report.md")
    
    sdk = CodeActSDK()
    
    # 处理 result_mode
    if result_mode == "auto":
        result_mode = "display_only"
    
    try:
        print("=" * 70)
        print("alpha_021_d5 自相关深度诊断与突破脚本")
        print("=" * 70)
        print(f"账号: {email}")
        print(f"数据库: {db_path}")
        print(f"报告路径: {report_path}")
        print()
        
        # 初始化数据库
        conn = init_db(db_path)
        print(f"✅ 数据库初始化完成")
        
        # 创建会话
        print(f"\n📡 连接 WQB API...")
        import ace_lib
        from ace_lib import SingleSession
        
        # 使用ACE库的登录方式
        s = create_session(email, password)
        print(f"✅ 登录成功")
        print()
        
        # ========================================
        # 第一步：获取 alpha_021_d5 提交检查结果
        # ========================================
        print("📊 第一步：获取 alpha_021_d5 提交检查结果")
        print("-" * 50)
        
        d5_alpha_id = "O0xZv69J"
        d5_factor_name = "alpha_021_d5"
        d5_check = fetch_check_submission(s, d5_alpha_id, d5_factor_name, conn)
        print()
        
        # ========================================
        # 第二步：获取 d1/d3/d5 自相关数据
        # ========================================
        print("📊 第二步：获取 d1/d3/d5 自相关性数据")
        print("-" * 50)
        
        alpha_pairs = [
            ("O0xZv69J", "alpha_021_d5"),
            ("E5eEALEL", "alpha_021_d3"),
            ("E5eE3Zp1", "alpha_021_d1_raw"),
        ]
        
        self_corr_results = []
        for alpha_id, factor_name in alpha_pairs:
            sc = fetch_self_correlation(s, alpha_id, factor_name, conn)
            self_corr_results.append(sc)
            # 限流
            time.sleep(2)
        
        print()
        
        # 打印对比摘要
        print("📋 自相关对比摘要:")
        for sc in self_corr_results:
            max_corr = sc.get("max_correlation", "N/A")
            if isinstance(max_corr, float):
                status = "达标" if max_corr < 0.7 else "超标"
                print(f"  {sc['factor_name']}: max_corr={max_corr:.4f} ({status})")
            else:
                print(f"  {sc['factor_name']}: max_corr={max_corr}")
        
        print()
        
        # ========================================
        # 第三步：构建并提交新因子
        # ========================================
        print("🚀 第三步：构建并提交新因子回测")
        print("-" * 50)
        
        new_factors = build_new_factors()
        print(f"共构建 {len(new_factors)} 个新因子")
        
        # 筛选需要提交的（跳过已完成的）
        factors_to_submit = []
        for f in new_factors:
            existing = alpha_exists(conn, f["expression"], f["settings"])
            if not existing or existing.get("status") not in ("COMPLETED",):
                factors_to_submit.append(f)
            else:
                print(f"  跳过已完成: {f['name']} (alpha_id={existing.get('alpha_id')})")
        
        print(f"需要提交: {len(factors_to_submit)} 个")
        print()
        
        new_factor_results = []
        
        if factors_to_submit:
            new_factor_results = submit_and_simulate(s, factors_to_submit, conn)
        else:
            print("  所有因子已存在，跳过提交")
        
        # 补充已存在因子的结果
        existing_results = []
        for f in new_factors:
            existing = alpha_exists(conn, f["expression"], f["settings"])
            if existing and existing.get("status") == "COMPLETED":
                existing_results.append({
                    "factor": f,
                    "alpha_id": existing.get("alpha_id"),
                    "status": "COMPLETED",
                    "sharpe": existing.get("sharpe"),
                    "fitness": existing.get("fitness"),
                    "turnover": existing.get("turnover"),
                    "existing": True
                })
        
        # 合并结果
        all_new_results = existing_results + [r for r in new_factor_results if not r.get("existing")]
        # 去重
        seen_names = set()
        final_new_results = []
        for r in all_new_results:
            name = r["factor"]["name"]
            if name not in seen_names:
                seen_names.add(name)
                final_new_results.append(r)
        
        print()
        
        # ========================================
        # 第四步：对达标因子执行提交检查
        # ========================================
        print("🔍 第四步：对达标因子执行提交检查")
        print("-" * 50)
        
        # 筛选达标因子
        qualifying_factors = [r for r in final_new_results
                             if isinstance(r.get("sharpe"), float) and r["sharpe"] >= 1.25
                             and isinstance(r.get("fitness"), float) and r["fitness"] >= 1.0
                             and r.get("alpha_id")]
        
        print(f"达标因子数量: {len(qualifying_factors)}")
        
        new_check_results = []
        for r in qualifying_factors:
            alpha_id = r["alpha_id"]
            factor_name = r["factor"]["name"]
            
            # 限流等待
            if new_check_results:
                time.sleep(5)
            
            check_result = fetch_check_submission(s, alpha_id, factor_name, conn)
            new_check_results.append(check_result)
        
        print()
        
        # ========================================
        # 第五步：生成报告
        # ========================================
        print("📝 第五步：生成报告")
        print("-" * 50)
        
        generate_report(d5_check, self_corr_results, final_new_results, new_check_results, report_path)
        
        # ========================================
        # 提交结果
        # ========================================
        conn.close()
        
        # 构建摘要消息
        summary_lines = []
        summary_lines.append("## alpha_021_d5 自相关诊断与突破完成\n")
        
        # d5检查结果摘要
        if not d5_check.get("empty") and not d5_check.get("error"):
            checks = d5_check.get("checks", [])
            passed = sum(1 for c in checks if c.get("result", "").upper() == "PASS")
            failed = sum(1 for c in checks if c.get("result", "").upper() == "FAIL")
            summary_lines.append(f"### d5 提交检查: {passed}/{len(checks)} 通过")
            failed_checks = [c for c in checks if c.get("result", "").upper() == "FAIL"]
            for c in failed_checks:
                summary_lines.append(f"- ❌ {c.get('name')}: {c.get('value')} (阈值: {c.get('limit')})")
            summary_lines.append("")
        
        # 自相关对比摘要
        summary_lines.append("### 自相关对比 (d1/d3/d5)")
        for sc in self_corr_results:
            max_corr = sc.get("max_correlation", "N/A")
            if isinstance(max_corr, float):
                status = "✅" if max_corr < 0.7 else "❌"
                summary_lines.append(f"- {sc['factor_name']}: {max_corr:.4f} {status}")
            else:
                summary_lines.append(f"- {sc['factor_name']}: {max_corr}")
        summary_lines.append("")
        
        # 新因子回测摘要
        if final_new_results:
            completed = [r for r in final_new_results if r.get("status") == "COMPLETED"]
            qualifying = [r for r in completed 
                         if isinstance(r.get("sharpe"), float) and r["sharpe"] >= 1.25
                         and isinstance(r.get("fitness"), float) and r["fitness"] >= 1.0]
            summary_lines.append(f"### 新因子回测: {len(completed)}/{len(final_new_results)} 完成")
            summary_lines.append(f"- Sharpe≥1.25 且 Fitness≥1.0: {len(qualifying)} 个")
            if qualifying:
                top = sorted(qualifying, key=lambda x: x.get("fitness", 0), reverse=True)[:3]
                summary_lines.append("- Top 3 (按Fitness):")
                for r in top:
                    summary_lines.append(f"  • {r['factor']['name']}: S={r['sharpe']:.2f}, F={r['fitness']:.2f}")
            summary_lines.append("")
        
        # 提交检查摘要
        if new_check_results:
            all_passed = [cr for cr in new_check_results if cr.get("all_pass")]
            summary_lines.append(f"### 提交检查: {len(all_passed)}/{len(new_check_results)} 全部通过")
            for cr in new_check_results:
                status = "🎉" if cr.get("all_pass") else "⚠️"
                summary_lines.append(f"- {status} {cr.get('factor_name')}")
            summary_lines.append("")
        
        summary_lines.append(f"📄 完整报告: `{report_path}`")
        
        message = "\n".join(summary_lines)
        
        # 提交结果
        await sdk.submit_result(
            status="success",
            result_mode=result_mode,
            message=message,
            data={
                "report_path": report_path,
                "d5_check": d5_check,
                "self_corr_results": self_corr_results,
                "new_factor_count": len(final_new_results),
                "qualifying_count": len(qualifying_factors),
                "check_results_count": len(new_check_results),
            }
        )
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"\n❌ 脚本执行失败: {e}")
        print(error_detail)
        
        try:
            await sdk.submit_result(
                status="error",
                result_mode="notify",
                message=f"alpha_021_d5 诊断脚本执行失败: {str(e)}",
                data={"error": str(e), "traceback": error_detail}
            )
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())
