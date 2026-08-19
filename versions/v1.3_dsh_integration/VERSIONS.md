# BTCU Harness Version Archive

**Policy**: All historical versions are preserved. Never delete past code.

| Version | Commit | Date | Description | Archive |
|---|---|---|---|---|
| **v0.2** | `47ce720` | 2024-11 | BTCU Harness v0.2: Balanced Ternary Cognitive Unit Harness | Git tag |
| **v0.3** | `7481949` | 2025-01 | NLP自我层+增强第三选择+认知轨迹+模式学习+持久化+认知气候 | `versions/v0.3_core/` |
| **v1.0** | `5e897b0` | 2025-03 | 生产级升级 - 类型修复/日志/性能/CLI/CI/集成测试 | Git tag |
| **v1.1** | `9ae8c56` | 2025-06 | Phase 1: multi-LLM/MongoDB/REST API/Docker/Quickstart | `versions/v1.1_mcp_base/` |
| **v1.1b** | `9f05e4d` | 2025-07 | Phase 2: benchmark suite + token economy simulation | Git tag |
| **v1.1c** | `d8699a2` | 2025-08 | BTCU Harness v1.0 academic paper (IEEE format) | Git tag |
| **v1.1d** | `f50cd49` | 2026-08-15 | LangChain 1.x middleware + MCP Server architecture | `versions/v1.0_langchain_mcp/` |
| **v1.2** | `4469ab5` | 2026-08-15 | Dual-System Cognitive Architecture (System 1 / System 2) | `versions/v1.2_dual_system/` |
| **v1.2c** | `0fa29ab` | 2026-08-16 | BTCU Cognitive Civilization Theory + version archives | `versions/v1.2_civilization/` |
| **v1.2.1** | `98a24c7` | 2026-08-19 | 双系统 + 永久版本存档（chore: version 1.2.1） | Git tag |
| **v1.3** | *(this commit)* | 2026-08-19 | DeepSeek Harness 融合 - agent preset（btcu.mjs JS 端口）+ vendored reference + 版本一致性修正 | `versions/v1.3_dsh_integration/` |

## Version Archive Directories

```
versions/
  v0.3_core/              # 核心认知架构（19683状态空间、模式学习、认知气候）
  v1.0_langchain_mcp/      # LangChain中间件 + MCP Server v1.1.0
  v1.1_mcp_base/           # MCP Server基础版（基础Tools/Resources/Prompts）
  v1.2_dual_system/        # 双系统认知架构（System 1/2、认知防御、审计）
  v1.2_civilization/       # 认知文明论 + 完整版本存档
  v1.3_dsh_integration/    # DeepSeek Harness 融合（integrations/deepseek-harness/ 快照）
```

## How to Access a Specific Version

```bash
# Via Git checkout
git checkout <commit-hash>

# Via archive directory
cd versions/v1.2_dual_system/
# Full source code at that commit is preserved here

# Create a new archive for any commit
git archive --format=tar <commit> | tar -x -C versions/v<version>/
```

## Current Version

**v1.3** — DeepSeek Harness 融合版（Dual-System + DSH Integration）

- 在 v1.2.1 双系统架构之上，新增 DeepSeek Harness 融合：
  `integrations/deepseek-harness/`（agent preset：`btcu.mjs` JS 端口 + 六个
  `btcu_*` 工具 + 双系统人设协议），Python 参考实现随仓库存档。
- System 1 (Fast): Pattern library with exact/k-NN/fuzzy matching
- System 2 (Slow): LLM-based deliberation with audit（DSH 中 System 2 即模型本身）
- Cognitive Safety Guard: ε-exploration, rigidity detection, feedback traps
- MCP Server v1.2: 7 Tools, 6 Resources, 2 Prompts
- Python 测试: 336 passed, 1 skipped；DSH preset 对拍 56 断言；token 增量实测 +1,258/请求
- 版本一致性修正：`__init__.__version__` 0.2.0 → 1.3.0（此前与 pyproject 不同步）；历史版本补 git tags

## Philosophy

> "每个版本都是认知进化的一个阶段，删除旧版本就是删除进化历史。"
> 
> BTCU的认知空间是逐步积累的智能资产。v0.3的朴素投影 → v1.0的工程化 → v1.1的协议化 → v1.2的双系统化，每一层都建立在前一层之上。
> 
> 保留所有版本，就像保留所有认知记忆。这是BTCU作为"文明层"的基本承诺。

