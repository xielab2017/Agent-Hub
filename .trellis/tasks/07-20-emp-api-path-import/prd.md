# EMP API Contract and Secure Path Import

## Goal

在 EasyMultiProfiler Web v7 中增加 Agent Hub 所需的版本能力协商、持久状态目录和受控本地路径预检/导入，同时保持现有 multipart 与 Web UI 行为兼容。

## Requirements

- `GET /api/capabilities` 返回稳定、可测试的 `api_version=1.0` 契约。
- `EMP_SESSION_DIR`、`EMP_JOB_DIR` 可配置；未配置时使用平台用户数据目录而不是 `/tmp`。
- `EMP_ALLOWED_ROOTS` 是路径导入唯一授权来源。
- path preview 有文件类型、大小、行列、方向、metadata 样本列、交集与警告。
- path import 复用 `build_mae`/`add_experiment_to_mae`，不复制统计导入逻辑。
- 路径必须存在、为普通文件、位于 allowed roots，拒绝 traversal 与 symlink escape。
- 新接口使用 `safe_api` 错误包装，现有 endpoint 和返回字段不破坏。
- 任意 R 执行接口不属于 capabilities，也不作为 Agent 能力暴露。

## Acceptance Criteria

- [x] capabilities 契约测试通过。
- [x] session/job 在指定目录持久化且重启后可读取。
- [x] allowed、outside-root、`..`、symlink、目录和缺失文件测试通过。
- [x] fixture preview 正确报告方向和样本交集。
- [x] path import 与同文件 multipart import 复用同一导入函数，并验证核心 samples/features/omics。
- [x] 现有固定 16S Web API smoke 不回归。
