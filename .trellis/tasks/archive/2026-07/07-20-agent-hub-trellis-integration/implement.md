# Agent Hub Trellis 受控任务模式执行计划

## 1. Task Foundation

- [x] 更新任务基线到 `v5.0.6` 并激活任务。
- [x] 增加 Trellis 配置默认值和关闭开关。
- [x] 建立 `ali/trellis.py` 的路径、模型、状态机和原子持久化边界。

## 2. Backend Integration

- [x] 实现任务建议、发现、创建、绑定、审批、迁移、验证和解除绑定。
- [x] 实现规划工件只读 API 与任务状态恢复。
- [x] 在 `ali/routes.py` 增加薄路由。
- [x] 在主 Agent、Claw 与 Fusion 共用的 prompt 组装入口注入受限 Trellis 上下文。
- [x] 将注入来源与阶段写入 route metadata，不记录工件全文。

## 3. Frontend Integration

- [x] 增加固定尺寸的会话任务条。
- [x] 增加创建/绑定、审批、质量检查、完成和解除绑定交互。
- [x] 控制中心增加 Trellis 任务详情和 Markdown 工件预览。
- [x] 完成中文、英文及自动语言文案。
- [x] 保持页面刷新和轮询期间聊天滚动位置稳定。

## 4. Codex Installation

- [x] 核对 npm 官方最新版本并升级全局 `@mindfoldhq/trellis`。
- [x] 校验当前仓库 Codex 平台文件和 PromptSubmit hook。
- [x] 运行 `trellis update` 更新项目托管文件，避免覆盖用户业务文件。
- [x] 验证 `trellis --version`、`.codex/hooks.json` 和 `~/.codex/config.toml`。

## 5. Tests And Quality Gate

- [x] 新增 `tests/test_trellis.py`。
- [x] 运行目标测试、全量 Python 测试和前端语法检查。
- [x] 启动本地服务，检查桌面与窄屏界面和 API 恢复。
- [x] 运行 `trellis-check` 要求的规范、复用和跨层检查。
- [x] 将稳定契约写回 `.trellis/spec/`。

## 6. Commit And Rollback

- [x] 仅暂存 Trellis 集成、项目 Trellis 配置和测试；排除无关组学文件。
- [x] 提交前运行 `git diff --cached --check`。
- [ ] 创建独立分支并提交，记录测试结果和剩余风险。
- [ ] 回滚方式：设置 `trellis.enabled=false`；必要时撤回提交，不删除已有任务目录。
