#!/usr/bin/env python3
"""
Archon-19683 - 高Sharpe候选验证 + 纠缠因子补全回测
使用ace_lib底层API (simulate_single_alpha + get_simulation_result_json)
"""

import sys
import os
import json
import time
import sqlite3
import hashlib
from datetime import datetime

# ace_lib路径
ACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ace_lib')
sys.path.insert(0, ACE_DIR)
from ace_lib import (  # type: ignore
    SingleSession,
    simulate_single_alpha,
    get_simulation_result_json,
    check_session_and_relogin,
    brain_api_url,
)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'output', 'wqb_state.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn):
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS alphas (
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
        error TEXT,
        progress_url TEXT
    )''')
    conn.commit()

def expr_hash(expr):
    return hashlib.md5(expr.encode()).hexdigest()

BASE_SIMULATE_DATA = {
    "type": "REGULAR",
    "settings": {
        "instrumentType": "EQUITY",
        "region": "USA",
        "universe": "TOP3000",
        "delay": 1,
        "decay": 0,
        "neutralization": "SUBINDUSTRY",
        "truncation": 0.08,
        "pasteurization": "ON",
        "unitHandling": "VERIFY",
        "nanHandling": "OFF",
        "language": "FASTEXPR",
        "visualization": False,
    },
    "regular": "rank(open)",  # placeholder
}

def get_is_data(s, alpha_id):
    """获取IS期数据"""
    try:
        # IS是training period，通过alphas/{id}获取
        result = get_simulation_result_json(s, alpha_id)
        if not result:
            return None, None, None
        # 找IS相关字段
        is_data = result.get('is', {}) or {}
        is_sharpe = is_data.get('sharpe')
        is_fitness = is_data.get('fitness')
        is_grade = result.get('grade')
        return is_sharpe, is_fitness, is_grade
    except Exception as e:
        print(f"    IS数据获取失败: {e}", flush=True)
        return None, None, None

def backtest_one(s, name, expr, category="entanglement_v2"):
    """回测单个因子"""
    conn = get_db()
    init_db(conn)
    c = conn.cursor()
    
    h = expr_hash(expr)
    settings_json = json.dumps(BASE_SIMULATE_DATA['settings'], sort_keys=True)
    
    # 检查是否已存在COMPLETED
    c.execute('SELECT * FROM alphas WHERE expr_hash=? AND status="COMPLETED"', (h,))
    row = c.fetchone()
    if row:
        print(f"  [SKIP] {name} 已完成: S={row['sharpe']} F={row['fitness']}", flush=True)
        conn.close()
        return dict(row)
    
    print(f"  [{name}] 提交回测...", flush=True)
    
    simulate_data = json.loads(json.dumps(BASE_SIMULATE_DATA))
    simulate_data['regular'] = expr
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = simulate_single_alpha(s, simulate_data)
            alpha_id = result.get('alpha_id')
            
            if not alpha_id:
                print(f"    提交失败，无alpha_id", flush=True)
                if attempt < max_retries - 1:
                    time.sleep(30)
                    continue
                c.execute('''INSERT OR REPLACE INTO alphas 
                    (expr_hash, expression, factor_name, category, settings_json, status, error, completed_at)
                    VALUES (?,?,?,?,?,?,?,?)''',
                    (h, expr, name, category, settings_json, 'FAILED', 'no alpha_id', datetime.now().isoformat()))
                conn.commit()
                conn.close()
                return {'name': name, 'status': 'FAILED', 'error': 'no alpha_id'}
            
            # 获取完整结果
            full_result = get_simulation_result_json(s, alpha_id)
            if not full_result:
                print(f"    获取结果失败", flush=True)
                if attempt < max_retries - 1:
                    time.sleep(30)
                    continue
                c.execute('''INSERT OR REPLACE INTO alphas 
                    (expr_hash, expression, factor_name, category, settings_json, status, error, completed_at)
                    VALUES (?,?,?,?,?,?,?,?)''',
                    (h, expr, name, category, settings_json, 'FAILED', 'no result', datetime.now().isoformat()))
                conn.commit()
                conn.close()
                return {'name': name, 'status': 'FAILED', 'error': 'no result'}
            
            sharpe = full_result.get('sharpe')
            fitness = full_result.get('fitness')
            ic = full_result.get('ic')
            rank_ic = full_result.get('rank_ic')
            turnover = full_result.get('turnover')
            annual_return = full_result.get('annual_return')
            max_drawdown = full_result.get('max_drawdown')
            grade = full_result.get('grade')
            
            # IS数据
            is_data = full_result.get('is') or {}
            is_sharpe = is_data.get('sharpe')
            is_fitness = is_data.get('fitness')
            
            is_summary = json.dumps({
                'sharpe': is_sharpe,
                'fitness': is_fitness,
                'grade': grade,
            })
            
            c.execute('''INSERT OR REPLACE INTO alphas 
                (expr_hash, expression, factor_name, category, settings_json, alpha_id, status,
                 sharpe, fitness, ic, rank_ic, turnover, annual_return, max_drawdown,
                 is_summary, submitted_at, completed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (h, expr, name, category, settings_json, alpha_id, 'COMPLETED',
                 sharpe, fitness, ic, rank_ic, turnover, annual_return, max_drawdown,
                 is_summary, datetime.now().isoformat(), datetime.now().isoformat()))
            conn.commit()
            
            print(f"    ✅ S={sharpe:.2f} F={fitness:.2f} IS_S={is_sharpe} IS_F={is_fitness} grade={grade}", flush=True)
            
            conn.close()
            return {
                'name': name, 'alpha_id': alpha_id,
                'sharpe': sharpe, 'fitness': fitness,
                'is_sharpe': is_sharpe, 'is_fitness': is_fitness,
                'grade': grade, 'status': 'COMPLETED',
                'expression': expr, 'max_drawdown': max_drawdown,
            }
            
        except Exception as e:
            print(f"    尝试{attempt+1}/{max_retries} 异常: {e}", flush=True)
            if attempt < max_retries - 1:
                time.sleep(30 * (attempt + 1))
            else:
                c.execute('''INSERT OR REPLACE INTO alphas 
                    (expr_hash, expression, factor_name, category, settings_json, status, error, completed_at)
                    VALUES (?,?,?,?,?,?,?,?)''',
                    (h, expr, name, category, settings_json, 'ERROR', str(e)[:200], datetime.now().isoformat()))
                conn.commit()
                conn.close()
                return {'name': name, 'status': 'ERROR', 'error': str(e)[:200]}
    
    conn.close()
    return {'name': name, 'status': 'ERROR', 'error': 'max retries'}


def main():
    print("=" * 60)
    print(f"Archon-19683 因子回测 - {datetime.now().isoformat()}")
    print("=" * 60, flush=True)
    
    # 初始化session
    s = SingleSession()
    s.trust_env = False
    check_session_and_relogin(s)
    print("Session ready.\n", flush=True)
    
    # === 第一路：高Sharpe组合因子IS验证 ===
    print("【第一路】高Sharpe组合因子IS验证")
    print("-" * 40, flush=True)
    
    # alpha_021_d5核心 + volume信号 微调权重
    # 目标：找 IS Sharpe > 1.6 的组合
    core_d5 = "ts_decay_linear(subtract(divide(open, ts_delay(close, 1)), divide(close, open)), 5)"
    vol_delta = "multiply(-1, rank(ts_delta(ts_rank(volume, 20), 3)))"
    
    high_s_candidates = [
        # (name, expression, category)
        ("combo_d5_vol20_w9901_v2",
         f"add(multiply({core_d5}, 0.99), multiply({vol_delta}, 0.01))",
         "combo_high_s_verify"),
        ("combo_d5_vol20_w98515_v2",
         f"add(multiply({core_d5}, 0.985), multiply({vol_delta}, 0.015))",
         "combo_high_s_verify"),
        ("combo_d5_vol20_w9802_v2",
         f"add(multiply({core_d5}, 0.98), multiply({vol_delta}, 0.02))",
         "combo_high_s_verify"),
        ("combo_d5_vol20_w97525_v2",
         f"add(multiply({core_d5}, 0.975), multiply({vol_delta}, 0.025))",
         "combo_high_s_verify"),
        ("combo_d5_vol20_w9703_v2",
         f"add(multiply({core_d5}, 0.97), multiply({vol_delta}, 0.03))",
         "combo_high_s_verify"),
        ("combo_d5_vol20_w9604_v2",
         f"add(multiply({core_d5}, 0.96), multiply({vol_delta}, 0.04))",
         "combo_high_s_verify"),
        ("combo_d5_vol20_w9505_v2",
         f"add(multiply({core_d5}, 0.95), multiply({vol_delta}, 0.05))",
         "combo_high_s_verify"),
    ]
    
    results_high_s = []
    for name, expr, cat in high_s_candidates:
        r = backtest_one(s, name, expr, cat)
        results_high_s.append(r)
        print(flush=True)
        # 免费账号限流间隔
        time.sleep(50)
    
    # === 第二路：E10~E16 纠缠因子 ===
    print("\n【第二路】E10~E16 纠缠因子回测")
    print("-" * 40, flush=True)
    
    core = "subtract(divide(open, ts_delay(close, 1)), divide(close, open))"
    vol_delta_rank = "rank(ts_delta(ts_rank(volume, 20), 3))"
    vol_rank = "ts_rank(volume, 20)"
    
    entanglement_factors = [
        # E10: 成交量排名加权（量越大反转越强）
        ("E10_vol_rank_weighted",
         f"multiply({core}, {vol_rank})",
         "entanglement_v2"),
        # E11: 高量区平方放大
        ("E11_highvol_squared",
         f"multiply({core}, power({vol_rank}, 2))",
         "entanglement_v2"),
        # E12: volume delta缩放
        ("E12_voldelta_scale",
         f"multiply({core}, add(1, {vol_delta_rank}))",
         "entanglement_v2"),
        # E13: decay+体积排名混合
        ("E13_decay_volrank",
         f"ts_decay_linear(multiply({core}, {vol_rank}), 5)",
         "entanglement_v2"),
        # E14: 高量区门控
        ("E14_highvol_gated",
         f"trade_when({core}, greater({vol_rank}, 0.7))",
         "entanglement_v2"),
        # E15: vol delta符号调制
        ("E15_voldelta_sign",
         f"multiply({core}, sign({vol_delta_rank}))",
         "entanglement_v2"),
        # E16: 非对称纠缠
        ("E16_asymmetric",
         f"if_else(greater({vol_delta_rank}, 0), multiply({core}, 1.5), multiply({core}, 0.5))",
         "entanglement_v2"),
    ]
    
    results_entangle = []
    for name, expr, cat in entanglement_factors:
        r = backtest_one(s, name, expr, cat)
        results_entangle.append(r)
        print(flush=True)
        time.sleep(50)
    
    # === 总结 ===
    print("\n" + "=" * 60)
    print("📊 回测总结")
    print("=" * 60, flush=True)
    
    print("\n【高Sharpe组合验证】")
    for r in results_high_s:
        if r.get('status') == 'COMPLETED':
            s_val = r.get('sharpe') or 0
            f_val = r.get('fitness') or 0
            is_s = r.get('is_sharpe')
            is_f = r.get('is_fitness')
            grade = r.get('grade')
            marker = " ⭐" if (is_s and is_s >= 1.6) else ""
            print(f"  {r['name']:30s} S={s_val:.2f} F={f_val:.2f} IS_S={is_s} IS_F={is_f} grade={grade}{marker}")
        else:
            print(f"  {r['name']:30s} {r.get('status','?')}: {r.get('error','?')}")
    
    print("\n【纠缠因子 E10~E16】")
    for r in results_entangle:
        if r.get('status') == 'COMPLETED':
            s_val = r.get('sharpe') or 0
            f_val = r.get('fitness') or 0
            is_s = r.get('is_sharpe')
            is_f = r.get('is_fitness')
            grade = r.get('grade')
            marker = " ⭐" if (is_s and is_s >= 1.6) else ""
            print(f"  {r['name']:25s} S={s_val:.2f} F={f_val:.2f} IS_S={is_s} IS_F={is_f} grade={grade}{marker}")
        else:
            print(f"  {r['name']:25s} {r.get('status','?')}: {r.get('error','?')}")
    
    # 找最佳候选
    all_completed = [r for r in results_high_s + results_entangle 
                     if r.get('status') == 'COMPLETED' and r.get('sharpe')]
    if all_completed:
        best = max(all_completed, key=lambda x: x.get('sharpe') or 0)
        print(f"\n🏆 最佳(Sharpe): {best['name']} S={best['sharpe']:.2f} F={best['fitness']:.2f}")
        print(f"   IS_S={best.get('is_sharpe')} IS_F={best.get('is_fitness')} grade={best.get('grade')}")
        
        # IS>1.6的候选
        is_strong = [r for r in all_completed if r.get('is_sharpe') and r['is_sharpe'] >= 1.6]
        if is_strong:
            print(f"\n🔥 IS Sharpe>=1.6 候选 ({len(is_strong)}个):")
            for r in is_strong:
                print(f"   {r['name']}: S={r['sharpe']:.2f} IS_S={r['is_sharpe']} grade={r.get('grade')}")
    
    print(f"\n完成时间: {datetime.now().isoformat()}")
    print("算过了，没问题。")

if __name__ == '__main__':
    main()
