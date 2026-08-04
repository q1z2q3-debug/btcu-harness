#!/usr/bin/env python3
"""
Archon-19683 - 补漏回测 v3
跑缺失的高Sharpe组合 + 纠缠因子，429无限指数退避
"""
import sys, os, json, time, sqlite3, hashlib, requests
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'output', 'wqb_state.db')
API_URL = "https://api.worldquantbrain.com"
EMAIL = "q1z2q3@126.com"
PASSWORD = "W2025zq0118"

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
    "nanHandling": "ON",
    "language": "FASTEXPR",
    "visualization": False,
    "testPeriod": "P1Y6M",
}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def login():
    s = requests.Session()
    s.trust_env = False
    s.auth = (EMAIL, PASSWORD)
    for attempt in range(5):
        r = s.post(f"{API_URL}/authentication")
        if r.status_code in (200, 201):
            print(f"  登录成功: {r.status_code}", flush=True)
            return s
        print(f"  登录失败 {r.status_code}，重试...", flush=True)
        time.sleep(30 * (attempt + 1))
    raise Exception("登录失败")

def expr_hash(expr):
    return hashlib.md5(expr.encode()).hexdigest()

def submit_and_wait(s, expr, name, category, settings_json, max_wait=1800):
    conn = get_db()
    c = conn.cursor()
    h = expr_hash(expr)
    
    # 已完成则跳过
    c.execute("SELECT status, sharpe, fitness FROM alphas WHERE expr_hash=?", (h,))
    row = c.fetchone()
    if row and row['status'] == 'COMPLETED' and row['sharpe'] is not None:
        print(f"  [SKIP] {name} 已完成 S={row['sharpe']:.2f} F={row['fitness']:.2f}", flush=True)
        conn.close()
        return True
    
    data = {
        "type": "REGULAR",
        "settings": BASE_SETTINGS,
        "regular": expr,
    }
    
    # 提交
    progress_url = None
    submit_attempt = 0
    while True:
        try:
            r = s.post(f"{API_URL}/simulations", json=data, timeout=60)
            if r.status_code in (200, 201, 202):
                progress_url = r.headers.get("Location", "")
                if not progress_url and r.json().get("id"):
                    progress_url = f"{API_URL}/simulations/{r.json()['id']}"
                print(f"    提交成功", flush=True)
                break
            elif r.status_code == 429:
                submit_attempt += 1
                wait = min(60 * (2 ** min(submit_attempt - 1, 6)), 600)
                print(f"    提交429(#{submit_attempt}) 等{wait}s", flush=True)
                time.sleep(wait)
            else:
                print(f"    提交失败 {r.status_code}: {r.text[:200]}", flush=True)
                time.sleep(30)
        except Exception as e:
            print(f"    提交异常: {e}", flush=True)
            time.sleep(30)
    
    if not progress_url:
        conn.close()
        return False
    
    # 轮询
    elapsed = 0
    alpha_id = None
    while elapsed < max_wait:
        try:
            r = s.get(progress_url, timeout=60)
            if r.status_code == 429:
                ra = float(r.headers.get("Retry-After", 30))
                time.sleep(ra)
                elapsed += ra
                continue
            if r.status_code // 100 != 2:
                time.sleep(30)
                elapsed += 30
                continue
            
            retry_after = float(r.headers.get("Retry-After", 0))
            d = r.json()
            
            if retry_after == 0 or d.get("status") in ("COMPLETE", "COMPLETED", "ERROR"):
                if d.get("status") == "ERROR":
                    print(f"    模拟ERROR", flush=True)
                    conn.close()
                    return False
                alpha = d.get("alpha")
                if alpha and alpha != 0:
                    alpha_id = alpha
                    break
                if d.get("id") and d.get("status") == "COMPLETE":
                    alpha_id = d["id"]
                    break
            time.sleep(min(retry_after, 30))
            elapsed += min(retry_after, 30)
        except Exception as e:
            print(f"    轮询异常: {e}", flush=True)
            time.sleep(20)
            elapsed += 20
    
    if not alpha_id:
        print(f"    超时", flush=True)
        conn.close()
        return False
    
    # 获取alpha详情
    try:
        r2 = s.get(f"{API_URL}/alphas/{alpha_id}", timeout=60)
        if r2.status_code == 200:
            ad = r2.json()
        else:
            ad = d
    except:
        ad = d
    
    sharpe = ad.get("sharpe")
    fitness = ad.get("fitness")
    grade = ad.get("grade", "")
    is_data = ad.get("is", {}) or {}
    is_sharpe = is_data.get("sharpe")
    is_fitness = is_data.get("fitness")
    max_dd = ad.get("maxDrawdown")
    
    c.execute('''INSERT OR REPLACE INTO alphas 
        (expr_hash, expression, factor_name, category, settings_json, alpha_id, status,
         sharpe, fitness, max_drawdown, is_summary, completed_at)
        VALUES (?,?,?,?,?,?, 'COMPLETED',?,?,?,?,?)''',
        (h, expr, name, category, settings_json, alpha_id,
         sharpe, fitness, max_dd,
         json.dumps(is_data) if is_data else None,
         datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    s_s = f"{sharpe:.2f}" if sharpe is not None else "?"
    f_s = f"{fitness:.2f}" if fitness is not None else "?"
    is_s = f"{is_sharpe:.2f}" if is_sharpe is not None else "?"
    is_f = f"{is_fitness:.2f}" if is_fitness is not None else "?"
    print(f"    ✅ S={s_s} F={f_s} IS_S={is_s} IS_F={is_f} grade={grade}", flush=True)
    return True

def main():
    print("=" * 60)
    print(f"Archon-19683 补漏回测 v3 - {datetime.now().isoformat()}")
    print("=" * 60, flush=True)
    
    s = login()
    settings_json = json.dumps(BASE_SETTINGS)
    
    # 所有待跑因子列表
    tasks = []
    
    # 1. 缺失的高Sharpe组合 (w0970, w0950)
    core_d5 = "ts_decay_linear(subtract(divide(open, ts_delay(close, 1)), divide(close, open)), 5)"
    vol_delta = "multiply(-1, rank(ts_delta(ts_rank(volume, 20), 3)))"
    
    for w in [0.97, 0.95]:
        w_str = str(int(w * 1000)).zfill(3)
        name = f"combo_d5_vol20_w0{w_str}_v2"
        expr = f"multiply({w:.3f}, {core_d5}) + multiply({1-w:.3f}, {vol_delta})"
        tasks.append((name, expr, "combo_vol"))
    
    # 2. 纠缠因子 E10~E16
    ent_exprs = {
        "E10_volrank_overnight": 
            "multiply(rank(volume), subtract(divide(open, ts_delay(close, 1)), divide(close, open)))",
        "E11_highvol_squared":  # 已完成，占位跳过
            "",
        "E12_voldelta_scale":
            "multiply(ts_delta(ts_rank(volume, 20), 3), subtract(divide(open, ts_delay(close, 1)), divide(close, open)))",
        "E13_decay_volrank":
            "ts_decay_linear(multiply(rank(volume), subtract(divide(open, ts_delay(close, 1)), divide(close, open))), 5)",
        "E14_volrank_abs_reversal":
            "multiply(rank(volume), abs(subtract(divide(open, ts_delay(close, 1)), divide(close, open))))",
        "E15_sign_vol_weighted":
            "multiply(sign(subtract(divide(open, ts_delay(close, 1)), divide(close, open))), multiply(rank(volume), rank(volume)))",
        "E16_volmom_overnight":
            "multiply(ts_delta(rank(volume), 5), subtract(divide(open, ts_delay(close, 1)), divide(close, open)))",
    }
    
    for name, expr in ent_exprs.items():
        if expr:
            tasks.append((name, expr, "entanglement"))
    
    print(f"\n共 {len(tasks)} 个因子待回测")
    print("-" * 50, flush=True)
    
    done = 0
    for name, expr, category in tasks:
        print(f"\n  [{name}] 提交...", flush=True)
        ok = submit_and_wait(s, expr, name, category, settings_json)
        if ok:
            done += 1
        # 免费账号1并发，每个之间多留点缓冲
        time.sleep(65)
    
    print(f"\n{'='*60}")
    print(f"完成 {done}/{len(tasks)}")
    print(f"结束时间: {datetime.now().isoformat()}")
    print("=" * 60, flush=True)

if __name__ == "__main__":
    main()
