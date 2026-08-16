# Zenodo 发表指南：BTCU 论文

> 本指南帮助你将在 GitHub 上准备好的 BTCU 学术论文发表到 Zenodo 平台，获取 DOI。
>
> **准备状态**：✓ 论文已撰写完成，✓ 元数据已配置，✓ 文件已推送到 GitHub
>
> **下一步**：按照以下步骤完成 Zenodo 上传

---

## 发表前确认清单

- [x] 论文正文已完成：`docs/academic_paper/BTCU_Cognitive_Architecture_Paper.md`
- [x] 补充材料已准备：推导报告、对比验证、新发现
- [x] 元数据文件已配置：`docs/academic_paper/ZENODO_METADATA.json`
- [x] 所有文件已推送到 GitHub
- [ ] Zenodo 账户注册/登录
- [ ] 上传文件
- [ ] 填写元数据
- [ ] 发布并获得 DOI

---

## 第一步：访问 Zenodo

1. 打开浏览器，访问：**https://zenodo.org**
2. 点击右上角 **"Log in"** 或 **"Sign up"**
3. 推荐用 **GitHub 账户** 直接登录（最简单）
4. 登录后进入个人仪表盘

---

## 第二步：创建新上传

1. 点击 **"Upload"** → **"New Upload"**
2. 进入上传界面

---

## 第三步：上传文件

### 主要文件（必须上传）

**论文正文**（选择以下一种格式）：

**选项 A - Markdown 格式**（推荐，保留可编辑性）：
- 文件路径：`docs/academic_paper/BTCU_Cognitive_Architecture_Paper.md`
- 文件大小：约 27 KB
- 优点：可被 GitHub 渲染，便于社区审阅和协作

**选项 B - PDF 格式**（如果需要）：
- 说明：由于环境限制，当前没有直接生成 PDF
- 如果需要 PDF，可以：
  - 将 Markdown 复制到在线 Markdown 转 PDF 工具
  - 或使用 VS Code + Markdown PDF 插件
  - 或稍后用本地 LaTeX 环境生成

### 补充材料（建议上传）

| 文件名 | 内容描述 |
|---|---|
| `derivation_report.md` | 平衡三进制常数推导的完整预演报告 |
| `paper_vs_preliminary_comparison.md` | 预演与实际论文的对比验证 |
| `new_discoveries.md` | 从验证过程中产生的新洞察 |
| `ternary_constants.py` | Python 数值验证脚本（可运行） |

---

## 第四步：填写元数据

Zenodo 上传界面会要求填写以下信息。我已经为你准备好完整的元数据，直接复制粘贴即可：

### 基本信息

| 字段 | 填写内容 |
|---|---|
| **Upload type** | Publication → Working paper |
| **Title** | BTCU: A Dual-System Cognitive Architecture with Emergent Soul Layer for AI Agents |
| **Authors** | BTCU Project (Primary: q1z2q3) |
| **Description** | （见下方完整描述） |
| **Keywords** | cognitive architecture, balanced ternary, dual-system cognition, emergent personality, AI soul layer, pattern matching, System 1/2, philosophical AI, cognitive computing, agent architecture |
| **License** | Creative Commons Attribution 4.0 International (CC-BY-4.0) |

### 完整描述（复制到 Description 字段）

```
We present BTCU (Balanced Ternary Cognitive Universe), a dual-system cognitive architecture for AI agents that bridges structured discrete state spaces with emergent behavioral personalities. Building upon the mathematical necessity of balanced ternary {-1, 0, +1} as the minimal integer state space for directed transitions (Ball, 2026), BTCU instantiates a 9-dimensional cognitive coordinate system yielding 19,683 distinct cognitive states. The architecture implements a Kahneman-inspired dual-process model: System 1 provides rapid pattern-matching cognition (< 5ms, 0 tokens) while System 2 performs deep reflective reasoning (200-500ms) via LLM integration. A novel "soul layer" emerges from accumulated experience patterns, endowing agents with persistent behavioral styles, value orientations, and intrinsic wisdom drawn from classical philosophical traditions (Yin Fu Jing, Heart Sutra, Tao Te Ching). We validate the architecture through 322 automated tests achieving 100% pass rate, benchmark demonstrations showing 97% cognitive consistency scores, and a token economy simulation demonstrating 60% cost reduction through pattern reuse. BTCU represents a shift from tool-based AI augmentation to civilization-layer cognitive infrastructure, where the architecture is constitutive rather than additive to agent intelligence.
```

### 相关标识符（Related Identifiers）

在 "Related/alternate identifiers" 部分添加：

| 关系 | 标识符 | 资源类型 |
|---|---|---|
| isSupplementedBy | https://github.com/q1z2q3-debug/btcu-harness | Software |
| isSupplementedBy | https://pypi.org/project/btcu-harness/ | Other |
| references | 10.5281/zenodo.18810282 | Publication → Journal article |
| references | 10.5281/zenodo.18806015 | Publication → Journal article |
| references | 10.5281/zenodo.18797375 | Publication → Journal article |

### 社区（Communities）

添加以下社区：
- `ai`（人工智能）
- `cogsci`（认知科学）
- （可选）`cs`（计算机科学）

---

## 第五步：发布设置

1. **Access right**: 选择 **"Open Access"**（开放获取）
2. **Embargo**: 选择 **"No"**（不设置 embargo）
3. **Reserve DOI**: 点击 **"Reserve DOI"** 按钮预留 DOI（可选）

---

## 第六步：发布

1. 确认所有信息填写正确
2. 勾选 **"I confirm that I have read and accept the Zenodo policies"**
3. 点击 **"Publish"** 按钮
4. Zenodo 会立即分配一个 DOI（格式：10.5281/zenodo.XXXXXXX）

---

## 发布后操作

### 获取 DOI

发布后，Zenodo 会显示：
- **DOI**: 10.5281/zenodo.XXXXXXX
- **URL**: https://doi.org/10.5281/zenodo.XXXXXXX

### 更新 GitHub 仓库

获取 DOI 后，请更新以下文件：

1. **README.md**: 在论文引用部分添加 DOI 链接
2. **ZENODO_METADATA.json**: 更新实际的 DOI 编号
3. **BTCU_Cognitive_Architecture_Paper.md**: 在页眉添加 DOI

### 引用格式

发表后，BTCU 论文可以这样引用：

**APA 格式**:
```
BTCU Project. (2026). BTCU: A dual-system cognitive architecture with emergent soul layer for AI agents. Zenodo. https://doi.org/10.5281/zenodo.XXXXXXX
```

**BibTeX 格式**:
```bibtex
@misc{btcu2026,
  author = {{BTCU Project}},
  title = {BTCU: A Dual-System Cognitive Architecture with Emergent Soul Layer for AI Agents},
  year = {2026},
  publisher = {Zenodo},
  doi = {10.5281/zenodo.XXXXXXX},
  url = {https://doi.org/10.5281/zenodo.XXXXXXX}
}
```

---

## 可选：生成 PDF 版本

如果你希望同时提供 PDF 版本，有以下几种方式：

### 方式一：在线转换（最简单）
1. 打开 https://md2pdf.netlify.app/ 或类似工具
2. 粘贴 Markdown 内容
3. 下载 PDF
4. 重新上传 PDF 到 Zenodo（可以补充到已发布的记录中）

### 方式二：VS Code + 插件
1. 安装 "Markdown PDF" 插件
2. 打开 `BTCU_Cognitive_Architecture_Paper.md`
3. 右键 → "Markdown PDF: Export (pdf)"

### 方式三：Pandoc（命令行）
```bash
# 需要安装 pandoc 和 LaTeX
pandoc BTCU_Cognitive_Architecture_Paper.md \
  -o BTCU_Cognitive_Architecture_Paper.pdf \
  --pdf-engine=xelatex \
  -V geometry:margin=2.5cm \
  -V fontsize=11pt
```

---

## 常见问题

**Q: Zenodo 是免费的吗？**
A: 是的，Zenodo 由 CERN 支持，对学术成果永久免费存储。

**Q: DOI 是永久的吗？**
A: 是的，DOI 一旦分配就永久有效，即使文件更新，DOI 也不会改变。

**Q: 可以更新已发布的记录吗？**
A: 可以。Zenodo 支持版本控制，你可以上传新版本，DOI 保持不变，但会获得一个新的版本号。

**Q: 需要等待审核吗？**
A: 不需要。Zenodo 是开放存取平台，上传后立即发布，无需同行评审。

**Q: 可以设置 embargo（延迟公开）吗？**
A: 可以，但当前论文建议立即公开，以加速学术交流和社区反馈。

---

## 联系支持

如果在 Zenodo 上传过程中遇到问题：
- Zenodo 帮助中心：https://help.zenodo.org/
- GitHub Issues：https://github.com/q1z2q3-debug/btcu-harness/issues
- 邮件：q1z2q3@126.com

---

> **当前状态**：论文已完成，文件已推送到 GitHub，等待你完成 Zenodo 上传获取 DOI。
>
> 完成上传后，BTCU 项目将拥有正式的学术引用标识，可以被其他研究者引用和参考。
