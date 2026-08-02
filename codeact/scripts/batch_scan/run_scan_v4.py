#!/usr/bin/env python3
"""v4: 单进程串行，打印进度，失败跳过"""
import sys, os, requests, json, time

for v in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy'):
    os.environ.pop(v, None)

brain_api = 'https://api.worldquantbrain.com/'
email = 'q1z2q3@126.com'
password = 'W2025zq0118'

expr_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(expr_dir, '..', 'output')
os.makedirs(output_dir, exist_ok=True)
results_file = os.path.join(output_dir, 'scan_all_results.json')

# 读所有表达式
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

# 已知结果
known = {
    'A_1': {'train_sharpe':0.19,'test_sharpe':0.19,'train_fitness':0.06,'test_fitness':0.06},
    'A_2': {'train_sharpe':0.12,'test_sharpe':0.12,'train_fitness':0.03,'test_fitness':0.03},
    'A_3': {'train_sharpe':-0.09,'test_sharpe':-0.09,'train_fitness':-0.02,'test_fitness':-0.02},
    'A_4': {'train_sharpe':0.69,'test_sharpe':0.69,'train_fitness':0.11,'test_fitness':0.11},
    'A_5': {'train_sharpe':1.25,'test_sharpe':1.25,'train_fitness':0.29,'test_fitness':0.29},
    'A_6': {'train_sharpe':0.61,'test_sharpe':0.61,'train_fitness':0.15,'test_fitness':0.15},
    'A_7': {'train_sharpe':1.1,'test_sharpe':1.1,'train_fitness':0.42,'test_fitness':0.42},
    'A_8': {'train_sharpe':-1.23,'test_sharpe':-1.23,'train_fitness':-0.37,'test_fitness':-0.37},
    'A_9': {'train_sharpe':-0.15,'test_sharpe':-0.15,'train_fitness':-0.02,'test_fitness':-0.02},
    'A_10': {'train_sharpe':1.08,'test_sharpe':2.05,'train_fitness':0.53,'test_fitness':1.29,'alpha_id':'RR1PopYb','is_sharpe':1.36,'is_fitness':0.73,'grade':'INFERIOR'},
    'A_11': {'train_sharpe':1.33,'test_sharpe':1.33,'train_fitness':0.23,'test_fitness':0.23},
    'A_12': {'train_sharpe':0.13,'test_sharpe':0.13,'train_fitness':0.01,'test_fitness':0.01},
    'A_13': {'train_sharpe':-0.61,'test_sharpe':-0.61,'train_fitness':-0.09,'test_fitness':-0.09},
    'A_14': {'train_sharpe':None,'test_sharpe':None,'status':'skip'},
}

results = []
done = set()
for n in names:
    if n in known:
        r = {'name': n, 'expression': expressions[names.index(n)]}
        r.update(known[n])
        results.append(r)
        done.add(n)

def save():
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

s = requests.Session()
s.trust_env = False
s.auth = (email, password)
s.post(brain_api + 'authentication', timeout=15)

total = len(expressions)
print(f'共{total}个，已完成{len(done)}个，剩余{total-len(done)}个', flush=True)

for i in range(total):
    name = names[i]
    expr = expressions[i]
    if name in done:
        continue
    
    # 每8个刷新认证
    idx_from_start = i - sum(1 for j in range(i) if names[j] in done)
    if idx_from_start > 0 and idx_from_start % 8 == 0:
        s.auth = (email, password)
        r = s.post(brain_api + 'authentication', timeout=15)
        print(f'  [刷新认证 {idx_from_start}] {r.status_code}', flush=True)
        if r.status_code == 429:
            time.sleep(55)
            s.auth = (email, password)
            s.post(brain_api + 'authentication', timeout=15)
    
    sim_data = {'type':'REGULAR','settings':{'instrumentType':'EQUITY','region':'USA','universe':'TOP3000','delay':1,'decay':0,'neutralization':'SUBINDUSTRY','truncation':0.08,'pasteurization':'ON','testPeriod':'P1Y6M','unitHandling':'VERIFY','nanHandling':'OFF','maxTrade':'OFF','language':'FASTEXPR','visualization':False},'regular':expr}
    
    alpha_id = None
    submitted = False
    
    for attempt in range(8):
        try:
            r = s.post(brain_api + 'simulations', json=sim_data, timeout=20)
            if r.status_code == 201:
                loc = r.headers.get('Location', '')
                submitted = True
                for poll in range(150):
                    time.sleep(5)
                    try:
                        r2 = s.get(loc, timeout=10)
                        if r2.status_code == 200:
                            d = r2.json()
                            a = d.get('alpha')
                            if a:
                                alpha_id = a
                                break
                        elif r2.status_code == 401:
                            s.auth = (email, password)
                            s.post(brain_api + 'authentication', timeout=15)
                    except:
                        pass
                break
            elif r.status_code == 429:
                time.sleep(45)
            elif r.status_code == 401:
                s.auth = (email, password)
                s.post(brain_api + 'authentication', timeout=15)
                time.sleep(3)
            elif r.status_code >= 400:
                print(f'[{i+1}/{total}] {name}: {r.status_code} {r.text[:150]}', flush=True)
                break
        except Exception as e:
            time.sleep(10)
    
    result = {'name': name, 'expression': expr}
    if alpha_id:
        try:
            r3 = s.get(brain_api + 'alphas/' + alpha_id, timeout=15)
            if r3.status_code == 200:
                ad = r3.json()
                t = ad.get('train', {}); te = ad.get('test', {}); isd = ad.get('is', {})
                result.update({
                    'alpha_id': alpha_id,
                    'train_sharpe': t.get('sharpe'), 'test_sharpe': te.get('sharpe'),
                    'train_fitness': t.get('fitness'), 'test_fitness': te.get('fitness'),
                    'train_dd': t.get('drawdown'), 'test_dd': te.get('drawdown'),
                    'is_sharpe': isd.get('sharpe'), 'is_fitness': isd.get('fitness'),
                    'grade': ad.get('grade'), 'status': 'ok'
                })
                is_checks = isd.get('checks', [])
                for c in is_checks:
                    if c.get('name') == 'SELF_CORRELATION':
                        result['sc_status'] = c.get('result')
                        if 'value' in c:
                            result['sc_value'] = c.get('value')
                ts = te.get('sharpe','?'); tf = te.get('fitness','?')
                g = ad.get('grade','?')
                print(f'[{i+1}/{total}] {name:5s} S={ts} F={tf} G={g}', flush=True)
            else:
                result['status'] = 'get_stats_failed'
                print(f'[{i+1}/{total}] {name}: 获取统计失败 {r3.status_code}', flush=True)
        except Exception as e:
            result['status'] = f'error: {e}'
            print(f'[{i+1}/{total}] {name}: 统计异常 {e}', flush=True)
    else:
        result['status'] = 'submit_failed'
        print(f'[{i+1}/{total}] {name}: 提交失败', flush=True)
    
    results.append(result)
    done.add(name)
    save()

print(f'\n=== 全部完成: {len([r for r in results if r.get("status")=="ok"])}/{total} ===', flush=True)
sorted_r = sorted([r for r in results if r.get('test_sharpe')], key=lambda x: x.get('test_sharpe') or 0, reverse=True)
print('\nTop 15:', flush=True)
for i, r in enumerate(sorted_r[:15]):
    ts = r.get('test_sharpe',0) or 0
    tf = r.get('test_fitness',0) or 0
    g = r.get('grade','?')
    sc = r.get('sc_status','?')
    print(f'  {i+1}. {r["name"]:5s} S={ts:.2f} F={tf:.2f} G={g} SC={sc}', flush=True)
