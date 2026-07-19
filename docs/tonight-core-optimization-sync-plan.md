# Agent Hub 今晚核心优化同步 Plan

## 目标

将本版本的 NVIDIA 模型治理、分类 Auto、多模型融合和会话导航能力同步到另一个版本，同时避免覆盖目标版本已有功能。

## 一、同步范围

### 1. NVIDIA 模型健康检测与自动隐藏

核心文件：

- `ali/model_intelligence.py`
- 模型配置与模型列表相关 API
- 控制中心模型配置页面

需要同步：

- 首次拉取 NVIDIA 模型后执行快速可用性测试。
- 无法调用、404、超时或返回空内容的模型不进入普通模型选择列表。
- 保存健康状态、测试时间、延迟和错误摘要。
- 后续启动优先读取缓存，只对过期或新增模型重新测试。
- 保留“重新深度分析/重新测试”入口。
- 健康检测区分 Chat、Vision、Embedding、Reranker、Tool Calling 和 Reasoning。

建议健康状态：

```text
healthy
degraded
timeout
unsupported
unavailable
untested
```

快速测试只判断模型能否使用，深度分析再判断模型适合处理什么任务。

### 2. 模型自动深度分析与分类

需要对通过健康测试的模型建立能力画像，并映射到系统任务大类：

```text
C0 simple      日常问答、轻量任务、低延迟
C1 office      办公、总结、写作、翻译
C2 code        编程、调试、代码审查
C3 research    深度推理、研究、复杂分析
Vision         图片理解、多模态
Embedding      向量化与知识库检索
Reranker       搜索结果重排
```

模型画像建议结构：

```json
{
  "model": "org/model",
  "provider": "nvidia-nim",
  "healthy": true,
  "capabilities": {
    "chat": true,
    "vision": false,
    "reasoning": true,
    "coding": 0.85,
    "writing": 0.72,
    "tool_calling": false
  },
  "performance": {
    "latency_ms": 3200,
    "stability": 0.94,
    "quality_score": 0.86
  },
  "recommended_categories": ["C2", "C3"]
}
```

判断来源优先级：

1. 实际能力测试。
2. NVIDIA 模型元数据。
3. 模型名称和家族规则。
4. 人工覆盖配置。

不要只根据模型名称完成自动分类。

### 3. 每个类型独立 Auto 配置

控制中心需要提供：

```text
C0：Auto / 手动模型
C1：Auto / 手动模型
C2：Auto / 手动模型
C3：Auto / 手动模型
Vision：Auto / 手动模型
Embedding：Auto / 手动模型
Reranker：Auto / 手动模型
```

Auto 选择流程：

```text
任务需求
  → 任务分类
  → 筛选健康且能力匹配的模型
  → 综合质量、延迟、稳定性和 Token 成本评分
  → 选择当前最佳模型
```

必须保留人工覆盖：

- 系统默认使用 Auto。
- 用户可以为每个大类固定模型。
- 单次任务可以覆盖系统配置。
- 固定模型失败时，允许按策略降级到 Auto 备选模型。

### 4. 主页面任务类型和模型选择

主页面不能只有一个总 Auto，需要提供：

- 任务类型：`Auto / C0 / C1 / C2 / C3 / Vision`
- 模型选择：`Auto · 使用类别推荐 / 具体可用模型`
- Auto 预览：`Auto → C3/research · qwen/qwen3.5-122b-a10b`

建议展示：

- 分类结果。
- 最终模型。
- 后端提供商。
- 思考深度。
- 融合模式。
- 降级原因。

## 二、多模型融合优化

核心文件：

- `ali/fusion.py`
- 流式任务路由与执行代码
- `/api/fusion/plan`
- 主页面融合模式选择器

### 1. 融合模式

同步三档模式：

#### Fast

- 使用单模型执行。
- 优先低延迟和低 Token。
- 适合简单问答和短任务。

#### Auto

- 根据任务复杂度决定使用单模型或多模型。
- 简单任务不启动融合。
- 编程、研究、决策等复杂任务自动启用多个模型。
- 作为默认推荐模式。

#### Deep

- 强制多模型并行。
- 多个模型从不同角度输出。
- 最后使用 Judge 模型综合和校验。
- 适合研究、复杂代码、方案比较和高风险结论。

### 2. 融合执行流程

```text
用户请求
  → OpenSquilla 分析任务与 Token 预算
  → 生成 Fusion Plan
  → 选择不同能力模型
  → 多路并行执行
  → 收集候选结果
  → Judge 去重、校验和综合
  → 输出最终答案
```

关键要求：

- 并行通道尽量使用不同模型。
- 每路设置独立 Token 上限。
- Judge 设置单独预算。
- 某一路失败不能导致整个任务失败。
- 所有候选失败时降级到最佳健康单模型。
- 隐藏并行内部子任务，避免污染普通会话列表。

### 3. Token 优化

OpenSquilla 负责：

- 判断是否值得启动多模型。
- 压缩各通道输入上下文。
- 按任务价值分配 Token。
- 对重复背景信息使用摘要或共享上下文。
- 限制候选答案长度。
- Judge 只读取结构化关键结论，避免无限拼接全文。

建议预算结构：

```json
{
  "total_budget": 12000,
  "planner": 800,
  "lanes": [
    {"role": "analysis", "max_tokens": 2800},
    {"role": "critic", "max_tokens": 2200},
    {"role": "solution", "max_tokens": 3000}
  ],
  "judge": 3200
}
```

执行层需要支持 `max_tokens_override`，确保每一路真实遵守预算。

### 4. Fusion Plan API

同步接口：

```http
POST /api/fusion/plan
```

请求示例：

```json
{
  "prompt": "用户任务",
  "task_type": "auto",
  "fusion_mode": "auto",
  "thinking_depth": "medium"
}
```

响应建议：

```json
{
  "enabled": true,
  "mode": "auto",
  "reason": "复杂研究任务，需要事实检索、分析和审校",
  "lanes": [
    {
      "role": "research",
      "tier": "C3",
      "model": "model-a",
      "max_tokens": 2800
    },
    {
      "role": "critic",
      "tier": "C2",
      "model": "model-b",
      "max_tokens": 2200
    }
  ],
  "judge": {
    "tier": "C3",
    "model": "model-c",
    "max_tokens": 3000
  }
}
```

## 三、会话和文件夹交互

核心文件：

- `static/app.js`
- `static/style.css`
- `ali/sessions.py`
- `tests/test_session_navigation_ui.py`

同步后的交互：

- 单击文件夹：主界面展示该文件夹的全部任务。
- 单击主界面任务：只高亮选中。
- 双击任务：进入对应对话。
- 键盘按 Enter：进入对应对话。
- 重复点击当前会话也要重新加载内容，不能提前返回。
- 进入会话时关闭控制中心、目录选择和工作流弹层。
- 多模型内部子任务标记为 `hidden`，不展示在普通任务列表。
- 隐藏子任务如果被间接点击，应跳转到父会话。

后端会话字段：

```json
{
  "hidden": false,
  "parent_id": "",
  "folder_id": ""
}
```

普通列表默认调用：

```python
list_sessions(include_hidden=False)
```

## 四、建议同步顺序

### Phase 1：数据结构与后端

1. 同步会话的 `hidden`、`parent_id` 字段。
2. 同步模型健康状态和能力画像结构。
3. 同步 NVIDIA 快速检测与深度分析。
4. 同步分类推荐逻辑。
5. 同步 Fusion Plan 和 Token 预算。
6. 同步流式请求的 `max_tokens_override`。

完成标准：API 能独立返回健康模型、分类推荐和融合计划。

### Phase 2：执行链路

1. 单模型 Auto 路由。
2. 分类 Auto 路由。
3. 多模型并行。
4. Judge 综合。
5. 单路失败容错。
6. 全部失败降级。
7. 隐藏内部子任务。

完成标准：Fast、Auto、Deep 三种模式都能得到最终输出。

### Phase 3：前端

1. 控制中心增加各大类 Auto/手动配置。
2. 主页面增加任务类型选择。
3. 主页面增加具体模型选择。
4. 增加 Auto 预览。
5. 增加融合模式选择。
6. 恢复文件夹任务总览与双击进入对话。
7. 隐藏不可用模型和内部子任务。

### Phase 4：配置迁移

不要直接覆盖目标版本的完整配置。只迁移新增字段，并提供默认值：

```text
model_health_cache
model_profiles
category_models
category_auto
fusion_mode
fusion_token_budget
fusion_judge_model
```

旧配置缺少字段时应自动补齐，不能导致启动失败。

## 五、同步后的验收清单

- [ ] NVIDIA 模型首次加载会执行检测。
- [ ] 404、空响应和不支持 Chat 的模型不会出现在 Chat 列表。
- [ ] C0/C1/C2/C3/Vision/Embedding/Reranker 都有独立 Auto。
- [ ] 每个类型都能手动选择模型。
- [ ] 主页面既有 Auto，也能选择任务类型和具体模型。
- [ ] Auto 预览与实际调用模型一致。
- [ ] Fast 使用单模型。
- [ ] Auto 只在必要时启动融合。
- [ ] Deep 能启动多个不同模型。
- [ ] 每路 Token 上限真实生效。
- [ ] 单路失败时仍能生成最终答案。
- [ ] 内部子任务不会出现在普通会话列表。
- [ ] 点击文件夹能在主界面展示任务。
- [ ] 单击任务高亮，双击进入对话。
- [ ] 当前任务重复打开时不会卡在任务总览。
- [ ] 页面刷新后模型健康状态和分类结果仍然存在。

## 六、回归测试

至少迁移并运行：

```text
tests/test_model_intelligence.py
tests/test_fusion.py
tests/test_sync_routing_tier.py
tests/test_session_navigation_ui.py
```

当前版本相关回归基线：

```text
22 passed
```

同步后使用真实浏览器验证以下路径：

```text
点击文件夹
  → 主界面出现任务列表
  → 单击任务高亮
  → 双击任务
  → 对话消息恢复
```

## 七、同步原则

先同步模型治理和执行引擎，再同步界面。不要先复制前端，否则目标版本可能出现选项已经展示、但后端路由和执行能力尚未接通的半成品状态。
