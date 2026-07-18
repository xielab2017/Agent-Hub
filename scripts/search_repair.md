# 修复搜索 + 启用 OpenSquilla 路由（Token-saving）

## 背景

`Agent Hub` 在校园里跑搜索时，常出现两类问题：

1. **搜索"哑火"**：`ali/search_extensions.py` 依赖 `campus-office-ai.json` 的 `search.*` 段；当前配置（`~/.hermes/ali/campus-office-ai.json`）没有该段，`intend router` 实际只跑默认通用模式，特定意图（学术/赛事/新闻）拿不到质量数据。
2. **Token 浪费**：`ali/routing.py:412-417` 只在 `routing.use_opensquilla=true` 或 `ecosystem.activated.opensquilla.active=true` 时启用 OpenSquilla。当前配置两者皆无，每次都走单一 `minimax` 后端，复杂任务直接打 C1 模型，长文档/科研无 token 节流。

## 修复脚本

`/Users/liweixie/Projects/Agent-Hub-3.0/scripts/fix_search_and_opensquilla.py`（一次性、幂等、可回退）：

```bash
# 先 dry-run 看会改什么
python3 scripts/fix_search_and_opensquilla.py --dry-run

# 应用
python3 scripts/fix_search_and_opensquilla.py

# 只修搜索 / 只开 OpenSquilla
python3 scripts/fix_search_and_opensquilla.py --no-opensquilla
python3 scripts/fix_search_and_opensquilla.py --no-search

# 重启 Hub
./ctl.sh restart
```

脚本会写两个段：

```jsonc
"search": {
  "engine": "auto",
  "verify_tls": true,
  "proxy": "",
  "max_results": 8,
  "fallback_policy": "off",
  "diagnostics": false
},
"routing": {
  "use_opensquilla": true,
  "tier_models": {
    "C0": "deepseek-v4-flash",
    "C1": "deepseek-v4-pro",
    "C2": "kimi-k2.7-code",
    "C3": "deepseek-v4-pro"
  }
},
"ecosystem": {
  "activated": {
    "opensquilla": {
      "path": "/Users/liweixie/.agent-cli/ecosystem/opensquilla",
      "active": true,
      "description": "OpenSquilla token-saving routing (C0–C3 + ensemble). Cheapest-capable model per turn."
    }
  }
}
```

## 验证清单

| 检查项 | 命令 / 路径 |
|--------|-------------|
| 配置已写入 | `python3 -c 'import json;print(json.load(open("~/.hermes/ali/campus-office-ai.json"))["search"])'` |
| OpenSquilla 激活 | `jq '.ecosystem.activated.opensquilla.active' ~/.hermes/ali/campus-office-ai.json` |
| Hub 运行中 | `curl -s http://127.0.0.1:8765/api/health` |
| 路由引擎标记 | 让 Hub 答一次 "今天天气"，看响应里的 `routing_engine` 是否为 `opensquilla` |
| 搜索意图 | 让 Hub 答一次 "最近 Nature 关于 mRNA 修饰的论文"，应触发 `academic` 意图（OpenAlex/arXiv/PubMed） |

## Token 节流机制（OpenSquilla 内部）

- C0 — 短对话 / 分类 / 命名（fast）
- C1 — 日常办公（main）
- C2 — 长文档 / 科研（生成 + 可选 review）
- C3 — 复杂推理 / 代码（reasoning）
- 默认 `static_openrouter_b5` 5 模型融合，省钱同时保留质量
- 思考深度档（`light/medium/high/very_high`）会按需把 auto 路由向上 nudge，避免小任务打 C3

> 注：当前 hub 仅按 tier 路由（`ali/routing.py:412-417`），真正的 V4 路由器
> 在 `~/.agent-cli/ecosystem/opensquilla/src/opensquilla/squilla_router/`。
> 启用 hub 侧 OpenSquilla 后，复杂任务会自动经由该路由器。

## 回退

```bash
# 关 OpenSquilla
python3 scripts/fix_search_and_opensquilla.py --no-search   # 加 --dry-run 反而没用，直接编辑
jq 'del(.routing.use_opensquilla) | del(.ecosystem)' ~/.hermes/ali/campus-office-ai.json > /tmp/x.json
mv /tmp/x.json ~/.hermes/ali/campus-office-ai.json
./ctl.sh restart
```