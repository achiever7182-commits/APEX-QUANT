# APEX QUANT — Portfolio Construction & Risk Allocation Architecture

## 1. Overview & Architectural Philosophy

The **Portfolio Construction & Risk Allocation Subsystem** (`portfolio/`) bridges quantitative alpha signals and real-world capital management. It consumes the point-in-time ranked universe from Step 6 (`RankedUniverse`), instrument volatility, point-in-time returns, liquidity, sector taxonomy, and current holdings to produce a risk-constrained long-only cash equity portfolio with integer share quantities.

```
Step 6 RankedUniverse Snapshot + Point-in-Time Market Bars (<= T)
                                ↓
        Candidate Eligibility Screening (portfolio/constraints.py)
            - Price non-null & positive
            - ML forecast finite
            - Volatility finite
            - Sector metadata verified
            - Rejections tagged with explicit CandidateRejectionReason
                                ↓
        Point-in-Time Covariance Matrix Construction (portfolio/risk.py)
            - Historical aligned returns strictly <= T
            - Fallback diagonal variance detection with diagnostic flag
                                ↓
        Allocation Engine (portfolio/allocators.py & optimizer.py)
            - Equal Weight
            - Score Weighted
            - Inverse Volatility
            - Constrained Mean-Variance Optimizer (max mu^T w - (lambda/2) w^T Sigma w)
            - Fallback hierarchy: Constrained -> Score Weighted -> Equal Weight
                                ↓
        Integer Share Discretization & Cash Balancing (portfolio/portfolio_builder.py)
            - target_shares = floor(target_value / current_price)
            - residual_cash = total_capital - sum(actual_value) - estimated_costs
            - Zero negative cash guarantee
                                ↓
        Rebalancing Cost & Turnover Evaluation (portfolio/cost_model.py)
            - One-way turnover: 0.5 * sum(|w_target - w_current|)
            - Transaction cost & slippage in basis points
                                ↓
        Risk Contributions & Diagnostics Assembly (portfolio/diagnostics.py)
            - Marginal & percentage risk contributions (w_i * (Sigma w)_i / sigma_p^2)
            - HHI concentration & sector allocations
            - Structured PortfolioBuildResult
```

---

## 2. Step 6 to Step 7 Interface

Step 7 consumes the output of Step 6 directly without re-running machine learning or re-ranking stocks:

| Step 6 Output (`OpportunityRank`) | Step 7 Consumption |
| :--- | :--- |
| `symbol` | Portfolio instrument identifier |
| `rank` | Prioritized candidate selection |
| `opportunity_score` | Score-weighted allocation & candidate cutoff |
| `predicted_return` | Expected return vector $\mu$ in mean-variance optimization |
| `scoring_components.risk_adjusted_score` | Inverse-volatility proxy & risk adjustment |
| `sector` | Sector constraint checks ($\le \text{max\_sector\_weight}$) |
| `is_eligible` & `rejection_reason` | Initial eligibility screening |

---

## 3. Candidate Eligibility & Rejection Diagnostics

Candidates are screened prior to capital allocation. Excluded stocks receive an explicit `CandidateRejectionReason` code rather than being silently dropped:

| Check | Condition | Rejection Code |
| :--- | :--- | :--- |
| **Prior Step Eligibility** | Must be eligible in Step 6 | `OTHER` / Step 6 reason |
| **Price Validity** | Current price must be non-null, finite, and $> 0$ | `MISSING_PRICE` |
| **Prediction Validity** | Forecast $\hat{y}$ must be non-null and finite | `INVALID_PREDICTION` |
| **Volatility Validity** | Rolling volatility $\sigma$ must be non-null and $\ge 0$ | `INVALID_VOLATILITY` |
| **Sector Metadata** | Sector must not be empty or unclassified | `INVALID_SECTOR` |
| **Score Threshold** | Opportunity score must not be negative | `BELOW_MIN_SCORE` |

---

## 4. Portfolio Allocation Methods

The subsystem implements four distinct allocation strategies:

### A. Equal Weight (`equal_weight`)
Allocates equity capital equally across the top $K \le \text{max\_positions}$ candidates:
$$w_i = \min\left(w_{\max}, \frac{W_{\text{gross}}}{K}\right)$$
Subject to sector caps and single-stock ceilings.

### B. Score Weighted (`score_weighted`)
Allocates capital proportional to positive Step 6 Opportunity Scores:
$$w_i \propto \max(0, \text{Score}_i)$$
Iteratively projected into the constraint polytope ($\le w_{\max}$, $\le W_{\text{sector}}$, $\le W_{\text{gross}}$).

### C. Inverse Volatility (`inverse_volatility`)
Allocates inversely proportional to historical asset volatility:
$$w_i \propto \frac{1}{\sigma_{20d, i} + \epsilon}$$
Provides risk parity-like weighting across individual asset volatilities without full covariance.

### D. Constrained Mean-Variance Optimizer (`constrained`)
Solves the quadratic utility maximization problem:
$$\min_w \quad \frac{\lambda}{2} w^T \Sigma w - \mu^T w$$
Subject to:
1. $0 \le w_i \le \text{max\_single\_stock\_weight}$ (Long-only, no shorting)
2. $\sum_{i=1}^K w_i \le \text{max\_gross\_exposure}$ (Cash reserve buffer, no leverage)
3. $\sum_{i \in \text{sector } S} w_i \le \text{max\_sector\_weight}$ (Sector concentration limits)
4. (Optional) $\frac{1}{2}\sum |w_i - w_{0,i}| \le \text{max\_turnover}$ (Rebalance turnover ceiling)

Solved deterministically using `scipy.optimize.minimize` (SLSQP). If optimization fails to converge, falls back deterministically to `score_weighted` and then `equal_weight`.

---

## 5. Point-in-Time Risk Model & Covariance Matrix

Portfolio risk is evaluated via multi-asset covariance:
$$\sigma_{\text{portfolio}} = \sqrt{w^T \Sigma w}$$

### Invariants:
1. **Strict Lookahead Isolation**: Returns used to estimate $\Sigma$ are strictly $\le T$.
2. **Alignment & Sample Sufficiency**: Requires $\ge 5$ overlapping daily bars per pair over lookback window (default 60 days).
3. **Singularity Fallback**: If $\Sigma$ is ill-conditioned or missing assets, the risk model falls back to a regularized diagonal variance matrix ($\text{diag}(\sigma_i^2)$) and sets `is_covariance_fallback = True` in diagnostics.
4. **Risk Contributions**:
   - Marginal Risk Contribution: $\text{MRC}_i = \frac{(\Sigma w)_i}{\sigma_p}$
   - Percentage Risk Contribution: $\text{PRC}_i = \frac{w_i (\Sigma w)_i}{\sigma_p^2}$, where $\sum \text{PRC}_i = 1.0$.

---

## 6. Integer Share Discretization & Cash Handling

In Indian cash equity markets, trading occurs in discrete whole shares. The portfolio constructor implements integer discretization:

1. **Target Shares (Floor Rounding)**:
   $$\text{Shares}_i = \left\lfloor \frac{w_i \times \text{Total Capital}}{P_i} \right\rfloor$$
2. **Actual Position Value & Actual Weight**:
   $$\text{Value}_i = \text{Shares}_i \times P_i, \quad w_{\text{actual}, i} = \frac{\text{Value}_i}{\text{Total Capital}}$$
3. **Residual Cash & Transaction Costs**:
   $$\text{Cash}_{\text{remaining}} = \text{Total Capital} - \sum \text{Value}_i - \text{Estimated Costs}$$
4. **Zero Negative Cash Guarantee**: If transaction costs or price rounding causes cash to drop below zero, the largest position is decremented by 1 share until $\text{Cash} \ge 0$.

---

## 7. Rebalancing & Transaction Cost Model

When an existing portfolio is supplied, the builder evaluates rebalance deltas:
- $\Delta \text{shares}_i = \text{shares}_{\text{target}, i} - \text{shares}_{\text{current}, i}$
- Traded Dollar Volume: $\sum |\text{Value}_{\text{target}, i} - \text{Value}_{\text{current}, i}|$
- One-Way Turnover: $\tau = \frac{\text{Traded Dollar Volume}}{2 \times \text{Total Capital}}$
- Estimated Transaction Cost: $\text{Traded Dollar Volume} \times \frac{\text{cost\_bps} + \text{slippage\_bps}}{10000}$

---

## 8. Empirical Limitations & Research Disclaimers

> [!CAUTION]
> **Research Infrastructure Only — No Profitability Guarantee**:
> 1. **5-Stock Empirical Dataset**: Validations are conducted strictly on the 5-stock benchmark dataset (`RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`). No claim of full 500-stock scalability is made for this step.
> 2. **Transaction Cost Assumptions**: Basis-point fees (10 bps fee, 5 bps slippage) are stylized research assumptions, not guaranteed broker execution rates.
> 3. **Covariance Estimation**: Historical sample covariance is backward-looking and subject to estimation risk during regime shifts.
> 4. **Zero Execution**: This subsystem produces target portfolio specifications only. Broker execution, order management, and live trading are explicitly out of scope.
