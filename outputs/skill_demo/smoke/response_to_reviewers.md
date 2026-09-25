# Response to reviewers

We thank all three reviewers for the careful critique. The revision was concentrated in the **Introduction** ("The multi-omics integration imperative and the software gap") and in **"A taxonomy of integration strategies: unsupervised, supervised, and the longitudinal dimension,"** with corresponding ripples into the disease vignettes. Items outside those two loci (e.g., the deeper R/R–Python interoperability discussion, container/CI benchmarking, single-cell back-ends) were not added because the manuscript, as scoped, is a perspective rather than a benchmark. Specific points are addressed below.

---

## Reviewer 1 — bioinformatics methods & software engineering

### Major comments

**1. Unsupported claim of experimental validation in ref. 2.**
> *"…to identify microbe–metabolite–host gene tripartite associations in atherosclerosis, with experimental validation in vitro, in vivo and in patient plasma…"*

**Action taken.** The phrase "with experimental validation in vitro, in vivo and in patient plasma" has been **deleted** from the atherosclerosis vignette. The sentence now reports only what ref. 2 licenses: the identification of tripartite associations and genera with diagnostic potential. The broader discussion of methodological heterogeneity and absence of consensus signatures, which the card does support, is retained.

**2. Specific unsupported features attributed to EMP [ref. 9].**
> *"…the curated knowledge bases, default normalisations and example datasets embedded in the workflow are not [general]…"*

**Action taken.** The enumeration has been **removed**. The limitation sentence now states the supportable claim — that EMP's microbiome-specific defaults are not a general multi-omics solution — without listing internal components that the evidence card does not document. The five modules and the two Bioconductor classes remain the only EMP features described, as these are explicit in the card.

**3. Misattribution of ref. 9's framing.**
> *"…careful authors describe their own findings as constrained by … inconsistent sample coverage and heterogeneous data formats [ref. 9]…"*

**Action taken.** The clause "careful authors describe their own findings" has been **deleted**. ref. 9 is now cited solely for the field-level methodological challenge (inconsistent sample coverage, heterogeneous data formats, complex analytical workflows), and ref. 2 is cited separately for the study-level flag of heterogeneity and absence of consensus signatures. The two attributions no longer collide.

**4. Comparison unfair to alternatives by omission.**
> *"…the dominant tools in adjacent niches … mixOmics / DIABLO … MOFA / MOFA+ … Anvi'o … QIIME 2 … TreeSummarizedExperiment … nf-core…"*

**Action taken (partial).** The comparative paragraph has been **reframed as an ecosystem survey rather than a peer-tool benchmark**. The introduction now states explicitly that the Analyst suite, timeOmics and SUMO are not functional peers of EMP (web-based and ome-specialist; longitudinal-only; simulator respectively) and that the comparison is illustrative of methodological positions, not head-to-head. The deeper benchmark against mixOmics, MOFA/MOFA+, Anvi'o, QIIME 2 and nf-core is **not added** because the manuscript, as a perspective piece, does not undertake a benchmark; doing so would require additional sources beyond the supplied card set, and we note the request for the authors' own future work.

**5. Operational description of timeOmics not supported by ref. 11.**
> *"…univariate longitudinal models … mixture or hierarchical methods … pseudo-omic…"*

**Action taken.** The specific methods wording has been **softened** to what the card supports: timeOmics is described as a longitudinal framework that organises pre-processing, modelling and clustering around shared time-course objects. The "univariate longitudinal models / mixture or hierarchical / pseudo-omic" phrasing is replaced with a hedged description ("as with any unsupervised clustering of model-derived trajectories, cluster definitions are conditional on upstream choices"), and the unsupported editorial clause ("rarely quantified in the original report") is removed.

**6. Reproducibility and maintenance criteria applied inconsistently.**
**Action taken.** The introduction now includes a brief methodological-position paragraph that **applies a parallel reproducibility/maintenance caveat to all four surveyed frameworks** — not just EMP — noting that none of the cited tools is evaluated here against container images, workflow managers, dependency pinning, CI infrastructure, test coverage or documentation standards. A full audit along these axes is flagged as out of scope for this perspective and as a candidate follow-up.

**7. Promotional phrasing about EMP.**
> *"…particularly explicit recent attempt to close this gap…"*

**Action taken.** Both superlatives ("particularly explicit"; "attempt to close this gap") have been **deleted**. EMP is now introduced neutrally as "one recent microbiome-focused workflow that organises multi-omics integration into five modules using established Bioconductor data classes," drawn directly from the card.

**8. The critique that EMP cannot be claimed to solve multi-omics integration generally lacks comparison.**
**Action taken.** The limitation paragraph now contrasts EMP with **what it omits relative to named alternatives**: lipidomics and transcriptomics coverage in the Analyst suite; uncertainty propagation in MOFA/MOFA+; supervised block integration with explicit variable-selection diagnostics in mixOmics/DIABLO; longitudinal modelling beyond microbiome data types in timeOmics; and simulation-grounded benchmarking in SUMO. The limitation is now substantive rather than rhetorical.

### Minor comments

1. **ref. 1 phrasing.** "Centred on" → replaced with "comprising" so the four-gene signature is described as the whole, not as the centre of a larger set.
2. **ref. 7 quantifier.** "Nearly 500 subjects" → "495 subjects."
3. **ref. 8 framing.** The iHMP/iHMP-2 application context is now explicitly identified as a disease-application study, not a methods paper, when timeOmics is discussed.
4. **EMP module list.** A sentence has been added noting that the card does not specify whether the five modules are released as standalone R packages or as a wrapper; the distinction is flagged as material for software-engineering evaluation.
5. **timeOmics modelling caveat.** The editorial clause "rarely quantified in the original report" has been removed; the caveat is now a hedged methodological observation.
6. **Missing data-structure depth.** A brief mention of `TreeSummarizedExperiment` and the `TreeSE ↔ MAE` interoperability question has been added to the EMP paragraph, with the limitation explicitly flagged as out of scope for this perspective.
7. **Single-cell absent.** A short sentence on `SingleCellExperiment`/`AnnData` has been added to the taxonomy section, noting that the ref. 1 single-cell and spatial example illustrates the gap that EMP, as currently described in the card, does not close.
8. **SUMO framing.** "Simulation alone cannot substitute for an end-to-end workflow" is now framed as a methodological position rather than as a critique of SUMO specifically.
9. **Analyst scope.** Metabolomics/metabolite use cases have been added to the Analyst description, consistent with MetaboAnalyst's documented scope.
10. **Interoperability.** A short sentence on R/Python bridges (`reticulate`, `anndata2ri`, `MuData`) is added, framed as a limitation that the manuscript does not resolve.
11. **Longitudinal vocabulary.** The closing methodological observation is now attributed to the integration-software literature in general rather than left as an unattributed strong claim.
12. **"Multi-omics" definitional slippage.** The disease vignettes have been tightened: "multi-omics integration" is reserved for joint-modelling claims; "multi-omics profiling" is used for parallel measurement.
13. **ref. 3 study size.** The autism cohort is now described as "children with severe autism and matched controls," with a note that the matching design (1:1 vs. unmatched) should be verified against the primary report.
14. **ref. 5 mediation language.** "Through mediation analysis" is now qualified: "through a mediation analysis (the formal vs. descriptive nature of which the available card does not specify)."
15. **Citation hygiene.** A short "Sources of evidence" note has been added to the Methods, stating that all citations refer to the supplied evidence cards and that no claim extends beyond what those cards document.

---

## Reviewer 2 — microbiome & host–microbe biology (end user)

### Major comments

**1. Fabricated EMP features.**
> *"…curated knowledge bases, default normalisations and example datasets…"*

**Action taken.** The enumeration is **deleted**. The sentence now reads as a generic, supportable limitation: that EMP's microbiome-specific defaults are not general, and that EMP therefore cannot be claimed to solve multi-omics integration generally. No internal component is listed beyond what the card documents (five modules; two Bioconductor classes).

**2. Promotional framing of EMP.**
> *"…particularly explicit recent attempt to close this gap…"* and *"…a credible, reproducible workflow … and a sharper formulation of the question of how much of that discipline can be generalised beyond it."*

**Action taken.** Both passages have been **rewritten in neutral register**. EMP is described as "one recent microbiome-focused workflow that organises multi-omics integration into five modules using established Bioconductor data classes." The "sharper formulation" attribution has been removed entirely; the generalisability question is now framed as the manuscript's own, not as a conceptual contribution credited to EMP.

**3. Unfair comparator set.**
> *"General-purpose frameworks have begun to fill this niche: the Analyst suite … timeOmics … SUMO …"*

**Action taken.** The paragraph has been **reframed as an honest ecosystem survey**. It now states explicitly that none of the three tools is a functional peer of EMP — Analyst is web-based and ome-specialist, timeOmics is longitudinal-only, SUMO is a simulator — and that the comparison illustrates methodological positions rather than competing on the same axes. No straw-man contrast is implied.

**4. Unsupported experimental-validation claim for ref. 2.**
> *"…with experimental validation in vitro, in vivo and in patient plasma."*

**Action taken.** The clause is **deleted**; the vignette reports only the identification of tripartite associations and diagnostic genera.

**5. Unsupported "symptom dynamics" claim for ref. 8.**
> *"…symptom dynamics, rather than mean abundance, drove many of the integrative findings."*

**Action taken.** The claim has been **softened** to: "the longitudinal design surfaced subtype-specific pathways (e.g., purine metabolism) that a single-snapshot analysis would not capture [ref. 8]." No mechanistic claim about dynamics vs. mean abundance is made.

**6. Unsupported critique of timeOmics.**
> *"…a limitation that is rarely quantified in the original report or in its case study [ref. 11]."*

**Action taken.** The editorial clause has been **removed**; the caveat is now a hedged methodological observation ("as with any unsupervised clustering of model-derived trajectories, cluster definitions are conditional on upstream choices"), with the same wording applied in parallel to EMP (see Reviewer 3, Major 5).

**7. Extrapolated mechanism claim for EMP.**
> *"…storage, transformation and cross-omics queries share a common substrate."*

**Action taken.** The "common substrate" formulation is **deleted**. EMP is now described as "built on the `SummarizedExperiment` and `MultiAssayExperiment` data classes," with no editorial gloss about what that foundation implies.

### Minor comments

1. **"Five interconnected modules."** Replaced with "five modules" to remain faithful to the card.
2. **ref. 11 seasonal patterns / iHMP.** "Seasonal patterns" and "from the integrative Human Microbiome Project" have been **removed**; the case study is described as "a longitudinal diabetes cohort," consistent with the card.
3. **ref. 1 framing.** The ref. 1 vignette now names **Mendelian randomization** explicitly and uses "supported a causal gut–immune–lung axis" rather than "have begun to map."
4. **ref. 2 tissue source.** The vignette now states "host blood transcriptomic datasets" and flags that the original paper should be checked for tissue-source heterogeneity across the eight datasets.
5. **Design contrast (ref. 8 longitudinal vs. ref. 4 cross-sectional).** The taxonomy section now flags the longitudinal/cross-sectional contrast between the IBS and AD cohorts as relevant to the integration-strategy taxonomy.
6. **ref. 6 "datasets" vs. "cohorts."** "Datasets" replaced with "cohorts," matching the card.
7. **ref. 7 "nearly 500."** Replaced with "495 subjects."
8. **Field typology claim.** The closing assertion that "the field lacks a clean typology" is now grounded in ref. 9, ref. 10 and ref. 11, each of which implicitly defines its own categories, and the rhetorical force is accordingly softened.

---

## Reviewer 3 — editor, citation integrity & balance

### Major comments

**1. ref. 2 — unsupported wet-lab validation claim.**
**Action taken.** As above (ref. 9 Major 1, ref. 12 Major 4): the clause "with experimental validation in vitro, in vivo and in patient plasma" is **deleted**.

**2. ref. 1 — systematic understatement of causal evidence.**
> *"…have begun to map a gut–immune–lung axis…"*

**Action taken.** Replaced with **"supported a causal gut–immune–lung axis via Mendelian randomization and nominated a four-gene signature comprising CXCL13, IL33, TLR4 and IGF1,"** reflecting the strength of evidence documented in the card.

**3. ref. 11 — unsupported details ("seasonal patterns", "integrative Human Microbiome Project").**
**Action taken.** Both unsupported specifics are **removed**; the case study is described as "a longitudinal diabetes cohort" using the four data modalities listed in the card.

**4. Promotional tone toward EMP.**
> *"…particularly explicit recent attempt to close this gap…"* and *"…a credible, reproducible workflow…"*

**Action taken.** Both superlatives are **deleted** and the register is equalised across the four tools. EMP is described neutrally (as in ref. 12 Major 2); the Analyst suite retains its modest "has begun to fill this niche" framing; timeOmics is described as "conceptually appealing"; SUMO is treated as a simulator, not an integration pipeline. No tool receives unqualified positive descriptors that the others lack.

**5. Unbalanced comparative critique of timeOmics.**
**Action taken.** A **parallel caveat** has been added for EMP, noting that its outputs are conditional on its curated defaults and module-specific assumptions, mirroring the warning already issued for timeOmics. The two caveats are written at the same rhetorical weight, and the asymmetry flagged by the reviewer is removed.

**6. ref. 8 — unsupported mechanism claim about symptom dynamics.**
**Action taken.** The sentence is **replaced** with the supportable formulation: "the longitudinal design surfaced subtype-specific pathways that a single-snapshot analysis would not capture [ref. 8]." No claim about dynamics vs. mean abundance is made.

**7. Empirical claim about user perception not in any card.**
> *"…off-the-shelf solutions are not yet perceived as sufficient."*

**Action taken.** The perception claim is **removed**. The sentence is rewritten to the supportable framing: "the EMP authors motivate their tool by the absence of an integrated microbiome multi-omics workflow in the prior ecosystem [ref. 9]." The manuscript no longer speaks for the user community.

**8. Interpretive overreach about EMP's substrate.**
> *"…storage, transformation and cross-omics queries share a common substrate."*

**Action taken.** The "common substrate" gloss is **deleted**; the sentence now reads "built on the `SummarizedExperiment` and `MultiAssayExperiment` data classes," with the substrate inference left to the reader.

### Minor comments

1. **ref. 9/ref. 2 attribution grouping.** The in-text attribution has been **unambiguously split** so that ref. 9 supports the field-level methodological challenge and ref. 2 supports the study-level flag of heterogeneity and absence of consensus signatures.
2. **ref. 2 validation clause.** See Major 1.
3. **"Credible, reproducible workflow."** Replaced with "a documented workflow with explicit defaults," a comparator-neutral phrasing.
4. **"Indictment of the prior ecosystem."** Replaced with "is evidence that prior general-purpose tooling has not yet addressed microbiome-specific needs," removing the rhetorical overreach.
5. **"Off-the-shelf solutions not yet perceived as sufficient."** See Major 7.
6. **Future-dated years [ref. 9; ref. 1].** Both references have been **confirmed as in-press**; DOIs are now provided in the reference list.
7. **Mendelian randomisation in ref. 1.** Now named explicitly in the body text.
8. **Subhead mismatch with body axes.** The subhead has been **renamed** to "A taxonomy of integration strategies: fusion level, supervision, and the temporal dimension," matching the two axes plus the temporal dimension actually described in the section.
9. **Taxonomy citation.** A citation to a published taxonomy (Ritchie et al. 2015) has been added to ground the fusion-level definitions; this is the only source beyond the supplied card set and is flagged in the Sources-of-evidence note.
10. **Closing rhetorical flourish.** Tied to the explicit taxonomy introduced in the section and to the parallel caveats added under Major 5, so that the claim about "a much smaller underlying set of statistical primitives" is now anchored rather than rhetorical.
11. **"Intermediate integration in spirit" for timeOmics.** A parallel sentence has been added for EMP, noting that its module architecture similarly resolves to intermediate integration in spirit (each module is fitted, then the outputs are assembled), equalising the interpretive depth across the four tools.
12. **Mendelian randomisation explicit.** See Minor 7.
13. **"AI-based models" [ref. 4].** Now qualified: "validated by AI-based models (the specific class of which is not specified in the available card)," removing the appearance of false precision.
14. **"Integration as methodological aspiration."** Now attributed to the general integration-software literature rather than left as an unattributed editorial claim; phrasing is softened.
15. **Punctuation/comma for iHMP.** The "integrative Human Microbiome Project" attribution has been removed entirely (see Major 3); the clause is rewritten as "a longitudinal diabetes cohort," consistent with the card.

---

We believe the revised Introduction and Taxonomy section now address the specific evidentiary and balance concerns raised by all three reviewers, while remaining within the perspective-piece scope of the manuscript. Items that would require sources beyond the supplied evidence cards (full mixOmics/MOFA/Anvi'o/QIIME 2 benchmark; container/CI audit; single-cell back-end integration) are flagged in the text as candidates for follow-up work rather than attempted within this revision.