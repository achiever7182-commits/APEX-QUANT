#pragma once
/**
 * config.h — Shared configuration for the C++ trading bot.
 *
 * Mirrors the Python config.py so both sides of the project use the same
 * default values for symbol, thresholds, cooldowns, and risk parameters.
 */

namespace config {

// Market / symbol
constexpr char kSymbol[]   = "BTCUSDT";
constexpr char kWsUrl[]    = "wss://stream.testnet.binance.vision/ws/btcusdt@trade";
constexpr char kRestBase[] = "https://testnet.binance.vision";

// Strategy parameters
constexpr double kThresholdPct = 0.25;  // tick momentum threshold (%) — comfortably exceeds exchange fees

// Risk / execution parameters
constexpr double kCooldownSeconds  = 15.0;
constexpr int    kMaxOpenPositions = 1;
constexpr double kMaxDailyLossPct  = 0.05;
constexpr double kPositionSizePct  = 0.02;

// REST API
constexpr int kRecvWindowMs = 5000;

}  // namespace config
