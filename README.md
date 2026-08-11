# CodeReview Harness

[English](README.en.md) · [简体中文](README.md)

基于自研轻量 **Agent Harness** 的自动化**代码审查与修复 Agent**——围绕约束机制、反馈回路、工作流控制、持续改进循环四大支柱（Harness Engineering）构建。

`crh review` 审查 git 仓库的工作区变更并输出结构化报告（AST 静态分析 + LLM 审查）；`crh fix` 通过人工审批的工作流应用修复，用编译 + 测试验证，失败自动回滚；`crh eval` 在注入 bug 的评估集上度量检出率/修复率。

## 亮点

- **Provider 无关的 Harness 内核**——Agent 循环（`harness/loop.py`）只认识消息、工具和 `LLMProvider` 协议。内置确定性 Mock 与 OpenAI/DeepSeek 兼容实现；`--static` 可完全离线运行。
- **治理层**（`governance/`）——敏感路径黑名单、只读判定、变更作用域强制（只允许修改 diff 涉及的文件）、三种权限模式、人工审批门（HITL）。
- **"先检查再下结论"约束**——审查模型必须至少调用一次工具才能出报告；未检查代码就产出报告会被判定为无效并打回重查。
- **反馈回路**——工具结果回灌循环；修复验证失败把错误信息回喂模型重试（有上限）；JSON 输出违反 schema 自动触发自我修复一轮。
- **显式工作流控制**（`workflow/`）——严格状态机（PLAN→REVIEW→PROPOSE→APPROVE→APPLY→VALIDATE→REPORT）、跨阶段步数预算、备份回滚。
- **评估闭环**（`eval/`）——注入 bug 的 fixture 仓库、检出率/修复率指标、失败案例 JSONL 回归日志。

详见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) 的支柱逐项映射。

## 环境要求

- Python ≥ 3.12 与 [uv](https://docs.astral.sh/uv/)
- 被审查的目录必须是 **git 仓库**（crh 审查的是 git 工作区变更）

## 安装与配置 API Key

```bash
uv sync --extra dev

# 全局安装 crh（任意目录可用）
uv tool install --editable .

# 配置一次 API Key —— crh 按以下优先级读取：
#   --api-key <key>            命令行参数
#   --env-file <path>          显式指定 .env 文件
#   API_KEY / OPENAI_API_KEY   环境变量
#   当前目录的 .env             项目级
#   ~/.crh/.env                用户级（推荐，全局生效）
mkdir -p ~/.crh && echo "API_KEY=sk-..." > ~/.crh/.env
```

新开的终端会自动读取配置。验证：`crh review --static`（离线，无需 key）或任意 LLM 命令会打印 `[crh] using API key from ...` 显示 key 来源。

## 快速开始

```bash
# 离线确定性审查（无需 API key）
crh review --repo /path/to/repo --static

# 完整 LLM 审查（默认走 DeepSeek）
crh review --repo /path/to/repo

# 审查 + 人工审批修复闭环（审批修复计划与每次写入）
crh fix --repo /path/to/repo

# 无人值守修复（CI 场景）
crh fix --repo /path/to/repo --auto-approve --mode full_auto

# 评估套件（离线、可复现）
crh eval
```

`--json` 输出机器可读报告；报告默认写入 `output/` 目录。

## 真实验证

对含注入变更的真实仓库运行，DeepSeek 驱动的完整闭环在静态分析之外发现了 **SQL 注入**（critical）、货币精度丢失、异常吞没导致的 `NameError`——证明"LLM + 静态分析"的组合能发现任一方单独无法发现的问题。

## 报告示例

```markdown
# Review Report — /tmp/crh-demo

**1 finding(s)**

## `net.py`

- **[medium]** `PY-MUTABLE-DEFAULT` `bug` :12 — Mutable default argument in process shared across calls.
  - suggestion: Use `None` and initialize inside the function.
```

## 目录结构

```
src/code_review_harness/
├── harness/      # Agent 循环、消息模型、上下文预算、同步包装
├── llm/          # Provider 抽象、Mock、OpenAI/DeepSeek 兼容实现
├── tools/        # 工具注册表 + 内置工具（文件/git/校验/写入）
├── governance/   # 权限、模式、作用域、审批门、受治理执行器
├── review/       # diff 解析、AST 静态分析、提示词/schema、审查管线
├── fix/          # 快照/回滚、验证反馈循环、修复管线
├── workflow/     # 状态机 + 顶层编排器
├── eval/         # 注入 bug 数据集、指标、离线 runner
└── cli.py        # `crh` 命令（异步核心的同步入口）
```

## 开发

```bash
uv run pytest        # 134 个测试
uv run crh eval      # 离线评估（6 类注入 bug，检出率/修复率 1.0）
```

## 参考

`openharness/` 目录作为 Agent Harness 设计的参考素材保留（已从 git 排除）。
