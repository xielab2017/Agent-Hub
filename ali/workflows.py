"""Campus office automation workflows and presets."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from . import audit, obsidian, routing
from .config import STATE_DIR, ensure_state_dirs
from .settings import api_key_status, load_campus_config

WORKFLOWS_DIR = STATE_DIR / "workflow-runs"


PRESETS: list[dict[str, Any]] = [
    {
        "id": "meeting_minutes",
        "name": "会议纪要",
        "tier": "C1",
        "route": "office",
        "icon": "📝",
        "description": "将会议笔记整理为结构化纪要（决议 / 待办 / 风险）",
        "prompt_template": (
            "请将以下会议内容整理为中文办公纪要，包含：\n"
            "1. 会议信息（时间/参与人/主题，未知则标注待补）\n"
            "2. 讨论要点\n"
            "3. 决议事项\n"
            "4. 待办（负责人、截止日期）\n"
            "5. 风险与跟进\n"
            "输出 Markdown。不要发送邮件，不要写入正式知识库。\n\n---\n{input}\n"
        ),
        "save_to_inbox": True,
        "inbox_title": "会议纪要",
    },
    {
        "id": "email_draft",
        "name": "邮件草稿",
        "tier": "C1",
        "route": "office",
        "icon": "✉️",
        "description": "生成可审阅的邮件草稿（不发送）",
        "prompt_template": (
            "请根据以下信息起草一封中文公务邮件草稿。\n"
            "要求：语气得体、结构清晰（称呼/正文/结尾）、列出可选主题行。\n"
            "严禁实际发送邮件；只输出草稿文本。\n\n---\n{input}\n"
        ),
        "save_to_inbox": True,
        "inbox_title": "邮件草稿",
    },
    {
        "id": "doc_summary",
        "name": "文档摘要",
        "tier": "C0",
        "route": "simple",
        "icon": "📄",
        "description": "短摘要 + 关键要点 + 建议文件名",
        "prompt_template": (
            "对以下材料做短摘要（≤200字）、3-5条要点，并建议一个中文文件名。\n"
            "输出 Markdown。\n\n---\n{input}\n"
        ),
        "save_to_inbox": False,
    },
    {
        "id": "research_review",
        "name": "长文生成+审核",
        "tier": "C2",
        "route": "office",
        "icon": "🔬",
        "description": "科研/长文档：先生成后给出审核清单（C2）",
        "prompt_template": (
            "这是 C2 任务：请先给出完整中文稿，再附「DeepSeek 风格」审核清单"
            "（事实风险、逻辑缺口、需引用处、可删改建议）。\n"
            "不要写入正式目录，不要外发。\n\n---\n{input}\n"
        ),
        "save_to_inbox": True,
        "inbox_title": "长文候选",
    },
    {
        "id": "code_decision",
        "name": "复杂推理/决策",
        "tier": "C3",
        "route": "reasoning",
        "icon": "🧠",
        "description": "架构决策、代码审查、复杂推理（DeepSeek）",
        "prompt_template": (
            "以严谨推理完成以下任务。给出假设、步骤、结论与风险。"
            "若涉及代码，指出关键改动面。\n\n---\n{input}\n"
        ),
        "save_to_inbox": False,
    },
    {
        "id": "vision_extract",
        "name": "多模态提取",
        "tier": "Vision",
        "route": "vision",
        "icon": "🖼️",
        "description": "PPT/PDF/图表文字与结构提取（需模型支持）",
        "prompt_template": (
            "（Vision 路由）请根据用户描述的幻灯片/PDF/图表内容，提取结构、关键数字与结论，"
            "并用 Qwen/DeepSeek 可综合的要点列表输出。\n\n---\n{input}\n"
        ),
        "save_to_inbox": True,
        "inbox_title": "多模态提取",
    },
    {
        "id": "deploy_preflight",
        "name": "部署预检",
        "tier": "C1",
        "route": "office",
        "icon": "🧭",
        "description": "对照 campus-office-ai 配置做只读预检清单（不安装）",
        "prompt_template": (
            "你是校园办公 AI 部署助手。根据当前配置做【只读预检】，列出：\n"
            "拟检查组件、下载来源、目标目录、网络、权限、回滚方案、阻断项。\n"
            "未经用户明确确认，不得安装、改防火墙、注册开机启动、索引 Vault 或写共享目录。\n"
            "当前配置摘要：\n{config_json}\n\n用户补充：\n{input}\n"
        ),
        "include_config": True,
        "save_to_inbox": False,
    },
    {
        "id": "acceptance_check",
        "name": "验收清单",
        "tier": "C1",
        "route": "office",
        "icon": "✅",
        "description": "生成验收项对照表（Hermes/API/路由/Obsidian/安全）",
        "prompt_template": (
            "根据校园办公 AI 验收标准，基于当前配置输出验收对照表："
            "Hermes、校园API、Qwen、DeepSeek、OpenSquilla路由、Obsidian读写、安全。\n"
            "标注通过/失败/未知，并给出下一步命令建议。\n"
            "配置：\n{config_json}\n\n用户补充：\n{input}\n"
        ),
        "include_config": True,
        "save_to_inbox": True,
        "inbox_title": "验收报告草稿",
    },
    {
        "id": "sop_candidate",
        "name": "SOP 写入候选区",
        "tier": "C1",
        "route": "office",
        "icon": "📚",
        "description": "生成 SOP/Skill 草案，仅写入 Obsidian AI_Candidates",
        "prompt_template": (
            "请将以下内容整理为可复用的 SOP（步骤、输入、输出、审批点、回滚）。"
            "明确标注 status=candidate，不得视为已生效制度。\n\n---\n{input}\n"
        ),
        "save_to_inbox": True,
        "inbox_title": "SOP候选",
    },
]


def list_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "tier": p["tier"],
            "route": p["route"],
            "icon": p.get("icon", ""),
            "description": p["description"],
            "save_to_inbox": bool(p.get("save_to_inbox")),
        }
        for p in PRESETS
    ]


def get_preset(preset_id: str) -> dict[str, Any] | None:
    for p in PRESETS:
        if p["id"] == preset_id:
            return p
    return None


def build_workflow_message(preset_id: str, user_input: str) -> dict[str, Any]:
    preset = get_preset(preset_id)
    if not preset:
        raise ValueError(f"unknown workflow: {preset_id}")
    cfg = load_campus_config()
    # strip secrets from config dump
    safe_cfg = json.loads(json.dumps(cfg))
    if isinstance(safe_cfg.get("backend"), dict):
        for k in list(safe_cfg["backend"].keys()):
            if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower():
                safe_cfg["backend"][k] = "***"
    tmpl = preset["prompt_template"]
    msg = tmpl.format(
        input=(user_input or "（无补充，请基于配置给出通用方案）").strip(),
        config_json=json.dumps(safe_cfg, ensure_ascii=False, indent=2),
    )
    route_info = routing.resolve_route(preset.get("route") or "office", msg, cfg)
    return {
        "preset": {
            "id": preset["id"],
            "name": preset["name"],
            "tier": preset["tier"],
            "save_to_inbox": bool(preset.get("save_to_inbox")),
            "inbox_title": preset.get("inbox_title") or preset["name"],
        },
        "message": msg,
        "route": route_info,
        "system": routing.system_preamble(route_info, cfg),
    }


def health_snapshot() -> dict[str, Any]:
    """Read-only health for Control Center."""
    cfg = load_campus_config()
    backend = cfg.get("backend") or {}
    key = api_key_status(cfg)
    vault = obsidian.vault_status()
    matrix = routing.routing_matrix()
    models_set = sum(1 for m in (cfg.get("models") or {}).values() if m)
    return {
        "backend_type": backend.get("type"),
        "base_url_set": bool(backend.get("base_url")),
        "api_key": key,
        "models_configured": models_set,
        "data_policy": cfg.get("data_policy"),
        "vault": vault,
        "routing_matrix": matrix,
        "workspace": cfg.get("workspace") or "",
        "checks": [
            {"id": "config", "ok": True, "detail": "campus-office-ai.json loaded"},
            {"id": "base_url", "ok": bool(backend.get("base_url")), "detail": backend.get("base_url") or "missing"},
            {"id": "api_key", "ok": key["present"], "detail": key["hint"]},
            {"id": "models", "ok": models_set >= 2, "detail": f"{models_set} model slots filled"},
            {"id": "vault", "ok": vault["exists"] or not vault["configured"], "detail": vault["vault_path"] or "not set"},
            {
                "id": "external_fallback",
                "ok": not (
                    cfg.get("data_policy") == "restricted"
                    and (cfg.get("routing") or {}).get("restricted_external_fallback")
                ),
                "detail": "restricted + external fallback is unsafe",
            },
        ],
    }


def record_run(preset_id: str, session_id: str, route: dict[str, Any], status: str) -> None:
    ensure_state_dirs()
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.time(),
        "preset_id": preset_id,
        "session_id": session_id,
        "route": route,
        "status": status,
    }
    path = WORKFLOWS_DIR / f"{int(time.time())}_{preset_id}.json"
    path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    audit.log_event("workflow_run", entry)
