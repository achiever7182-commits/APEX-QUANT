export interface AccountSummary {
  mode: string;
  market_open: boolean;
  kill_switch: {
    active: boolean;
    reason?: string;
    engaged_at?: string;
    operator?: string;
  };
  broker: {
    name: string;
    trading_mode: string;
    connection_status: string;
    supports_live_orders: boolean;
  };
  initial_capital: number;
  cash: number;
  positions_value: number;
  total_equity: number;
  daily_pnl: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_fees: number;
  total_slippage: number;
  max_drawdown: number;
  positions_count: number;
  positions: Position[];
  last_reconciliation?: {
    status: string;
    is_clean: boolean;
  };
}

export interface Position {
  symbol: string;
  shares: number;
  average_cost: number;
  current_price: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  realized_pnl: number;
  last_updated: string;
}

export interface Order {
  order_id: string;
  client_order_id?: string | null;
  idempotency_key?: string | null;
  symbol: string;
  side: "BUY" | "SELL";
  order_type: string;
  requested_quantity: number;
  filled_quantity: number;
  unfilled_quantity: number;
  limit_price?: number | null;
  average_fill_price?: number | null;
  status: "PENDING" | "SUBMITTED" | "FILLED" | "REJECTED" | "CANCELLED" | "UNCERTAIN" | "PARTIALLY_FILLED";
  rejection_reason?: string | null;
  rejection_details?: string | null;
  created_at: string;
  validated_at?: string | null;
  submitted_at?: string | null;
  completed_at?: string | null;
  metadata?: Record<string, any>;
}

export interface Fill {
  fill_id: string;
  order_id: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: number;
  fill_price: number;
  transaction_fee: number;
  slippage_cost: number;
  timestamp: string;
}

export interface RealtimeQuote {
  symbol: string;
  exchange: string;
  timestamp: string | null;
  last_price: number;
  bid: number;
  ask: number;
  volume: number;
  open: number;
  high: number;
  low: number;
  previous_close: number;
  data_source: string;
  age_seconds: number | null;
}

export interface UniverseConstituent {
  symbol: string;
  company_name: string;
  sector: string;
  industry: string;
  isin: string | null;
  exchange: string;
  listing_status: string;
}

export interface ScannerItem {
  rank: number;
  symbol: string;
  company_name: string;
  price: number;
  day_change_pct: number;
  quant_score: number | null;
  predicted_return: number | null;
  confidence: number | null;
  prediction_status?: string;
  momentum: "Strong" | "Neutral" | "Weak";
  volatility: "Low" | "Medium" | "High";
  relative_strength: number;
  rsi_14: number;
  volatility_20d: number;
  sector: string;
  industry: string;
  risk_status: "PASS" | "WARNING" | "BLOCKED";
}

export interface StockBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface StockDetail {
  symbol: string;
  company_name: string;
  sector: string;
  industry: string;
  isin?: string | null;
  price: number;
  day_change: number;
  day_change_pct: number;
  open: number;
  high: number;
  low: number;
  previous_close: number;
  volume: number;
  quant_score: number | null;
  predicted_return_5d: number | null;
  confidence: number | null;
  prediction_status?: string;
  features: {
    rsi_14: number;
    volatility_20d_ann: number;
    volume_ratio_20d: number;
    relative_strength_5d: number;
  };
  risk: {
    max_allowed_weight_pct: number;
    current_portfolio_weight_pct: number;
    risk_status: "PASS" | "WARNING" | "BLOCKED";
    shares_owned: number;
  };
  bars: StockBar[];
}

export interface MLModelMeta {
  model_name: string;
  version: string;
  target_name: string;
  target_horizon: number;
  features: string[];
  training_start: string;
  training_end: string;
  validation_start: string;
  validation_end: string;
  test_start: string;
  test_end: string;
  created_at?: string;
  metrics: {
    val_mae: number;
    val_rmse: number;
    val_mean_ic: number;
    val_ic_ir: number;
    test_mae: number;
    test_rmse: number;
    test_mean_ic: number;
    test_ic_ir: number;
  };
  research_disclaimer: string;
}

export interface StrategyMetrics {
  name: string;
  total_return_pct: number;
  cagr_pct: number;
  calendar_cagr_pct: number;
  annualized_volatility_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  calmar_ratio: number;
  total_turnover: number;
  total_fees: number;
  total_slippage: number;
  total_costs: number;
  rebalance_count: number;
  trade_count: number;
  final_equity: number;
}

export interface BacktestResults {
  status: string;
  disclaimer: string;
  message?: string;
  period: {
    start_date: string;
    end_date: string;
    duration_months: number;
    rebalance_frequency: string;
    execution_convention: string;
    initial_capital: number;
    risk_free_rate: number;
  } | null;
  strategies: Record<string, StrategyMetrics>;
  benchmarks?: {
    buy_and_hold_return_pct?: number;
    equal_weight_return_pct?: number;
    cash_return_pct?: number;
  };
  walk_forward_periods?: Array<{
    period_id: string;
    return_pct: number;
    annualized_vol_pct: number;
    sharpe: number;
    max_drawdown_pct: number;
    turnover: number;
    costs: number;
  }>;
  equity_curve?: Array<{
    date: string;
    strategy: number;
    benchmark_bh: number;
    benchmark_eq: number;
  }>;
}

export interface RiskCheck {
  id: number;
  name: string;
  status: "PASS" | "WARNING" | "BLOCKED";
  current: string;
  limit: string;
  details: string;
}

export interface RiskStatus {
  mode: string;
  supports_live_orders: boolean;
  kill_switch: {
    active: boolean;
    reason?: string;
    engaged_at?: string;
    operator?: string;
  };
  overall_status: "HEALTHY" | "WARNING" | "BLOCKED";
  limits: {
    max_daily_loss_pct: number;
    max_drawdown_pct: number;
    max_single_stock_weight_pct: number;
    max_sector_weight_pct: number;
    max_gross_exposure_pct: number;
    liquidity_limit_pct: number;
  };
  utilization: {
    daily_loss_pct: number;
    drawdown_pct: number;
    gross_exposure_pct: number;
    max_stock_concentration_pct: number;
    max_stock_symbol: string;
    max_sector_concentration_pct: number;
    max_sector_name: string;
    cash: number;
    equity: number;
  };
  checks: RiskCheck[];
}

export interface ReconciliationReport {
  status: "MATCH" | "DISCREPANCY" | "ERROR";
  is_clean: boolean;
  audit_timestamp?: string;
  duration_ms?: number;
  discrepancies?: Array<{
    category: string;
    symbol?: string;
    expected: any;
    actual: any;
    details: string;
  }>;
  local_orders_count?: number;
  broker_orders_count?: number;
  local_fills_count?: number;
  broker_fills_count?: number;
  positions_match?: boolean;
  cash_discrepancy?: number;
}

export interface SystemHealthSummary {
  mode: string;
  supports_live_orders: boolean;
  market_session: string;
  is_market_open: boolean;
  kill_switch: {
    active: boolean;
    reason?: string;
  };
  initial_capital: number;
  cash: number;
  positions_value: number;
  total_equity: number;
  daily_pnl: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_fees: number;
  total_slippage: number;
  max_drawdown: number;
  positions_count: number;
  last_reconciliation?: ReconciliationReport;
  last_cycle?: any;
}

export interface RealtimeFeedHealth {
  status: "HEALTHY" | "DEGRADED" | "DOWN";
  market_session: string;
  connection_state: string;
  active_subscriptions: number;
  messages_received: number;
  valid_messages: number;
  invalid_messages: number;
  duplicate_messages: number;
  dropped_messages: number;
  reconnect_count: number;
  stale_quotes_count: number;
  last_receive_timestamp?: string;
  last_event_timestamp?: string;
}

export interface OperationalTelemetry {
  sessions_started: number;
  sessions_completed: number;
  sessions_failed: number;
  cycles_started: number;
  cycles_completed: number;
  orders_generated: number;
  orders_filled: number;
  orders_rejected: number;
  duplicate_orders: number;
  risk_rejections: number;
  data_errors: number;
  model_errors: number;
  execution_errors: number;
  reconciliation_errors: number;
  restart_recoveries: number;
  average_cycle_latency: number;
  maximum_cycle_latency: number;
  symbols_processed: number;
  symbols_rejected: number;
  current_session?: string | null;
  current_cycle?: string | null;
  current_state: string;
  last_successful_cycle?: string | null;
  last_error?: string | null;
  last_reconciliation_status?: string | null;
}

export interface SessionRecord {
  session_id: string;
  simulation_date: string;
  start_time: string;
  end_time?: string | null;
  state: string;
  cycle_count: number;
  orders_count: number;
  fills_count: number;
  fees: number;
  slippage: number;
  equity: number;
  cash: number;
  positions_value: number;
  realized_pnl: number;
  unrealized_pnl: number;
  drawdown: number;
  reconciliation_status: string;
  error_count: number;
  error_message?: string | null;
  cycles?: any[];
  positions_snapshot?: Record<string, any>;
}

export interface PaperPerformanceReport {
  disclaimer: string;
  universe: string[];
  date_range: { start?: string; end?: string };
  initial_capital: number;
  final_equity: number;
  total_return_pct: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_fees: number;
  total_slippage: number;
  total_costs: number;
  turnover: number;
  max_drawdown_pct: number;
  annualized_volatility_pct: number;
  sharpe_ratio?: number | null;
  sortino_ratio?: number | null;
  win_rate_pct: number;
  trade_count: number;
  sessions_count: number;
  simulation_seed?: number | null;
  model_version: string;
  data_source: string;
  equity_curve: Array<{
    session_id: string;
    simulation_date: string;
    equity: number;
    cash: number;
    drawdown: number;
  }>;
}

export interface SimulationRunConfig {
  sessions_count?: number;
  start_date?: string;
  initial_capital?: number;
  random_seed?: number;
  universe?: string[];
  slippage_bps?: number;
  transaction_cost_bps?: number;
  is_async?: boolean;
}

