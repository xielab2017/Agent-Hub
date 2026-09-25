# Reviewer 1 — bioinformatics methods & software engineering

## Summary assessment

This is an ambitious review of multi-omics integration software that uses EasyMultiProfiler (EMP) as a worked example of a domain-specific, workflow-level solution. The scope is broad — taxonomy of integration strategies, R/Python frameworks, microbiome-centred tools, GUI/web servers, container infrastructure, and benchmarks — and the manuscript is generally well-structured and clearly written, with appropriately critical framing. However, the manuscript contains several unsupported factual claims about individual tools (notably CFViSA, MOADLN, moiraine) and frequently attributes interpretive limitations about EMP to the EMP paper itself, which I cannot verify from the evidence card. I recommend **major revision** before acceptance: the unsupported technical claims must be corrected or removed, the EMP-specific section should be tightened against what R1 actually supports, and the evaluation framework (scalability, data structures, interoperability, documentation, maintenance, reproducibility) should be applied systematically rather than rhetorically.

## Major comments

**1. Unsupported technical claim about CFViSA's implementation stack.**
*Passage:* "CFViSA takes a complementary, web-based route, offering 79 analytical tools and integrated microbiome and transcriptome pipelines through a point-and-click Scala/AKKA front end backed by R computations [R40]."
*Problem:* The R40 evidence card says CFViSA is "a free web platform integrating two omics pipelines (microbiome and transcriptome analyses) and 79 analysis tools for sequence processing, visualization and statistical analysis of omics data." The Scala/AKKA implementation detail and the "backed by R computations" claim are not present in the card. This is a fabricated architectural detail.
*Fix:* Delete the implementation specifics and stick to what R40 supports, e.g., "CFViSA offers 79 analysis tools spanning sequence processing, visualisation and statistical analysis for microbiome and transcriptome data behind a unified web interface [R40]."

**2. Unsupported architectural details for MOADLN.**
*Passage:* "The MOADLN framework, for instance, uses three fully connected layers per omics and a self-attention module to reduce dimensionality before concatenating the views for downstream classification [R17]."
*Problem:* The R17 card describes MOADLN as "a deep learning multi-omics integration method using self-attention to capture patient correlations and a Multi-Omics Correlation Discovery Network to learn cross-omic label correlations for biomedical data classification." It does not specify "three fully connected layers per omics" or "concatenating the views." These architectural details are not supported by the evidence.
*Fix:* Soften to "MOADLN uses self-attention to capture patient correlations and a Multi-Omics Correlation Discovery Network to learn cross-omic label correlations for biomedical data classification [R17]."

**3. Unattributed embellishment of moiraine's design.**
*Passage:* "moiraine focuses on reproducibility across multiple competing integration algorithms and explicitly automates the formatting required for each method [R3]" and "moiraine [R3] focuses on reproducibility across multiple competing integration algorithms and explicitly automates the formatting required for each method."
*Problem:* R3 says moiraine "preprocesses data, runs one or more integration methods, produces visualizations and enables comparison of results across different integration tools." The "explicitly automates the formatting required for each method" detail is an editorial embellishment that does not appear in the card.
*Fix:* Replace with the card-supported description.

**4. Unsupported claim about EMP's user interface.**
*Passage:* "In practice, EMP behaves less as a new statistical engine and more as a curated wrapper that exposes a natural-language-style interface around this data infrastructure…"
*Problem:* The R1 evidence card does not describe EMP's interface as "natural-language-style." This appears to be a fabrication. The card only confirms the five-module structure built on Bioconductor containers.
*Fix:* Either remove the interface characterisation or attribute it explicitly to the manuscript's interpretation: "the manuscript reads EMP as behaving less as a new statistical engine than as a curated wrapper around Bioconductor containers."

**5. EMP limitations presented as established but not in the evidence card.**
*Passage:* "First, EMP is currently scoped to host-microbiome cohorts and does not natively support cross-kingdom meta-omics layers such as metatranscriptomic or metaproteomic assembly, leaving a gap that gNOMO fills for non-model systems [R1]."
*Problem:* R1 does not state what EMP does *not* support. This is the manuscript's own inference, presented with a citation to EMP as if it were a documented limitation. Same issue for: "What the publication does not demonstrate, however, is robust performance on non-model host-associated microbiomes" and "Second, its tight coupling to Bioconductor classes means that its feature set is paced by Bioconductor release cycles."
*Fix:* Mark these as the author's own assessment rather than as findings from R1. For example: "In our reading, EMP is currently scoped to host-microbiome cohorts and does not appear to natively support cross-kingdom meta-omics layers…".

**6. Empirical strengths attributed to EMP not supported by the card.**
*Passage:* "Its strength is the disciplined decomposition of a multi-step microbiome pipeline into a coherent R-based workflow that reduces methodological inconsistency between meta-omics datasets and improves reproducibility, which the authors themselves identify as a key bottleneck in the field [R1]."
*Problem:* R1 frames the motivation in terms of "inconsistent sample coverage, heterogeneous data formats, and complex analytical workflows" that "collectively impair reproducibility and reliability" — but does not claim EMP "reduces methodological inconsistency between meta-omics datasets" as an empirical finding. This is promotional phrasing, and the citation [R1] does not anchor it.
*Fix:* Rephrase to what the card actually supports: "EMP organises the analytical life-cycle into five interconnected modules built on Bioconductor containers, addressing what the EMP authors identify as the field's core bottlenecks — inconsistent sample coverage, heterogeneous formats and complex analytical workflows that erode reproducibility [R1]."

**7. Promotional tone in the EMP section and concluding recommendations.**
*Passages:*
- "EasyMultiProfiler should be positioned within this roadmap as a defensible choice for host-microbiome research, particularly for groups that need a stable, reproducible entry point…"
- "Its modular design and adherence to established container classes are genuine strengths."
- "EMP offers exactly this entry point" (in recommendations).
- "Positioned this way, EMP is best understood as an integration of ecosystems rather than an integration of omics layers in the methodological sense."
*Problem:* These passages read as endorsement rather than critical assessment. The evidence card does not support "defensible choice" or "genuine strengths" as conclusions from EMP itself — these are manuscript inferences.
*Fix:* Reword as critical assessment, e.g., "On the evidence surveyed here, EMP appears to be a reasonable entry point for host-microbiome research for groups that value Bioconductor-container reproducibility, but the publication does not benchmark it against the alternatives discussed above."

**8. Evaluation criteria applied rhetorically rather than systematically.**
*Problem:* The introduction promises an evaluation across "scalability, data structures, interoperability, documentation, maintenance, reproducibility" but these criteria are never applied to the surveyed tools in a consistent, comparable way. The benchmarking section discusses evaluation metrics (silhouette, NMI, c-index, AUPR) but does not score the surveyed tools against the same rubric.
*Fix:* Either add a comparative table that scores each tool on the five criteria using explicit indicators (e.g., version-controlled release cycle, container availability, public benchmark coverage), or revise the introduction to acknowledge that the review is qualitative and omit the criteria list.

**9. Unfair comparison framing for gNOMO and EMP.**
*Passage:* "EMP does not natively ingest host-side omics alongside microbial layers in a unified Bioconductor class. EMP's emphasis is complementary: it takes already-processed microbiome features and integrates them with host omics inside a single analytical container… In a sense, EMP and gNOMO can be viewed as addressing different points along the same methodological axis…"
*Problem:* This is presented as a neutral complementarity statement, but R26 (gNOMO) is described only briefly while EMP receives a paragraph of positioning. The framing implicitly elevates EMP by suggesting the "downstream host-microbe integration" position is the more advanced or central methodological axis. There is no evidence that this axis is more central than gNOMO's upstream meta-omics assembly position — both are equally essential.
*Fix:* Treat EMP and gNOMO symmetrically; explicitly acknowledge that the review's use of EMP as a worked example is a choice of the review, not a methodological judgment.

**10. Missing key tools.**
*Problem:* The review omits several important multi-omics integration tools and infrastructure components that would round out the survey:
- The MOFA+ paper (Argelaguet et al.) — MOFA itself is only referenced through MOTL [R32].
- SNF (Wang et al. 2014) — only referenced through the CRC benchmark [R4].
- Seurat — only referenced through the single-cell benchmark [R10].
- iClusterPlus — only referenced through MultiModalGraphics [R52].
- WGCNA — only referenced through ExpOmics [R41].
- The review mentions containerised infrastructure but does not cite Dockstore or nf-core as community alternatives to WorkflowHub.
*Fix:* Either expand the card-supported tool set or acknowledge these omissions explicitly. At minimum, briefly characterise MOFA itself, since the factor-analytic branch of intermediate integration is otherwise described only through its transfer-learning extension.

## Minor comments

**1.** The phrase "pipeline that spans preprocessing, integration, dimensionality reduction, clustering, biomarker discovery and visualisation" in the introduction is unnecessarily prescriptive — these are not always distinct steps in every workflow.

**2.** In the section on early integration, "Conceptual schemes such as STATegra formalise early integration" — STATegra is described as "stepwise combines machine learning component analysis, non-parametric data combination, and multi-omics exploratory analysis" in R24, which is more accurately intermediate than early integration. Clarify.

**3.** The sentence "DIABLO from the mixOmics package sits at the boundary of intermediate and supervised integration" is correct but the discussion of supervised methods immediately after jumps to the survival benchmark; consider linking DIABLO more explicitly to the survival-prediction context.

**4.** "The persistence of MultiAssayExperiment across method implementations is a clear illustration of how container design outlives the lifetime of any single integration algorithm" is an overstatement — MultiAssayExperiment is the dominant but not universal container; Python ecosystems largely do not adopt it.

**5.** The phrase "FAIR Digital Object pattern just described" — FAIR Digital Objects are a standardisation initiative, not a single pattern. Be precise.

**6.** "the long-term archival value is more limited than the FAIR Digital Object pattern just described" — this is an opinion dressed as fact; soften.

**7.** In the EMP-vs-MoAGL-SA discussion, the manuscript states that deep-learning alternatives "were competitive only on specific evaluation axes and were not uniformly superior to SNF" — the comparison conflates MoAGL-SA's BRCA/KIRP/KIRC evaluation with the CRC benchmark's evaluation axes. Clarify which axes are referenced.

**8.** "CFViSA complements rather than substitutes for dedicated meta-omics engines" — this is fine but the claim that CFViSA "does not orchestrate raw metagenomic read assembly, metatranscriptomic mapping or metaproteomic peptide identification" should be hedged; R40 mentions "sequence processing" as a capability.

**9.** Repetition: "Five interconnected modules — data extraction, preparation, support, analysis and visualisation" appears in nearly identical wording in the introduction, the EMP section and the recommendations. Vary the phrasing or cross-reference once.

**10.** The manuscript uses "R3" as both an evidence card and an inline citation in the same sentence at one point ("a well-tuned matrix factorisation or a similarity-network fusion approach [R31, R3, R4]"), which can confuse readers. Standardise citation style.

**11.** "a curated wrapper that exposes a natural-language-style interface" — already flagged in Major Comment 4 but worth restating: this phrasing recurs and should be removed throughout.

**12.** The conclusion states "The evidence on EMP itself does not claim coverage of these domains" — but the manuscript's earlier assertions about what EMP does and does not support are framed as if they were reported in R1. Make the source of each claim (R1 vs. manuscript inference) explicit throughout the EMP section.

**13.** "single-cell analyst" (R6) is mentioned in multiple sections with inconsistent capitalisation (sometimes "single-cell analyst", sometimes "Single-cell analyst"). Normalise.

**14.** The manuscript occasionally conflates "the authors" (of R1, EMP) with the review's own voice. For example, "which the authors themselves identify as a key bottleneck" — distinguish carefully between the EMP authors' claims and the review's interpretation.

**15.** Some passages contain phrasing better suited to a perspective than a review ("the field's most consequential deficit is therefore not the absence of new methods but the absence of standardisation across them"). Either reframe as a review conclusion or explicitly mark as opinion.

**16.** The "Critical perspectives, controversies and emerging frontiers" section mixes benchmarking findings, methodological critiques, and forward-looking commentary. Consider tightening with explicit subsections to aid navigation.

# Reviewer 2 — microbiome & host–microbe biology (end user)

## Summary assessment

This is an ambitious review that frames multi-omics software around EMP as a "worked example," and the breadth of coverage across general R/Python frameworks, GUI/web platforms, containerised workflows and benchmarks is commendable. However, the manuscript contains several specific factual claims about EMP that the EMP evidence card [R1] does not support, an internally inconsistent characterisation of which omics layers EMP handles, and a comparative framing toward alternative tools (gNOMO, MuSA, Analyst suite, moiraine) that selectively emphasises EMP's strengths without reciprocally weighting the alternatives' evidence base. As a microbiome-/host–microbe-oriented reader, I also find that the practical guidance for choosing between tools in a real microbiome study design (compositionality, sparsity, phylogeny, cross-kingdom host–microbe alignment) is asserted rather than operationalised. **Recommendation: major revision**, with concrete corrections to the EMP-specific claims and a more balanced, evidence-anchored comparison to alternatives before the manuscript can serve as a useful resource for microbiome practitioners.

## Major comments

**1. The repeated "natural-language-style interface" claim is not supported by [R1].**
*Passage*: "EMP behaves less as a new statistical engine and more as a curated wrapper that exposes a natural-language-style interface around this data infrastructure, enabling users to assemble microbiome cohorts, host transcriptomes and metabolite profiles into a single MultiAssayExperiment object and to dispatch them to established methods without having to wrangle disparate input formats [R1]"; and "leveraging SummarizedExperiment and MultiAssayExperiment containers with a natural-language-style interface [R1]" (Recommendations).
*Problem*: The EMP card [R1] describes a "five-module (extraction, preparation, support, analysis, visualization) framework" anchored on SummarizedExperiment/MultiAssayExperiment. It does not characterise the interface as "natural-language-style." The same passage also extends EMP's documented scope to "host transcriptomes and metabolite profiles," which is not in the card. *Fix*: Either remove the "natural-language-style" descriptor or cite the section of the EMP paper that documents it; similarly, restrict scope claims to "microbiome multi-omics" as the card states, and do not assert host-transcriptome coverage without primary evidence.

**2. The claim that EMP does *not* natively support metatranscriptomic/metaproteomic layers is unsupported by [R1] and contradicts other passages.**
*Passage*: "First, EMP is currently scoped to host-microbiome cohorts and does not natively support cross-kingdom meta-omics layers such as metatranscriptomic or metaproteomic assembly, leaving a gap that gNOMO fills for non-model systems [R26]."
*Problem*: The EMP card [R1] does not state that metatranscriptomic or metaproteomic data are unsupported; rather, it positions EMP as a "multi-omics microbiome data integration" workflow, and the broader review [R54] cited in the same paragraph explicitly enumerates "genomic, transcriptomic, proteomic and metabolomic" layers as in scope. The claim also contradicts the earlier passage that EMP "takes already-processed microbiome features and integrates them with host omics inside a single analytical container," which is itself an over-extension of [R1]. *Fix*: Remove or substantially soften the unsupported negative claim; if the manuscript intends to argue that EMP *currently demonstrates* only certain omics layers, that must be evidenced from the EMP paper itself, not invented from a contrast with gNOMO.

**3. The introduction frames EMP as the field's motivating example but does not support the implied causality.**
*Passage*: "This combination — heterogeneous data formats, inconsistent sample coverage, complex analytical chains and weak reproducibility standards — is precisely what motivated the development of workflow-level solutions such as EasyMultiProfiler (EMP)…[R1]"
*Problem*: [R1] does not claim EMP was motivated by an infrastructural field-level diagnosis; the card simply presents the workflow and its modules. The introduction uses EMP as a synecdoche for "what the field needs," which is promotional and overreach. *Fix*: Reword to describe EMP as one illustration of the workflow-level response, not as the canonical example motivated by the infrastructural critique; cite the broader roadmap perspective [R54] for the structural argument.

**4. The closing "integration of ecosystems rather than an integration of omics layers" formulation is promotional puffery.**
*Passage*: "Positioned this way, EMP is best understood as an integration of ecosystems rather than an integration of omics layers in the methodological sense."
*Problem*: This is rhetoric, not evidence. It also subtly reframes EMP's contribution so that the absence of a novel integration method becomes a virtue, which is precisely the kind of promotional framing a peer reviewer should flag. *Fix*: Replace with a neutral, evidence-anchored statement: EMP's contribution per [R1] is a five-module reproducible wrapper over Bioconductor data classes for microbiome multi-omics; the absence of novel integration mathematics is a limitation, not a redefinition.

**5. The "bioconductor release-cycle" critique is asserted without evidence and is unfair to EMP specifically.**
*Passage*: "its tight coupling to Bioconductor classes means that its feature set is paced by Bioconductor release cycles, which can lag behind community-driven methods distributed through CRAN, PyPI or GitHub."
*Problem*: This is a generic critique that could apply to any Bioconductor package (mixOmics [R27], MultiAssayExperiment itself [R28], miodin [R48], CancerSubtypes [R49], FindIT2 [R45]), yet the manuscript only levels it at EMP. The EMP card does not raise release cadence as an issue. *Fix*: Either omit the claim or apply it symmetrically to the Bioconductor-based alternatives moiraine, miodin, mixOmics, CancerSubtypes, and MultiAssayExperiment itself; otherwise the framing is asymmetric.

**6. The comparison with gNOMO is asymmetrically framed.**
*Passage*: "In a sense, EMP and gNOMO can be viewed as addressing different points along the same methodological axis — upstream meta-omics assembly versus downstream host-microbe integration — and neither subsumes the other."
*Problem*: gNOMO [R26] is described as needing manual cross-kingdom host-microbe alignment, while EMP is described as integrating host and microbial layers — yet [R1] never documents host-side omics integration as an EMP feature (see Major comment 2). The "complementarity" framing depends on the unsupported EMP-host-omics claim. *Fix*: Reframe the comparison strictly around what each card documents: gNOMO for non-model meta-omics assembly [R26], EMP for reproducible microbiome multi-omics integration on Bioconductor classes [R1]; do not invent EMP's host-omics scope to make the dichotomy work.

**7. The EMP-vs-Analyst/MuSA comparison unfairly characterises the alternatives.**
*Passage*: "These platforms excel at lowering the entry barrier and at providing interactive visualisation, but they typically require data upload to external servers, offer limited algorithmic transparency, and are constrained by the analyses pre-implemented in the web backend. EMP retains the transparency and extensibility of R while constraining users to the Bioconductor release cycle and to locally reproducible execution [R1, R28]."
*Problem*: The negatives are pinned to the web/GUI alternatives while EMP's negatives are hedged. [R8] describes the Analyst suite components as "fully functional standalone resources" with documented protocols — it is not characterised as opaque. [R25] (MuSA) is itself built on MultiAssayExperiment, so the "transparency" distinction is partly false. *Fix*: Symmetrically note the strengths (web accessibility, no install burden) and weaknesses (transparency, customisation) of both classes; do not stack critiques only against the alternatives.

**8. The recommendation that EMP is the entry point for "bench biologists and clinical microbiologists" is not well-supported by [R1] and ignores the practical accessibility barrier.**
*Passage*: "Bench biologists and clinical microbiologists seeking reproducible host-microbiome analyses should privilege opinionated, containerised workflows built on shared data classes rather than bespoke scripts; EasyMultiProfiler offers exactly this entry point…"
*Problem*: EMP is described in [R1] as an R workflow built on Bioconductor classes, which is not the lowest entry barrier for bench biologists — CFViSA [R40], the Analyst suite [R8], ExpOmics [R41], and the single-cell analyst [R6] all explicitly target this audience. Recommending EMP for non-computational bench biologists contradicts the manuscript's own characterisation of GUI tools as lowering the entry barrier. *Fix*: Replace with audience-matched recommendations: bench biologists → GUI/web tools (CFViSA, Analyst suite); computational microbiologists → EMP/mioraine/miodin; method developers → underlying Bioconductor classes.

**9. The recommendation claim that EMP "minimises engineering burden" for moderate-sized cohorts is unsupported.**
*Passage*: "For studies combining metagenomics, metatranscriptomics and metabolomics in moderate-sized cohorts, EMP provides a credible, well-documented path that minimises engineering burden while remaining extensible through its five-module architecture."
*Problem*: [R1] does not compare engineering burden against moiraine [R3], miodin [R48], or timeOmics [R20]; "credible" and "minimises engineering burden" are value judgments, not findings from the card. *Fix*: Soften to "EMP provides one workflow-level option whose R/Bioconductor substrate minimises class-conversion overhead for users already in that ecosystem," and explicitly note that the engineering-burden claim is the author's synthesis, not a finding of [R1].

**10. The microbiome-perspective treatment lacks operational specificity for real study designs.**
*Passage*: Throughout "Microbiome-centred multi-omics tools: the case for host–microbiome integration."
*Problem*: A microbiome-focused reviewer expects concrete guidance on compositional data handling, sparsity/zero-inflation, phylogeny-aware integration, batch effects across heterogeneous meta-omics, and how each tool addresses them. The section gestures at these but never operationalises them against the cards. *Fix*: Add a short, evidence-anchored subsection that maps each microbiome-specific tool (EMP [R1], gNOMO [R26], CFViSA [R40]) to concrete capabilities: (i) whether the tool handles compositionality explicitly, (ii) how it treats missingness/partial coverage (the [R1] card names inconsistent sample coverage as a motivation), and (iii) whether it accepts phylogenetic input.

## Minor comments

1. "Disciplined decomposition" (microbiome section, EMP paragraph) is editorial and not in [R1]; consider "structured decomposition" or simply describe the five-module architecture.
2. "Well suited to human and mammalian microbiome projects where established reference databases and curated metadata schemas exist" — [R1] does not assert this scoping; rephrase as the author's inference or remove.
3. "Cohort assembly and reporting" (EMP-vs-moMoiraine paragraph) is a vague phrase; specify which cohort-assembly step (e.g., column metadata harmonisation, feature ID reconciliation) is being compared.
4. "Natural-language-style" is used twice (EMP design section and Recommendations); see Major 1 — even if kept, the term should be defined once and not used as a value claim.
5. The R1 citation in the introductory framing "is precisely what motivated the development of workflow-level solutions such as EasyMultiProfiler" attaches the infrastructural diagnosis to EMP specifically — see Major 3 — and should be reworded to describe EMP as one instance.
6. "Operationalised rather than merely endorsed" (recommendations) — the authors do not operationalise the [R54] roadmap for any of the microbiome tools reviewed; the manuscript should either attempt the operationalisation or state explicitly that this remains an open gap.
7. "Reproducibility depends largely on the maturity of its dependent Bioconductor packages rather than on a self-contained FAIR Digital Object" — this is a fair observation per [R1], but it is repeated across the "Data structures" and "EMP design" sections; consolidate.
8. The phrase "modular design" is used several times for EMP without [R1] supporting "modular" as a documented term; [R1] describes "five interconnected modules," which is consistent but not identical.
9. "Curated wrapper" (EMP design section) is editorial; either cite a section of the EMP paper that frames it this way or rephrase as "a wrapper around Bioconductor classes for microbiome multi-omics."
10. The EMP-vs-MuSA sentence "adding imaging-derived features that fall outside EMP's scope [R25]" is fine, but the manuscript then generalises this to mean EMP lacks scope, when in fact [R25] describes MuSA's scope (radiogenomics) — small asymmetry worth tightening.
11. "In a sense" (twice in the EMP section) is rhetorical hedging; replace with explicit qualification if kept.
12. The closing line "the shortest route to turning multi-omics from a methodological showcase into a routinely reliable component of biomedical research" is promotional rhetoric unmoored from evidence; either delete or anchor in [R54].
13. The roadmap item "harmonised data structures — extending the MultiAssayExperiment paradigm into longitudinal, single-cell and microbiome-specific contexts" is fine, but should explicitly note that timeOmics [R20] already does this for longitudinal designs, which is what the sentence gestures at without crediting.
14. The manuscript cites [R28] twice in the same EMP paragraph to support that MultiAssayExperiment "has become the de facto standard"; that judgement is fine but is the author's, not a finding of [R28].
15. "Defensible choice for host-microbiome research" (Recommendations) is a value judgement; prefer "a documented option among Bioconductor-based microbiome workflows."

# Reviewer 3 — editor, citation integrity & balance

## Summary assessment

This is an ambitious, broadly-scoped review of multi-omics integration software that uses EasyMultiProfiler (EMP) as a worked example. The taxonomy (early/intermediate/late × unsupervised/supervised) is useful and most comparative claims about the surrounding tools are appropriately sourced. However, the manuscript has several citation-integrity defects and a recurrent promotional tilt toward EMP: at least two factual claims about EMP directly contradict the EMP evidence card, several architectural or implementation details attributed to other tools are not in their cards, and the closing recommendations overstate what R1 actually supports. **Major revision required** before the manuscript can be relied upon as an even-handed landscape review.

## Major comments

1. **"Natural-language-style interface" — unsupported and repeated three times.**
   - **Passages:** (a) "EMP behaves less as a new statistical engine and more as a curated wrapper that exposes a **natural-language-style interface** around this data infrastructure…" (§"EMP: design…"). (b) "EasyMultiProfiler offers exactly this entry point, leveraging SummarizedExperiment and MultiAssayExperiment containers with a **natural-language-style interface** [R1]" (§Recommendations).
   - **Problem:** The R1 evidence card says only that EMP "uses SummarizedExperiment and MultiAssayExperiment classes to provide a unified five-module … framework." It does not characterise EMP's interface as "natural-language-style." The phrase is therefore an unsupported characterisation of the featured tool, repeated for emphasis.
   - **Fix:** Remove the phrase in both places; rewrite as "a coherent, class-coordinated workflow interface" if a general characterisation is needed, or simply state what R1 supports (a five-module pipeline over Bioconductor containers).

2. **Self-contradictory and card-contradictory framing of EMP's host-omics support.**
   - **Passage:** "EMP does not natively ingest host-side omics alongside microbial layers in a unified Bioconductor class" (§Microbiome-centred tools), followed two sentences later by "EMP's emphasis is complementary: it takes already-processed microbiome features and **integrates them with host omics inside a single analytical container**."
   - **Problem:** The two sentences in the same paragraph directly contradict each other. Worse, the first sentence contradicts R1, whose stated focus is explicitly **host-microbiome** multi-omics integration in a MultiAssayExperiment substrate. This is both an internal inconsistency and a citation-integrity failure around the featured tool.
   - **Fix:** Delete the "EMP does not natively ingest host-side omics…" sentence entirely. Rephrase the comparison with gNOMO as a fair upstream/downstream contrast that does not deny EMP's host-omics capability (e.g., "EMP focuses on host-microbe integration using processed feature tables, whereas gNOMO focuses on raw meta-omics assembly for non-model hosts").

3. **EMP scope-limitation claim not supported by R1.**
   - **Passage:** "EMP is currently scoped to host-microbiome cohorts and does not natively support cross-kingdom meta-omics layers such as metatranscriptomic or metaproteomic assembly, leaving a gap that gNOMO fills for non-model systems."
   - **Problem:** R1 does not state what EMP does **not** support. It describes EMP as a five-module workflow for "standardized, reproducible multi-omics microbiome data integration" without excluding metatranscriptomic/metaproteomic layers. Asserting a limitation not present in the only available evidence is methodologically inappropriate, especially for the featured tool.
   - **Fix:** Either remove the limitation, or downgrade to "whether EMP natively performs metatranscriptomic/metaproteomic assembly is not addressed in the available evidence; users with that requirement should evaluate gNOMO [R26] in parallel."

4. **CFViSA implementation details not in R40.**
   - **Passage:** "CFViSA, offering 79 analytical tools and integrated microbiome and transcriptome pipelines through a point-and-click **Scala/AKKA front end backed by R computations** [R40]" and "CFViSA complements rather than substitutes for dedicated meta-omics engines… [it] does not orchestrate raw metagenomic read assembly, metatranscriptomic mapping or metaproteomic peptide identification."
   - **Problem:** R40 only characterises CFViSA as "a free web platform" with "two omics pipelines … and 79 analysis tools." There is no mention of Scala/AKKA, no mention of an R backend, and no explicit statement that it does not perform upstream read assembly. The negative characterisation is editorial and uncited.
   - **Fix:** Strip the implementation claim ("Scala/AKKA front end backed by R computations") and the negative "does not orchestrate" sentence; keep only what R40 supports ("a free web platform combining 79 tools with microbiome and transcriptome pipelines").

5. **MOADLN architecture detail not in R17.**
   - **Passage:** "The MOADLN framework, for instance, uses **three fully connected layers per omics** and a self-attention module to reduce dimensionality before concatenating the views for downstream classification [R17]."
   - **Problem:** R17 only states that MOADLN uses self-attention to capture patient correlations and a Multi-Omics Correlation Discovery Network for cross-omic labels; it does not specify three fully-connected layers per omics.
   - **Fix:** Replace with "uses self-attention and a Multi-Omics Correlation Discovery Network to combine omics-specific encoders before classification [R17]."

6. **LOSTdb quantitative claims not verifiable from the evidence card.**
   - **Passage:** "LOSTdb goes further by manually curating 295 multi-omics datasets—bulk RNA-seq, genomic, proteomic, methylation and scRNA-seq—across **34,393 samples and over 1.2 million single cells**…"
   - **Problem:** The R34 card is truncated ("LOSTdb comprise…"). The dataset count (295) is in the card; the sample and single-cell counts are not. The manuscript asserts precise numbers the reviewer cannot confirm.
   - **Fix:** Either attribute to the original paper directly (and drop the [R34] tag for the specific figures) or soften to "hundreds of multi-omics datasets spanning bulk and single-cell modalities [R34]."

7. **DeePathNet/DeepKEGG causal claim not supported by R50.**
   - **Passage:** "the top performers, DeePathNet and DeepKEGG, **owe much of their advantage to the explicit integration of biological prior knowledge and global feature interactions**."
   - **Problem:** R50 only states that these two methods "were identified as top performers" and that "consensus biomarker panels" were provided. It does not attribute their advantage to biological prior knowledge or global feature interactions; this causal interpretation is not in the card.
   - **Fix:** Rephrase to the card-supported statement: "DeePathNet and DeepKEGG ranked as top performers in a benchmark of 20 statistical, ML and DL methods against gold-standard prognostic and therapeutic biomarkers [R50]."

8. **Comparison imbalance: EMP receives unqualified endorsements in the recommendations that exceed the evidence.**
   - **Passage (Recommendations/Roadmap):** "Bench biologists and clinical microbiologists seeking reproducible host-microbiome analyses should privilege opinionated, containerised workflows built on shared data classes rather than bespoke scripts; **EasyMultiProfiler offers exactly this entry point**…" and "EasyMultiProfiler should be positioned within this roadmap **as a defensible choice**… **Its modular design and adherence to established container classes are genuine strengths**."
   - **Problem:** "Exactly this entry point", "defensible choice", and "genuine strengths" are endorsements that go beyond what R1 substantiates. R1's claim is narrower (a five-module workflow over Bioconductor classes with reproducibility as its stated aim). Parallel recommendations for moiraine, miodin and timeOmics in the same paragraph are descriptive rather than endorsing; EMP alone is singled out for affirmative advocacy.
   - **Fix:** Either extend equivalent, balanced phrasing to the other R/Bioconductor tools discussed (moiraine, miodin, timeOmics, MultiAssayExperiment itself) or remove the prescriptive language for EMP specifically and rephrase as "EMP, moiraine and miodin each offer reusable R-based entry points with different scope; users should match tool to data modality and cohort design."

9. **Comparative framing of MOFA family is implicitly uneven.**
   - **Passage:** "the principal algorithmic families represented in the corpus" — and later, "[EMP's] new methodological contributions are therefore modest when measured against packages such as DIABLO within mixOmics [R27], MOFA, network-fusion-based methods [R4]…"
   - **Problem:** MOFA itself is not cited as an evidence card (only its extension MOTL is, R32). The MOFA family is invoked as a benchmark for EMP without a comparable evidence card, which is acceptable if MOFA is treated as a community standard, but the same standard of "no head-to-head benchmark exists" is applied asymmetrically: the manuscript concedes that no tool (including EMP, MOFA, DIABLO) has been benchmarked under matched conditions, yet EMP is repeatedly positioned as the practical recommendation.
   - **Fix:** Make the asymmetry explicit ("EMP, MOFA, DIABLO and the deep-learning family have not been benchmarked against each other in a host-microbiome setting; tool choice therefore rests on scope and infrastructure fit rather than demonstrated superiority").

## Minor comments

1. **Mixed British/American spelling.** "organising" and "behaviour" appear alongside "analyse," "favour," and "homogenising"; standardise (American English dominates elsewhere in the text).

2. **SCALE/AKKA claim also appears in the GUI section ("a point-and-click Scala/AKKA front end").** Remove or cite an implementation reference, not R40.

3. **Long paragraphs reduce readability.** §"Microbiome-centred multi-omics tools" and §"Web servers, GUI tools" each contain paragraphs of 350+ words that mix description, comparison and critique. Consider splitting into sub-paragraphs by tool.

4. **Repetition of the five-module description of EMP.** The five-module architecture (extraction, preparation, support, analysis, visualisation) is restated almost verbatim in the introduction, §"Microbiome-centred…", §"Data structures…", §"EMP: design…" and §Recommendations. Consolidate to one descriptive paragraph and refer back to it elsewhere.

5. **"SCALE/AKKA" should be "Scala/AKKA"** (a typo in two passages).

6. **"data-class ecosystem"** is used as jargon without definition on first use; briefly gloss ("Bioconductor's container classes").

7. **R11 description embellishment.** The manuscript says the FAIR Digital Object case study involved "RO-Crate metadata and explicit versioning of both workflow and container images." R11 confirms RO-Crate and version control; "explicit versioning of container images" is an extrapolation. Soften to "version control of workflow and container specification."

8. **"ready-to-analyse TCGA multi-omics objects that demonstrably reduce obstacles"** — "demonstrably" is acceptable but R28 says "reducing obstacles"; "demonstrably reduce" slightly overstates. Optional softening.

9. **The phrase "canonical stress test"** in the introduction is rhetorical; consider a more neutral formulation ("a particularly demanding application domain").

10. **Citation density imbalance.** The introduction front-loads EMP and the Bioconductor substrate with multiple supporting citations (R1, R28, R54) while the GUI section relies on R40 once for CFViSA despite a long, evaluative paragraph; this makes the surrounding tools look less substantiated than EMP.

11. **The concluding sentence** ("A coordinated commitment to these foundations is the shortest route…") is rhetorical; the manuscript would benefit from a more concrete closing pointer (e.g., naming the unmet benchmark infrastructure the roadmap implies).

12. **Internal cross-reference inconsistency.** §"Critical perspectives" cites R19 as illustrating "spaced-seed hashing" while the R19 card mentions only "barcode identification, mapping and deconvolution." "Spaced-seed hashing" appears to be borrowed from a related methodology rather than from R19 itself.

13. **Uncited general claims in the introduction** ("five to seven data types", "several thousand samples", "a dozen or more competing implementations") should either be cited or flagged as the author's general estimate.