"""Capability-gated, typed planning for EasyMultiProfiler workflows.

This module is deliberately pure: it compiles trusted local workflow templates
into the existing AnalysisPlan contract but never invokes an endpoint or emits
executable R code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from .emp_models import AnalysisPlan, DatasetManifest, PlanStep, new_id


class PlanningError(ValueError):
    """Raised when capabilities, scientific inputs, or a plan are invalid."""


def _object(
    properties: dict[str, dict[str, Any]],
    required: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


_GROUP = {"type": "string", "minLength": 1}
_LEVEL = {"type": "string", "minLength": 1}

# Local schemas are the authority. A remote capabilities response can remove
# tools from this set, but can never add an endpoint or executable operation.
STEP_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "emp.workflow.validate": _object(
        {
            "workflow": {"type": "string", "enum": [
                "microbiome_16s", "transcriptomics", "metabolomics",
                "metagenomics", "clinical",
            ]},
            "group_var": _GROUP,
            "min_group_size": {"type": "integer", "minimum": 2},
        },
        ("workflow", "group_var", "min_group_size"),
    ),
    "emp.prepare.taxonomy": _object(
        {
            "collapse_level": {"type": "string", "enum": [
                "Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species",
            ]},
            "drop_unassigned": {"type": "boolean"},
            "tax_sep": {"type": "string", "enum": [";", "|", ","]},
        },
        ("collapse_level", "drop_unassigned", "tax_sep"),
    ),
    "emp.prepare.normalize": _object(
        {
            "method": {"type": "string", "enum": [
                "tss", "clr", "deseq2", "tmm", "median", "quantile", "log2",
            ]},
        },
        ("method",),
    ),
    "emp.analyze.alpha": _object(
        {
            "method": {"type": "string", "enum": ["shannon", "simpson", "observed", "chao1"]},
            "group_var": _GROUP,
        },
        ("method", "group_var"),
    ),
    "emp.analyze.differential": _object(
        {
            "workflow": {"type": "string", "enum": [
                "microbiome_16s", "transcriptomics", "metabolomics", "metagenomics",
            ]},
            "group_var": _GROUP,
            "reference_level": _LEVEL,
            "test_level": _LEVEL,
            "method": {"type": "string", "enum": [
                "wilcoxon", "deseq2", "edger", "limma", "limma_voom", "aldex2",
            ]},
            "adjust_method": {"type": "string", "enum": ["BH", "BY", "bonferroni"]},
            "alpha": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1},
        },
        ("workflow", "group_var", "reference_level", "test_level", "method", "adjust_method", "alpha"),
    ),
    "emp.analyze.enrichment": _object(
        {
            "workflow": {"type": "string", "enum": ["transcriptomics", "metabolomics", "metagenomics"]},
            "method": {"type": "string", "enum": ["gsea", "ora", "pathway"]},
            "source_step": {"type": "string", "minLength": 1},
            "organism": {"type": "string", "enum": ["hsa", "mmu", "rno"]},
        },
        ("workflow", "method", "source_step", "organism"),
    ),
    "emp.analyze.association": _object(
        {
            "group_var": _GROUP,
            "outcome_var": {"type": "string", "minLength": 1},
            "model_family": {"type": "string", "enum": ["gaussian", "binomial", "cox"]},
            "adjust_method": {"type": "string", "enum": ["BH", "BY", "bonferroni"]},
        },
        ("group_var", "outcome_var", "model_family", "adjust_method"),
    ),
}


@dataclass(frozen=True)
class WorkflowSpec:
    workflow: str
    required_tools: tuple[str, ...]
    required_parameters: tuple[str, ...]
    min_group_size: int = 2


WORKFLOW_SPECS: dict[str, WorkflowSpec] = {
    "microbiome_16s": WorkflowSpec(
        "microbiome_16s",
        ("emp.workflow.validate", "emp.prepare.taxonomy", "emp.analyze.alpha", "emp.analyze.differential"),
        (
            "group_var", "reference_level", "test_level", "taxonomy_level", "alpha_metric",
            "differential_method", "adjust_method", "alpha",
        ),
    ),
    "transcriptomics": WorkflowSpec(
        "transcriptomics",
        ("emp.workflow.validate", "emp.prepare.normalize", "emp.analyze.differential", "emp.analyze.enrichment"),
        (
            "group_var", "reference_level", "test_level", "normalization",
            "differential_method", "enrichment_method", "adjust_method", "alpha",
            "organism",
        ),
        3,
    ),
    "metabolomics": WorkflowSpec(
        "metabolomics",
        ("emp.workflow.validate", "emp.prepare.normalize", "emp.analyze.differential", "emp.analyze.enrichment"),
        (
            "group_var", "reference_level", "test_level", "normalization",
            "differential_method", "enrichment_method", "adjust_method", "alpha",
            "organism",
        ),
        3,
    ),
    "metagenomics": WorkflowSpec(
        "metagenomics",
        ("emp.workflow.validate", "emp.prepare.normalize", "emp.analyze.differential", "emp.analyze.enrichment"),
        (
            "group_var", "reference_level", "test_level", "normalization",
            "differential_method", "enrichment_method", "adjust_method", "alpha",
            "organism",
        ),
        2,
    ),
    "clinical": WorkflowSpec(
        "clinical",
        ("emp.workflow.validate", "emp.analyze.association"),
        ("group_var", "outcome_var", "model_family", "adjust_method"),
        3,
    ),
}

WORKFLOW_PARAMETER_OPTIONS: dict[str, dict[str, frozenset[Any]]] = {
    "microbiome_16s": {
        "taxonomy_level": frozenset({"Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species"}),
        "alpha_metric": frozenset({"shannon", "simpson", "observed", "chao1"}),
        "differential_method": frozenset({"wilcoxon", "aldex2"}),
    },
    "transcriptomics": {
        "normalization": frozenset({"deseq2", "tmm", "log2"}),
        "differential_method": frozenset({"deseq2", "edger", "limma_voom"}),
        "enrichment_method": frozenset({"gsea", "ora"}),
        "organism": frozenset({"hsa", "mmu", "rno"}),
    },
    "metabolomics": {
        "normalization": frozenset({"median", "quantile", "log2"}),
        "differential_method": frozenset({"limma", "wilcoxon"}),
        "enrichment_method": frozenset({"ora", "pathway"}),
        "organism": frozenset({"hsa", "mmu", "rno"}),
    },
    "metagenomics": {
        "normalization": frozenset({"tss", "clr"}),
        "differential_method": frozenset({"aldex2", "wilcoxon"}),
        "enrichment_method": frozenset({"ora", "pathway"}),
        "organism": frozenset({"hsa", "mmu", "rno"}),
    },
    "clinical": {
        "model_family": frozenset({"gaussian", "binomial", "cox"}),
    },
}


def _capability_names(values: Any, *, key: str) -> Optional[set[str]]:
    if values is None:
        return None
    if isinstance(values, Mapping):
        return {str(name) for name, enabled in values.items() if enabled is not False}
    if not isinstance(values, list):
        raise PlanningError(f"EMP capabilities {key} must be a list or object")
    names: set[str] = set()
    for item in values:
        if isinstance(item, str):
            names.add(item)
        elif isinstance(item, Mapping):
            name = str(item.get("id") or item.get("name") or "").strip()
            if name:
                names.add(name)
        else:
            raise PlanningError(f"EMP capabilities {key} contains an invalid entry")
    return names


class WorkflowRegistry:
    """Filters the immutable local workflow allowlist by EMP capabilities."""

    def __init__(self, capabilities: Mapping[str, Any]) -> None:
        if not isinstance(capabilities, Mapping):
            raise PlanningError("EMP capabilities must be an object")
        self.capabilities = dict(capabilities)
        self._workflows = _capability_names(capabilities.get("workflows"), key="workflows") or set()
        self._tools = _capability_names(capabilities.get("tools"), key="tools")

    def available_workflows(self) -> tuple[str, ...]:
        available = []
        for name, spec in WORKFLOW_SPECS.items():
            if name not in self._workflows:
                continue
            if self._tools is not None and not set(spec.required_tools).issubset(self._tools):
                continue
            available.append(name)
        return tuple(available)

    def get(self, workflow: str) -> WorkflowSpec:
        name = str(workflow or "").strip()
        if name not in WORKFLOW_SPECS:
            raise PlanningError(f"unsupported EMP workflow: {name}")
        if name not in self.available_workflows():
            raise PlanningError(f"EMP capabilities do not enable workflow: {name}")
        return WORKFLOW_SPECS[name]

    def tool_schema(self, tool: str) -> dict[str, Any]:
        if tool not in STEP_TOOL_SCHEMAS:
            raise PlanningError(f"unregistered EMP tool: {tool}")
        if self._tools is not None and tool not in self._tools:
            raise PlanningError(f"EMP capabilities do not enable tool: {tool}")
        return STEP_TOOL_SCHEMAS[tool]


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    return False


def validate_json_schema(value: Mapping[str, Any], schema: Mapping[str, Any], *, label: str = "parameters") -> None:
    """Validate the strict JSON-Schema subset used by local EMP tools."""
    if not isinstance(value, Mapping):
        raise PlanningError(f"{label} must be an object")
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    missing = [name for name in required if name not in value]
    if missing:
        raise PlanningError(f"{label} missing required field(s): {', '.join(missing)}")
    if schema.get("additionalProperties") is False:
        unknown = sorted(set(value) - set(properties))
        if unknown:
            raise PlanningError(f"{label} contains unknown field(s): {', '.join(unknown)}")
    for name, item in value.items():
        rule = properties.get(name)
        if not isinstance(rule, Mapping):
            continue
        expected = rule.get("type")
        if expected and not _matches_type(item, str(expected)):
            raise PlanningError(f"{label}.{name} must be {expected}")
        if "enum" in rule and item not in rule["enum"]:
            raise PlanningError(f"{label}.{name} has an unsupported value")
        if isinstance(item, str) and len(item) < int(rule.get("minLength") or 0):
            raise PlanningError(f"{label}.{name} cannot be empty")
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            if "minimum" in rule and item < rule["minimum"]:
                raise PlanningError(f"{label}.{name} is below the minimum")
            if "maximum" in rule and item > rule["maximum"]:
                raise PlanningError(f"{label}.{name} exceeds the maximum")
            if "exclusiveMinimum" in rule and item <= rule["exclusiveMinimum"]:
                raise PlanningError(f"{label}.{name} must exceed the lower bound")
            if "exclusiveMaximum" in rule and item >= rule["exclusiveMaximum"]:
                raise PlanningError(f"{label}.{name} must be below the upper bound")


def _metadata_profile(manifest: DatasetManifest, group_var: str) -> tuple[list[str], dict[str, int]]:
    metadata = manifest.file_for_role("metadata") or manifest.file_for_role("clinical")
    if metadata is None or not metadata.preview:
        raise PlanningError("metadata preview is required for scientific plan validation")
    headers = [str(value).strip() for value in metadata.preview[0]]
    if group_var not in headers:
        raise PlanningError(f"group variable is not present in metadata: {group_var}")
    index = headers.index(group_var)
    counts: dict[str, int] = {}
    for row in metadata.preview[1:]:
        value = str(row[index]).strip() if index < len(row) else ""
        if value:
            counts[value] = counts.get(value, 0) + 1
    return headers, counts


def _critical_parameters(spec: WorkflowSpec, parameters: Mapping[str, Any]) -> dict[str, Any]:
    missing = [name for name in spec.required_parameters if parameters.get(name) in (None, "")]
    if missing:
        raise PlanningError(f"critical parameter(s) require confirmation: {', '.join(missing)}")
    values = {name: parameters[name] for name in spec.required_parameters}
    for name, allowed in WORKFLOW_PARAMETER_OPTIONS[spec.workflow].items():
        if values.get(name) not in allowed:
            raise PlanningError(f"critical parameter {name} is not valid for {spec.workflow}")
    if values.get("adjust_method") not in {"BH", "BY", "bonferroni"}:
        raise PlanningError("critical parameter adjust_method has an unsupported value")
    if "alpha" in values:
        alpha = values["alpha"]
        if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha < 1:
            raise PlanningError("critical parameter alpha must be between 0 and 1")
    return values


def _differential_params(workflow: str, values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "workflow": workflow,
        "group_var": values["group_var"],
        "reference_level": values["reference_level"],
        "test_level": values["test_level"],
        "method": values["differential_method"],
        "adjust_method": values.get("adjust_method", "BH"),
        "alpha": values.get("alpha", 0.05),
    }


class AnalysisPlanCompiler:
    def __init__(self, capabilities: Mapping[str, Any]) -> None:
        self.registry = WorkflowRegistry(capabilities)

    def compile(
        self,
        manifest: DatasetManifest,
        *,
        hub_session_id: str,
        parameters: Mapping[str, Any],
        workflow: Optional[str] = None,
        emp_mode: str = "local-api",
        language: str = "zh",
        title: str = "",
    ) -> AnalysisPlan:
        workflow_name = str(workflow or manifest.omics_type or "").strip()
        spec = self.registry.get(workflow_name)
        if manifest.omics_type != workflow_name:
            raise PlanningError("workflow does not match the dataset omics type")
        if not str(hub_session_id or "").strip():
            raise PlanningError("hub_session_id is required")
        if emp_mode not in {"local-api", "remote-api", "r-direct"}:
            raise PlanningError(f"unsupported EMP adapter mode: {emp_mode}")

        values = dict(parameters or {})
        critical = _critical_parameters(spec, values)
        group_var = str(critical["group_var"])
        headers, counts = _metadata_profile(manifest, group_var)
        levels = sorted(counts)
        if len(levels) < 2:
            raise PlanningError("group variable must contain at least two non-empty levels")
        too_small = {level: count for level, count in counts.items() if count < spec.min_group_size}
        if too_small:
            detail = ", ".join(f"{level}={count}" for level, count in sorted(too_small.items()))
            raise PlanningError(f"group levels do not meet minimum sample count {spec.min_group_size}: {detail}")
        if workflow_name != "clinical":
            reference = str(critical["reference_level"])
            test = str(critical["test_level"])
            if reference == test:
                raise PlanningError("reference_level and test_level must differ")
            unknown = [level for level in (reference, test) if level not in counts]
            if unknown:
                raise PlanningError(f"selected group level is absent from metadata: {', '.join(unknown)}")
        else:
            outcome = str(critical["outcome_var"])
            if outcome not in headers:
                raise PlanningError(f"outcome variable is not present in metadata: {outcome}")
            if outcome == group_var:
                raise PlanningError("outcome_var and group_var must differ")

        steps = self._steps(workflow_name, spec, values)
        plan = AnalysisPlan(
            plan_id=new_id("plan"),
            title=title.strip() or f"{workflow_name} analysis",
            dataset_manifest_id=manifest.manifest_id,
            dataset_fingerprint=manifest.fingerprint(),
            hub_session_id=str(hub_session_id),
            emp_mode=emp_mode,
            workflow=workflow_name,
            experiment_name=manifest.experiment_name,
            steps=steps,
            output={
                "language": "en" if str(language).lower() == "en" else "zh",
                "include_tables": True,
                "include_plots": True,
                "include_bundle": True,
                "generate_report": True,
                "critical_parameters": critical,
                "group_counts": counts,
            },
            requires_confirmation=True,
        )
        self.validate(plan, manifest)
        return plan

    compile_plan = compile

    def _steps(self, workflow: str, spec: WorkflowSpec, values: Mapping[str, Any]) -> list[PlanStep]:
        validate = PlanStep(
            "validate", "emp.workflow.validate",
            {"workflow": workflow, "group_var": values["group_var"], "min_group_size": spec.min_group_size},
        )
        if workflow == "microbiome_16s":
            taxonomy = PlanStep(
                "taxonomy_prepare", "emp.prepare.taxonomy",
                {"collapse_level": values["taxonomy_level"], "drop_unassigned": False, "tax_sep": ";"},
                ["validate"],
            )
            alpha = PlanStep(
                "alpha", "emp.analyze.alpha",
                {"method": values["alpha_metric"], "group_var": values["group_var"]},
                ["taxonomy_prepare"],
            )
            differential = PlanStep(
                "differential", "emp.analyze.differential",
                _differential_params(workflow, values), ["taxonomy_prepare"],
            )
            return [validate, taxonomy, alpha, differential]
        if workflow == "clinical":
            association = PlanStep(
                "association", "emp.analyze.association",
                {
                    "group_var": values["group_var"],
                    "outcome_var": values["outcome_var"],
                    "model_family": values["model_family"],
                    "adjust_method": values.get("adjust_method", "BH"),
                },
                ["validate"],
            )
            return [validate, association]

        normalize = PlanStep(
            "normalize", "emp.prepare.normalize", {"method": values["normalization"]}, ["validate"],
        )
        differential = PlanStep(
            "differential", "emp.analyze.differential",
            _differential_params(workflow, values), ["normalize"],
        )
        enrichment = PlanStep(
            "enrichment", "emp.analyze.enrichment",
            {
                "workflow": workflow,
                "method": values["enrichment_method"],
                "source_step": "differential",
                "organism": values["organism"],
            },
            ["differential"],
        )
        return [validate, normalize, differential, enrichment]

    def validate(self, plan: AnalysisPlan, manifest: DatasetManifest) -> None:
        spec = self.registry.get(plan.workflow)
        if plan.dataset_manifest_id != manifest.manifest_id:
            raise PlanningError("plan references a different dataset manifest")
        if plan.dataset_fingerprint != manifest.fingerprint():
            raise PlanningError("dataset manifest changed after plan compilation")
        if not plan.steps:
            raise PlanningError("analysis plan has no steps")
        ids = [step.id for step in plan.steps]
        if len(ids) != len(set(ids)):
            raise PlanningError("analysis step identifiers must be unique")
        by_id = {step.id: step for step in plan.steps}
        for step in plan.steps:
            if step.tool not in spec.required_tools:
                raise PlanningError(f"tool is not allowed for {plan.workflow}: {step.tool}")
            schema = self.registry.tool_schema(step.tool)
            validate_json_schema(step.params, schema, label=f"step {step.id}")
            unknown_dependencies = sorted(set(step.depends_on) - set(by_id))
            if unknown_dependencies:
                raise PlanningError(f"step {step.id} has unknown dependencies: {', '.join(unknown_dependencies)}")
            if step.id in step.depends_on:
                raise PlanningError(f"step {step.id} cannot depend on itself")

        visited: set[str] = set()
        active: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in active:
                raise PlanningError("analysis plan dependency cycle detected")
            if step_id in visited:
                return
            active.add(step_id)
            for dependency in by_id[step_id].depends_on:
                visit(dependency)
            active.remove(step_id)
            visited.add(step_id)

        for step_id in ids:
            visit(step_id)

        critical = plan.output.get("critical_parameters")
        if not isinstance(critical, Mapping):
            raise PlanningError("plan output must preserve critical_parameters")
        critical = _critical_parameters(spec, critical)
        _metadata_profile(manifest, str(critical["group_var"]))
        expected_steps = self._steps(plan.workflow, spec, critical)
        if [step.id for step in plan.steps] != [step.id for step in expected_steps]:
            raise PlanningError("analysis steps do not match the registered workflow template")
        for actual, expected in zip(plan.steps, expected_steps):
            if actual.tool != expected.tool or actual.params != expected.params or actual.depends_on != expected.depends_on:
                raise PlanningError(f"step {actual.id} differs from its confirmed workflow template")

    validate_plan = validate


def _topological_ids(plan: AnalysisPlan) -> list[str]:
    by_id = {step.id: step for step in plan.steps}
    if len(by_id) != len(plan.steps):
        raise PlanningError("analysis step identifiers must be unique")
    order: list[str] = []
    visited: set[str] = set()
    active: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id not in by_id:
            raise PlanningError(f"unknown analysis step: {step_id}")
        if step_id in active:
            raise PlanningError("analysis plan dependency cycle detected")
        if step_id in visited:
            return
        active.add(step_id)
        for dependency in by_id[step_id].depends_on:
            visit(dependency)
        active.remove(step_id)
        visited.add(step_id)
        order.append(step_id)

    for step in plan.steps:
        visit(step.id)
    return order


def _descendant_closure(plan: AnalysisPlan, roots: Iterable[str]) -> list[str]:
    by_id = {step.id: step for step in plan.steps}
    selected = {str(value) for value in roots}
    unknown = sorted(selected - set(by_id))
    if unknown:
        raise PlanningError(f"unknown analysis step(s): {', '.join(unknown)}")
    changed = True
    while changed:
        changed = False
        for step in plan.steps:
            if step.id not in selected and any(dependency in selected for dependency in step.depends_on):
                selected.add(step.id)
                changed = True
    return [step_id for step_id in _topological_ids(plan) if step_id in selected]


def retry_closure(plan: AnalysisPlan, failed_steps: Iterable[str] | Mapping[str, Any]) -> list[str]:
    """Return failed steps plus all downstream dependants in plan order."""
    if isinstance(failed_steps, Mapping):
        roots = [step_id for step_id, status in failed_steps.items() if status in {"failed", "error"}]
    else:
        roots = list(failed_steps)
    return _descendant_closure(plan, roots)


@dataclass(frozen=True)
class PlanDiff:
    added_steps: tuple[str, ...] = ()
    removed_steps: tuple[str, ...] = ()
    changed_steps: tuple[str, ...] = ()
    impacted_steps: tuple[str, ...] = ()
    critical_parameter_changes: dict[str, tuple[Any, Any]] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(
            self.added_steps or self.removed_steps or self.changed_steps
            or self.critical_parameter_changes
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "added_steps": list(self.added_steps),
            "removed_steps": list(self.removed_steps),
            "changed_steps": list(self.changed_steps),
            "impacted_steps": list(self.impacted_steps),
            "critical_parameter_changes": {
                key: {"before": before, "after": after}
                for key, (before, after) in self.critical_parameter_changes.items()
            },
        }


def diff_plans(before: AnalysisPlan, after: AnalysisPlan) -> PlanDiff:
    """Compare executable plan content and identify downstream invalidation."""
    before_steps = {step.id: step for step in before.steps}
    after_steps = {step.id: step for step in after.steps}
    added = tuple(step.id for step in after.steps if step.id not in before_steps)
    removed = tuple(step.id for step in before.steps if step.id not in after_steps)
    changed = tuple(
        step.id for step in after.steps
        if step.id in before_steps and (
            step.tool != before_steps[step.id].tool
            or step.params != before_steps[step.id].params
            or step.depends_on != before_steps[step.id].depends_on
        )
    )
    before_critical = before.output.get("critical_parameters") or {}
    after_critical = after.output.get("critical_parameters") or {}
    critical_changes = {
        key: (before_critical.get(key), after_critical.get(key))
        for key in sorted(set(before_critical) | set(after_critical))
        if before_critical.get(key) != after_critical.get(key)
    }
    roots = list(added) + list(changed)
    impacted = tuple(_descendant_closure(after, roots)) if roots else ()
    return PlanDiff(
        added_steps=added,
        removed_steps=removed,
        changed_steps=changed,
        impacted_steps=impacted,
        critical_parameter_changes=critical_changes,
    )


# Clear aliases for callers that prefer function-oriented APIs.
CapabilityWorkflowRegistry = WorkflowRegistry
plan_diff = diff_plans


def compile_analysis_plan(
    capabilities: Mapping[str, Any],
    manifest: DatasetManifest,
    *,
    hub_session_id: str,
    parameters: Mapping[str, Any],
    workflow: Optional[str] = None,
    emp_mode: str = "local-api",
    language: str = "zh",
    title: str = "",
) -> AnalysisPlan:
    """Function-oriented entry point for callers that do not retain a compiler."""
    return AnalysisPlanCompiler(capabilities).compile(
        manifest,
        hub_session_id=hub_session_id,
        parameters=parameters,
        workflow=workflow,
        emp_mode=emp_mode,
        language=language,
        title=title,
    )


__all__ = [
    "AnalysisPlanCompiler",
    "CapabilityWorkflowRegistry",
    "PlanDiff",
    "PlanningError",
    "STEP_TOOL_SCHEMAS",
    "WORKFLOW_SPECS",
    "WORKFLOW_PARAMETER_OPTIONS",
    "WorkflowRegistry",
    "WorkflowSpec",
    "compile_analysis_plan",
    "diff_plans",
    "plan_diff",
    "retry_closure",
    "validate_json_schema",
]
