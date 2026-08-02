#!/usr/bin/env python3
"""
WQB d5突破 - 阶段1：批量回测（仅模拟，不检查自相关）
将结果存入state.db，供阶段2使用
"""
import os
import sys
import time
import json
import sqlite3
import hashlib
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

ACE_LIB_DIR = os.path.join(SCRIPT_DIR, "ace_lib")
sys.path.insert(0, ACE_LIB_DIR)
sys.path.insert(0, SCRIPT_DIR)

from ace_lib import start_session, generate_alpha, simulate_alpha_list

SUBMIT_INTERVAL = 45.0

DEFAULT_SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 15, "neutralization": "SUBINDUSTRY",
    "truncation": 0.08, "pasteurization": "ON", "testPeriod": "P1Y6M",
    "unitHandling": "VERIFY", "nanHandling": "OFF", "maxTrade": "ON",
    "language": "FASTEXPR", "visualization": False,
}

D5_EXPR = "ts_decay_linear(subtract(divide(open, ts_delay(close, 1)), divide(close, open)), 5)"
VOL20_EXPR = "multiply(ts_std_dev(log(divide(close, ts_delay(close, 1))), 20), sqrt(252))"
VOL5_EXPR = "ts_std_dev(log(divide(close, ts_delay(close, 1))), 5)"


def make_combo_expr(d5_weight: float, vol20_weight: float) -> str:
    return f"add(multiply({d5_weight}, {D5_EXPR}), multiply({vol20_weight}, multiply(-1, ts_rank({VOL20_EXPR}, 20))))"


# Phase 1: vol20 combos with decay=0
PHASE1 = [
    {"name": "combo_d5_vol20_w98515", "expr": make_combo_expr(0.985, 0.015), "override": {"decay": 0}},
    {"name": "combo_d5_vol20_w99010", "expr": make_combo_expr(0.99, 0.01), "override": {"decay": 0}},
    {"name": "combo_d5_vol20_w99505", "expr": make_combo_expr(0.995, 0.005), "override": {"decay": 0}},
    {"name": "combo_d5_vol20_w98218", "expr": make_combo_expr(0.982, 0.018), "override": {"decay": 0}},
]

# Phase 2: d5协同信号
PHASE2 = [
    {"name": "combo_d5_volume_confirm", "expr": f"multiply({D5_EXPR}, ts_rank(volume, 5))", "override": {"decay": 0}},
    {"name": "combo_d5_vol5", "expr": f"multiply({D5_EXPR}, multiply(-1, ts_rank({VOL5_EXPR}, 5)))", "override": {"decay": 0}},
    {"name": "alpha_021_d5_neut_none", "expr": D5_EXPR, "override": {"decay": 0, "neutralization": "NONE"}},
]


def normalize_settings(settings):
    full = dict(DEFAULT_SETTINGS)
    full.update(settings)
    return full


def expr_hash(expr, settings):
    norm = normalize_settings(settings)
    key = expr + "|" + json.dumps(norm, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()[:16]


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alphas (
            expr_hash TEXT PRIMARY KEY, expression TEXT NOT NULL,
            factor_name TEXT, category TEXT, settings_json TEXT NOT NULL,
            alpha_id TEXT, status TEXT DEFAULT 'PENDING',
            sharpe REAL, fitness REAL, ic REAL, rank_ic REAL,
            turnover REAL, annual_return REAL, max_drawdown REAL,
            is_summary TEXT, yearly_json TEXT,
            submitted_at TEXT, completed_at TEXT, error TEXT
        )
    """)
    conn.commit()
    return conn


def alpha_exists(conn, expr, settings):
    h = expr_hash(expr, settings)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alphas WHERE expr_hash = ?", (h,))
    row = cursor.fetchone()
    if row:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    return None


def save_alpha(conn, expr, settings, factor_name, alpha_id, status, stats=None, error=None):
    h = expr_hash(expr, settings)
    settings_json = json.dumps(normalize_settings(settings), sort_keys=True)
    now = datetime.now().isoformat()
    cursor = conn.cursor()
    existing = alpha_exists(conn, expr, settings)
    if existing:
        updates = []
        params = []
        if alpha_id:
            updates.append("alpha_id = ?"); params.append(alpha_id)
        if status:
            updates.append("status = ?"); params.append(status)
        if stats:
            for k in ["sharpe", "fitness", "turnover"]:
                if k in stats and stats[k] is not None:
                    updates.append(f"{k} = ?"); params.append(stats[k])
        if error:
            updates.append("error = ?"); params.append(error)
        updates.append("completed_at = ?"); params.append(now)
        params.append(h)
        cursor.execute(f"UPDATE alphas SET {', '.join(updates)} WHERE expr_hash = ?", params)
    else:
        cursor.execute("""
            INSERT INTO alphas (expr_hash, expression, factor_name, settings_json, alpha_id,
             status, sharpe, fitness, turnover, completed_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (h, expr, factor_name, settings_json, alpha_id, status,
              stats.get("sharpe") if stats else None,
              stats.get("fitness") if stats else None,
              stats.get("turnover") if stats else None,
              now, error))
    conn.commit()


def extract_stats(result):
    stats = {"sharpe": None, "fitness": None, "turnover": None}
    is_stats = result.get("is_stats")
    if is_stats is not None and hasattr(is_stats, 'empty') and not is_stats.empty:
        try:
            row = is_stats.iloc[0]
            for k in ["sharpe", "fitness", "turnover"]:
                if k in row:
                    stats[k] = row[k]
        except Exception:
            pass
    if stats["sharpe"] is None:
        alpha_result = result.get("result", result.get("alpha", {}))
        if isinstance(alpha_result, dict):
            is_data = alpha_result.get("is", {})
            if is_data:
                stats["sharpe"] = is_data.get("sharpe", stats["sharpe"])
                stats["fitness"] = is_data.get("fitness", stats["fitness"])
                stats["turnover"] = is_data.get("turnover", stats["turnover"])
    return stats


def run_simulation_batch(session, factors, base_settings, conn, label):
    to_sim = []
    for f in factors:
        fs = dict(base_settings)
        fs.update(f.get("override", {}))
        existing = alpha_exists(conn, f["expr"], fs)
        if existing and existing.get("alpha_id") and existing.get("status") == "COMPLETED":
            print(f"  [跳过] {f['name']}: alpha_id={existing['alpha_id']}")
        else:
            to_sim.append(f)
    
    if not to_sim:
        print(f"  {label}: 全部已存在，无需模拟")
        return
    
    sim_data_list = []
    for f in to_sim:
        fs = dict(base_settings)
        fs.update(f.get("override", {}))
        sd = generate_alpha(
            regular=f["expr"],
            region=fs.get("region", "USA"),
            universe=fs.get("universe", "TOP3000"),
            delay=fs.get("delay", 1),
            decay=fs.get("decay", 15),
            neutralization=fs.get("neutralization", "SUBINDUSTRY"),
            truncation=fs.get("truncation", 0.08),
            pasteurization=fs.get("pasteurization", "ON"),
            test_period=fs.get("testPeriod", "P1Y6M"),
        )
        sim_data_list.append(sd)
    
    print(f"  {label}: 模拟 {len(sim_data_list)} 个因子...")
    sim_config = {"get_pnl": False, "get_stats": False, "save_pnl_file": False,
                  "save_stats_file": False, "save_result_file": False,
                  "check_submission": False, "check_self_corr": False, "check_prod_corr": False}
    
    results = simulate_alpha_list(session, sim_data_list, limit_of_concurrent_simulations=1, simulation_config=sim_config)
    
    # 匹配结果
    def match(r):
        sd = r.get("simulate_data", {})
        re = sd.get("regular", "")
        for f in to_sim:
            if f["expr"] == re:
                fs = dict(base_settings)
                fs.update(f.get("override", {}))
                rs = sd.get("settings", {})
                if fs.get("neutralization", "SUBINDUSTRY") == rs.get("neutralization", "SUBINDUSTRY"):
                    return f["name"]
        return None
    
    name_map = {}
    for r in results:
        n = match(r)
        if n:
            name_map[n] = r
    
    for f in to_sim:
        r = name_map.get(f["name"], {"alpha_id": None})
        aid = r.get("alpha_id")
        fs = dict(base_settings)
        fs.update(f.get("override", {}))
        if aid:
            stats = extract_stats(r)
            save_alpha(conn, f["expr"], fs, f["name"], aid, "COMPLETED", stats)
            print(f"  [完成] {f['name']}: alpha_id={aid}, S={stats.get('sharpe')}, F={stats.get('fitness')}")
        else:
            save_alpha(conn, f["expr"], fs, f["name"], None, "FAILED", error="回测失败")
            print(f"  [失败] {f['name']}: 回测未完成")


def main():
    email = os.environ.get("BRAIN_CREDENTIAL_EMAIL", "q1z2q3@126.com")
    password = os.environ.get("BRAIN_CREDENTIAL_PASSWORD", "W2025zq0118")
    db_path = os.path.join(OUTPUT_DIR, "wqb_state.db")
    
    if len(sys.argv) > 1:
        email = sys.argv[1]
    if len(sys.argv) > 2:
        password = sys.argv[2]
    
    os.environ["BRAIN_CREDENTIAL_EMAIL"] = email
    os.environ["BRAIN_CREDENTIAL_PASSWORD"] = password
    
    conn = init_db(db_path)
    print(f"数据库: {db_path}")
    print("登录 WQB...")
    session = start_session()
    print("登录成功！")
    
    # Phase 1: vol20 combos
    print("\n" + "=" * 60)
    print("阶段1: vol20权重精调 (decay=0)")
    print("=" * 60)
    run_simulation_batch(session, PHASE1, DEFAULT_SETTINGS, conn, "阶段1")
    
    # Phase 2: d5协同信号
    print("\n" + "=" * 60)
    print("阶段2: d5协同信号")
    print("=" * 60)
    run_simulation_batch(session, PHASE2, DEFAULT_SETTINGS, conn, "阶段2")
    
    conn.close()
    print("\n阶段1完成！所有因子已保存到数据库。请运行阶段2脚本来执行自相关检查和提交检查。")


if __name__ == "__main__":
    main()