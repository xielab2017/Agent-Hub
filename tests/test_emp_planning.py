from __future__ import annotations

from copy import deepcopy

import pytest

from ali.emp_models import DatasetFile, DatasetManifest, PlanStep
from ali.emp_planning import (
    AnalysisPlanCompiler,
    PlanningError,
    STEP_TOOL_SCHEMAS,
    WorkflowRegistry,
    diff_plans,
    retry_closure,
)


ALL_WORKFLOWS = [
    "microbiome_16s", "transcriptomics", "metabolomics", "metagenomics", "clinical",
]


def _capabilities(*, workflows=ALL_WORKFLOWS, tools=None):
    payload = {"api_version": "1.0", "workflows": list(workflows)}
    if tools is not None:
        payload["tools"] = list(tools)
    return payload


def _manifest(omics_type: str, *, rows=None) -> DatasetManifest:
    metadata_rows = rows or [
        ["SampleID", "Group", "Outcome"],
        ["S1", "control", "1.1"],
        ["S2", "control", "1.4"],
        ["S3", "control", "1.2"],
        ["S4", "treated", "2.1"],
        ["S5", "treated", "2.4"],
        ["S6", "treated", "2.2"],
    ]
    return DatasetManifest(
        manifest_id=f"manifest-{omics_type}",
        workspace="/workspace",
        omics_type=omics_type,
        experiment_name=f"study-{omics_type}",
        files=[
            DatasetFile("assay", "assay.csv", 100, 1.0, sha256="a" * 64),
            DatasetFile("metadata", "metadata.csv", 80, 1.0, sha256="b" * 64, preview=metadata_rows),
        ],
        sample_id_column="SampleID",
        sample_overlap={"matched": 6},
    )


def _parameters(workflow: str) -> dict:
    common = {
        "group_var": "Group",
        "reference_level": "control",
        "test_level": "treated",
        "adjust_method": "BH",
        "alpha": 0.05,
    }
    if workflow == "microbiome_16s":
        return {**common, "taxonomy_level": "Genus", "alpha_metric": "shannon", "differential_method": "wilcoxon"}
    if workflow == "transcriptomics":
        return {**common, "normalization": "deseq2", "differential_method": "deseq2", "enrichment_method": "gsea", "organism": "mmu"}
    if workflow == "metabolomics":
        return {**common, "normalization": "median", "differential_method": "limma", "enrichment_method": "pathway", "organism": "hsa"}
    if workflow == "metagenomics":
        return {**common, "normalization": "clr", "differential_method": "aldex2", "enrichment_method": "ora", "organism": "hsa"}
    return {"group_var": "Group", "outcome_var": "Outcome", "model_family": "gaussian", "adjust_method": "BH"}


def test_registry_intersects_local_allowlist_with_capabilities() -> None:
    registry = WorkflowRegistry(_capabilities(workflows=["microbiome_16s", "transcriptomics", "unknown"]))
    assert registry.available_workflows() == ("microbiome_16s", "transcriptomics")
    with pytest.raises(PlanningError, match="unsupported"):
        registry.get("unknown")

    tools = set(STEP_TOOL_SCHEMAS) - {"emp.analyze.enrichment"}
    filtered = WorkflowRegistry(_capabilities(tools=tools))
    assert filtered.available_workflows() == ("microbiome_16s", "clinical")


@pytest.mark.parametrize("workflow", ALL_WORKFLOWS)
def test_compiler_emits_valid_typed_dag_for_each_workflow(workflow: str) -> None:
    manifest = _manifest(workflow)
    compiler = AnalysisPlanCompiler(_capabilities())
    plan = compiler.compile(
        manifest,
        hub_session_id="hub-1",
        parameters=_parameters(workflow),
        workflow=workflow,
    )
    assert plan.workflow == workflow
    assert plan.dataset_fingerprint == manifest.fingerprint()
    assert plan.requires_confirmation is True
    assert plan.output["critical_parameters"]["group_var"] == "Group"
    assert plan.output["group_counts"] == {"control": 3, "treated": 3}
    assert all(step.tool in STEP_TOOL_SCHEMAS for step in plan.steps)
    compiler.validate(plan, manifest)


def test_compiler_rejects_missing_critical_parameter_and_unsupported_capability() -> None:
    manifest = _manifest("transcriptomics")
    compiler = AnalysisPlanCompiler(_capabilities(workflows=["microbiome_16s"]))
    with pytest.raises(PlanningError, match="do not enable"):
        compiler.compile(manifest, hub_session_id="hub-1", parameters=_parameters("transcriptomics"))

    compiler = AnalysisPlanCompiler(_capabilities())
    parameters = _parameters("transcriptomics")
    del parameters["reference_level"]
    with pytest.raises(PlanningError, match="critical parameter"):
        compiler.compile(manifest, hub_session_id="hub-1", parameters=parameters)


def test_scientific_validation_checks_group_column_levels_and_minimum_samples() -> None:
    compiler = AnalysisPlanCompiler(_capabilities())
    parameters = _parameters("transcriptomics")
    parameters["group_var"] = "Missing"
    with pytest.raises(PlanningError, match="not present"):
        compiler.compile(_manifest("transcriptomics"), hub_session_id="hub-1", parameters=parameters)

    sparse = _manifest("transcriptomics", rows=[
        ["SampleID", "Group", "Outcome"],
        ["S1", "control", "1"], ["S2", "control", "2"], ["S3", "control", "3"],
        ["S4", "treated", "4"], ["S5", "treated", "5"],
    ])
    with pytest.raises(PlanningError, match="minimum sample count 3"):
        compiler.compile(sparse, hub_session_id="hub-1", parameters=_parameters("transcriptomics"))

    bad_level = _parameters("microbiome_16s")
    bad_level["test_level"] = "absent"
    with pytest.raises(PlanningError, match="absent from metadata"):
        compiler.compile(_manifest("microbiome_16s"), hub_session_id="hub-1", parameters=bad_level)


def test_plan_validation_rejects_unknown_params_tools_and_cycles() -> None:
    manifest = _manifest("microbiome_16s")
    compiler = AnalysisPlanCompiler(_capabilities())
    plan = compiler.compile(manifest, hub_session_id="hub-1", parameters=_parameters("microbiome_16s"))

    invalid_param = deepcopy(plan)
    invalid_param.steps[0].params["r_code"] = "system('unsafe')"
    with pytest.raises(PlanningError, match="unknown field"):
        compiler.validate(invalid_param, manifest)

    valid_but_unconfirmed = deepcopy(plan)
    valid_but_unconfirmed.steps[-1].params["alpha"] = 0.01
    with pytest.raises(PlanningError, match="confirmed workflow template"):
        compiler.validate(valid_but_unconfirmed, manifest)

    invalid_tool = deepcopy(plan)
    invalid_tool.steps[0].tool = "emp.user_r.run"
    with pytest.raises(PlanningError, match="not allowed"):
        compiler.validate(invalid_tool, manifest)

    cyclic = deepcopy(plan)
    cyclic.steps[0].depends_on = [cyclic.steps[-1].id]
    with pytest.raises(PlanningError, match="cycle"):
        compiler.validate(cyclic, manifest)


def test_plan_diff_reports_parameter_changes_and_downstream_impact() -> None:
    compiler = AnalysisPlanCompiler(_capabilities())
    manifest = _manifest("transcriptomics")
    before = compiler.compile(manifest, hub_session_id="hub-1", parameters=_parameters("transcriptomics"))
    changed_parameters = _parameters("transcriptomics")
    changed_parameters["differential_method"] = "limma_voom"
    after = compiler.compile(manifest, hub_session_id="hub-1", parameters=changed_parameters)

    difference = diff_plans(before, after)
    assert difference.changed is True
    assert difference.changed_steps == ("differential",)
    assert difference.impacted_steps == ("differential", "enrichment")
    assert difference.critical_parameter_changes["differential_method"] == ("deseq2", "limma_voom")
    assert difference.to_dict()["critical_parameter_changes"]["differential_method"]["after"] == "limma_voom"


def test_retry_closure_contains_failed_steps_and_all_downstream_steps() -> None:
    compiler = AnalysisPlanCompiler(_capabilities())
    plan = compiler.compile(
        _manifest("transcriptomics"),
        hub_session_id="hub-1",
        parameters=_parameters("transcriptomics"),
    )
    assert retry_closure(plan, ["normalize"]) == ["normalize", "differential", "enrichment"]
    assert retry_closure(plan, {"validate": "done", "differential": "error"}) == ["differential", "enrichment"]
    plan.steps = [plan.steps[3], plan.steps[1], plan.steps[0], plan.steps[2]]
    assert retry_closure(plan, ["normalize"]) == ["normalize", "differential", "enrichment"]
    with pytest.raises(PlanningError, match="unknown analysis step"):
        retry_closure(plan, ["missing"])


def test_workflow_specific_parameter_choices_are_enforced() -> None:
    compiler = AnalysisPlanCompiler(_capabilities())
    parameters = _parameters("transcriptomics")
    parameters["normalization"] = "clr"
    with pytest.raises(PlanningError, match="not valid for transcriptomics"):
        compiler.compile(_manifest("transcriptomics"), hub_session_id="hub-1", parameters=parameters)


def test_compiler_never_emits_arbitrary_endpoint_or_r_code_fields() -> None:
    compiler = AnalysisPlanCompiler(_capabilities())
    for workflow in ALL_WORKFLOWS:
        plan = compiler.compile(
            _manifest(workflow),
            hub_session_id="hub-security",
            parameters=_parameters(workflow),
        )
        serialized = str(plan.to_dict()).lower()
        assert "user_r" not in serialized
        assert "r_code" not in serialized
        assert "http://" not in serialized
        assert "https://" not in serialized
