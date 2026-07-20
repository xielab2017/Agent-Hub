# Agent Hub Trellis 受控任务模式设计

## Scope

首版在 Agent Hub 内提供可选的 Trellis 任务治理能力，不复制 Trellis CLI，也不让 Web 服务执行任意 shell 命令。官方 Trellis CLI 仍负责项目初始化、升级和 Codex hook；Agent Hub 负责读取已初始化工作区中的任务、维护会话绑定、审批、阶段和验证记录，并在模型调度前注入受限上下文。

## Decisions

- 系统只建议进入受控模式，必须由用户确认后才能创建任务。
- 首版不自动初始化任意工作区；缺少 `.trellis` 时返回安装提示。
- 规划工件在网页中只读展示；修改继续由本地编辑器或编码 Agent 完成。
- 一个 Agent Hub 主会话最多绑定一个当前 Trellis 任务。
- Agent Hub 不直接执行 `trellis`、Git、发布或用户提供的验证命令。
- 任务文件是长期事实来源，会话 JSON 只保存稳定绑定和最近状态摘要。

## Data Flow

```text
Workspace input
  -> normalize + allowed workspace check
  -> .trellis/tasks discovery
  -> Trellis task service
  -> thin HTTP routes
  -> session binding / UI

User message
  -> task-mode suggestion
  -> explicit create or bind
  -> approval gate
  -> bounded task context builder
  -> existing Agent/Claw/Fusion prompt assembly

Validation result
  -> normalized check record
  -> task state transition
  -> task.json + session binding persistence
  -> UI status recovery
```

## Backend Boundary

新增 `ali/trellis.py`，集中负责：

- 工作区和 `.trellis` 路径规范化与逃逸防护。
- 任务发现、创建、读取和有限状态迁移。
- `task.json` 原子写入及规划工件只读读取。
- 会话绑定持久化、审批记录和验证结果。
- 复杂任务建议与有预算、确定顺序、脱敏的上下文构建。

`ali/routes.py` 只解析 HTTP 输入并调用服务。`ali/streaming.py` 只消费服务返回的上下文块和路由元数据，不解析 Trellis 文件。

## API Contract

- `GET /api/trellis/status?session_id=&workspace=`：能力、工作区、绑定任务和可用任务。
- `GET /api/trellis/artifact?session_id=&name=`：读取绑定任务的允许工件。
- `POST /api/trellis/suggest`：判断是否建议受控模式，不产生副作用。
- `POST /api/trellis/tasks`：用户确认后创建任务并绑定会话。
- `POST /api/trellis/bind`：绑定已有任务。
- `POST /api/trellis/approve`：记录规划审批并转为执行中。
- `POST /api/trellis/transition`：受状态机约束的阶段迁移。
- `POST /api/trellis/validation`：记录验证结果；失败不能完成。
- `POST /api/trellis/unbind`：解除会话绑定，不删除任务。

所有写请求要求有效 `session_id` 和已初始化工作区。任务引用只接受安全 slug，不接受绝对路径。

## Persistence

- Trellis 任务：`<workspace>/.trellis/tasks/<date>-<slug>/task.json` 及 Markdown 工件。
- Agent Hub 绑定：沿用会话 JSON 的 `trellis` 字段，旧会话缺少字段时按未绑定处理。
- 任务状态：`planning`、`pending_approval`、`in_progress`、`quality_check`、`blocked`、`completed`。
- 审批与验证保存在 `task.json.meta.agent_hub`，包含时间、身份、摘要和命令结果，不保存密钥。

## Context Budget And Redaction

注入顺序固定为 PRD、设计、实施计划、任务状态、验收条件。每个文件和总块均有字符上限。读取时屏蔽常见 Token、API Key、密码、私钥块和 `.env` 风格值；路径仅展示工作区相对路径。

无绑定、集成关闭、工作区不可用或文件损坏时返回空上下文，原有聊天路径继续运行。

## UI

- 会话标题下方使用固定高度的紧凑任务条，显示阶段、进度和主要操作。
- 控制中心增加 Trellis 页签，展示任务列表、规划工件、审批和验证摘要。
- 新增中文、英文文案，自动语言模式复用现有 `t()` 机制。
- 轮询只更新任务条内容，不重建聊天区域，避免滚动跳动。

## Compatibility And Rollback

- 配置 `trellis.enabled=false` 时完全关闭注入和入口。
- 未初始化工作区、旧会话和普通聊天无需迁移。
- 回滚只需禁用配置或撤回新增模块/路由/界面；任务 Markdown 不删除。

## Validation

- 单元测试覆盖路径逃逸、状态机、审批门禁、上下文预算/脱敏、恢复和普通聊天兼容。
- 路由测试覆盖创建、绑定、读取、审批、验证失败和解除绑定。
- 前端至少进行语法检查和本地桌面/窄屏页面检查。
