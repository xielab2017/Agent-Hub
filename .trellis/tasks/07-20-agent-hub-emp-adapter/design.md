# Agent Hub Adapter Design

- `emp_models.py` 使用 dataclass + 显式 `from_dict` 校验，避免额外运行时依赖。
- `emp_discovery.py` 使用 `csv`、`hashlib`、`Path`；按字节/行/文件数限制扫描。
- `emp_client.py` 使用标准库 HTTP 栈以符合当前项目依赖风格，并提供可注入 transport 便于测试。
- `emp_service.py` 负责状态目录、锁、原子写、plan state machine、fingerprint、mapping、job 恢复和 artifact 下载。
- `emp_tools.py` 返回固定工具描述/JSON Schema，并只调用 service 方法。
- 路由采用 `/api/emp/*`，全部走现有认证与 audit。
- UI 复用控制中心、workspace input、SSE/轮询和现有 model progress 样式，不引入 iframe 或嵌套卡片。
