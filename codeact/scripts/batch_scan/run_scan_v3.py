#!/usr/bin/env python3
"""v3: 更健壮，每完成一个保存中间结果，失败跳过继续下一个"""
import sys, os, requests, json, time, traceback

for v in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy'):
    os.environ.pop(v, None)

brain_api = 'https://api.worldquantbrain.com/'
email = 'q1z2q3@126.com'
password = 'W2025zq0118'

# 读表达式
expr_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(expr_dir, '..', 'output')
os.makedirs(output_dir, exist_ok=True)
results_file = os.path.join(output_dir, 'scan_all_results.json')
log_file = os.path.join(output_dir, 'scan_v3_output.log')

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

# 已完成结果（前14个）
results = [
    {'name':'A_1','train_sharpe':0.19,'test_sharpe':0.19,'train_fitness':0.06,'test_fitness':0.06},
    {'name':'A_2','train_sharpe':0.12,'test_sharpe':0.12,'train_fitness':0.03,'test_fitness':0.03},
    {'name':'A_3','train_sharpe':-0.09,'test_sharpe':-0.09,'train_fitness':-0.02,'test_fitness':-0.02},
    {'name':'A_4','train_sharpe':0.69,'test_sharpe':0.69,'train_fitness':0.11,'test_fitness':0.11},
    {'name':'A_5','train_sharpe':1.25,'test_sharpe':1.25,'train_fitness':0.29,'test_fitness':0.29},
    {'name':'A_6','train_sharpe':0.61,'test_sharpe':0.61,'train_fitness':0.15,'test_fitness':0.15},
    {'name':'A_7','train_sharpe':1.1,'test_sharpe':1.1,'train_fitness':0.42,'test_fitness':0.42},
    {'name':'A_8','train_sharpe':-1.23,'test_sharpe':-1.23,'train_fitness':-0.37,'test_fitness':-0.37},
    {'name':'A_9','train_sharpe':-0.15,'test_sharpe':-0.15,'train_fitness':-0.02,'test_fitness':-0.02},
    {'name':'A_10','train_sharpe':2.05,'test_sharpe':2.05,'train_fitness':1.29,'test_fitness':1.29},
    {'name':'A_11','train_sharpe':1.33,'test_sharpe':1.33,'train_fitness':0.23,'test_fitness':0.23},
    {'name':'A_12','train_sharpe':0.13,'test_sharpe':0.13,'train_fitness':0.01,'test_fitness':0.01},
    {'name':'A_13','train_sharpe':-0.61,'test_sharpe':-0.61,'train_fitness':-0.09,'test_fitness':-0.09},
    {'name':'A_14','train_sharpe':None,'test_sharpe':None,'train_fitness':None,'test_fitness':None,'status':'failed'},
]

done_names = {r['name'] for r in results}

def log(msg):
    print(msg, flush=True)
    with open(log_file, 'a') as f:
        f.write(msg + '\n')

def save_results():
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

def new_session():
    s = requests.Session()
    s.trust_env = False
    s.auth = (email, password)
    for attempt in range(5):
        try:
            r = s.post(brain_api + 'authentication', timeout=15)
            if r.status_code in (200, 201):
                return s
            elif r.status_code == 429:
                time.sleep(60)
            else:
                log(f'  认证失败: {r.status_code} {r.text[:100]}')
                time.sleep(30)
        except Exception as e:
            log(f'  认证异常: {e}')
            time.sleep(10)
    return None

log(f'开始扫描: 总{len(expressions)}个，已完成{len(done_names)}个，剩余{len(expressions)-len(done_names)}个')

s = new_session()
if not s:
    log('初始认证失败，退出')
    sys.exit(1)

total = len(expressions)
for i in range(total):
    name = names[i]
    expr = expressions[i]
    if name in done_names:
        continue
    
    # 每5个刷新一次session
    if (i + 1) % 5 == 0:
        log(f'  [刷新session]')
        s = new_session()
        if not s:
            log('刷新失败，继续用旧的')
    
    sim_data = {'type':'REGULAR','settings':{'instrumentType':'EQUITY','region':'USA','universe':'TOP3000','delay':1,'decay':0,'neutralization':'SUBINDUSTRY','truncation':0.08,'pasteurization':'ON','testPeriod':'P1Y6M','unitHandling':'VERIFY','nanHandling':'OFF','maxTrade':'OFF','language':'FASTEXPR','visualization':False},'regular':expr}
    
    success = False
    alpha_id = None
    
    for attempt in range(5):
        try:
            r = s.post(brain_api + 'simulations', json=sim_data, timeout=20)
            if r.status_code == 201:
                loc = r.headers.get('Location', '')
                # 轮询结果
                for poll in range(180):  # 最多等15分钟
                    time.sleep(5)
                    try:
                        r2 = s.get(loc, timeout=15)
                        if r2.status_code == 200:
                            d = r2.json()
                            alpha = d.get('alpha')
                            if alpha:
                                alpha_id = alpha
                                break
                        elif r2.status_code == 401:
                            s = new_session()
                            if not s:
                                break
                    except Exception as pe:
                        continue
                break
            elif r.status_code == 429:
                time.sleep(45)
            elif r.status_code == 401:
                s = new_session()
                time.sleep(5)
            elif r.status_code >= 400:
                log(f'[{i+1}/{total}] {name}: {r.status_code} {r.text[:200]}')
                break
        except Exception as e:
            log(f'[{i+1}/{total}] {name} attempt{attempt}: 异常 {e}')
            time.sleep(10)
    
    if alpha_id:
        # 获取详细统计
        for gattempt in range(3):
            try:
                r3 = s.get(brain_api + 'alphas/' + alpha_id, timeout=15)
                if r3.status_code == 200:
                    ad = r3.json()
                    t = ad.get('train', {}); te = ad.get('test', {})
                    results.append({'name':name,'alpha_id':alpha_id,
                        'train_sharpe':t.get('sharpe'),'test_sharpe':te.get('sharpe'),
                        'train_fitness':t.get('fitness'),'test_fitness':te.get('fitness'),
                        'train_dd':t.get('drawdown'),'test_dd':te.get('drawdown'),
                        'expression':expr, 'status':'ok'})
                    ts = te.get('sharpe','?'); tf = te.get('fitness','?')
                    log(f'[{i+1}/{total}] {name:5s} S={ts} F={tf}')
                    success = True
                    break
                elif r3.status_code == 401:
                    s = new_session()
            except Exception as ge:
                log(f'  获取统计异常: {ge}')
                time.sleep(5)
    
    if not success:
        results.append({'name':name,'expression':expr,'status':'failed'})
        log(f'[{i+1}/{total}] {name}: 失败，跳过')
    
    save_results()
    done_names.add(name)

log(f'\n完成: {len([r for r in results if r.get("status")=="ok"])}/{total}')
sorted_r = sorted([r for r in results if r.get('test_sharpe') is not None], key=lambda x: x.get('test_sharpe') or 0, reverse=True)
log('\n=== Top 15 ===')
for i, r in enumerate(sorted_r[:15]):
    ts = r.get('train_sharpe', 0) or 0
    tes = r.get('test_sharpe', 0) or 0
    tf = r.get('test_fitness', 0) or 0
    log(f'  {i+1}. {r["name"]:5s} S_train={ts:.2f} S_test={tes:.2f} F={tf:.2f}')

log('全部完成')
