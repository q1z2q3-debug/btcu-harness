# WQB 因子提交检查报告

生成时间: 2026-07-21 00:20:03

## 总体结果

- 检查因子总数: 8
- 通过所有检查: 0 个
- 未通过: 8 个

## ❌ 未通过提交检查的因子

| 因子名称 | Alpha ID | Sharpe | Fitness | 换手 | 自相关性 | 失败项 |
|---------|----------|--------|---------|------|---------|--------|
| combo_raw_vol120_w7030_decay10 | akEvjnbW | 1.99 | 1.25 | 0.4702 | 0.9183 | 未知 |
| combo_d10_vol120_w8020 | O0xaOO91 | 2.24 | 1.34 | 0.5176 | 0.9687 | 未知 |
| alpha_021 | xAdqoYmb | 1.62 | 0.94 | 0.4507 | N/A | 未知 |
| reversal_5 | QPVxWaNK | 1.09 | 0.89 | 0.3067 | N/A | 未知 |
| hist_vol_120 | zqmxAwmR | 0.44 | 0.43 | 0.0316 | N/A | 未知 |
| alpha_005 | pwKmkoP3 | 0.96 | 1.23 | 0.0843 | N/A | 未知 |
| amihud_illiq | akE68vZ6 | 1.08 | 0.72 | 0.0216 | N/A | 未知 |
| alpha_021_decay5 | vRvgKm8A | 1.84 | 0.86 | 0.7452 | N/A | 未知 |

## 详细检查结果

### alpha_021 (xAdqoYmb)

- 状态: COMPLETED
- Sharpe: 1.62
- Fitness: 0.94
- 换手率: 0.4507
- 自相关性: None
- 错误: HTTP 403: {"is":{"checks":[{"name":"LOW_SHARPE","result":"PASS","limit":1.25,"value":1.62},{"name":"LOW_FITNESS","result":"FAIL","limit":1.0,"value":0.94},{"name":"LOW_TURNOVER","result":"PASS","limit":0.01,"va

### reversal_5 (QPVxWaNK)

- 状态: COMPLETED
- Sharpe: 1.09
- Fitness: 0.89
- 换手率: 0.3067
- 自相关性: None
- 错误: HTTP 403: {"is":{"checks":[{"name":"LOW_SHARPE","result":"FAIL","limit":1.25,"value":1.09},{"name":"LOW_FITNESS","result":"FAIL","limit":1.0,"value":0.89},{"name":"LOW_TURNOVER","result":"PASS","limit":0.01,"va

### hist_vol_120 (zqmxAwmR)

- 状态: COMPLETED
- Sharpe: 0.44
- Fitness: 0.43
- 换手率: 0.0316
- 自相关性: None
- 错误: HTTP 403: {"is":{"checks":[{"name":"LOW_SHARPE","result":"FAIL","limit":1.25,"value":0.44},{"name":"LOW_FITNESS","result":"FAIL","limit":1.0,"value":0.43},{"name":"LOW_TURNOVER","result":"PASS","limit":0.01,"va

### alpha_005 (pwKmkoP3)

- 状态: COMPLETED
- Sharpe: 0.96
- Fitness: 1.23
- 换手率: 0.0843
- 自相关性: None
- 错误: HTTP 403: {"is":{"checks":[{"name":"LOW_SHARPE","result":"FAIL","limit":1.25,"value":0.96},{"name":"LOW_FITNESS","result":"PASS","limit":1.0,"value":1.23},{"name":"LOW_TURNOVER","result":"PASS","limit":0.01,"va

### amihud_illiq (akE68vZ6)

- 状态: COMPLETED
- Sharpe: 1.08
- Fitness: 0.72
- 换手率: 0.0216
- 自相关性: None
- 错误: HTTP 403: {"is":{"checks":[{"name":"LOW_SHARPE","result":"FAIL","limit":1.25,"value":1.08},{"name":"LOW_FITNESS","result":"FAIL","limit":1.0,"value":0.72},{"name":"LOW_TURNOVER","result":"PASS","limit":0.01,"va

### alpha_021_decay5 (vRvgKm8A)

- 状态: COMPLETED
- Sharpe: 1.84
- Fitness: 0.86
- 换手率: 0.7452
- 自相关性: None
- 错误: HTTP 403: {"is":{"checks":[{"name":"LOW_SHARPE","result":"PASS","limit":1.25,"value":1.84},{"name":"LOW_FITNESS","result":"FAIL","limit":1.0,"value":0.86},{"name":"LOW_TURNOVER","result":"PASS","limit":0.01,"va

### combo_raw_vol120_w7030_decay10 (akEvjnbW)

- 状态: COMPLETED
- Sharpe: 1.99
- Fitness: 1.25
- 换手率: 0.4702
- 自相关性: 0.9183
- 错误: HTTP 201: 

### combo_d10_vol120_w8020 (O0xaOO91)

- 状态: COMPLETED
- Sharpe: 2.24
- Fitness: 1.34
- 换手率: 0.5176
- 自相关性: 0.9687
- 错误: HTTP 403: {"is":{"checks":[{"name":"LOW_SHARPE","result":"PASS","limit":1.25,"value":2.24},{"name":"LOW_FITNESS","result":"PASS","limit":1.0,"value":1.34},{"name":"LOW_TURNOVER","result":"PASS","limit":0.01,"va
