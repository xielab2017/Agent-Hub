# Agent Hub x EMP 本机联合分析 Phase 0-1

## Goal

在不重写 EasyMultiProfiler（EMP）统计算法、不执行任意 LLM 生成 R 代码的前提下，完成 Agent Hub 与 EasyMultiProfiler Web v7 的本机 16S 端到端联合分析 MVP：发现本地数据、生成受约束清单和计划、用户确认、安全导入 EMP、执行验证/分类准备/Alpha 分析、恢复任务状态、下载并登记结果、生成可追溯中文摘要。

## Background

- Agent Hub 基线：`v5.0.5`，现有 Python 测试 `153 passed`。
- Agent Hub 交付分支：`v5.0.6`。
- EMP 基线：`v7.0.0`，仓库 `EasyMultiProfiler-Web-V2`，当前无未提交改动。
- EMP 已有 `/api/health`、工作流目录、session、multipart import、16S validate/taxonomy/alpha、async job、bundle 和下载 API。
- EMP 当前 session/job 根目录硬编码于 `/tmp`；CORS 允许 `*`；没有 `/api/capabilities` 和通用受控 path import。
- EMP smoke 脚本引用缺失的 `webapp/tests/smoke_workflows.py`，Phase 0 必须修复测试入口或提供等价基线脚本。

## Confirmed Product Decisions

- MVP 组学：16S。
- 运行模式：仅 `local-api`；`remote-api` 与 `r-direct` 不在本次实现范围。
- EMP 启动策略：Agent Hub 仅检测并给出启动命令，不自动安装或启动 R 依赖。
- 报告：Markdown 摘要 + 原始 artifact；DOCX/PDF 报告后续实现。
- 数据策略：默认不离开本机，原始矩阵不发送给 LLM。
- 分析计划：固定且类型化的 16S 模板，关键参数需要用户确认。

## Requirements

### R1. API 契约和能力协商

- EMP 新增 `GET /api/capabilities`，声明 API/EMP 版本、path import、async jobs、bundles、persistent sessions、工作流和限制。
- Agent Hub 只根据能力响应启用 path import；缺失能力时显示明确兼容提示。
- 契约样例和最小 DatasetManifest 固化到文档或测试 fixture。

### R2. 安全本地数据发现

- Agent Hub 只读扫描获准工作区或会话上传目录，默认深度 2。
- 跳过隐藏目录、`.git`、环境目录、密钥类文件和符号链接逃逸。
- 识别 CSV/TSV/TXT 文件角色、16S 类型、矩阵方向、metadata 样本 ID、匹配/缺失/重复，并生成 `DatasetManifest v1.0`。
- 预览限制读取字节和行数；不得修改原始文件。

### R3. EMP 受控路径导入

- EMP 新增 `/api/import/path/preview` 与 `/api/import/path`。
- 所有路径 `normalizePath(..., mustWork=TRUE)` 后必须位于 `EMP_ALLOWED_ROOTS`。
- 拒绝目录遍历、符号链接逃逸、目录和设备文件。
- path import 复用现有 `build_mae()` / `add_experiment_to_mae()`，返回与 multipart import 兼容的结果。
- 输入 manifest 记录相对路径、大小、mtime 和 SHA-256。

### R4. 持久 session/job 根目录

- EMP session 根由 `EMP_SESSION_DIR` 控制，未设置时使用平台用户数据目录；测试可使用临时目录。
- EMP job 根由 `EMP_JOB_DIR` 控制，并保持现有 JSON/RDS 状态兼容。
- EMP 重启后既有 session 和 job 文件仍可查询。

### R5. Agent Hub 类型化适配层

- 新增 `ali/emp_models.py`、`emp_client.py`、`emp_discovery.py`、`emp_service.py`、`emp_tools.py`。
- `routes.py` 只做输入解析、权限检查与响应映射。
- EMP HTTP 错误归一化为稳定错误码和中英文用户提示。
- GET 可有限重试；创建 session、导入和运行分析不盲目重试。
- 所有下载限制目标目录、文件名、大小和来源 URL。

### R6. Manifest、Plan、映射、Job 和 Artifact 持久化

- 状态目录为 `<Agent Hub state>/emp/`，按 manifests/plans/mappings/jobs/artifacts/reports 分层。
- Agent Hub session 可映射多个 endpoint-scoped EMP session；本地和远程 ID 不混用。
- `AnalysisPlan v1.0` 必须使用注册工具、无环依赖、真实分组变量和已确认关键参数。
- 重复运行同一已确认计划不得重复提交相同昂贵任务。
- 页面刷新或 Agent Hub 重启后能恢复未完成 job 并继续轮询。

### R7. 16S MVP 执行链

- 支持导入、`microbiome_16s.validate`、taxonomy prepare 和 Alpha 分析。
- 计划 UI 显示输入、分组变量、taxonomy level、Alpha metric、运行位置和预计输出。
- 运行 UI 使用稳定步骤尺寸展示 pending/running/done/error/cancelled。
- 至少登记一个结果表和一个 PDF/PNG artifact。

### R8. 可追溯解释、安全和审计

- 计算结果与 LLM 解释分开保存。
- 每个主要结论引用 artifact/表格/图形来源，并记录统计方法、参数和版本。
- 不把相关性表述为因果关系；数据不足或假设不满足时先显示警告。
- token、完整敏感 metadata 和原始矩阵不得进入模型上下文或日志。
- `/api/user_r/run` 等任意 R 执行接口绝不注册为 Agent Hub 工具。

### R9. 兼容、关闭和回滚

- `emp.enabled=false` 完全关闭集成，不影响聊天、Claw、Fusion、现有工作流和模型路由。
- EMP 新接口向后兼容现有 Web UI。
- path import 不可用时本次 MVP只提示 multipart 兼容路径，不静默改变运行方式。
- 回滚不删除原始数据、已下载 artifact 或 EMP session。

## Acceptance Criteria

- [ ] AC1：双方原有测试基线有记录，Agent Hub 原有 153 项测试继续通过。
- [ ] AC2：EMP capabilities 响应通过 schema/契约测试。
- [ ] AC3：EMP path preview/import 仅接受 allowed roots，遍历和 symlink escape 测试通过。
- [ ] AC4：扫描固定 16S fixture 生成稳定 manifest，正确识别 assay、metadata、方向和样本交集。
- [ ] AC5：Agent Hub 在 EMP 不可用时返回可操作启动提示而非 traceback。
- [ ] AC6：本机 16S 流程完成 session 创建、导入、validate、taxonomy、Alpha 和结果下载。
- [ ] AC7：刷新 Agent Hub 后继续显示真实 job 状态；重启后映射与 artifact 不丢失。
- [ ] AC8：重复点击同一 plan 不产生第二个等价昂贵任务。
- [ ] AC9：至少一个结果表和一个图/PDF 被校验 checksum 后登记为 artifact。
- [ ] AC10：中文 Markdown 摘要列出输入摘要、参数、版本、来源、结果和限制。
- [ ] AC11：Agent Hub 未向 LLM 发送原始矩阵，且未暴露任意 R 执行工具。
- [ ] AC12：中英文和自动语言模式完整；运行进度更新不造成页面跳动。
- [ ] AC13：macOS 路径实际 smoke 通过；Windows/Linux 路径语义由单元测试覆盖。
- [ ] AC14：两个仓库均有变更清单、测试结果、剩余风险和回滚说明。

## Out Of Scope

- 远程 EMP 上传、认证、TLS、配额与多用户隔离。
- R Direct Runner。
- 任意自然语言生成任意 EMP API 调用。
- 16S 之外的正式端到端工作流。
- 将 EMP Web UI 通过 iframe 嵌入 Agent Hub。
- 自动安装或启动大型 R 依赖。

## Delivery

- Agent Hub：分支 `v5.0.6`，基于 `v5.0.5`。
- EMP：在 `v7.0.0` 基线上提交向后兼容 API 变更，具体发布分支在完成验证时记录。
