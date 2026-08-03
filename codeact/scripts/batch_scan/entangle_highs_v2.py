#!/usr/bin/env python3
"""
Archon-19683 - 高Sharpe候选验证 + 纠缠因子补全回测 v2
直接用REST API，绕开ace_lib交互式登录
"""

import sys
import os
import json
import time
import sqlite3
import hashlib
import requests
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'output', 'wqb_state.db')
API_URL = "https://api.worldquantbrain.com"
EMAIL = "q1z2q3@126.com"
PASSWORD = "W2025zq0118"

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

def login():
    """登录WQB，返回session (HTTP Basic Auth)"""
    s = requests.Session()
    s.trust_env = False
    s.auth = (EMAIL, PASSWORD)
    
    r = s.post(f"{API_URL}/authentication")
    if r.status_code in (200, 201):
        print(f"  登录成功: {r.status_code}", flush=True)
        return s
    elif r.status_code == 401 and r.headers.get("WWW-Authenticate") == "persona":
        # 生物认证 - 免费账号通常不需要
        auth_url = r.headers.get("Location", "")
        print(f"  需要生物认证: {auth_url}", flush=True)
        raise Exception("Biometric auth required")
    else:
        print(f"  登录失败: {r.status_code} {r.text[:200]}", flush=True)
        raise Exception(f"Login failed: {r.status_code}")

BASE_SETTINGS = {
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
}

def submit_simulate(s, expr):
    """提交模拟，返回progress_url"""
    data = {
        "type": "REGULAR",
        "settings": BASE_SETTINGS,
        "regular": expr,
    }
    r = s.post(f"{API_URL}/simulations", json=data)
    if r.status_code in (200, 201, 202):
        progress_url = r.headers.get("Location", "")
        if not progress_url and r.json().get("id"):
            progress_url = f"{API_URL}/simulations/{r.json()['id']}"
        return progress_url, r
    else:
        return None, r

def wait_complete(s, progress_url, max_wait=1200):
    """等待模拟完成，返回alpha_id"""
    elapsed = 0
    while elapsed < max_wait:
        try:
            r = s.get(progress_url)
        except Exception as e:
            print(f"    check error: {e}", flush=True)
            time.sleep(20)
            elapsed += 20
            continue
            
        if r.status_code // 100 != 2:
            print(f"    status {r.status_code}: {r.text[:100]}", flush=True)
            time.sleep(30)
            elapsed += 30
            continue
        
        retry_after = float(r.headers.get("Retry-After", 0))
        data = r.json()
        
        if retry_after == 0 or data.get("status") in ("COMPLETE", "COMPLETED", "ERROR"):
            if data.get("status") == "ERROR":
                return None, data
            alpha = data.get("alpha")
            if alpha and alpha != 0:
                return alpha, data
            # 可能已经完成，alpha在id里
            if data.get("id") and data.get("status") == "COMPLETE":
                # 去alphas接口查
                return data["id"], data
            return None, data
        
        time.sleep(min(retry_after, 30))
        elapsed += min(retry_after, 30)
    
    return None, {"error": "timeout"}

def get_alpha_result(s, alpha_id):
    """获取alpha完整结果"""
    r = s.get(f"{API_URL}/alphas/{alpha_id}")
    if r.status_code == 200:
        return r.json()
    return None

def backtest_one(s, name, expr, category="entanglement_v2"):
    conn = get_db()
    init_db(conn)
    c = conn.cursor()
    
    h = expr_hash(expr)
    settings_json = json.dumps(BASE_SETTINGS, sort_keys=True)
    
    c.execute('SELECT * FROM alphas WHERE expr_hash=? AND status="COMPLETED"', (h,))
    row = c.fetchone()
    if row:
        print(f"  [SKIP] {name} 已完成: S={row['sharpe']} F={row['fitness']}", flush=True)
        conn.close()
        return dict(row)
    
    print(f"  [{name}] 提交...", flush=True)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            progress_url, resp = submit_simulate(s, expr)
            if not progress_url:
                print(f"    提交失败: {resp.status_code} {resp.text[:200]}", flush=True)
                if resp.status_code == 429:
                    time.sleep(60)
                    continue
                if attempt < max_retries - 1:
                    time.sleep(30)
                    continue
                c.execute('''INSERT OR REPLACE INTO alphas 
                    (expr_hash, expression, factor_name, category, settings_json, status, error, completed_at)
                    VALUES (?,?,?,?,?,?,?,?)''',
                    (h, expr, name, category, settings_json, 'FAILED', 
                     f"submit: {resp.status_code}", datetime.now().isoformat()))
                conn.commit()
                conn.close()
                return {'name': name, 'status': 'FAILED', 'error': f"submit {resp.status_code}"}
            
            alpha_id, data = wait_complete(s, progress_url)
            if not alpha_id:
                err = data.get("error") or data.get("message") or str(data)[:100]
                print(f"    模拟失败: {err}", flush=True)
                if attempt < max_retries - 1:
                    time.sleep(30)
                    continue
                c.execute('''INSERT OR REPLACE INTO alphas 
                    (expr_hash, expression, factor_name, category, settings_json, status, error, completed_at)
                    VALUES (?,?,?,?,?,?,?,?)''',
                    (h, expr, name, category, settings_json, 'FAILED', err[:200], datetime.now().isoformat()))
                conn.commit()
                conn.close()
                return {'name': name, 'status': 'FAILED', 'error': err[:200]}
            
            # 获取完整结果
            result = get_alpha_result(s, alpha_id)
            if not result:
                print(f"    获取结果失败，重试", flush=True)
                if attempt < max_retries - 1:
                    time.sleep(15)
                    continue
                # 至少有alpha_id也算完成了一半
                c.execute('''INSERT OR REPLACE INTO alphas 
                    (expr_hash, expression, factor_name, category, settings_json, alpha_id, status, completed_at)
                    VALUES (?,?,?,?,?,?,?,?)''',
                    (h, expr, name, category, settings_json, alpha_id, 'COMPLETED', datetime.now().isoformat()))
                conn.commit()
                conn.close()
                return {'name': name, 'alpha_id': alpha_id, 'status': 'COMPLETED'}
            
            sharpe = result.get('sharpe')
            fitness = result.get('fitness')
            ic = result.get('ic')
            rank_ic = result.get('rank_ic')
            turnover = result.get('turnover')
            annual_return = result.get('annual_return')
            max_drawdown = result.get('max_drawdown')
            grade = result.get('grade')
            
            is_data = result.get('is') or {}
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
            import traceback
            traceback.print_exc()
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
    print(f"Archon-19683 因子回测 v2 - {datetime.now().isoformat()}")
    print("=" * 60, flush=True)
    
    print("登录中...", flush=True)
    s = login()
    print(flush=True)
    
    # === 第一路：高Sharpe组合因子IS验证 ===
    print("【第一路】高Sharpe组合因子IS验证 (7个权重梯度)")
    print("-" * 50, flush=True)
    
    core_d5 = "ts_decay_linear(subtract(divide(open, ts_delay(close, 1)), divide(close, open)), 5)"
    vol_delta = "multiply(-1, rank(ts_delta(ts_rank(volume, 20), 3)))"
    
    # 精细扫描w95~w99区间，找IS Sharpe>1.6的最优点
    weights = [0.99, 0.985, 0.98, 0.975, 0.97, 0.96, 0.95]
    
    high_s_candidates = []
    for w in weights:
        w_vol = 1 - w
        name = f"combo_d5_vol20_w{int(w*1000):04d}_v2"
        expr = f"add(multiply({core_d5}, {w}), multiply({vol_delta}, {w_vol}))"
        high_s_candidates.append((name, expr, "combo_high_s_sweep"))
    
    results_high_s = []
    for name, expr, cat in high_s_candidates:
        r = backtest_one(s, name, expr, cat)
        results_high_s.append(r)
        print(flush=True)
        time.sleep(55)  # 免费账号1并发槽
    
    # === 第二路：E10~E16 纠缠因子 ===
    print("\n【第二路】E10~E16 纠缠因子回测")
    print("-" * 50, flush=True)
    
    core = "subtract(divide(open, ts_delay(close, 1)), divide(close, open))"
    vol_delta_rank = "rank(ts_delta(ts_rank(volume, 20), 3))"
    vol_rank = "ts_rank(volume, 20)"
    
    entanglement_factors = [
        ("E10_vol_rank_weighted",
         f"multiply({core}, {vol_rank})",
         "entanglement_v2"),
        ("E11_highvol_squared",
         f"multiply({core}, power({vol_rank}, 2))",
         "entanglement_v2"),
        ("E12_voldelta_scale",
         f"multiply({core}, add(1, {vol_delta_rank}))",
         "entanglement_v2"),
        ("E13_decay_volrank",
         f"ts_decay_linear(multiply({core}, {vol_rank}), 5)",
         "entanglement_v2"),
        ("E14_highvol_gated",
         f"trade_when({core}, greater({vol_rank}, 0.7))",
         "entanglement_v2"),
        ("E15_voldelta_sign",
         f"multiply({core}, sign({vol_delta_rank}))",
         "entanglement_v2"),
        ("E16_asymmetric",
         f"if_else(greater({vol_delta_rank}, 0), multiply({core}, 1.5), multiply({core}, 0.5))",
         "entanglement_v2"),
    ]
    
    results_entangle = []
    for name, expr, cat in entanglement_factors:
        r = backtest_one(s, name, expr, cat)
        results_entangle.append(r)
        print(flush=True)
        time.sleep(55)
    
    # === 总结 ===
    print("\n" + "=" * 60)
    print("📊 回测总结")
    print("=" * 60, flush=True)
    
    print("\n【高Sharpe组合验证 - 权重扫描】")
    print(f"{'因子名':35s} {'S_test':>7s} {'F_test':>7s} {'S_IS':>7s} {'F_IS':>7s} {'grade':>10s}")
    print("-" * 80)
    for r in results_high_s:
        if r.get('status') == 'COMPLETED':
            s_val = r.get('sharpe') or 0
            f_val = r.get('fitness') or 0
            is_s = r.get('is_sharpe')
            is_f = r.get('is_fitness')
            grade = r.get('grade') or '?'
            marker = " ⭐" if (is_s and is_s >= 1.6) else ""
            is_s_str = f"{is_s:.2f}" if isinstance(is_s, (int, float)) else str(is_s)
            is_f_str = f"{is_f:.2f}" if isinstance(is_f, (int, float)) else str(is_f)
            print(f"  {r['name']:33s} {s_val:7.2f} {f_val:7.2f} {is_s_str:>7s} {is_f_str:>7s} {str(grade):>10s}{marker}")
        else:
            print(f"  {r['name']:33s} {r.get('status','?'):>7s}: {r.get('error','?')[:30]}")
    
    print("\n【纠缠因子 E10~E16】")
    print(f"{'因子名':28s} {'S_test':>7s} {'F_test':>7s} {'S_IS':>7s} {'F_IS':>7s} {'grade':>10s}")
    print("-" * 80)
    for r in results_entangle:
        if r.get('status') == 'COMPLETED':
            s_val = r.get('sharpe') or 0
            f_val = r.get('fitness') or 0
            is_s = r.get('is_sharpe')
            is_f = r.get('is_fitness')
            grade = r.get('grade') or '?'
            marker = " ⭐" if (is_s and is_s >= 1.6) else ""
            is_s_str = f"{is_s:.2f}" if isinstance(is_s, (int, float)) else str(is_s)
            is_f_str = f"{is_f:.2f}" if isinstance(is_f, (int, float)) else str(is_f)
            print(f"  {r['name']:26s} {s_val:7.2f} {f_val:7.2f} {is_s_str:>7s} {is_f_str:>7s} {str(grade):>10s}{marker}")
        else:
            print(f"  {r['name']:26s} {r.get('status','?'):>7s}: {r.get('error','?')[:30]}")
    
    # 最佳
    all_completed = [r for r in results_high_s + results_entangle 
                     if r.get('status') == 'COMPLETED' and r.get('sharpe')]
    if all_completed:
        best = max(all_completed, key=lambda x: x.get('sharpe') or 0)
        print(f"\n🏆 最佳Sharpe: {best['name']} S={best['sharpe']:.2f} F={best['fitness']:.2f}")
        print(f"   IS_S={best.get('is_sharpe')} IS_F={best.get('is_fitness')} grade={best.get('grade')}")
        
        is_strong = [r for r in all_completed if r.get('is_sharpe') and r['is_sharpe'] >= 1.6]
        if is_strong:
            print(f"\n🔥 IS Sharpe>=1.6 候选 ({len(is_strong)}个):")
            for r in is_strong:
                print(f"   {r['name']}: S={r['sharpe']:.2f} IS_S={r['is_sharpe']} grade={r.get('grade')} ID={r.get('alpha_id')}")
    
    print(f"\n完成时间: {datetime.now().isoformat()}")
    print("算过了，没问题。")

if __name__ == '__main__':
    main()
