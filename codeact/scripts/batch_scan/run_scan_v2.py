#!/usr/bin/env python3
"""继续扫描：跳过前9个已完成因子，一次登录复用session"""
import sys, os, requests, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ace_lib'))

for v in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy'):
    os.environ.pop(v, None)

brain_api = 'https://api.worldquantbrain.com/'
email = 'q1z2q3@126.com'
password = 'W2025zq0118'

# 读表达式
expr_dir = os.path.dirname(os.path.abspath(__file__))
expressions = []; names = []
for cat_file, cat_prefix in [
    ('expressions_category_A_volume.txt', 'A'),
    ('expressions_category_B_corr.txt', 'B'),
    ('expressions_category_C_nonlinear.txt', 'C'),
    ('expressions_category_D_price.txt', 'D')
]:
    with open(os.path.join(expr_dir, cat_file)) as f:
        lines = f.readlines()
    idx = 1
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        expressions.append(line)
        names.append(f'{cat_prefix}_{idx}')
        idx += 1

# 前9个已完成的结果
done = [
    {'name':'A_1','train_sharpe':0.19,'test_sharpe':0.19,'train_fitness':0.06,'test_fitness':0.06},
    {'name':'A_2','train_sharpe':0.12,'test_sharpe':0.12,'train_fitness':0.03,'test_fitness':0.03},
    {'name':'A_3','train_sharpe':-0.09,'test_sharpe':-0.09,'train_fitness':-0.02,'test_fitness':-0.02},
    {'name':'A_4','train_sharpe':0.69,'test_sharpe':0.69,'train_fitness':0.11,'test_fitness':0.11},
    {'name':'A_5','train_sharpe':1.25,'test_sharpe':1.25,'train_fitness':0.29,'test_fitness':0.29},
    {'name':'A_6','train_sharpe':0.61,'test_sharpe':0.61,'train_fitness':0.15,'test_fitness':0.15},
    {'name':'A_7','train_sharpe':1.1,'test_sharpe':1.1,'train_fitness':0.42,'test_fitness':0.42},
    {'name':'A_8','train_sharpe':-1.23,'test_sharpe':-1.23,'train_fitness':-0.37,'test_fitness':-0.37},
    {'name':'A_9','train_sharpe':-0.15,'test_sharpe':-0.15,'train_fitness':-0.02,'test_fitness':-0.02},
]
results = list(done)

s = requests.Session()
s.trust_env = False
s.auth = (email, password)
r = s.post(brain_api + 'authentication')
print(f'认证: {r.status_code}')
if r.status_code not in (200, 201):
    print(r.text)
    sys.exit(1)

# 每10个因子刷新一次认证，避免session过期
refresh_every = 10

start_idx = 9  # 从第10个开始（索引9）
total = len(expressions)
print(f'继续扫描: 从第{start_idx+1}个到第{total}个，共{total-start_idx}个')

for i in range(start_idx, total):
    expr = expressions[i]
    name = names[i]
    
    # 定期刷新认证
    if (i - start_idx) % refresh_every == 0 and i > start_idx:
        s.auth = (email, password)
        r = s.post(brain_api + 'authentication')
        print(f'  [刷新认证] {r.status_code}')
        if r.status_code == 429:
            time.sleep(60)
            s.auth = (email, password)
            s.post(brain_api + 'authentication')
    
    sim_data = {'type':'REGULAR','settings':{'instrumentType':'EQUITY','region':'USA','universe':'TOP3000','delay':1,'decay':0,'neutralization':'SUBINDUSTRY','truncation':0.08,'pasteurization':'ON','testPeriod':'P1Y6M','unitHandling':'VERIFY','nanHandling':'OFF','maxTrade':'OFF','language':'FASTEXPR','visualization':False},'regular':expr}
    
    success = False
    for attempt in range(30):
        try:
            r = s.post(brain_api + 'simulations', json=sim_data, timeout=15)
            if r.status_code == 201:
                loc = r.headers.get('Location', '')
                for poll in range(120):
                    time.sleep(5)
                    r2 = s.get(loc, timeout=10)
                    if r2.status_code == 200:
                        d = r2.json()
                        alpha = d.get('alpha')
                        if alpha:
                            r3 = s.get(brain_api + 'alphas/' + alpha, timeout=10)
                            if r3.status_code == 200:
                                ad = r3.json()
                                t = ad.get('train', {}); te = ad.get('test', {})
                                results.append({'name':name,'alpha_id':alpha,
                                    'train_sharpe':t.get('sharpe'),'test_sharpe':te.get('sharpe'),
                                    'train_fitness':t.get('fitness'),'test_fitness':te.get('fitness'),
                                    'train_dd':t.get('drawdown'),'test_dd':te.get('drawdown'),
                                    'expression':expr})
                                ts = te.get('sharpe','?'); tf = te.get('fitness','?')
                                print(f'[{i+1}/{total}] {name:5s} S={ts} F={tf}')
                                sys.stdout.flush()
                            success = True
                            break
                        # 还在运行，继续等
                    elif r2.status_code == 401:
                        # session过期，刷新
                        s.auth = (email, password)
                        s.post(brain_api + 'authentication')
                    else:
                        pass
                break
            elif r.status_code == 429:
                time.sleep(30)
            elif r.status_code == 401:
                s.auth = (email, password)
                s.post(brain_api + 'authentication')
                time.sleep(5)
            else:
                print(f'[{i+1}] {name}: {r.status_code} {r.text[:150]}')
                break
        except Exception as e:
            print(f'[{i+1}] {name}: 异常 {e}')
            time.sleep(10)
    
    if not success:
        print(f'[{i+1}] {name}: 失败')
        sys.stdout.flush()
    
    # 保存中间结果
    out = os.path.join(expr_dir, '..', 'output', 'scan_all_results.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as f:
        json.dump(results, f, indent=2, default=str)

print(f'\n完成: {len(results)}/{total}')
sorted_r = sorted(results, key=lambda x: x.get('test_sharpe') or 0, reverse=True)
print('\n=== Top 15 ===')
for i, r in enumerate(sorted_r[:15]):
    ts = r.get('train_sharpe', 0) or 0
    tes = r.get('test_sharpe', 0) or 0
    tf = r.get('test_fitness', 0) or 0
    print(f'  {i+1}. {r["name"]:5s} S_train={ts:.2f} S_test={tes:.2f} F={tf:.2f}')
