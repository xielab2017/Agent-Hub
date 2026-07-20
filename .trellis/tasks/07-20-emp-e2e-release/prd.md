# EMP End-to-End Validation and Release

## Goal

用固定 16S 数据验证两个仓库的真实纵向链路、重启恢复、产物追踪和安全边界，并形成可发布的 v5.0.6 证据。

## Requirements

- 使用 EMP 仓库已有 `tests/16S_level-7.csv` 与 `tests/16S_mapping.csv` 或其最小派生 fixture。
- EMP 在隔离端口、临时 session/job 目录和显式 allowed root 下运行。
- smoke 覆盖 capabilities、scan、preview、session、import、validate、taxonomy、Alpha、result/artifact。
- 验证 Agent Hub 页面/服务刷新后的 job 恢复和重复点击保护。
- 文档记录安装、配置、启动、故障排查、安全、测试和回滚。
- 两个仓库分开提交，绝不夹带无关用户文件。

## Acceptance Criteria

- [x] 本机 16S smoke 完整通过。
- [x] 原始 fixture checksum 前后不变。
- [x] 至少一个表与一个图/PDF artifact 有 checksum 和来源。
- [x] Markdown 摘要可追溯且包含限制。
- [x] 两仓回归测试通过，git diff 仅含计划范围。
- [ ] Agent Hub `v5.0.6` 推送成功并报告 EMP 对应提交。
