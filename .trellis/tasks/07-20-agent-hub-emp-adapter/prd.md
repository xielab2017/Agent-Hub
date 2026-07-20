# Agent Hub EMP Local Adapter

## Goal

为 Agent Hub 增加默认关闭、可审计、可恢复的 EMP 本机 16S 分析能力，并以类型化工具和计划门禁约束所有 EMP 调用。

## Requirements

- 增加方案定义的 `emp` 配置，token 仅引用 secret 环境变量名。
- 扫描只允许工作区与会话上传根，默认深度 2，预览和 checksum 有资源上限。
- DatasetManifest、AnalysisPlan、mapping、job 和 artifact 使用版本化模型和原子 JSON 持久化。
- `EmpClient` 只允许配置的 loopback origin，处理能力协商、超时、有限 GET 重试和错误归一化。
- 固定 16S plan 校验 workflow、group、taxonomy level、Alpha metric 和 DAG。
- 未确认 plan 不可运行；相同 fingerprint 的 active/completed run 防重复。
- 只暴露白名单 EMP 工具，不暴露任意 URL 或 R 代码执行。
- UI 支持扫描、配对修正、计划确认、稳定进度、取消、artifact 和中英文。

## Acceptance Criteria

- [x] EMP 关闭时现有 Agent Hub 行为无回归。
- [x] 扫描与路径安全测试覆盖 macOS/Windows/Linux 语义。
- [x] EMP 不可用、版本不兼容、validation、timeout 和 result missing 错误可读。
- [x] plan 确认和重复提交保护通过自动测试。
- [x] job/mapping/artifact 在服务重启后恢复。
- [x] UI 不跳动且 zh/en/auto 完整。
- [x] 原始矩阵和 secret 不进入 LLM 或日志。
