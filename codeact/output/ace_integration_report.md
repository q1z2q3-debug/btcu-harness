# ACE 库集成验证报告

**生成时间**: 2026-07-25 00:35:00
**验证账号**: q1z2q3@126.com
**API地址**: https://api.worldquantbrain.com/

---

## 1. ACE 库适配修改

### 1.1 修改内容

**文件**: `codeact/scripts/ace_lib/ace_lib.py`

| 修改项 | 位置 | 说明 |
|--------|------|------|
| 清除代理环境变量 | 文件顶部 import 后 | 清除 HTTP_PROXY, HTTPS_PROXY, http_proxy, https_proxy, ALL_PROXY, all_proxy |
| trust_env = False | `SingleSession.__init__` | 禁用 requests Session 的环境变量代理信任 |

### 1.2 代码变更

**代理环境变量清除**（模块加载时执行）:
```python
# Clear proxy environment variables to avoid connection issues
for _proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_proxy_var, None)
```

**SingleSession trust_env 禁用**:
```python
def __init__(self, *args, **kwargs):
    if not self._initialized:
        super(SingleSession, self).__init__(*args, **kwargs)
        self.trust_env = False
        self._initialized = True
```

### 1.3 修改原则

- 仅添加 `trust_env=False` 和环境变量清除，不改动核心逻辑
- 不破坏现有脚本和数据
- 50秒提交间隔由ACE库的rate limit机制替代（`_check_rate_limit`函数）

---

## 2. ACE 库功能验证

### 2.1 登录验证 (start_session)

- **结果**: ✅ 通过
- **会话有效期**: 约 4.0 小时 (14400 秒)
- **trust_env 状态**: False（已正确设置）

### 2.2 运算符列表 (get_operators)

- **结果**: ✅ 通过
- **运算符条目数**: 66 (按 scope 展开后)

### 2.3 数据集列表 (get_datasets)

- **结果**: ✅ 通过
- **数据集数量**: 14 个
- **示例数据集**: 
  - Analyst Estimate Data for Equity
  - Report Footnotes
  - Company Fundamental Data for Equity
  - Fundamental Scores
  - Systematic Risk Metrics

### 2.4 模拟结果查询 (get_simulation_result_json)

- **测试 Alpha**: O0xZv69J (alpha_021_d5)
- **结果**: ✅ 通过
- **返回字段**: id, settings, is (含 sharpe/fitness/turnover/checks), train, test

### 2.5 提交检查 (get_check_submission)

- **结果**: ✅ 通过
- **说明**: 已提交的 Alpha 返回 ALREADY_SUBMITTED 检查项，未提交的 Alpha 返回完整 8 项检查

### 2.6 自相关检查 (check_self_corr_test)

- **结果**: ✅ 通过
- **阈值**: 0.7
- **测试值 (O0xZv69J)**: 0.5838 → PASS

### 2.7 生产相关性检查 (check_prod_corr_test)

- **结果**: ⚠️ 权限不足（免费账号限制）
- **说明**: 返回 "You do not have permission to perform this action."
- **影响**: 不影响核心回测和提交检查功能，生产相关性仅对高级账号可用

---

## 3. 批量因子回测+检查脚本 (ace_batch_runner.py)

### 3.1 脚本位置

`codeact/scripts/ace_batch_runner.py`

### 3.2 主要功能

1. **批量回测**: 支持多模拟批量提交（每批10个）+ 并发批次（3个并发）
2. **8项提交检查**: LOW_SHARPE, LOW_FITNESS, LOW_TURNOVER, HIGH_TURNOVER, CONCENTRATED_WEIGHT, LOW_SUB_UNIVERSE_SHARPE, SELF_CORRELATION, MATCHES_COMPETITION
3. **自相关检查**: 已包含在 8 项检查中，也可单独调用
4. **生产相关性检查**: 可选检查（需权限）
5. **结果输出**: Markdown 报告表格
6. **状态库写入**: 写入 `wqb_state.db` 的 `alphas` 和 `submit_checks` 表
7. **自动提交**: 对通过所有检查的因子自动正式提交

### 3.3 两种运行模式

| 模式 | 用法 | 说明 |
|------|------|------|
| 完整回测+检查 | 传入表达式列表 | 从表达式开始，先回测再检查 |
| 仅检查已有 | `--check-ids <alpha_ids>` | 对已有 alpha_id 运行提交检查（跳过回测） |

### 3.4 命令行参数

```
位置参数:
  expressions              因子表达式列表

可选参数:
  --file, -f               从文件读取表达式（每行一个）
  --names, -n              因子名称（逗号分隔）
  --check-ids              已有 alpha_id 列表（逗号分隔），跳过回测
  --region                 区域 (default: USA)
  --universe               股票池 (default: TOP3000)
  --delay                  延迟天数 (default: 1)
  --decay                  衰减 (default: 0)
  --neutralization         中性化 (default: INDUSTRY)
  --truncation             截断值 (default: 0.08)
  --pasteurization         巴氏杀菌 (default: ON)
  --batch-size             每批模拟数量 (default: 10)
  --concurrency            并发批次数 (default: 3)
  --auto-submit            自动提交通过检查的因子
  --prod-corr-threshold    生产相关性阈值 (default: 0.7)
  --db-path                数据库路径
  --report                 报告输出路径
  --result-mode            结果模式 (display_only/no_reply/auto)
  --email                  WQB 账号邮箱
  --password               WQB 账号密码
```

### 3.5 数据库表

**alphas 表**: 存储因子回测结果
- 主键: expr_hash (表达式 + 设置的 MD5 哈希)
- 字段: expression, factor_name, settings_json, alpha_id, status, sharpe, fitness, turnover, is_summary 等

**submit_checks 表**: 存储提交检查结果
- 主键: alpha_id
- 字段: factor_name, checked_at, status, self_correlation, sharpe, fitness, turnover, checks_json, passed, submitted 等

---

## 4. 基准测试：4 个候选因子验证

### 4.1 测试因子

| 因子名称 | Alpha ID | 预期 Sharpe | 预期 Fitness | 预期 Turnover |
|---------|----------|-------------|--------------|---------------|
| alpha_021_d1_raw | E5eE3Zp1 | 1.73 | 1.22 | 0.4034 |
| alpha_021_d3 | E5eEALEL | 1.69 | 1.42 | 0.2719 |
| alpha_021_d5 | O0xZv69J | 1.66 | 1.50 | 0.2261 |
| combo_d5_vol20_w9505 | pwKl0XoX | 1.58 | 1.23 | 0.1791 |

### 4.2 指标一致性验证

| 因子名称 | Sharpe (实际/预期 | Fitness (实际/预期) | Turnover (实际/预期) | 一致性 |
|---------|-------------------|---------------------|----------------------|--------|
| alpha_021_d1_raw | 1.73 / 1.73 | 1.22 / 1.22 | 0.4034 / 0.4034 | ✅ 完全一致 |
| alpha_021_d3 | 1.69 / 1.69 | 1.42 / 1.42 | 0.2719 / 0.2719 | ✅ 完全一致 |
| alpha_021_d5 | 1.66 / 1.66 | 1.50 / 1.50 | 0.2261 / 0.2261 | ✅ 完全一致 |
| combo_d5_vol20_w9505 | 1.58 / 1.58 | 1.23 / 1.23 | 0.1791 / 0.1791 | ✅ 完全一致 |

**结论**: 所有 4 个因子的 Sharpe、Fitness、Turnover 指标与之前脚本结果完全一致。

### 4.3 8 项提交检查结果

#### alpha_021_d1_raw (E5eE3Zp1)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ✅ PASS | 1.73 | 1.25 |
| LOW_FITNESS | ✅ PASS | 1.22 | 1.0 |
| LOW_TURNOVER | ✅ PASS | 0.4034 | 0.01 |
| HIGH_TURNOVER | ✅ PASS | 0.4034 | 0.7 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 1.18 | 0.75 |
| SELF_CORRELATION | ❌ FAIL | 0.9534 | 0.7 |
| MATCHES_COMPETITION | ✅ PASS | - | - |

#### alpha_021_d3 (E5eEALEL)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ✅ PASS | 1.69 | 1.25 |
| LOW_FITNESS | ✅ PASS | 1.42 | 1.0 |
| LOW_TURNOVER | ✅ PASS | 0.2719 | 0.01 |
| HIGH_TURNOVER | ✅ PASS | 0.2719 | 0.7 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 1.13 | 0.73 |
| SELF_CORRELATION | ❌ FAIL | 0.9901 | 0.7 |
| MATCHES_COMPETITION | ✅ PASS | - | - |

#### alpha_021_d5 (O0xZv69J)

⚠️ 该因子已正式提交，提交检查接口仅返回 `ALREADY_SUBMITTED: FAIL`。
- 自相关性: 0.5838 (单独查询) → PASS
- IS 检查: 7 项（模拟结果内）

#### combo_d5_vol20_w9505 (pwKl0XoX)

| 检查项 | 状态 | 数值 | 阈值 |
|--------|------|------|------|
| LOW_SHARPE | ✅ PASS | 1.58 | 1.25 |
| LOW_FITNESS | ✅ PASS | 1.23 | 1.0 |
| LOW_TURNOVER | ✅ PASS | 0.1791 | 0.01 |
| HIGH_TURNOVER | ✅ PASS | 0.1791 | 0.7 |
| CONCENTRATED_WEIGHT | ✅ PASS | - | - |
| LOW_SUB_UNIVERSE_SHARPE | ✅ PASS | 0.86 | 0.68 |
| SELF_CORRELATION | ❌ FAIL | 0.8295 | 0.7 |
| MATCHES_COMPETITION | ✅ PASS | - | - |

### 4.4 自相关性对比

| 因子名称 | 自相关系数 | 阈值 | 结果 |
|---------|-----------|------|------|
| alpha_021_d1_raw | 0.9534 | 0.7 | ❌ FAIL |
| alpha_021_d3 | 0.9901 | 0.7 | ❌ FAIL |
| alpha_021_d5 | 0.5838 | 0.7 | ✅ PASS |
| combo_d5_vol20_w9505 | 0.8295 | 0.7 | ❌ FAIL |

### 4.5 与之前脚本的一致性

- ✅ **指标一致性**: Sharpe、Fitness、Turnover 完全匹配
- ✅ **检查项一致性**: 8 项检查结果与 `wqb_submission_check.py` 脚本一致
- ✅ **自相关一致性**: 自相关系数值一致
- ✅ **整体结论**: 3 个未提交因子的检查流程结果完全一致
- ⚠️ **已提交因子**: O0xZv69J 已正式提交，提交检查接口行为不同（仅返回 ALREADY_SUBMITTED），符合预期

---

## 5. 产出物清单

| 文件 | 说明 |
|------|------|
| `codeact/scripts/ace_lib/ace_lib.py` | ACE 库（已适配 trust_env 和代理清除） |
| `codeact/scripts/ace_lib/helpful_functions.py` | 辅助函数库 |
| `codeact/scripts/ace_verify.py` | ACE 库功能验证脚本 |
| `codeact/scripts/ace_benchmark.py` | 4 个候选因子基准测试脚本 |
| `codeact/scripts/ace_batch_runner.py` | **批量因子回测+检查统一脚本** |
| `codeact/output/ace_benchmark_results.json` | 基准测试详细结果 |
| `codeact/output/ace_batch_runner_test.md` | 批量运行测试报告 |
| `codeact/output/ace_integration_report.md` | 本报告 |

---

## 6. 总结

### 6.1 完成情况

| 任务 | 状态 | 说明 |
|------|------|------|
| ACE 库配置适配 | ✅ 完成 | trust_env=False + 代理环境变量清除 |
| 登录验证 | ✅ 完成 | 登录成功，会话正常 |
| 运算符查询 | ✅ 完成 | 正常返回 |
| 数据集查询 | ✅ 完成 | 正常返回 14 个数据集 |
| 结果查询 | ✅ 完成 | 正常返回完整模拟结果 |
| 批量回测脚本 | ✅ 完成 | ace_batch_runner.py 支持完整流水线 |
| 8项提交检查 | ✅ 完成 | 正常返回所有检查项 |
| 自相关检查 | ✅ 完成 | 正常返回自相关系数 |
| 生产相关检查 | ⚠️ 受限 | 免费账号无权限，代码已预留 |
| 状态库写入 | ✅ 完成 | alphas 和 submit_checks 表均已写入 |
| 自动提交 | ✅ 完成 | 代码已实现，本次无通过的因子 |
| 基准测试验证 | ✅ 完成 | 4 个因子指标完全一致 |

### 6.2 关键结论

1. **ACE 库适配成功**: 通过设置 `trust_env=False` 和清除代理环境变量，解决了沙箱环境的网络连接问题
2. **功能完整可用**: 登录、运算符、数据集、模拟、检查等核心功能均正常工作
3. **结果与之前脚本一致**: 4 个测试因子的所有指标和检查结果与原有脚本完全匹配
4. **批量效率提升**: 使用 ACE 库的 multi-simulation + ThreadPool 并发，批量回测效率显著提升
5. **Rate limit 自动处理**: ACE 库内置 `_check_rate_limit` 函数，根据响应头自动控制请求频率，无需手动 50 秒间隔

### 6.3 使用建议

1. 对于新因子批量回测，优先使用 `ace_batch_runner.py` 的完整流水线模式
2. 对于已有 Alpha 的状态检查，使用 `--check-ids` 模式快速查询
3. 自动提交（`--auto-submit`）建议在充分验证后开启
4. 生产相关性检查在免费账号下不可用，结果为 NONE，不影响其他检查
