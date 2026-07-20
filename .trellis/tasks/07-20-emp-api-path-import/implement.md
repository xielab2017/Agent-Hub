# EMP API Implementation

1. [x] 增加 Agent API helper 与目录/allowed-root 单元测试。
2. [x] 将 session/job 根目录改为环境驱动并测试兼容文件布局。
3. [x] 增加 capabilities endpoint 和契约 fixture。
4. [x] 提取共享导入函数，保持 multipart 路由兼容。
5. [x] 增加 preview/path import endpoint。
6. [x] 增加安全、preview、导入 parity 测试。
7. [x] 在隔离端口和临时目录运行 smoke。

## Verification

- `Rscript webapp/tests/test_emp_agent_api.R`: passed.
- Changed R sources parse and Plumber application loads successfully.
- Default listener verified as `127.0.0.1`; Docker explicitly overrides to `0.0.0.0`.
- 16S HTTP smoke imported 132 samples and 470 features, prepared taxonomy,
  calculated 132 Alpha rows, and downloaded PNG/PDF artifacts.
- Persistent session and asynchronous job recovery passed across API restart.
- Input fixture SHA-256 values were unchanged after the workflow.

Rollback：删除新增路由/helper并恢复根目录默认解析；不得删除测试产生目录之外的 session。
