# Response to Reviewers

We thank the three reviewers for their detailed and constructive critiques. The revision has re-grounded the manuscript in the evidence actually supported by the cited sources, neutralised promotional language around EasyMultiProfiler (EMP), expanded the tool coverage, and operationalised the previously declarative evaluation criteria. Below we address each comment in turn. Section references in the response correspond to the revised manuscript.

---

## Reviewer 1 — bioinformatics methods & software engineering

### Major comments

**M1. Promotional framing of EMP violates the review's stated neutrality.**

*Comment (excerpt):* "The manuscript repeatedly violates its own 'not to crown a winner' pledge. EMP is given dedicated exposition, positive qualifiers, and the explicit recommendation in the final roadmap."

**Response.** We have revised the framing throughout. The dedicated EMP section is retained but its closing paragraph no longer uses "excellent," "battle-tested," or "lowers the activation energy," and the final sentence now reads as a defensible positioning rather than an endorsement. The roadmap recommendation has been softened from "anchor on … EMP first" to a structurally even-handed statement that lists several candidate anchor data structures (MultiAssayExperiment, SummarizedExperiment, the mixOmics `MultiAssayExperiment`-compatible containers, and the gNOMO-class feature-table convention) and only then notes that EMP instantiates the first on a microbiome corpus. The Introduction's final paragraph has been rephrased to remove the "featured example" asymmetry and to clarify that EMP is treated under the same criteria as the other tools.

**M2. Specific EMP claims that the primary EMP card does not support.**

*Comment (excerpt):* "The following manuscript claims therefore exceed [the EMP card] — 'natural-language-style pipeline syntax'; 'explicit support for matched human and mouse host multi-omics'; 'embed microbiome-specific QC, taxonomic aggregation and pathway mapping'; 'microbiome-aware extension in EasyMultiProfiler'; 'battle-tested Bioconductor back-end'; 'an excellent microbiome-oriented workflow.'"

**Response.** We have audited every EMP claim against the primary EMP publication. Specifically:

- The "natural-language-style pipeline syntax" descriptors have been removed wherever they appeared (EMP design section, Critical perspectives). They are replaced by "module-oriented, R-based interface" or "five-module decomposition" — language directly supported by the EMP card.
- The "QC, taxonomic aggregation, and pathway mapping" triad has been rewritten as "modules for extraction, preparation, support, analysis and visualisation of microbiome data," with the triad reinstated only when the broader primary publication is cited.
- "Microbiome-aware extension" has been corrected to "a workflow built on MultiAssayExperiment with five named modules."
- "Battle-tested Bioconductor back-end" has been deleted.
- "An excellent microbiome-oriented workflow" has been replaced by "an R-based workflow coupling SummarizedExperiment/MultiAssayExperiment containers with a five-module pipeline, illustrated on human and mouse host–microbiome cohorts."
- "Explicit support" has been softened to "documented application to matched human and mouse host multi-omics alongside microbiome layers."

**M3. Unfair editorialising about competing tools.**

*Comment (excerpt):* "Several sentences disparage alternatives using criteria not grounded in the cited cards … 'ergonomics are oriented to statisticians rather than bench scientists' … 'agnostic to the experimental provenance' … 'these assumptions are not simultaneously testable with current benchmarks.'"

**Response.** All three passages have been removed or rewritten:

- The mixOmics sentence about audience-oriented ergonomics has been deleted; the remaining contrast now states only that EMP is a workflow-layer tool while MOFA/MOFA+ and mixOmics are inferential engines.
- The SNF "agnostic to experimental provenance" clause has been deleted.
- The sentence about simultaneous testability of SNF vs. factor-analytic assumptions has been rephrased as "and benchmarking studies have not, to date, formally distinguished these assumptions empirically" and flagged as an author observation rather than a card-supported statement.

**M4. Mislabelled taxonomic placement of MUUMI and incorrect configurability claims.**

*Comment (excerpt):* "ref. 8 (MUUMI) is … not itself a matrix-factorisation method, nor does it specifically handle incomplete blocks … Neither ref. 14 nor ref. 15 abstract states configurability across intermediate/late integration modes."

**Response.** The Introduction sentence that bracketed MUUMI with incomplete-block handling has been corrected to cite the incomplete-block matrix-factorisation tool (MLMF) alone, and MUUMI is now correctly introduced in the Reproducibility section as "unifies statistical meta-analysis with network-based multi-omics integration (including similarity network fusion)," consistent with its later correct description in the same section. The DeepMoIC/MOADLN configurability sentence has been replaced with: "DeepMoIC and MOADLN instantiate intermediate (representation-fusion) integration, with downstream classification heads that some authors have characterised as decision-level," and is now flagged as an author taxonomy rather than a property of the cited papers.

**M5. Evaluation criteria are declared but not operationalised.**

*Comment (excerpt):* "The introduction lists criteria … yet the manuscript never populates a comparison matrix or even an itemised scoring rubric."

**Response.** We have added a comparison matrix in a new Appendix A1, with rows for twelve representative tools (EMP, MOFA2, mixOmics-DIABLO, MLMF, SNF, DeepMoIC, MO-GCAN, gNOMO2, PALM, moiraine, timeOmics, SUMO) and columns matching the declared criteria (input data structures, missingness handling, supervision, scalability ceiling, biological target, reproducibility infrastructure, independent benchmarking evidence). Cells are populated only with card-supported statements; where evidence is silent, the cell is explicitly marked "not in cited card." The matrix is referenced from the Benchmarking section.

**M6. Critical gaps in tool coverage.**

*Comment (excerpt):* "The manuscript omits … single-cell multi-omics, bulk multi-omics canonical baselines, microbiome-centric toolchain, pathway/functional integration, container formats."

**Response.** We have expanded the coverage and added an explicit "Scope and exclusions" paragraph in the Introduction:

- **Single-cell multi-omics:** the manuscript now discusses scVI/scANVI, totalVI, scArches, GLUE, MultiVI, Cobolt, LIGER, bindSC and scGen alongside the previously named leaders, and clarifies that these are out of scope for the microbiome-centric focus of the EMP section.
- **Bulk multi-omics baselines:** MOFA2 is now introduced explicitly as the actively maintained successor to MOFA/MOFA+, with a note that the bulk/single-cell claims attributed to MOFA and MOFA+ transfer in principle but are not independently re-evaluated here. iCluster+/iClusterBayes, JIVE, AJIVE and intNMF are briefly situated in the matrix-factorisation lineage.
- **Microbiome-centric toolchain:** HUMAnN, MetaWRAP, Anvi'o, QIIME 2 and MEGAN are now named as the de facto microbiome multi-omics processing stack and acknowledged as a prerequisite layer rather than a competitor to EMP.
- **Pathway / functional integration:** FELLA, decoupleR, GSVA/ssGSEA, and the progeny / ProseMirror ecosystem are now mentioned alongside pathwayMultiomics, and the pathway-analysis comparison column in the new matrix reflects their scope.
- **Container formats:** the reproducibility section now characterises Docker / Singularity-Apptainer / Conda / charliecloud support per tool to the extent supported by the cards.

**M7. The MOFA family is under-described and MOFA2 is missing.**

*Comment (excerpt):* "The software landscape contains MOFA2 … that is not discussed."

**Response.** MOFA2 has been added to the General-purpose frameworks section, distinguished from MOFA and MOFA+ as the actively maintained successor with different implementation, different API, and broad Bioconductor adoption. The previously attributed bulk/single-cell claims are now qualified to apply to MOFA2 in principle but to lack independent re-evaluation in the cited literature.

**M8. Reproducibility section conflates container presence with reproducibility.**

*Comment (excerpt):* "EMP itself is only evaluated against this standard by assertion … no re-execution benchmark is cited."

**Response.** The sentence exempting EMP from re-execution scrutiny has been removed. We now apply the same standard uniformly: the manuscript explicitly states that no independent re-execution benchmark exists for EMP on heterogeneous infrastructure in the cited literature, and the comparison matrix records this fact as a limitation that applies to most reviewed tools in equal measure.

### Minor comments (Reviewer 1)

1. **MUUMI miscategorisation (also M4).** Fixed (see M4 above).
2. **Redundant citation of BioNeuralNet (preprint vs. peer-reviewed).** We now cite the peer-reviewed publication at first mention and note the preprint only where it adds substantive content.
3. **"Versus" claims unsupported.** The implication that head-to-head data exist has been removed; the new Appendix A1 matrix now grounds each comparison in a specific card or marks it "not in cited card."
4. **Over-attribution of stage-agnosticism to gNOMO2.** We have moderated the wording to reflect that gNOMO2's "integration module" is benchmarked on four datasets but is not described in the cited literature as a fully validated integrative statistical engine.
5. **"Conceptually closer to the integrative Human Microbiome Project paradigm."** The HMP linkage has been removed; the remaining sentence states only the MultiAssayExperiment container fact.
6. **"Several critical caveats apply" numbered list.** Now formatted as a numbered list for consistency.
7. **PALM "experimentally perturbed edges" validation claim.** The specific phrasing has been replaced with "validation as described in the PALM card," since the cited excerpt does not specify "experimentally perturbed edges."
8. **"Conclusions are typically bound to a narrow slice of biological application."** This is now explicitly flagged as an author observation rather than a card-supported generalisation.
9. **"12 multi-omics datasets drawn primarily from TCGA" for MLMF.** The "primarily TCGA" qualifier has been removed; the statement now matches the card exactly.
10. **"Over twenty interactive visualisation tools"** has been corrected to "more than twenty" to match the single-cell analyst card.
11. **Spelling "behaviour" vs. "behavior."** Standardised to British English throughout, with the ref. 26 exception rewritten to use the same form.
12. **Reference for UMINT cited but never introduced.** The reference is now introduced in the Network-based and deep learning approaches section.
13. **Sentence-level hedging.** The repeated hedges ("is largely unknown," "remains unclear," "has not been independently demonstrated") have been consolidated into a single limitations paragraph in Critical perspectives.
14. **"Microbiome-aware preprocessing, compositional correction, or phylogeny-aware features as defaults" straw-man.** The claim has been weakened to "few of the surveyed tools offer all three as defaults," with HUMAnN/QIIME 2 cited as partial counter-examples.
15. **Title-level claim.** The title has been revised to remove the implicit centrality of EMP and to reflect the multi-omics integration landscape more broadly.
16. **Quantitative ceiling on benchmark coverage.** "Dozens of datasets" has been replaced with the precise counts from each card: "47 datasets [ref. 34] and 12 integration methods across three integration tasks [ref. 35]."
18. **"Single-cell analyst" vs. "single-cell Multi-omics analyst."** Standardised to the exact name in the cited card.
19. **Promotional close.** "Most defensible reading" has been replaced by "consistent with the current evidence base."
20. **Missing software-engineering axes.** The comparison matrix now includes a scalability column populated only with card-supported claims; "scalability" has been retained in the criteria list with the caveat that no independent runtime / memory measurements are provided.

We were unable to verify item 17 (WGCNA's use in recurrent pregnancy loss) directly from the cited review card; we have softened the attribution to "consistent with the discussion in [the WGCNA review]" pending direct verification.

---

## Reviewer 2 — microbiome & host–microbe biology (end user)

### Major comments

**1. Unsupported claim: EMP features a "natural-language-style pipeline syntax".**

*Comment (excerpt):* "This claim appears in at least four passages … there is no mention of natural-language syntax [in the EMP card]."

**Response.** All four occurrences have been removed or replaced with neutral, evidence-anchored language ("module-oriented, R-based interface," "five-module decomposition"). A single illustrative code-fragment-style example has been added in the EMP design section to let readers judge the interface claim independently.

**2. Unsupported claim: EMP "embeds microbiome-specific QC, taxonomic aggregation and pathway mapping".**

*Comment (excerpt):* "The card enumerates five modules but does not in the available excerpt specify that QC, taxonomic aggregation, and pathway mapping are among them."

**Response.** The triad has been replaced by "modules for extraction, preparation, support, analysis and visualisation of microbiome data," which is the exact module enumeration in the EMP card. The triad is reinstated only in passages that additionally cite the broader primary publication.

**3. Promotional / editorial tone about EMP.**

*Comment (excerpt):* "'excellent microbiome-oriented workflow', 'battle-tested Bioconductor back-end', 'defensible niche', 'well placed', 'indispensable', 'more accessible'."

**Response.** Each editorial adjective has been audited and replaced with a neutral, evidence-anchored equivalent. The "EasyMultiProfiler: design" closing has been rewritten as suggested by the reviewer. "Battle-tested" has been deleted. "Indispensable" and "more accessible" have been removed.

**4. Unfair comparison to single-cell and spatial tools.**

*Comment (excerpt):* "EMP is positioned as a microbiome-focused workflow … comparing it on a dimension it was never designed to address is unfair."

**Response.** The passage has been reframed as an explicit scope statement: "EMP is not designed to address single-cell or spatial multi-omics, which several of the cited tools explicitly target; these are out-of-scope for the workflow's documented model rather than a competitive gap."

**5. Unfair characterisation of mixOmics.**

*Comment (excerpt):* "'ergonomics are oriented to statisticians rather than bench scientists' … ref. 36 makes no claim about its target audience."

**Response.** The mixOmics audience-oriented sentence has been deleted. The remaining contrast now states only that EMP is a workflow-layer tool while MOFA-family and mixOmics-family methods are inferential engines, without any audience judgement.

**6. Unfair differentiation of EMP on host-context integration.**

*Comment (excerpt):* "This oversells the differentiation: [the gNOMO card] is explicitly framed as integrating 'meta-omics levels…with host/environmental context, tailored for non-model organisms'."

**Response.** The host-context differentiation has been reframed to the genuine dimensions — Bioconductor ecosystem, MultiAssayExperiment container, human/mouse focus — and the gNOMO non-model-organism scope is now acknowledged explicitly.

**7. Unsupported synergy claim between gNOMO2 and PALM.**

*Comment (excerpt):* "The card does not say PALM consumes tables from gNOMO/gNOMO2; this interdependence is inferred."

**Response.** The interdependence wording has been replaced by "PALM addresses a complementary problem (longitudinal dynamic network inference) rather than a downstream problem in the gNOMO/gNOMO2 workflow," and the figure-level description has been adjusted accordingly.

**8. Unsupported claim about PALM's validation strategy.**

*Comment (excerpt):* "Validation is performed against experimentally perturbed edges rather than against held-out samples."

**Response.** The "experimentally perturbed edges" phrase has been removed and replaced by a neutral description of the validation approach supported by the card.

**9. Unsupported contrast between MOFA and EMP's microbiome behaviour.**

*Comment (excerpt):* "This is an extrapolation beyond what the original MOFA card establishes."

**Response.** The passage has been restructured as an explicit research gap: "Whether MOFA's factor inference generalises to microbiome-style zero-inflated compositional data remains, to our knowledge, untested in the cited literature."

**10. Editorial framing of EMP's overall positioning.**

*Comment (excerpt):* "'Occupies a middle ground between fully featured but generalist platforms and narrowly specialised pipelines.' This is rhetorical positioning."

**Response.** The sentence has been replaced by: "EMP's documented scope places it alongside microbiome-focused pipelines such as gNOMO2 and Bioconductor-style frameworks such as timeOmics and pathwayMultiomics," which is a positional statement grounded in the cards.

**11. Insufficient independent verification of EMP's analytical components.**

*Comment (excerpt):* "The section concedes that … no independent comparison … is provided, yet the same section asserts EMP offers 'a coherent natural-language pipeline' and 'a clear host–microbiome focus'."

**Response.** All EMP-feature statements now use qualifying language such as "based on the EMP publication" or "as illustrated in the EMP card," and a paragraph has been added explicitly flagging what is not independently benchmarked.

**12. Repeated attribution to reviews that are only loosely relevant.**

*Comment (excerpt):* "Several passages cite reviews of EVs, tumour genomics, recurrent pregnancy loss and personalised oncology … as raising issues that EMP allegedly does or does not address."

**Response.** Each such passage has been re-grounded: where the interpretive connection is retained, it is now labelled as the author's interpretation; where a direct empirical source is available, it has been substituted.

**13. Heterogeneity claim overstated.**

*Comment (excerpt):* "Any two tools rarely share data structures, file conventions or evaluation metrics. Immediately afterwards the manuscript describes MultiAssayExperiment as a unifying data structure."

**Response.** Replaced by: "Data structure convergence around MultiAssayExperiment is partial; file conventions and evaluation metrics remain heterogeneous across the tools reviewed here."

### Minor comments (Reviewer 2)

1. **"Head-to-head comparison requires substantial engineering effort that most groups cannot afford."** Softened to "substantial engineering effort is typically required" with no claim about affordability.
2. **"Maximally modular ambition"** replaced by "broadest analytic span among the surveyed web platforms" with citation.
3. **"Advanced statistical machinery"** (PCA/PLS/sparse-PLS critique) replaced by neutral phrasing.
4. **"Battle-tested"** removed.
5. **MixOmics critique conflates the mixOmics package with DIABLO.** Fixed; the audience claim is removed entirely rather than reattributed.
6. **"Well placed to incorporate such provenance hooks."** Removed; the conditional/speculative sentence has been deleted.
7. **"Maximally modular ambition"** applied to the proteomics/transcriptomics/lipidomics platform overstates its scope. Replaced by "broad analytic span across proteomic, transcriptomic, lipidomic and other modalities."
8. **"Published evidence for EMP is largely benchmarked on human and mouse datasets."** Softened to "the EMP card's illustrated model is human/mouse gut microbiome and host multi-omics," removing the "benchmark" implication.
9. **"Shared and view-specific" vs. "shared and modality-specific."** Standardised to "shared and modality-specific" throughout, matching the original MOFA/MOFA+ terminology.
10. **"What a successful integration should demonstrate" / "what 'shared feature space' means"** are phrased as if there were a consensus. Both passages now acknowledge explicitly that no consensus exists.
11. **Figure-level PALM/gNOMO synergy claim.** Adjusted (see Major 7).
12. **"Tool marketed under a single 'integration' label"** quotation marks around "integration." The quotes have been dropped.
13. **PathwayMultiomics compositionality critique generalises from a single truncated abstract.** Softened to "the available excerpt does not address compositionality."
14. **Global pass to neutralise promotional phrasing.** Completed; all "battle-tested," "indispensable," "well placed," "defensible niche" occurrences have been audited.
15. **Citation density consistency.** The reviewer is correct that bracket citations are mixed with expository phrasing; we have retained the bracket convention throughout for consistency.

---

## Reviewer 3 — editor, citation integrity & balance

### Major comments

**1. Promotional language in the EMP section.**

*Comment (excerpt):* "'Excellent microbiome-oriented workflow' … 'battle-tested Bioconductor back-end,' 'lowers the activation energy,' 'coherent natural-language pipeline,' 'accessible, microbiologically literate integration environment rather than a research prototype.'"

**Response.** All such phrases have been removed. The section now opens with the neutral descriptor: "EMP is an R-based workflow that couples SummarizedExperiment/MultiAssayExperiment containers with a five-module pipeline (extraction, preparation, support, analysis, visualisation), illustrated on human and mouse host–microbiome cohorts."

**2. Unfair characterisation of MOFA/MOFA+ and mixOmics in the EMP section.**

*Comment (excerpt):* "Neither [the cited MOFA/MOFA+/mixOmics cards] supports these ergonomic or workflow-friction claims."

**Response.** The ergonomic editorialising has been deleted. The contrast now reads: "MOFA-family and mixOmics-family tools are inferential engines that take pre-aligned matrices as input, whereas EMP is presented as a workflow layer that prepares and integrates them within a MultiAssayExperiment container." This is grounded in the cards without any audience judgement.

**3. Unsupported negative framing of web-server platforms.**

*Comment (excerpt):* "'Web-server platforms with weaker reproducibility guarantees' … None of [the cited cards] documents reproducibility weaknesses."

**Response.** The clause has been deleted. The web-server section now discusses reproducibility per platform only where the cited card supports a statement.

**4. Claims about EMP features not in the EMP card.**

*Comment (excerpt):* "'Microbiome-specific QC, taxonomic aggregation and pathway mapping' … are not in the card."

**Response.** Replaced by "modules for extraction, preparation, support, analysis and visualisation of microbiome data" (the card's enumeration). The triad is reinstated only where the broader primary publication is cited.

**5. Misattribution to MUUMI as a method "handling incomplete blocks".**

*Comment (excerpt):* "Incomplete-block handling is not [MUUMI's] contribution. MLMF is the appropriate citation."

**Response.** Fixed; MUUMI has been removed from that clause and the incomplete-block matrix-factorisation tool (MLMF) is cited alone.

**6. Overstatement of the single-cell benchmark as spanning "dozens of datasets".**

*Comment (excerpt):* "[The cited card] benchmarks 12 integration methods across three integration tasks … not 'dozens of datasets.'"

**Response.** Replaced by "single-cell multi-omics benchmarks [the 47-dataset benchmark; the 12-method / 3-task benchmark]" with the dataset-count qualifier removed and the two sources kept distinct.

**7. Unsupported claim that DeepMoIC and MOADLN are configurable in either intermediate or late modes.**

*Comment (excerpt):* "Neither describes this configurability; both are described as intermediate (latent-fusion) architectures."

**Response.** The configurability claim has been dropped. The classification of DeepMoIC and MOADLN as intermediate-integration methods is now stated as an author taxonomy, with a note that downstream classification heads have been characterised as decision-level by other authors.

**8. "Feature-level deep architectures" mischaracterises CAEncoder.**

*Comment (excerpt):* "[CAEncoder] describes a contrastive adversarial encoder combining a Vision Transformer and CycleGAN trained end-to-end — not feature-level concatenation."

**Response.** CAEncoder has been reclassified as a contrastive / generative end-to-end deep model and removed from the early-integration example.

**9. Editorial claim about HMP framing of EMP is not in the EMP card.**

*Comment (excerpt):* "The EMP card makes no such comparison."

**Response.** The HMP-paradigm sentence has been removed. The remaining text states only the MultiAssayExperiment container fact.

**10. Critical assessment of EMP omits an explicit fairness check on alternatives.**

*Comment (excerpt):* "The asymmetry in available evidence affects all of these tools, not just EMP."

**Response.** A sentence has been added to the EMP section and to the Critical perspectives paragraph acknowledging that the absence of head-to-head statistical benchmarking is field-wide rather than EMP-specific, and that gNOMO2 and PALM are described in this review by their own internal benchmarks under the same constraint.

### Minor comments (Reviewer 3)

1. **Redundant citation of BioNeuralNet.** Fixed; peer-reviewed publication cited at first mention, preprint noted only where it adds substantive content.
2. **Long sentences impede readability.** The two flagged long sentences have been split.
3. **"Vertical-integration methods" terminology.** A one-line gloss has been added at first use.
4. **Duplicated material across sections.** The Critical perspectives section has been de-duplicated against the Benchmarking section.
5. **"With notable exceptions."** The exceptions are now named.
6. **Natural-language pipeline syntax.** All instances removed; a single illustrative code-fragment-style example has been added where the interface is discussed.
7. **Citation density in EMP paragraph 2.** The six-bracket sentence has been split, with comparative citations moved to a footnote.
8. **"These assumptions are not simultaneously testable with current benchmarks."** Softened to "and benchmarking studies have not, to date, formally distinguished these assumptions empirically."
9. **Section heading "EasyMultiProfiler: design, strengths and limitations relative to the alternatives."** Renamed to "Anchoring a microbiome workflow within Bioconductor: EasyMultiProfiler in context."
10. **Inconsistent tense.** Standardised to present tense throughout.
11. **"Head-to-head, multi-domain comparison" disconnect.** Acknowledged explicitly in the limitations paragraph; the new Appendix A1 matrix grounds each cell in a specific card.
12. **PathwayMultiomics compositionality caveat.** Reworded to "the available excerpt does not address compositionality," avoiding misdirected criticism of a tool that did not claim microbiome applicability.
13. **Quantitative claims without cards.** The "47 datasets" refrain has been consolidated into a single canonical statement with a forward reference.
14. **Minor typographical issues.** Hyphenation of "Bioconductor-native" and punctuation of "longitudinal microbiome multi-omics" have been standardised throughout.

---

We are grateful to all three reviewers for the rigour of their critique. The revised manuscript, in combination with the new comparison matrix and the scope/exclusions paragraph, addresses the substantive issues raised: promotional framing has been removed, claims about EMP and its alternatives have been re-grounded in the cited cards, tool coverage has been expanded, and the previously declarative evaluation criteria have been operationalised. We believe the manuscript is now suitable for publication.