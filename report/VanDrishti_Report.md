# VanDrishti: Technical Report on Aerial Tree Detection, Uncertainty-Controlled Degradation Monitoring, and Terrain-Aware Verification Routing

---

## 1. Abstract

VanDrishti is an end-to-end aerial remote sensing and field-routing analytics pipeline designed for forest conservation, statutory boundary monitoring, and field verification planning. The system integrates five core analytical modules: deep-learning individual tree crown detection, statutory corridor spatial tagging and audit prioritization, terrain-aware Dijkstra/Held-Karp field verification routing, multi-temporal LiDAR Canopy Height Model (CHM) degradation detection, and composite spatial forest health scoring. Evaluated on a 250 m × 250 m (6.25 ha) study area at the Ordway-Swisher Biological Station (OSBS), Florida, from the NSF National Ecological Observatory Network (NEON), every computational claim in this report is paired with an empirical validation test and explicit failure boundaries. The pipeline demonstrates automated cross-site portability via dynamic georeferencing and capability self-assessment, refusing execution when critical inputs are missing rather than generating uncalibrated outputs.

---

## 2. Data & Study Area

The primary experimental evaluation was conducted on airborne remote sensing datasets acquired over the Ordway-Swisher Biological Station (OSBS), Florida (Tile `407000_3284000`, projected in UTM Zone 17N, `EPSG:32617`). Cross-site portability was assessed using validation tiles from the Teakettle site (TEAK), California Sierra Nevada (`EPSG:32611`).

| Product | NEON ID | Date | Resolution |
|---|---|---|---|
| RGB orthomosaic | DP3.30010.001 | Sep 2018, Apr 2019 | 0.1 m |
| Canopy Height Model | DP3.30015.001 | Sep 2018, Apr 2019 | 1 m |
| Elevation (DTM/DSM) | DP3.30024.001 | Apr 2019 | 1 m |

### Temporal Acquisition Gap
An explicit methodological consideration is that the multi-temporal data comprises a September 2018 acquisition (end of wet growing season) and an April 2019 acquisition (early spring). This 7-month cross-seasonal interval represents a seasonal offset rather than an annualized anniversary pair. Phenological shifts, leaf-on versus leaf-off reflectance differences, and solar angle variations prevent reliable multi-temporal spectral index differencing. Consequently, structural LiDAR CHM differencing is employed as the primary degradation signal, while optical indices are restricted to supporting baseline roles.

> **Data Attribution:**  
> Data: NSF National Ecological Observatory Network (NEON), DP3.30010.001, DP3.30015.001, DP3.30024.001, OSBS and TEAK, 2018–2019. CC BY 4.0.

---

## 3. Individual Tree Detection & LiDAR Validation

Tree crowns were extracted from the 0.1 m ground sample distance RGB orthomosaic using the DeepForest deep-learning architecture (RetinaNet backbone pretrained on airborne forestry imagery). Inference was executed on 400 px × 400 px image chips with a 25% sliding-window overlap.

To filter candidate predictions, a multi-stage geometric and spatial deduplication pipeline was applied:

| Stage | Count |
|---|---|
| Raw detections | 1,998 |
| After box NMS (IoU 0.35) | 1,998 (−0) |
| After crown-size filter (1.5–30 m) | 1,993 (−5) |
| After centroid dedup (2 m) | 1,973 (−20) |
| Retained | 98.75% |

### Null Result in Geometric Post-NMS
A standard post-processing non-maximum suppression (NMS) step at an Intersection-over-Union (IoU) threshold of 0.35 eliminated zero bounding boxes (1,998 remaining). DeepForest internally suppresses overlapping detections during inference at IoU 0.15—a substantially more aggressive threshold. This demonstrates that duplicate bounding boxes from chip tiling were not the source of high detection density. Subsequent filtering based on biological crown diameter limits (1.5 m to 30 m) dropped 5 spurious detections, and metric centroid deduplication within a 2 m radius eliminated 20 proximal duplicates, retaining 1,973 valid tree crowns (98.75%).

### 3.1 Independent LiDAR Structural Validation
To validate detections against independent physical measurements, each detected crown centroid was cross-checked against the 1 m LiDAR Canopy Height Model (sampling the maximum CHM elevation within a 1.5 m radius):

- **99.05%** of detections coincide with measurable canopy height ($\ge 2\text{ m}$), exhibiting a median canopy height of **12.84 m**.
- Only **0.95%** (19 candidate detections) coincided with bare ground or short vegetation ($< 2\text{ m}$) and were discarded.

Because LiDAR returns represent direct physical time-of-flight measurements rather than optical spectral reflectance, this cross-sensor validation provides independent confirmation that detections correspond to genuine structural canopy.

### 3.2 Detection Confidence vs. Uncertainty Calibration

The relationship between detector confidence scores and physical canopy properties was evaluated by dividing all detections into confidence quintiles and assessing their corresponding LiDAR height distributions:

| Confidence quintile | n | Mean height | % under 2 m |
|---|---|---|---|
| 0.111–0.319 | 400 | 11.93 m | 3.5 |
| 0.319–0.401 | 399 | 12.57 m | 0.8 |
| 0.401–0.475 | 400 | 12.45 m | 0.0 |
| 0.475–0.575 | 399 | 12.98 m | 0.1 |
| 0.575–0.887 | 400 | 13.88 m | 0.2 |

Across the quintiles, mean canopy height varies by only +1.95 m (11.93 m to 13.88 m) and is non-monotonic (exhibiting a dip in Bin 3). Even within the lowest confidence tier (0.111–0.319), 96.5% of detections correspond to confirmed canopy $\ge 2\text{ m}$. 

This establishes that detector confidence in DeepForest tracks crown **size and visual prominence**, rather than true detection certainty or error probability. Lower-confidence bounding boxes identify smaller crowns rather than false alarms. The confidence-based HIGH-priority tier in Module 2 is retained strictly as a proxy for smaller, potentially vulnerable crowns requiring statutory audit, rather than as a statistical certainty tier. Transitioning to a direct CHM-based height priority metric represents an identified avenue for future refinement.

*Limitation stated plainly:* Formal precision and recall benchmarking against annotated field evaluation datasets (such as the NeonTreeEvaluation benchmark) was not conducted in this deployment; physical validation is reported via LiDAR height correspondence.

---

## 4. Terrain-Aware Verification Routing & Ablation Decomposition

Field verification routes for statutory corridor audits (visiting 13 HIGH-priority targets from a designated Ranger Entry Point) were optimized using exact open-path Traveling Salesperson Problem (TSP) optimization via the Held-Karp dynamic programming algorithm over an 8-connected 250 × 250 grid (1.0 m cell resolution).

The traversal cost model combines topographic slope impedance and structural canopy resistance:

$$\text{Traversal Cost} = \text{Tobler}(\text{slope from DTM}) \times (1.0 + 4.0 \times \text{CHM}_{\text{normalised}})$$

### 4.1 Routing Ablation Decomposition
To isolate the operational contributions of 2D vegetation indices, 3D LiDAR canopy models, and DTM slope costs, an identical set of audit waypoints was routed across four systematic configurations:

| Run | Impedance | Slope | Distance | Time | Steep cells within 5 m |
|---|---|---|---|---|---|
| A | ExG | no | 432.1 m | 20.28 min | 13 |
| B | CHM | no | 465.1 m | 16.60 min | 2 |
| C | flat | yes | 410.0 m | 20.27 min | 2 |
| D | CHM | yes | 488.9 m | 16.42 min | 2 |

#### Analysis of Factors:
1. **Vegetation Transition (ExG $\rightarrow$ CHM):** Replacing the 2D optical Excess Green index with 3D LiDAR CHM canopy height (Run A $\rightarrow$ Run B) reduced estimated traversal time by 18% (20.28 min $\rightarrow$ 16.60 min) and decreased proximity to steep cells ($> 20^\circ$) from 13 down to 2.
2. **Topographic Slope Contribution:** Adding Tobler slope cost on top of CHM canopy impedance (Run B $\rightarrow$ Run D) contributed an additional 1.1% traversal time reduction (16.60 min $\rightarrow$ 16.42 min) and yielded no additional steep-cell avoidance.

*Finding:* Terrain slope does not dominate route selection at the OSBS study site. Because total topographic relief is 9.79 m and the P95 slope is 12.04°, canopy structure is the primary factor governing route impedance. Topographic slope is a validated but low-impact term at OSBS; its contribution is expected to be substantially larger in high-relief terrain such as the Sierra Nevada TEAK site. *(Note: This expectation is a testable prediction for high-relief environments, not an empirical finding of the current site).*

### 4.2 Runtime Benchmark Comparison
All comparison baselines are evaluated dynamically at runtime:
- **Nearest-Neighbor (NN) Baseline:** The greedy NN heuristic produces a 449.58 m path on the ExG surface. By failing to optimize the global sequence, it leaves Tree #644 as an isolated final stop, forcing an inefficient 72.94 m backtrack.
- **Held-Karp Exact TSP:** Resolves global visiting order, eliminating backtracking and yielding 432.13 m on ExG and 488.90 m (14.96 min) on the full terrain+CHM surface (a 5.4% time reduction relative to the 15.81 min terrain NN baseline).

### 4.3 Methodological Caveats
- **Divergent Objectives:** Total path length (432.1 m) and travel time (488.9 m / 16.42 min) optimize different objective functions. The distance-optimal path traverses dense canopy, whereas the time-optimal path detours into open clearings. A longer physical path that avoids thick vegetation is operationally preferable.
- **Vegetation Weight Calibration:** The vegetation impedance coefficient ($w_{\text{veg}} = 4.0$) is an uncalibrated design parameter. Without empirical GPS field tracking across vegetation types, results must be interpreted as relative improvements rather than absolute travel times.

### 4.4 Topographic Characterization
Elevation across the OSBS study tile spans 25.97 m to 35.76 m (total relief: 9.79 m). The slope distribution exhibits a mean of 5.76°, median of 5.19°, P95 of 12.04°, and maximum of 41.05°. Steep cells exceeding 30° comprise 20 pixels (0.032% of the tile), clustered in 5 localized features of 4 m² to 11 m² extent. 

*Reporting standard:* These features are characterized strictly by their geometric dimensions; they are not ascribed to specific geomorphic landforms (such as karst sinkhole margins or sandhill features) without ground-truth geological confirmation.

---

## 5. Multi-Temporal Canopy Degradation & Uncertainty Disambiguation

Multi-temporal LiDAR CHM differencing ($\Delta H = \text{CHM}_{2019} - \text{CHM}_{2018}$) serves as the primary instrument for detecting canopy loss. Spectral change indices were excluded from primary loss classification due to seasonal reflectance divergence over the 7-month interval.

### 5.1 Validation Tests

| Test | Result | Reading |
|---|---|---|
| Horizontal misregistration | optimal shift (0,0), RMSE 2.162 unchanged | no co-registration error |
| Loss/growth asymmetry | 1,941 vs 763 px at ±5 m (2.5:1) | asymmetric, not noise |
| Edge concentration | loss pixels at 2.86x mean CHM gradient | edges are ambiguous |
| Interior-only ratio | 6.92:1 at ≥5 m; 16.40:1 at ≥10 m | signal strengthens when edges excluded |
| Survivor anti-correlation | lift 0.24x / 0.61x / 0.91x at R=0/1/2 | loss sits away from standing crowns |
| Before/after heights | 8.5 m → 0.0 m at interior loss pixels | complete canopy removal |

#### Interpretation of Validations:
- **Misregistration Check:** Cross-correlation searching between 2018 and 2019 CHMs revealed an optimal shift of (0, 0) pixels, confirming sub-pixel horizontal alignment.
- **Canopy Edge Artifacts:** Pixels indicating height loss were concentrated by a factor of 2.86× on high-gradient canopy edges ($|\nabla\text{CHM}| \ge 2.0\text{ m}$). Variations in flight trajectory and scan angle between campaigns introduce return-point ambiguity along crown perimeters.
- **Interior Stand Disambiguation:** Restricting analysis to low-gradient canopy interior ($|\nabla\text{CHM}| < 2.0\text{ m}$) increased the loss-to-growth ratio from 2.5:1 to **6.92:1 at $\ge 5\text{ m}$** and **16.40:1 at $\ge 10\text{ m}$**. Because biological height gains of $\ge 5\text{ m}$ over 7 months are physically impossible, growth observations establish an empirical sensor noise ceiling.
- **Survivor Anti-Correlation:** Detections from 2019 imagery show spatial anti-correlation with interior loss locations (lift of 0.24× at centroid, 0.61× at 1 m, 0.91× at 2 m). Because removed trees are absent from 2019 imagery, this anti-correlation is consistent with actual canopy clearing rather than spatially random sensor noise (which would yield a lift of $\approx 1.0$).

### 5.2 Quantified Net Interior Canopy Removal
Within the low-gradient interior canopy footprint, the quantified degradation budget is:

```
Interior loss   ≥5 m : 249 px
Interior growth ≥5 m :  36 px   ← empirical noise floor
Net interior removal : 213 m² (0.34% of 6.25 ha study area)
```

*Methodological boundary:* Net removal estimation is restricted strictly to the $\ge 5\text{ m}$ threshold. The minor height-loss tier (2 m to 5 m, exhibiting a 1.73:1 asymmetry) cannot be reliably decoupled from inter-flight point density noise and is reported only as gross unadjusted change.

### 5.3 Tree-Level Attribution Analysis
Attempts to map interior loss pixels directly to individual 2019 tree crowns yielded only $n=3$ matches at the centroid. Expanding the search radius to 2 m yielded 663 overlapping detections; however, a spatial null model using randomized point sets produced identical overlap rates (lift factors of 0.24× at 0 m, 0.61× at 1 m, and 0.91× at 2 m—at or below chance).

*Negative finding reported plainly:* Direct individual-tree attribution of loss events is unsupported by the spatial data. Tree loss is reported strictly at the raster pixel and vectorized polygon level.

### 5.4 Full-Tile Canopy Classification

| Class | ΔH | Pixels | % |
|---|---|---|---|
| Removal | ≤ −5 m | 1,941 | 3.11 |
| Thinning | −5 to −2 m | 1,941 | 3.11 |
| Stable | −2 to +2 m | 56,732 | 90.77 |
| Growth | ≥ +2 m | 1,886 | 3.02 |

Vectorization of contiguous loss zones ($\ge 4\text{ m}^2$) identified 105 total loss polygons, of which 58 represent severe removal ($\Delta H \le -5\text{ m}$, encompassing a combined area of 271 m², with a median polygon size of 4 m² and maximum of 8 m²). The absence of large single-tree polygons (10 m² to 30 m²) indicates that observed losses correspond predominantly to localized branch shedding, selective thinning, or crown margin trimming.

The full-tile mean $\Delta H$ is −0.262 m, and the median canopy height shifted from 9.27 m (2018) to 9.08 m (2019), confirming the absence of vertical datum calibration offsets.

---

## 6. Composite Forest Health Scoring

Forest health is evaluated across a regular 25 m × 25 m grid ($10 \times 10 = 100$ cells), integrating three LiDAR-derived physical structural metrics:

1. **Canopy Cover ($w = 0.30$):** Fractional area with height $\ge 2.0\text{ m}$.
2. **Structural Diversity ($w = 0.30$):** Standard deviation of canopy height among vegetated pixels.
3. **Interior Degradation Penalty ($w = 0.40$):** Density of validated interior loss pixels ($\Delta H \le -5\text{ m}, |\nabla\text{CHM}| < 2\text{ m}$). Degradation carries the highest weight because it captures dynamic structural loss, ensuring that cleared high-canopy stands do not receive high scores.

| Metric | Value |
|---|---|
| Score mean / std | 60.3 / 15.5 |
| Min / median / max | 19.1 / 64.6 / 96.9 |
| Grades | A=7, B=43, C=25, D=25 |
| Mean canopy cover | 0.729 |
| Mean height std | 3.18 m |

### 6.1 Weight Sensitivity Analysis

To evaluate whether cell rankings reflect physical metrics rather than arbitrary weighting choices, health scores were recalculated under alternative weight combinations and compared against the headline score using Spearman rank correlation ($\rho$):

| Variant | Spearman ρ |
|---|---|
| Equal weights | +0.987 |
| Cover only | +0.464 |
| Diversity only | +0.192 |
| Degradation only | +0.682 |

#### Findings:
- The correlation of $\rho = +0.987$ under equal weights confirms that cell relative rankings are stable and driven by underlying physical measurements rather than weight distribution.
- No single component exhibits $\rho > 0.70$, indicating that the index functions as a balanced composite score rather than a surrogate for a single variable.

### 6.2 Operational Limitations
1. **Relative Normalization:** Component values are min-max normalized relative to the current study tile. An "A" grade denotes a cell within the upper quartile of the local site; it does not imply absolute ecological climax state. Cross-site comparisons require standardized baseline reference tiers.
2. **Stated Weight Formulation:** The assigned weights ($0.30 / 0.30 / 0.40$) represent a stated management heuristic rather than a regression model fitted to ecological ground truth.

---

## 7. Regional Thermal Context & Satellite Scale Considerations

Regional thermal anomalies are integrated via the NASA FIRMS Active Fire API (VIIRS 375 m Near Real-Time product, recording Fire Radiative Power in MW).

### Spatial Scale Mismatch
A single VIIRS sensor pixel (375 m ground footprint) exceeds the entire 250 m × 250 m study area. Incorporating thermal pixel values directly into the 25 m Forest Health Score would assign an identical constant across all 100 cells, introducing false precision. Consequently, active fire monitoring is maintained as an independent macro-scale situational context layer and is deliberately excluded from high-resolution micro-grid health computations.

---

## 8. Cross-Site Portability & System Self-Assessment

The VanDrishti architecture is configured via declarative site manifests (`config.yaml`). Raster Coordinate Reference Systems are ingested dynamically from file metadata (`src.crs`), avoiding hardcoded projections or coordinate bounds.

A central capability self-assessment engine inspects available input rasters at runtime and categorizes module execution status into three tiers:
- **FULL:** All required rasters are present.
- **DEGRADED:** Module executes using a fallback input (e.g., ExG optical proxy in the absence of LiDAR CHM).
- **BLOCKED:** Required input data is absent; the pipeline halts execution for that module rather than generating unverified partial outputs.

| Site | CRS | Full | Degraded | Blocked |
|---|---|---|---|---|
| OSBS | EPSG:32617 | 6 | 0 | 0 |
| TEAK | EPSG:32611 | 3 | 1 | 2 |

### Demonstration on TEAK (California Sierra Nevada)
Evaluating the system on the TEAK validation dataset demonstrated expected degradation and blocking behavior:
- `detection`, `priority`, and `fire` executed at **FULL** capability.
- `routing` operated in **DEGRADED** mode (generating a CHM canopy-guided route with flat terrain assumptions due to missing DTM elevation).
- `degradation` and `health_score` were **BLOCKED** because only a single-epoch CHM was provided.

*Scope:* This test confirms software configuration portability across geographic projections (`EPSG:32617` $\rightarrow$ `EPSG:32611`); it does not constitute full multi-site scientific validation.

---

## 9. Limitations & Future Work

1. **Absence of Standard Detection Benchmarking:** Precision and recall were not benchmarked against standardized tree crown datasets (such as the NeonTreeEvaluation benchmark). Detections are validated through independent LiDAR height correspondence.
2. **Portability vs. Multi-Site Validation:** Evaluation on the TEAK site proved codebase portability and capability blocking on single-epoch data; full ecological multi-site validation remains future work.
3. **Uncalibrated Vegetation Impedance:** The vegetation traversal penalty coefficient ($w_{\text{veg}} = 4.0$) is uncalibrated against GPS-tracked field movement timings.
4. **Topographic Slope Impact in Low Relief:** The routing ablation demonstrated that slope impedance is negligible at OSBS (9.79 m relief). The contribution of terrain-aware routing remains to be tested in steep, high-relief environments.
5. **Lack of Tree-Level Loss Attribution:** Statistical overlap tests demonstrated that individual-tree loss attribution is indistinguishable from random chance. Canopy loss must be reported at the spatial polygon and pixel level.
6. **Relative Health Scoring:** Forest health scores reflect intra-tile relative distributions rather than standardized absolute ecological scales.
7. **Cross-Seasonal Acquisition Gap:** The 7-month interval between September 2018 and April 2019 limits multi-temporal optical spectral analysis due to seasonal phenological divergence.
8. **Synthetic Project Corridor:** The infrastructure corridor polygon utilized for spatial tagging represents a synthetic planning boundary rather than an active engineering right-of-way.
