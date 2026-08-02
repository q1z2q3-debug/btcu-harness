#!/usr/bin/env python3
"""
快速验证脚本：检查已创建alpha的自相关 + 测试不同decay设置
"""
import os
import sys
import time
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ACE_LIB_DIR = os.path.join(SCRIPT_DIR, "ace_lib")
sys.path.insert(0, ACE_LIB_DIR)
sys.path.insert(0, SCRIPT_DIR)

from ace_lib import start_session, get_self_corr, get_check_submission, generate_alpha, simulate_single_alpha, simulation_progress, start_simulation

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")

email = sys.argv[1] if len(sys.argv) > 1 else "q1z2q3@126.com"
password = sys.argv[2] if len(sys.argv) > 2 else "W2025zq0118"

os.environ["BRAIN_CREDENTIAL_EMAIL"] = email
os.environ["BRAIN_CREDENTIAL_PASSWORD"] = password

print("登录 WQB...")
session = start_session()
print("登录成功！")

# 1. 检查已有alpha的自相关
alpha_ids_to_check = [
    ("combo_d5_vol20_w98515", "xAd1YqxW"),
    ("combo_d5_vol20_w99010", "KPEmOE8p"),
    ("combo_d5_vol20_w99505", "E5eVvO0K"),
    ("combo_d5_vol20_w98218", "88evjkWo"),
    ("combo_d5_volume_confirm", "le3M8G7A"),
    ("combo_d5_vol5", "xAd1Yw8n"),
]

print("\n" + "=" * 60)
print("1. 验证已有alpha的自相关")
print("=" * 60)

for name, aid in alpha_ids_to_check:
    try:
        alpha_info = session.get(f"https://api.worldquantbrain.com/alphas/{aid}").json()
        print(f"\n--- {name} ({aid}) ---")
        is_data = alpha_info.get("is", {})
        print(f"  Sharpe: {is_data.get('sharpe')}")
        print(f"  Fitness: {is_data.get('fitness')}")
        print(f"  Turnover: {is_data.get('turnover')}")
        
        time.sleep(5)
        sc_df = get_self_corr(session, aid)
        if not sc_df.empty:
            max_sc = sc_df["alpha_max_self_corr"].iloc[0]
            print(f"  Max Self-Corr: {max_sc}")
        else:
            print(f"  Self-Corr: 空")
    except Exception as e:
        print(f"  Error: {e}")

# 2. 测试vol20组合with decay=0
print("\n" + "=" * 60)
print("2. 测试decay=0的d5+vol20组合")
print("=" * 60)

D5_EXPR = "ts_decay_linear(subtract(divide(open, ts_delay(close, 1)), divide(close, open)), 5)"
VOL20_EXPR = "multiply(ts_std_dev(log(divide(close, ts_delay(close, 1))), 20), sqrt(252))"

# 测试4个权重
test_cases = [
    ("combo_d5_v20_98515_d0", 0.985, 0.015),
    ("combo_d5_v20_99010_d0", 0.99, 0.01),
    ("combo_d5_v20_99505_d0", 0.995, 0.005),
    ("combo_d5_v20_98218_d0", 0.982, 0.018),
]

for name, w_d5, w_vol in test_cases:
    combo_expr = f"add(multiply({w_d5}, {D5_EXPR}), multiply({w_vol}, multiply(-1, ts_rank({VOL20_EXPR}, 20))))"
    
    print(f"\n--- {name} ---")
    print(f"  权重: {w_d5}*d5 + {w_vol}*(-ts_rank(vol20,20))")
    
    sim_data = generate_alpha(
        regular=combo_expr,
        region="USA",
        universe="TOP3000",
        delay=1,
        decay=0,
        neutralization="SUBINDUSTRY",
        truncation=0.08,
        pasteurization="ON",
        test_period="P1Y6M",
    )
    
    sim_response = start_simulation(session, sim_data)
    result = simulation_progress(session, sim_response)
    
    if result["completed"]:
        alpha_result = result["result"]
        alpha_id = alpha_result["id"]
        print(f"  Alpha ID: {alpha_id}")
        print(f"  Sharpe: {alpha_result.get('is', {}).get('sharpe')}")
        print(f"  Fitness: {alpha_result.get('is', {}).get('fitness')}")
        print(f"  Turnover: {alpha_result.get('is', {}).get('turnover')}")
        
        time.sleep(10)
        sc_df = get_self_corr(session, alpha_id)
        if not sc_df.empty:
            max_sc = sc_df["alpha_max_self_corr"].iloc[0]
            print(f"  Max Self-Corr: {max_sc}")
        else:
            print(f"  Self-Corr: 空")
    else:
        print(f"  模拟失败")
    
    time.sleep(5)  # 间隔

# 3. 测试d5+volume_confirm with decay=0
print("\n" + "=" * 60)
print("3. 测试d5*ts_rank(volume,5) with decay=0")
print("=" * 60)

vol_confirm_expr = f"multiply({D5_EXPR}, ts_rank(volume, 5))"
sim_data = generate_alpha(
    regular=vol_confirm_expr,
    region="USA",
    universe="TOP3000",
    delay=1,
    decay=0,
    neutralization="SUBINDUSTRY",
    truncation=0.08,
    pasteurization="ON",
    test_period="P1Y6M",
)
sim_response = start_simulation(session, sim_data)
result = simulation_progress(session, sim_response)
if result["completed"]:
    alpha_result = result["result"]
    alpha_id = alpha_result["id"]
    print(f"  Alpha ID: {alpha_id}")
    print(f"  Sharpe: {alpha_result.get('is', {}).get('sharpe')}")
    print(f"  Fitness: {alpha_result.get('is', {}).get('fitness')}")
    print(f"  Turnover: {alpha_result.get('is', {}).get('turnover')}")
    time.sleep(10)
    sc_df = get_self_corr(session, alpha_id)
    if not sc_df.empty:
        max_sc = sc_df["alpha_max_self_corr"].iloc[0]
        print(f"  Max Self-Corr: {max_sc}")

print("\n验证完成！")