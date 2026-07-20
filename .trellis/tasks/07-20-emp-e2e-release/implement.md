# Integration and Release Implementation

1. [x] 建立契约 fixture 和 smoke 驱动。
2. [x] 启动隔离 EMP，验证 API 与科学链路。
3. [x] 启动 Agent Hub，验证 UI/恢复/幂等/artifact。
4. [x] 运行安全负例和两仓完整回归。
5. [x] 完成文档、diff 审计和回滚说明。
6. [ ] 分仓提交；推送 Agent Hub `v5.0.6`。

阻断条件：输入被修改、路径逃逸、重复昂贵任务、结果不可追溯、统计核心结果异常或 secret 泄漏。
