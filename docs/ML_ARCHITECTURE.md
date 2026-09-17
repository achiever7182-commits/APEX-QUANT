# APEX QUANT — Equity Machine Learning Prediction Architecture

## 1. Overview & System Objectives

The **Cross-Sectional ML Prediction Engine** (`ml/equity/`) provides a modular, reproducible, and mathematically rigorous machine-learning framework for Indian equities. It consumes feature sets from Step 4, aligns them with forward-looking return targets ($Y$), partitions data chronologically, trains multi-stock global models, evaluates cross-sectional forecasting ability (Spearman Information Coefficient), and manages versioned model artifacts under `models/equity/`.

```
Feature Set (Step 4 features/)
              ↓
Target Generation (ml/equity/targets.py: Forward Returns over [t, t+k])
              ↓
Point-in-Time Universe Filter (Step 3 universe/: Survivorship-Bias Safeguard)
              ↓
Chronological Split (ml/equity/split.py: Train < Val < Test)
              ↓
Multi-Stock Tabular Models (ml/equity/models.py: Naive, Ridge, RandomForest)
              ↓
Cross-Sectional Evaluation (ml/equity/evaluate.py: Spearman IC, Quantile Spreads)
              ↓
Model Registry (ml/equity/registry.py: Versioned Artifacts in models/equity/)
              ↓
Predictions Feed (Forwarded to Step 6 Stock Ranking)
```

---

## 2. Mathematical Target Formulation & Horizon Design

### A. Continuous Forward Return Targets (Regression)
For each asset $s$ at time $t$, the primary forecasting objective is the realized forward return over horizon $k \in \{1, 5, 10, 20\}$ trading sessions:
$$Y_{s,t,k} = \frac{Close_{s, t+k}}{Close_{s, t}} - 1.0$$

### B. Fundamental Distinction Between X and Y
- **Feature Vector $X_{s,t}$**: Formed strictly using information available at or before trading date $t$ (closing prices, moving averages, rolling volatility, volume up to session $t$).
- **Target Label $Y_{s,t,k}$**: The subsequent market outcome over $(t, t+k]$.
- **Tail Handling**: For the most recent $k$ trading sessions in the historical dataset, $Close_{t+k}$ has not occurred yet. The target evaluates to `NaN` and is excluded from training sets, while remaining eligible for live forward prediction.

### C. Binary Classification Target (Optional)
$$\text{TargetBinary}_{s,t,k} = \mathbf{1}\left(Y_{s,t,k} > \tau\right)$$
where $\tau$ is a configurable return hurdle (e.g. 0.0 or 0.005).

---

## 3. Survivorship-Bias Safeguards & Point-in-Time Universe

> [!IMPORTANT]
> **Strict Point-in-Time Universe Rule**:
> A training sample $(X_{s,t}, Y_{s,t})$ is admitted into the dataset **if and only if** symbol $s$ was an active constituent of the universe on calendar date $t$.

1. **Reconstitution Enforcement**: Historical reconstitution boundaries (e.g., JIOFIN admitted 2023-08-21, HDFCLTD delisted 2023-07-13, YESBANK removed 2020-03-27) are strictly enforced via `UniverseManager.nifty500.get_point_in_time_constituents(t)`.
2. **No Backward Projection**: Equities listed in the present day are never projected backward into historical training periods prior to their official index inclusion date.

---

## 4. Chronological Splitting & Walk-Forward Validation

### A. Chronological Splitter
To prevent temporal data leakage and regime contamination, datasets are **never randomly shuffled**. Multi-stock panels are partitioned strictly along sorted calendar dates:
- **Train Set**: $[T_{\text{start}}, T_{\text{val\_start}})$ (typically 70% of unique trading dates)
- **Validation Set**: $[T_{\text{val\_start}}, T_{\text{test\_start}})$ (typically 15% of trading dates)
- **Test Set**: $[T_{\text{test\_start}}, T_{\text{end}}]$ (final 15% of trading dates, held out untouched until final evaluation)

Invariant:
$$\max(\text{Train Dates}) < \min(\text{Val Dates}) < \min(\text{Test Dates})$$

### B. Walk-Forward Splitter
For backtest validation across shifting macro regimes, the `WalkForwardSplitter` generates expanding chronological folds:
- **Fold 1**: Train $[T_0, T_1]$, Validate $[T_1, T_2]$
- **Fold 2**: Train $[T_0, T_2]$, Validate $[T_2, T_3]$
- **Fold 3**: Train $[T_0, T_3]$, Validate $[T_3, T_4]$

---

## 5. Model Architectures & Preprocessing Isolation

### A. Tabular Baseline Models
1. **Naive Baseline (`NaiveBaselineModel`)**:
   - Predicts the historical training mean return: $\hat{y}_{s,t} = \mu_{\text{train}}$.
   - Establishes the floor benchmark: any viable machine learning model must statistically outperform this baseline.
2. **Linear Ridge Regression (`LinearEquityModel`)**:
   - $L_2$-regularized linear combination:
     $$\hat{y}_{s,t} = w^T X_{s,t} + b, \quad \min_w \|y - Xw\|_2^2 + \alpha \|w\|_2^2$$
   - Pipeline incorporates `SimpleImputer(strategy='median')` and `StandardScaler()`.
3. **Random Forest Regressor (`TreeEquityModel`)**:
   - Ensemble of non-linear decision trees with shallow maximum depth (`max_depth=6`), minimum leaf samples (`min_samples_leaf=20`), and deterministic random seeds (`random_state=42`) to prevent overfitting.

### B. Strict Preprocessing Isolation Invariant
All scalers, encoders, and median imputers are **fitted exclusively on the training split**:
```python
pipeline.fit(X_train, y_train)
```
The fitted parameters ($\mu_{\text{train}}, \sigma_{\text{train}}, \text{median}_{\text{train}}$) are applied frozen to validation and test splits. Test or validation observations never influence preprocessing parameters.

---

## 6. Model Evaluation & Cross-Sectional Diagnostics

Standard point-forecast metrics (RMSE, $R^2$) are insufficient for multi-stock trading, where relative ranking across stocks at time $t$ determines portfolio performance. `EquityEvaluator` computes both time-series and cross-sectional diagnostics:

### A. Time-Series Metrics
- **Mean Absolute Error (MAE)**: $\frac{1}{N}\sum |\hat{y}_i - y_i|$
- **Root Mean Squared Error (RMSE)**: $\sqrt{\frac{1}{N}\sum (\hat{y}_i - y_i)^2}$
- **Directional Accuracy**: $\%(\text{sign}(\hat{y}_i) == \text{sign}(y_i))$
- **Pearson Correlation**: $\rho(\hat{y}, y)$

### B. Cross-Sectional Information Coefficient (IC)
At each trading session $t$, the **Spearman Rank Correlation** between predicted returns and realized forward returns is evaluated across the active cross-section of stocks:
$$\text{IC}_t = \text{SpearmanCorr}\left(\{\hat{y}_{s,t}\}_{s \in U_t}, \{y_{s,t}\}_{s \in U_t}\right)$$

Summary diagnostics:
- **Mean IC**: $\mu_{\text{IC}} = \frac{1}{T}\sum_{t=1}^T \text{IC}_t$ (Values $> +0.03$ indicate meaningful predictive rank skill in quantitative equity research).
- **IC Volatility**: $\sigma_{\text{IC}}$
- **Information Ratio (IC_IR)**: $\frac{\mu_{\text{IC}}}{\sigma_{\text{IC}}}$
- **% Positive IC Days**: Percentage of trading sessions with $\text{IC}_t > 0$.

### C. Quantile Return Spreads
Predictions are partitioned into $Q$ cross-sectional quantiles (e.g. Quintiles $Q_1 \dots Q_5$) at each timestamp $t$. Realized future returns are averaged across each bucket to verify monotonicity:
$$\text{Spread} = \bar{R}(Q_{\text{top}}) - \bar{R}(Q_{\text{bottom}})$$

---

## 7. Model Artifact Management (`ModelRegistry`)

Trained models and their exact lineage are saved under `models/equity/`:
- **Model Binary**: `equity_v{N}.joblib`
- **Metadata Descriptor**: `equity_v{N}_meta.json` containing:
  - Model name & version
  - Target definition & horizon
  - Exact feature list and ordering
  - Train/Val/Test date bounds
  - Hyperparameters & random seed
  - Evaluated validation & test metrics

---

## 8. Anti-Leakage & Reproducibility Guarantees

1. **Features Isolation**: Mutating future rows ($t+1 \dots T$) produces zero variation in historical features ($t$).
2. **Target Isolation**: Forward return calculation uses `shift(-k)` only for $Y$. Features $X$ never reference negative shifts.
3. **Reproducibility**: Setting `random_state=42` guarantees bit-identical model weights, feature importances, and predictions across identical input datasets.

---

## 9. Regulatory & Quantitative Disclaimer

> [!CAUTION]
> **No Profitability Guarantee**:
> The models described in this subsystem are empirical machine-learning estimators designed to forecast relative return distributions and risk factors. Model outputs do NOT constitute guaranteed trading profits, automated buy/sell signals, or investment advice. Actual financial performance depends on downstream stock ranking (Step 6), portfolio optimization, transaction slippage, liquidity constraints, and market risk management.
