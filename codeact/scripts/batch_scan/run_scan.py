#!/usr/bin/env python3
"""逐个提交60个因子，等待并发槽释放，保存结果"""
import sys, os, requests, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ace_lib'))
import ace_lib
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

print(f'共 {len(expressions)} 个表达式')

results = []
s = requests.Session()
s.trust_env = False

for i, (expr, name) in enumerate(zip(expressions, names)):
    # 重新认证
    s.auth = (email, password)
    s.post(brain_api + 'authentication')
    
    sim_data = {'type':'REGULAR','settings':{'instrumentType':'EQUITY','region':'USA','universe':'TOP3000','delay':1,'decay':0,'neutralization':'SUBINDUSTRY','truncation':0.08,'pasteurization':'ON','testPeriod':'P1Y6M','unitHandling':'VERIFY','nanHandling':'OFF','maxTrade':'OFF','language':'FASTEXPR','visualization':False},'regular':expr}
    
    success = False
    for attempt in range(20):
        r = s.post(brain_api + 'simulations', json=sim_data, timeout=10)
        if r.status_code == 201:
            loc = r.headers.get('Location', '')
            for poll in range(60):
                r2 = s.get(loc, timeout=10)
                if r2.status_code == 200:
                    d = r2.json()
                    alpha = d.get('alpha')
                    if alpha:
                        r3 = s.get(brain_api + 'alphas/' + alpha, timeout=10)
                        if r3.status_code == 200:
                            ad = r3.json()
                            t = ad.get('train', {}); te = ad.get('test', {})
                            results.append({'name':name,'alpha_id':alpha,'train_sharpe':t.get('sharpe'),'test_sharpe':te.get('sharpe'),'train_fitness':t.get('fitness'),'test_fitness':te.get('fitness'),'train_dd':t.get('drawdown'),'test_dd':te.get('drawdown')})
                            print(f'[{i+1}/{len(expressions)}] {name:5s} S={te.get("sharpe","?")} F={te.get("fitness","?")}')
                        success = True
                        break
                    retry = r2.headers.get('Retry-After', 5)
                    time.sleep(float(retry) if retry else 5)
            break
        elif r.status_code == 429:
            time.sleep(60)
        else:
            print(f'[{i+1}] {name}: {r.status_code} {r.text[:100]}')
            break
    
    if not success:
        print(f'[{i+1}] {name}: 失败')
    
    # 等60秒再下一个
    if i < len(expressions) - 1:
        time.sleep(60)

print(f'\n完成: {len(results)}/{len(expressions)}')
sorted_r = sorted(results, key=lambda x: x.get('test_sharpe') or 0, reverse=True)
print('\n=== Top 15 ===')
for i, r in enumerate(sorted_r[:15]):
    print(f'  {i+1}. {r["name"]:5s} S_train={r["train_sharpe"]:.2f} S_test={r["test_sharpe"]:.2f}')

out = os.path.join(expr_dir, '..', 'output', 'scan_all_results.json')
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, 'w') as f:
    json.dump(results, f, indent=2, default=str)
print(f'结果已保存: {out}')
