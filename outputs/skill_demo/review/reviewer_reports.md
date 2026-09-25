# Reviewer 1 — bioinformatics methods & software engineering

```markdown
# Peer Review: "EasyMultiProfiler and the multi-omics integration landscape"

## Summary assessment

The manuscript provides a serviceable taxonomy of multi-omics integration tools and a thoughtful discussion of benchmarking culture, reproducibility, and microbiome-specific constraints. However, the review's stated ambition — to "expose, through comparison, the engineering choices that quietly determine which scientific questions are answerable" — is undermined by (i) pervasive promotional framing of EasyMultiProfiler that goes beyond what its own evidence card supports, (ii) editorializing evaluations of competing tools that are not derived from the cited cards, and (iii) conspicuous omissions of foundational tools that a software-engineering reviewer cannot overlook (e.g., major single-cell integration frameworks, microbiome-centric toolchains, and standardized pathway-analysis stacks). **Recommendation: major revision** before the manuscript's central comparative claims can be relied upon.

---

## Major comments

### M1. Promotional framing of EMP violates the review's stated neutrality

**Passage (Introduction, final paragraph):** "it applies a common set of criteria ... to a curated set of frameworks ... and uses those criteria to situate one microbiome-centred workflow as a featured example. The aim is not to crown a winner..."

**Problem:** The manuscript repeatedly violates its own "not to crown a winner" pledge. EMP is given dedicated exposition, positive qualifiers, and the explicit recommendation in the final roadmap: "anchor analysis on a versioned data class such as MultiAssayExperiment [R36] or its microbiome-aware extension in EasyMultiProfiler [R1] first." No other tool receives a comparable endorsement.

**Fix:** Either (a) explicitly designate this as an EMP-focussed perspective piece (and revise the framing throughout), or (b) provide equally specific, criteria-anchored "anchor on X first" recommendations for at least three other tools (e.g., MOFA2, mixOmics-DIABLO, gNOMO2) so the recommendation is structurally even-handed.

### M2. Specific EMP claims that R1 does not support

The R1 card states only that EMP is "a streamlined multi-omics workflow for microbiome research using SummarizedExperiment/MultiAssayExperiment classes with five modules (extraction, preparation, support, analysis, visualization) to standardize integration, workflow standardization and reproducibility" and that the model is "human/mouse gut microbiome + host multi-omics." The following manuscript claims therefore exceed R1:

- **"articulated through a natural-language-style pipeline syntax intended to make the workflow legible to biologists"** (EMP design section) and the repeated references to a "natural-language pipeline," "natural-language syntax," and "natural-language-style pipeline description." R1 does not characterize the syntax. Remove unless R1 is replaced by the primary publication that does.
- **"explicit support for matched human and mouse host multi-omics alongside microbiome layers"** (Microbiome tools section). R1 indicates the model organisms but does not characterize the support as "explicit."
- **"embed microbiome-specific QC, taxonomic aggregation and pathway mapping directly into a multi-omics workflow"** (Microbiome tools section). R1 enumerates five modules but does not list their functions; "QC, taxonomic aggregation, pathway mapping" are inferred, not stated.
- **"its microbiome-aware extension in EasyMultiProfiler [R1]"** (Roadmap). R1 does not characterize EMP as an "extension" of MultiAssayExperiment; EMP is described as a workflow *using* these classes.
- **"battle-tested Bioconductor back-end"** (EMP section). Editorial; not supported.
- **"an excellent microbiome-oriented workflow that lowers the activation energy for host–microbiome integration"** (EMP section, final sentence). "Excellent" and "lowers activation energy" are promotional.

**Fix:** Audit every EMP claim against R1's exact phrasing. Where the manuscript provides functionality or design detail not in R1, either cite the original publication directly or soften to language R1 supports ("a workflow built on MultiAssayExperiment, with five named modules").

### M3. Unfair editorializing about competing tools

Several sentences disparage alternatives using criteria not grounded in the cited cards:

- **"mixOmics provides flexible PLS-based machinery but exposes its methods through an API whose ergonomics are oriented to statisticians rather than bench scientists [R3, R35]."** Neither R3 nor R35 supports this ergonomic judgement.
- **"Network-based methods such as similarity network fusion are powerful for subtyping but presuppose per-modality similarity construction and are agnostic to the experimental provenance that microbiome studies require [R5, R20]."** The "agnostic to experimental provenance" claim is not in either card; R5 is about fusion mechanics, R20 about block-missingness Bayesian inference.
- **"SNF assumes that informative structure manifests as consistent cross-modality sample similarity, whereas factor-analytic methods assume a small number of latent axes generate correlated observations, and these assumptions are not simultaneously testable with current benchmarks."** This is presented as if cited, but no card supports this asymmetry characterisation.

**Fix:** Either back each of these with a specific primary citation, or move them to an explicit "author's commentary" paragraph and label as such. As written, they read like asymmetric framing that disadvantages every tool except EMP.

### M4. Mislabelled taxonomic placement of MUUMI and incorrect configurability claims

**Passage (Introduction):** "Matrix-factorisation and similarity-network-fusion families continue to multiply, with new entrants handling incomplete blocks [R6, R13]."

**Problem:** R6 (MUUMI) is described in its card as a package that "unifies statistical meta-analysis with network-based multi-omics integration (including similarity network fusion)" — it is not itself a matrix-factorisation method, nor does it specifically handle incomplete blocks. R13 (MLMF) is the incomplete-block matrix factorisation tool. Bundling them under one bracket is imprecise.

**Passage (Taxonomy):** "deep learning frameworks such as DeepMoIC [R19] and MOADLN [R23] can be configured in either intermediate or late modes."

**Problem:** Neither R19 nor R23 abstract states configurability across intermediate/late integration modes. R19 describes an autoencoder + patient-similarity + deep graph convolution pipeline; R23 describes a self-attention + MOCDN pipeline.

**Fix:** Re-cite precisely. Replace "DeepMoIC [R19] and MOADLN [R23] can be configured in either intermediate or late modes" with a statement such as "DeepMoIC [R19] and MOADLN [R23] instantiate intermediate (representation-fusion) integration, with downstream classification heads that some authors have characterised as decision-level." If the configurability claim is intended as a generalisation, mark it as the author's taxonomy rather than a property of the cited papers.

### M5. Evaluation criteria are declared but not operationalised

The introduction lists criteria — "input data structures, handling of missingness, supervision, scalability, biological target, reproducibility infrastructure and empirical benchmarking" — yet the manuscript never populates a comparison matrix or even an itemised scoring rubric. For a reviewer-2 software engineer this is the central deliverable and it is absent.

**Fix:** Include at least one comparison table with rows = ~12 representative tools (e.g., EMP, MOFA2, mixOmics-DIABLO, MLMF, SNF, DeepMoIC, MO-GCAN, gNOMO2, PALM, moiraine, timeOmics, SUMO) and columns matching the declared criteria, with cells explicitly marked "not in cited card" where the evidence is silent. Without this, the review's claim to apply criteria is rhetorical.

### M6. Critical gaps in tool coverage that a methods-focused reviewer must flag

The manuscript omits or only gestures at several major multi-omics integration tools that are widely used and would be expected in any 2025–2026 methods review:

- **Single-cell multi-omics (deeply underexplored):** scVI/scANVI, totalVI, scArches, GLUE, MultiVI, Cobolt, LIGER, bindSC, scGen. Only totalVI, scArches, Seurat, MOJITOO and scAI appear, and only as named leaders in [R17]. The review should at minimum explain why these tools are absent and what their omission implies for the cross-domain generalisability of its claims.
- **Bulk multi-omics canonical baselines:** MOFA2 (the current widely used MOFA release), iCluster+/iClusterBayes, JIVE, AJIVE, intNMF, NMF-based canonical correlation tools are not discussed. R2 and R4 describe the original MOFA and MOFA+; the manuscript should clarify whether its claims extend to MOFA2.
- **Microbiome-centric toolchain:** HUMAnN/MetaWRAP/Anvi'o/QIIME 2/MEGAN are not named even though they constitute the de facto microbiome multi-omics processing stack that any workflow in the [R21, R34] lineage depends on. The "microbiome-aware preprocessing" gap is real, but EMP cannot be said to fill it in isolation from this stack.
- **Pathway / functional integration:** only pathwayMultiomics [R32] is mentioned. Tools such as FELLA, decoupleR, GSVA/ssGSEA, and the progeny/ProseMirror ecosystem for pathway-aware factor interpretation should be discussed or explicitly excluded with reason.
- **Container formats:** "containerised" is used generically; the actual matrix of Docker / Singularity-Apptainer / Conda / charliecloud support across the cited pipelines is not characterised.

**Fix:** Add a paragraph (or appendix table) explaining scope and explicitly listing exclusions. The current silent omissions create the impression of curated framing toward EMP.

### M7. The MOFA family is under-described and MOFA2 is missing

**Passage (General-purpose frameworks):** "MOFA was introduced as an unsupervised probabilistic factor model for bulk multi-omics [R2] ... MOFA+ generalised this formulation [R4]."

**Problem:** The software landscape contains MOFA2, the actively maintained successor (different implementation, different API, broad adoption) that is not discussed. A software-engineering review of "general-purpose integration frameworks" should at minimum acknowledge MOFA2 and explain whether the bulk/single-cell claims attributed to MOFA and MOFA+ transfer.

**Fix:** Either cite MOFA2 specifically or state explicitly that the review is limited to the original MOFA and MOFA+ as described in R2 and R4, and that newer releases are out of scope.

### M8. Reproducibility section conflates container presence with reproducibility

**Passage (Data structures section):** "the presence of a Dockerfile should not be equated with reproducibility... Reproducibility should therefore be measured by re-execution success on independent infrastructure..."

**Problem:** This is correct in principle but EMP itself is only evaluated against this standard by assertion. The manuscript critiques reproducibility throughout yet exempts EMP from the same scrutiny: "EMP's natural-language-style pipeline description and modular architecture make it well placed to incorporate such provenance hooks [R1]" — but no re-execution benchmark is cited.

**Fix:** Apply the same re-execution benchmark standard to EMP that the manuscript demands of others. Either cite evidence of independent re-execution of EMP on heterogeneous infrastructure or remove the implication that EMP satisfies the higher standard.

---

## Minor comments

1. **R6 miscategorisation (also flagged in M4):** Elsewhere the manuscript correctly describes MUUMI as "unifies statistical meta-analysis with network-based integration" (Reproducibility section). The Introduction's matrix-factorisation framing is inconsistent with this later, correct description.

2. **Citation density inconsistency:** R8 and R12 are both cited for BioNeuralNet (R12 is the ArXiv preprint of R8). A software review should cite the peer-reviewed publication only unless the preprint adds substantive content.

3. **"Versus" claims unsupported:** "MOFA, mixOmics-DIABLO, SNF, MLMF or graph-neural-network alternatives" — the manuscript frequently lists these as EMP comparators but never cites head-to-head numbers. Either add a comparison table or remove the suggestion that head-to-head data exist.

4. **Over-attribution of stage-agnosticism to gNOMO2:** The manuscript repeatedly credits gNOMO2 with "integration" modules [R21], but R21 describes "differential abundance, integration, and visualization modules benchmarked on four datasets." The manuscript's repeated implication that gNOMO2 ships a fully validated integrative statistical engine should be moderated.

5. **Wording: "within a single MultiAssayExperiment container, which is conceptually closer to the integrative Human Microbiome Project paradigm"** (EMP section). "Conceptually closer" is editorial; the HMP linkage is not in R1.

6. **"Several critical caveats apply"** in the Web servers section is followed by a paragraph numbered 1–5 only conceptually; either number them formally or convert to a list.

7. **PALM validation:** "validation is performed against experimentally perturbed edges rather than against held-out samples" — R31 supports the DBN alignment claim but does not specify "experimentally perturbed edges" as the validation target. Check R31 primary text before retaining this specific phrasing.

8. **Footnote-style evidence drift:** "conclusions are typically bound to a narrow slice of biological application" (Benchmarking section) is generally true but not cited; consider adding a citation or marking as author observation.

9. **Numerical claim** "12 multi-omics datasets drawn primarily from TCGA" for MLMF — R13 says "12 multi-omics datasets" without the "primarily TCGA" qualifier. Either soften or cite R13 in full.

10. **Single-cell analyst claim:** "scCNV" appears in the manuscript's list of supported modalities for the single-cell analyst [R14]. R14's card lists "scRNA-seq, scATAC-seq, scImmune profiling, scCNV, CyTOF, flow cytometry" — OK, but "over twenty interactive visualisation tools" should be "more than twenty" or quote R14 exactly.

11. **Spelling: "behaviour"** appears in British English spelling throughout, while "behavior" also appears (childhood externalizing behaviour [R18]). Standardise.

12. **Reference [R25] is cited** for "UMINT" but never introduced in the body text. Either introduce or remove.

13. **Sentence-level hedging:** "is largely unknown," "remains unclear," "has not been independently demonstrated" recur and weaken critical claims. Consolidate into a single limitations paragraph.

14. **"Microbiome-aware preprocessing, compositional correction, or phylogeny-aware features as defaults"** — these are straw-man requirements; no method of the >30 cited offers all three. Either cite a specific tool that provides one of them as a counter-example or weaken the claim.

15. **Title-level claim:** The manuscript title (inferred) positions EMP centrally while the text claims neutrality. A reviewer cannot reconcile these without the title's wording being explicit.

16. **Quantitative ceiling on benchmark coverage:** "12 integration methods benchmarked on joint scRNA-seq and scATAC-seq tasks [R48]" — R48 card says "Benchmarks 12 multi-omics integration methods," which is correct, but the manuscript elsewhere uses "dozens of datasets [R17, R48]" where R17 = 47 datasets and R48 = unspecified. Avoid merging counts.

17. **WGCNA reference [R53]:** The manuscript mentions WGCNA in the context of recurrent pregnancy loss; R53 is a review. The attribution of WGCNA's use in RPL is plausible but should be checked against R53's actual content rather than asserted.

18. **"Single-cell analyst"** vs **"single-cell Multi-omics analyst"** — verify exact name against R14 to avoid reader confusion.

19. **Promotional close:** "treat EMP as a microbiome-specialised workflow layer that interoperates with — rather than supplants — these specialised methods is the most defensible reading of the current evidence." The phrase "most defensible" is editorial; consider "consistent with the current evidence base."

20. **Missing software-engineering axes:** the review criteria list "scalability" but no tool is benchmarked on runtime, peak memory, or thread scaling. Either include at least a coarse scalability table (cited or measured) or remove "scalability" from the criteria list to avoid methodological overpromising.
```

# Reviewer 2 — microbiome & host–microbe biology (end user)

# Peer review: Multi-omics integration software review with EMP as featured example

## Summary assessment

The manuscript provides a reasonably comprehensive taxonomic and benchmarking-oriented tour of multi-omics integration software, and the sections on general-purpose frameworks, network/DL methods and reproducibility infrastructure are largely well-supported by the cited cards. However, the EasyMultiProfiler (EMP)-dedicated sections and the framing of EMP throughout repeatedly add claims that are not supported by the R1 evidence card (especially a "natural-language-style pipeline syntax" and a feature triad of "QC, taxonomic aggregation and pathway mapping"), use promotional language inappropriate for a peer-reviewed review, and contain comparisons that are arguably unfair to single-cell tools and to mixOmics. **Recommendation: Major revision** — the manuscript should be re-grounded in the actual content of R1, the rhetorical register around EMP neutralised, and the comparative framing tightened before it can be considered for publication.

## Major comments

1. **Unsupported claim: EMP features a "natural-language-style pipeline syntax".** This claim appears in at least four passages: "its architecture spans … a natural-language-style pipeline syntax intended to make the workflow legible to biologists" (EasyMultiProfiler: design), "EMP's natural-language pipeline reads more like a procedural protocol" (same section), "the natural-language syntax" and "coherent natural-language pipeline" (Critical perspectives). R1's key finding describes a "streamlined multi-omics workflow … with five modules (extraction, preparation, support, analysis, visualization) to standardize integration, workflow standardization and reproducibility" — there is no mention of natural-language syntax. **Fix.** Either quote R1 directly to justify the claim, or delete these descriptors and replace with neutral language such as "module-oriented, R-based interface".

2. **Unsupported claim: EMP "embeds microbiome-specific QC, taxonomic aggregation and pathway mapping directly into a multi-omics workflow".** (Microbiome-centred multi-omics tools; also restated in EasyMultiProfiler: design.) R1 enumerates five modules but does not in the available excerpt specify that QC, taxonomic aggregation, and pathway mapping are among them. **Fix.** Either cite the specific R1 section demonstrating these features, or weaken the claim to "is presented as a workflow that integrates microbiome-friendly preprocessing within a MultiAssayExperiment container" with a supporting citation.

3. **Promotional / editorial tone about EMP.** Multiple instances: "an excellent microbiome-oriented workflow", "a battle-tested Bioconductor back-end", "a defensible niche", "well placed", "indispensable", "more accessible". R1's key finding does not characterise EMP in these terms. **Fix.** Replace editorial adjectives with neutral, evidence-anchored statements. Suggested rewrite of the "EasyMultiProfiler: design" closing: "EMP's documented strengths — its use of MultiAssayExperiment as the unifying container, the explicit five-module decomposition, and the host–microbiome focus — give it a specific niche among microbiome workflows, while the evidence base for these claims remains concentrated on human and mouse gut datasets [R1]."

4. **Unfair comparison to single-cell and spatial tools.** EasyMultiProfiler: design states EMP's components "do not … scale to the regime of modern single-cell and spatial multi-omics that other tools explicitly target [R14, R17, R25, R45, R48]." EMP is positioned as a microbiome-focused workflow (R1 model: human/mouse gut microbiome + host multi-omics); comparing it on a dimension it was never designed to address is unfair. **Fix.** Reframe as a scope statement: "EMP is not designed to address single-cell or spatial multi-omics, which R14, R17, R25, R45 and R48 explicitly target; these are out-of-scope rather than a competitive gap."

5. **Unfair characterisation of mixOmics.** EasyMultiProfiler: design: "mixOmics provides flexible PLS-based machinery but exposes its methods through an API whose ergonomics are oriented to statisticians rather than bench scientists [R3, R35]." R3 makes no claim about its target audience, and the editorial framing disparages an alternative without evidence. **Fix.** Remove or replace with a neutral statement about EMP's intended audience: "EMP's natural-language-style module syntax is intended for biologists who do not require statistical expertise to assemble the workflow."

6. **Unfair differentiation of EMP on host-context integration.** EasyMultiProfiler: design: "EMP differentiates itself by embracing host-side omics jointly with microbial profiles within a single MultiAssayExperiment container." This oversells the differentiation: R34 (gNOMO) is explicitly framed as integrating "meta-omics levels…with host/environmental context, tailored for non-model organisms". **Fix.** Clarify the genuine differentiation (Bioconductor ecosystem, MultiAssayExperiment container, human/mouse focus) rather than the host-omits claim.

7. **Unsupported synergy claim between gNOMO2 and PALM.** Microbiome-centred multi-omics tools: "the latter [gNOMO-class pipelines] produce matched feature tables at a single time point, whereas PALM consumes such tables and adds regulatory inference." R31 does not say PALM consumes tables from gNOMO/gNOMO2; this interdependence is inferred, not stated. **Fix.** Replace with "PALM addresses a complementary problem (longitudinal dynamic network inference) rather than a downstream problem in the gNOMO/gNOMO2 workflow" and remove the implication that gNOMO2 outputs are PALM-ready.

8. **Unsupported claim about PALM's validation strategy.** Microbiome-centred multi-omics tools: "validation is performed against experimentally perturbed edges rather than against held-out samples." R31's available excerpt does not describe validation against experimentally perturbed edges; this is an unsupported embellishment. **Fix.** Either cite the specific R31 section describing this validation or remove the claim.

9. **Unsupported contrast between MOFA and EMP's microbiome behaviour.** General-purpose frameworks: "the original MOFA publication demonstrates the framework on chronic lymphocytic leukaemia data, but the evidence does not establish how the method behaves under the highly skewed, zero-inflated distributions typical of microbiome relative abundance matrices, nor how factor interpretability degrades as the number of modalities grows beyond three." This is an extrapolation beyond what R2 establishes. **Fix.** Restructure as an explicit research gap, not a "limitation" of MOFA: "Whether MOFA's factor inference generalises to microbiome-style zero-inflated compositional data remains, to our knowledge, untested in the cited literature [R2]."

10. **Editorial framing of EMP's overall positioning.** EasyMultiProfiler: design: EMP "occupies a middle ground between fully featured but generalist platforms and narrowly specialised pipelines." This is rhetorical positioning rather than an empirically supported claim. **Fix.** Replace with "EMP's documented scope [R1] places it alongside microbiome-focused pipelines such as gNOMO2 [R21] and Bioconductor-style frameworks such as timeOmics [R27] and pathwayMultiomics [R32]".

11. **Insufficient independent verification of EMP's analytical components.** EasyMultiProfiler: design concedes that "the relative quantitative performance of EMP's analytical components remains unclear" and "no independent comparison … is provided", yet the same section asserts EMP offers "a coherent natural-language pipeline" and "a clear host–microbiome focus". Given the limited information in the R1 excerpt, the section should be considerably more cautious. **Fix.** Use language such as "based on the R1 description" or "as illustrated in R1" wherever the manuscript states EMP features, and flag what is not independently benchmarked.

12. **Repeated attribution to reviews that are only loosely relevant.** Several passages cite R55, R56, R53 or R60 as raising issues that EMP allegedly does or does not address (uncertainty quantification, interpretability). These cards are reviews of EVs, tumour genomics, recurrent pregnancy loss and personalised oncology respectively, not of EMP. The connections asserted are interpretive. **Fix.** Either cite a direct empirical source for each claim or weaken the wording to "consistent with issues raised in the broader integration literature".

13. **Heterogeneity claim overstated.** Introduction: "Any two tools rarely share data structures, file conventions or evaluation metrics". Immediately afterwards the manuscript describes MultiAssayExperiment as a unifying data structure for many of the reviewed tools. **Fix.** Replace with "Data structure convergence around MultiAssayExperiment [R36] is partial; file conventions and evaluation metrics remain heterogeneous across the tools reviewed here."

## Minor comments

1. "head-to-head comparison requires substantial engineering effort that most groups cannot afford" — no citation supports this; soften to "substantial engineering effort is typically required".

2. "maximally modular ambition" (Web servers) — editorial; replace with "broadest analytic span among the surveyed web platforms" or similar with a citation.

3. The phrase "advanced statistical machinery" applied to PCA/PLS/sparse-PLS in the Analyst-suite critique is dismissive and unsupported.

4. "battle-tested" — single occurrence should be replaced; appears in the EasyMultiProfiler: design section only.

5. MixOmics-related critique conflates R3 (mixOmics package) with R35 (DIABLO) when diagnosing who the API is "for"; R3 makes no audience claim.

6. The "natural-language-style pipeline description and modular architecture make it well placed to incorporate such provenance hooks" sentence is conditional/speculative and unsupported by R1; either remove or weaken.

7. "Profile [R10] exemplifies the maximally modular ambition" overstates R10's scope; R10 supports proteomics, transcriptomics, lipidomics and other modalities but does not claim "maximally modular".

8. "the published evidence for EMP is largely benchmarked on human and mouse datasets" — accurate with respect to R1's model but the term "benchmark" implies comparator runs; R1's truncated abstract cannot confirm this.

9. Several mentions of "shared and view-specific" vs "shared and modality-specific" latent factors should be standardised (R2/R4 use "modality-specific").

10. "what a successful integration should demonstrate" (Introduction) and "what 'shared feature space' means" (Critical perspectives) are phrased as if there were a consensus, which the manuscript elsewhere denies.

11. The figure-level description of PALM as a single-time-point consumer of gNOMO-class tables reintroduces the unsupported synergy claim (also covered in Major comment 7).

12. The phrasing "tool marketed under a single 'integration' label" (Taxonomy section) parenthetically uses quotation marks around "integration" without explanation; either drop the quotes or define them.

13. The manuscript's claim that pathwayMultiomics' "abstracts … do not show how pathwayMultiomics handles the compositional structure that dominates microbiome data" generalises from a single truncated abstract; soften to "the available excerpt does not address compositionality".

14. The review frequently uses "battle-tested", "indispensable", "well placed", "defensible niche" — these editorials accumulate to a tone that signals endorsement rather than evaluation. A global pass to neutralise promotional phrasing is warranted.

15. Reference style mixes "[R1]" bracket citations with expository phrasing ("MOFA was introduced as …"); consistent in-text citation style would help the reader compare claims with the card evidence.

# Reviewer 3 — editor, citation integrity & balance

## Summary assessment

This is an ambitious, well-structured review of multi-omics integration software that adopts an explicitly balanced framing ("aim is not to crown a winner") while reserving a dedicated section for the featured workflow EasyMultiProfiler (EMP). The taxonomy of stage/supervision/biological-target is useful, and the manuscript is candid about the limits of the benchmarking literature. However, the EMP-specific section leaks promotional language and contains several comparative claims about alternatives that are not supported by the cited evidence cards, and a handful of factual claims elsewhere misalign with what the cards actually report. **Recommendation: major revisions** — tighten the EMP section for neutrality, correct the unsupported comparative claims, and verify the disputed citations.

## Major comments

1. **Promotional language in the EMP section.** "EMP should be read as an **excellent** microbiome-oriented workflow" (§ EasyMultiProfiler, penultimate paragraph) is overtly evaluative and violates the reviewer's own "not to crown a winner" framing. Adjacent phrases ("battle-tested Bioconductor back-end," "lowers the activation energy," "coherent natural-language pipeline," "accessible, microbiologically literate integration environment rather than a research prototype") reinforce the same promotional tone. **Fix**: strip evaluative adjectives and replace with verifiable descriptors — e.g., "an R-based workflow that couples SummarizedExperiment/MultiAssayExperiment containers with a five-module pipeline, illustrated on human and mouse host–microbiome cohorts [R1]."

2. **Unfair characterisation of MOFA/MOFA+ and mixOmics in the EMP section.** The manuscript states that "Generic statistical frameworks such as Multi-Omics Factor Analysis and its single-cell descendant operate on bespoke matrix or tensor inputs and require users to manage modality alignment and sample bookkeeping themselves [R2, R4]; mixOmics provides flexible PLS-based machinery but exposes its methods through an API whose ergonomics are oriented to statisticians rather than bench scientists [R3, R35]." Neither R2, R4, R3 nor R35 supports these ergonomic or workflow-friction claims, and MOFA-family tools have well-documented MultiAssayExperiment interfaces in Bioconductor. **Fix**: delete the ergonomic editorialising and, if a contrast is needed, ground it in the cards (e.g., that MOFA is an inferential engine rather than an end-to-end microbiome workflow).

3. **Unsupported negative framing of web-server platforms.** "give it a defensible niche against both generic integration frameworks [R2, R3, R4] and **web-server platforms with weaker reproducibility guarantees** [R10, R15, R22, R43]." None of R10, R15, R22 or R43 documents reproducibility weaknesses; this is an unsupported comparative claim. **Fix**: remove the clause or substantiate it with an evidence card that explicitly compares reproducibility practices.

4. **Claims about EMP features not in card R1.** "Within this landscape, EasyMultiProfiler represents an attempt to embed **microbiome-specific QC, taxonomic aggregation and pathway mapping** directly into a multi-omics workflow" (Microbiome-centred multi-omics tools section). The R1 card excerpt only enumerates the five modules (extraction, preparation, support, analysis, visualisation) and the use of SummarizedExperiment/MultiAssayExperiment; QC, taxonomic aggregation and pathway mapping are not in the card. **Fix**: either anchor each feature to a specific section of R1 (page/figure), or weaken the sentence to "modules for extraction, preparation, support, analysis and visualisation of microbiome data [R1]."

5. **Misattribution to R6 (MUUMI) as a method "handling incomplete blocks".** The Introduction states "with new entrants handling incomplete blocks [R6, R13]." The R6 card describes MUUMI as unifying statistical meta-analysis with network-based integration including SNF; incomplete-block handling is not its contribution. R13 (MLMF) is the appropriate citation for incomplete data. **Fix**: replace R6 with the correct citation for incomplete-block handling, or remove R6 from this clause.

6. **Overstatement of R48 as a benchmark spanning "dozens of datasets".** The Introduction says "systematic benchmarks across dozens of datasets [R17, R48]." R48 benchmarks 12 integration **methods** across three integration tasks on joint scRNA-seq/scATAC-seq data, not "dozens of datasets." **Fix**: write "single-cell multi-omics benchmarks [R17, R48]" without the dataset-count qualifier.

7. **Unsupported claim that DeepMoIC and MOADLN are configurable in either intermediate or late modes.** The taxonomy section states "deep learning frameworks such as DeepMoIC [R19] and MOADLN [R23] **can be configured in either intermediate or late modes**." Neither R19 nor R23 describes this configurability; both are described as intermediate (latent-fusion) architectures. **Fix**: drop the configurability claim and, if the broader point about hidden mixing of stages is worth keeping, cite evidence that documents it.

8. **"Feature-level deep architectures" mischaracterises CAEncoder.** The same taxonomy section places CAEncoder [R40] alongside "feature-level deep architectures." R40 describes a contrastive adversarial encoder combining a Vision Transformer and CycleGAN trained end-to-end — not feature-level concatenation. **Fix**: reclassify CAEncoder as a contrastive/ generative end-to-end deep model, or omit it from the early-integration example.

9. **Editorial claim about HMP framing of EMP is not in R1.** "EMP differentiates itself … which is conceptually closer to the integrative Human Microbiome Project paradigm than to either a pure meta-omics pipeline or a pure host-cancer framework." R1 makes no such comparison. **Fix**: remove the HMP-paradigm claim or qualify it as the author's interpretation, not a statement from the source.

10. **Critical assessment of EMP omits an explicit fairness check on alternatives.** The EMP section notes the absence of "head-to-head statistical benchmarking against MOFA, mixOmics-DIABLO, SNF, MLMF or graph-neural-network alternatives" and lists this as a limitation. But gNOMO2 [R21] and PALM [R31] are described only by their *own* benchmarks in the same review; the manuscript should explicitly acknowledge that the asymmetry in available evidence affects all of these tools, not just EMP, to honour the "same criteria for every tool" principle. **Fix**: add one sentence acknowledging that absence of head-to-head benchmarking is field-wide, not EMP-specific.

## Minor comments

1. **Redundant citation of BioNeuralNet.** R8 and R12 refer to the same tool (one published, one preprint). Cite R8 only at first mention and note R12 is the preprint.

2. **Long sentences impede readability.** Examples: the second sentence of the introduction's final paragraph runs >80 words; the first sentence of the Critical Perspectives section similarly long. Consider splitting.

3. **"Vertical-integration methods" terminology.** Used twice (taxonomy and benchmarking sections) without definition; consider a one-line gloss at first use.

4. **Duplicated material across sections.** The Critical Perspectives section reiterates points from the Benchmarking section (e.g., no single dominant algorithm, sensitivity to normalisation). Consolidate to avoid the sense that EMP's limitations are emphasised more than other tools'.

5. **Phrasing: "with notable exceptions."** In the web-platforms critique this hedge is left unspecified; either name the exception(s) or remove the phrase.

6. **Natural-language pipeline syntax.** Repeatedly described but never concretely illustrated. A single inline example (e.g., one pipeline verb) would let readers judge the claim independently.

7. **Citation density in EMP paragraph 2.** Six bracketed citations in a single sentence ([R1, R3, R5, R13, R19, R39]) is hard to parse; consider splitting the sentence or moving the comparative citations to a footnote.

8. **"SNF assumes that informative structure manifests as consistent cross-modality sample similarity, whereas factor-analytic methods assume a small number of latent axes generate correlated observations, and these assumptions are not simultaneously testable with current benchmarks."** This is a strong inferential claim; the cards for R5 and R2 do not state that the assumptions are non-testable. Soften to "and benchmarking studies have not, to date, formally distinguished these assumptions empirically."

9. **Section heading "EasyMultiProfiler: design, strengths and limitations relative to the alternatives"** telegraphs that the section is structured around the featured tool; consider a more neutral heading such as "Anchoring a microbiome workflow within Bioconductor: EasyMultiProfiler in context."

10. **Inconsistent tense.** Some paragraphs use present tense for methods ("MOFA infers," "SNF fuses") and others switch to past for the same tools ("was benchmarked"); standardise.

11. **"head-to-head, multi-domain comparison"** in the Benchmarking section is asserted as necessary but the review itself does not perform one. The disconnect between stated ambition and delivered analysis should be acknowledged.

12. **PathwayMultiomics caveat on compositionality.** The General-Purpose section critiques R32 for not showing how it handles compositional microbiome data; R32 itself does not claim microbiome applicability, so the criticism may be misdirected at the tool rather than at its scope. Reword as "R32's evidence base does not include compositional microbiome data, leaving its behaviour there untested."

13. **Quantitative claims without cards.** "Three to four interacting layers" and "two to four omics combinations" are restatements of card content for R1 and R21 — fine — but "47 datasets evaluated" [R17] is repeated so often it verges on a refrain; consider one canonical statement with a forward reference.

14. **Minor typographical issues.** Check for consistent hyphenation of "Bioconductor-native" vs "Bioconductor native" and "longitudinal microbiome multi-omics" vs "longitudinal, microbiome, multi-omics."