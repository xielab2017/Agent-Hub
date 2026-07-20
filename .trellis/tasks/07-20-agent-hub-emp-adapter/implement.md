# Agent Hub Adapter Implementation

1. [x] 添加配置、模型、状态目录和测试 fixtures。
2. [x] 实现 discovery 与安全边界测试。
3. [x] 实现 client、错误模型和模拟 HTTP 测试。
4. [x] 实现 service 持久化、确认、幂等、映射和恢复。
5. [x] 实现 typed tools 与薄路由。
6. [x] 实现控制中心状态、扫描、配对修正、计划、运行、artifact UI。
7. [x] 添加 zh/en/auto 文案与桌面/390px 浏览器布局检查。
8. [x] 运行完整 Python 测试：`175 passed`。

## Verification

- EMP 专项测试：22 passed。
- Agent Hub 完整测试：175 passed。
- Node syntax and `git diff --check`: passed after final formatting.
- Browser E2E: scan 132/130/130, create/confirm/run, four artifacts visible.
- Desktop and 390px viewport: no horizontal page/card overflow; console errors: none.
- HTTP/1.1 request-body reuse regression is covered by route tests.

Rollback：`emp.enabled=false`；新增状态只保留不删除，旧会话结构不迁移。
