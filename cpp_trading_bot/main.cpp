#include "config.h"

#include <ixwebsocket/IXWebSocket.h>
#include <nlohmann/json.hpp>
#include <curl/curl.h>
#include <openssl/crypto.h>
#include <openssl/hmac.h>

#include <atomic>
#include <algorithm>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <limits>
#include <mutex>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using json = nlohmann::json;
using namespace std::chrono_literals;

// Import shared config constants into this translation unit's anonymous namespace.
namespace {
using config::kSymbol;
using config::kWsUrl;
using config::kRestBase;
using config::kThresholdPct;
using config::kCooldownSeconds;
using config::kMaxOpenPositions;
using config::kMaxDailyLossPct;
using config::kPositionSizePct;
using config::kRecvWindowMs;

std::atomic<bool> g_stop{false};

void handleSignal(int) {
    g_stop.store(true);
}

std::string timestamp(bool milliseconds = true) {
    const auto now = std::chrono::system_clock::now();
    const auto time = std::chrono::system_clock::to_time_t(now);
    std::tm local{};
#ifdef _WIN32
    localtime_s(&local, &time);
#else
    localtime_r(&time, &local);
#endif

    std::ostringstream out;
    out << std::put_time(&local, "%H:%M:%S");
    if (milliseconds) {
        const auto millis = std::chrono::duration_cast<std::chrono::milliseconds>(
            now.time_since_epoch()) % 1000;
        out << '.' << std::setfill('0') << std::setw(3) << millis.count();
    }
    return out.str();
}

long long epochMilliseconds() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

std::string hmacSha256(const std::string& secret, const std::string& data) {
    unsigned char digest[EVP_MAX_MD_SIZE]{};
    unsigned int digestLength = 0;
    HMAC(EVP_sha256(), secret.data(), static_cast<int>(secret.size()),
         reinterpret_cast<const unsigned char*>(data.data()), data.size(),
         digest, &digestLength);

    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (unsigned int i = 0; i < digestLength; ++i) {
        out << std::setw(2) << static_cast<unsigned int>(digest[i]);
    }
    return out.str();
}

size_t writeResponse(char* data, size_t size, size_t count, void* userData) {
    auto* response = static_cast<std::string*>(userData);
    response->append(data, size * count);
    return size * count;
}

struct Position {
    double entryPrice{};
    double size{};
    std::string entryTime;
};

struct ClosedTrade {
    double entryPrice{};
    double exitPrice{};
    double size{};
    double pnl{};
    std::string entryTime;
    std::string exitTime;
};

class BinanceRestClient {
public:
    BinanceRestClient(std::string apiKey, std::string apiSecret)
        : apiKey_(std::move(apiKey)), apiSecret_(std::move(apiSecret)) {
        curl_global_init(CURL_GLOBAL_DEFAULT);
    }

    ~BinanceRestClient() {
        curl_global_cleanup();
    }

    double fetchUsdtBalance() const {
        const auto response = signedRequest("GET", "/api/v3/account", "");
        const auto body = json::parse(response.body);
        for (const auto& balance : body.at("balances")) {
            if (balance.at("asset") == "USDT") {
                return std::stod(balance.at("free").get<std::string>());
            }
        }
        throw std::runtime_error("USDT balance was not present in account response");
    }

    struct OrderResult {
        double fillPrice{};
        double executedQuantity{};
        std::string orderId;
    };

    OrderResult marketOrder(const std::string& side, double quantity) const {
        std::ostringstream params;
        params << "symbol=" << kSymbol
               << "&side=" << side
               << "&type=MARKET"
               << "&quantity=" << std::setprecision(16) << quantity;
        const auto response = signedRequest("POST", "/api/v3/order", params.str());
        const auto body = json::parse(response.body);

        const double executedQuantity = std::stod(body.value("executedQty", "0"));
        double fillPrice = 0.0;
        if (body.contains("fills") && !body.at("fills").empty()) {
            double quoteTotal = 0.0;
            for (const auto& fill : body.at("fills")) {
                const double fillQuantity = std::stod(fill.at("qty").get<std::string>());
                quoteTotal += fillQuantity * std::stod(fill.at("price").get<std::string>());
            }
            fillPrice = executedQuantity > 0.0 ? quoteTotal / executedQuantity : 0.0;
        }
        if (fillPrice == 0.0) {
            const double quoteTotal = std::stod(body.value("cummulativeQuoteQty", "0"));
            fillPrice = executedQuantity > 0.0 ? quoteTotal / executedQuantity : 0.0;
        }
        if (executedQuantity <= 0.0 || fillPrice <= 0.0) {
            throw std::runtime_error("Binance returned an order without an executed fill");
        }
        std::string orderId = "unknown";
        if (body.contains("orderId")) {
            if (body["orderId"].is_number()) {
                orderId = std::to_string(body["orderId"].get<int64_t>());
            } else if (body["orderId"].is_string()) {
                orderId = body["orderId"].get<std::string>();
            } else {
                orderId = body["orderId"].dump();
            }
        }
        return {fillPrice, executedQuantity, orderId};
    }

private:
    struct Response {
        long httpStatus{};
        std::string body;
    };

    Response signedRequest(const std::string& method, const std::string& path,
                           const std::string& parameters) const {
        std::ostringstream query;
        if (!parameters.empty()) query << parameters << '&';
        query << "recvWindow=" << kRecvWindowMs << "&timestamp=" << epochMilliseconds();
        const std::string queryString = query.str();
        const std::string url = std::string(kRestBase) + path + "?" + queryString
                              + "&signature=" + hmacSha256(apiSecret_, queryString);

        CURL* curl = curl_easy_init();
        if (!curl) throw std::runtime_error("curl_easy_init failed");
        std::string body;
        struct curl_slist* headers = nullptr;
        headers = curl_slist_append(headers, ("X-MBX-APIKEY: " + apiKey_).c_str());
        headers = curl_slist_append(headers, "Content-Type: application/x-www-form-urlencoded");

        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeResponse);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &body);
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 15L);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);
        curl_easy_setopt(curl, CURLOPT_USERAGENT, "binance-testnet-cpp-bot/1.0");
        if (method == "POST") {
            curl_easy_setopt(curl, CURLOPT_POST, 1L);
            // All parameters are already present in the signed query string.
            // Sending them again in the body would change Binance's signed payload.
            curl_easy_setopt(curl, CURLOPT_POSTFIELDS, "");
        }

        const CURLcode result = curl_easy_perform(curl);
        long httpStatus = 0;
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpStatus);
        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
        if (result != CURLE_OK) {
            throw std::runtime_error(std::string("HTTP request failed: ") + curl_easy_strerror(result));
        }
        if (httpStatus < 200 || httpStatus >= 300) {
            throw std::runtime_error("Binance HTTP " + std::to_string(httpStatus) + ": " + body);
        }
        return {httpStatus, body};
    }

    std::string apiKey_;
    std::string apiSecret_;
};

class TickMomentumStrategy {
public:
    enum class Signal { Hold, Buy, Sell };

    Signal onPrice(double price, bool inPosition) {
        if (!referencePrice_) {
            referencePrice_ = price;
            return Signal::Hold;
        }
        const double changePct = (price - *referencePrice_) / *referencePrice_ * 100.0;
        if (!inPosition && changePct >= kThresholdPct) {
            referencePrice_ = price;
            return Signal::Buy;
        }
        if (inPosition && changePct <= -kThresholdPct) {
            referencePrice_ = price;
            return Signal::Sell;
        }
        return Signal::Hold;
    }

    void setReference(double price) { referencePrice_ = price; }

private:
    std::optional<double> referencePrice_;
};

struct SharedState {
    mutable std::mutex mutex;
    double currentPrice{};
    std::string currentSignal = "HOLD";
    std::optional<Position> position;
    double realizedPnl{};
    double unrealizedPnl{};
    std::vector<ClosedTrade> tradeHistory;
    int tradeCount{};
    int winCount{};
    int lossCount{};
    double lastTradePnl{};
    bool hasLastTrade{false};
    std::chrono::steady_clock::time_point lastTradeTime{};
};

bool cooldownExpired(const SharedState& state) {
    if (state.tradeCount == 0) return true;
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - state.lastTradeTime).count()
        >= kCooldownSeconds;
}

std::string positionText(const std::optional<Position>& position) {
    if (!position) return "NONE";
    std::ostringstream out;
    out << "LONG@" << std::fixed << std::setprecision(2) << position->entryPrice;
    return out.str();
}

void printStatus(const SharedState& state) {
    std::lock_guard<std::mutex> lock(state.mutex);
    const int closedTrades = state.winCount + state.lossCount;
    const double winRate = closedTrades ? 100.0 * state.winCount / closedTrades : 0.0;
    std::ostringstream line;
    line << '[' << timestamp() << "] price=" << std::fixed << std::setprecision(2) << state.currentPrice
         << " | signal=" << state.currentSignal
         << " | position=" << positionText(state.position)
         << " | realized_PnL=" << std::showpos << state.realizedPnl
         << " | unrealized_PnL=" << state.unrealizedPnl
         << " | trades=" << std::noshowpos << state.tradeCount
         << " | win_rate=" << std::fixed << std::setprecision(1) << winRate << "%";

    const double colorPnl = state.unrealizedPnl != 0.0 ? state.unrealizedPnl : state.lastTradePnl;
    if (colorPnl > 0.0) std::cout << "\033[32m";
    else if (colorPnl < 0.0) std::cout << "\033[31m";
    std::cout << line.str() << "\033[0m\n" << std::flush;
}

void timerLoop(SharedState& state) {
    while (!g_stop.load()) {
        std::this_thread::sleep_for(1s);
        if (!g_stop.load()) printStatus(state);
    }
}

void printSummary(const SharedState& state, std::chrono::steady_clock::duration duration) {
    std::lock_guard<std::mutex> lock(state.mutex);
    const int closedTrades = state.winCount + state.lossCount;
    const double winRate = closedTrades ? 100.0 * state.winCount / closedTrades : 0.0;
    double largestWin = 0.0;
    double largestLoss = 0.0;
    for (const auto& trade : state.tradeHistory) {
        largestWin = std::max(largestWin, trade.pnl);
        largestLoss = std::min(largestLoss, trade.pnl);
    }
    std::cout << "\nFINAL SESSION SUMMARY\n"
              << "Total trades: " << state.tradeCount << '\n'
              << "Total realized P&L: " << std::showpos << state.realizedPnl << " USDT\n"
              << "Win rate: " << std::noshowpos << winRate << "%\n"
              << "Session duration: " << std::chrono::duration<double>(duration).count() << " seconds\n"
              << "Largest single win: " << std::showpos << largestWin << " USDT\n"
              << "Largest single loss: " << largestLoss << " USDT\n";
}
} // namespace

int main() {
    std::signal(SIGINT, handleSignal);
    const char* apiKey = std::getenv("BINANCE_TESTNET_API_KEY");
    const char* apiSecret = std::getenv("BINANCE_TESTNET_API_SECRET");
    if (!apiKey || !apiSecret || std::strlen(apiKey) == 0 || std::strlen(apiSecret) == 0) {
        std::cerr << "Set BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET first.\n";
        return 1;
    }

    try {
        BinanceRestClient rest(apiKey, apiSecret);
        const double startingBalance = rest.fetchUsdtBalance();
        SharedState state;
        TickMomentumStrategy strategy;
        ix::WebSocket websocket;
        std::atomic<bool> connected{false};
        std::mutex websocketMutex;
        const auto sessionStart = std::chrono::steady_clock::now();

        websocket.setUrl(kWsUrl);
        websocket.enablePong();
        websocket.setOnMessageCallback([&](const ix::WebSocketMessagePtr& message) {
            if (message->type == ix::WebSocketMessageType::Open) {
                connected.store(true);
                std::cout << '[' << timestamp(false) << "] WebSocket connected.\n";
                return;
            }
            if (message->type == ix::WebSocketMessageType::Close) {
                connected.store(false);
                if (!g_stop.load()) std::cerr << '[' << timestamp(false) << "] WebSocket disconnected: " << message->closeInfo.reason << "\n";
                return;
            }
            if (message->type == ix::WebSocketMessageType::Error) {
                connected.store(false);
                std::cerr << '[' << timestamp(false) << "] WebSocket error: " << message->errorInfo.reason << "\n";
                return;
            }
            if (message->type == ix::WebSocketMessageType::Ping) {
                // IXWebSocket sends Pong frames automatically when enablePong()
                // is enabled; no application-level JSON response is needed.
                return;
            }
            if (message->type != ix::WebSocketMessageType::Message) return;

            try {
                const auto tick = json::parse(message->str);
                const double price = std::stod(tick.at("p").get<std::string>());
                bool shouldBuy = false;
                bool shouldSell = false;
                double requestedSize = 0.0;
                Position closingPosition{};
                {
                    std::lock_guard<std::mutex> lock(state.mutex);
                    const bool inPosition = state.position.has_value();
                    const auto signal = strategy.onPrice(price, inPosition);
                    state.currentPrice = price;
                    state.currentSignal = signal == TickMomentumStrategy::Signal::Buy ? "BUY" : signal == TickMomentumStrategy::Signal::Sell ? "SELL" : "HOLD";
                    if (state.position) state.unrealizedPnl = (price - state.position->entryPrice) * state.position->size;

                    shouldBuy = signal == TickMomentumStrategy::Signal::Buy
                        && !inPosition
                        && !state.position.has_value()
                        && kMaxOpenPositions > 0
                        && cooldownExpired(state)
                        && state.realizedPnl > -startingBalance * kMaxDailyLossPct;
                    if (shouldBuy) requestedSize = startingBalance * kPositionSizePct / price;

                    shouldSell = signal == TickMomentumStrategy::Signal::Sell
                        && inPosition
                        && cooldownExpired(state);
                    if (shouldSell) closingPosition = *state.position;
                }

                if (shouldBuy) {
                    try {
                        const auto order = rest.marketOrder("BUY", requestedSize);
                        std::lock_guard<std::mutex> orderLock(state.mutex);
                        state.position = Position{order.fillPrice, order.executedQuantity, timestamp(false)};
                        state.tradeCount++;
                        state.lastTradeTime = std::chrono::steady_clock::now();
                        std::cout << '[' << timestamp(false) << "] BUY executed at " << order.fillPrice << " | order=" << order.orderId << "\n";
                    } catch (const std::exception& error) {
                        strategy.setReference(price);
                        std::cerr << '[' << timestamp(false) << "] BUY failed: " << error.what() << "\n";
                    }
                } else if (shouldSell) {
                    try {
                        const auto order = rest.marketOrder("SELL", closingPosition.size);
                        std::lock_guard<std::mutex> orderLock(state.mutex);
                        const double pnl = (order.fillPrice - closingPosition.entryPrice) * closingPosition.size;
                        state.realizedPnl += pnl;
                        state.unrealizedPnl = 0.0;
                        state.tradeHistory.push_back({closingPosition.entryPrice, order.fillPrice, closingPosition.size, pnl, closingPosition.entryTime, timestamp(false)});
                        state.position.reset();
                        state.tradeCount++;
                        state.lastTradePnl = pnl;
                        state.hasLastTrade = true;
                        state.winCount += pnl > 0.0;
                        state.lossCount += pnl < 0.0;
                        state.lastTradeTime = std::chrono::steady_clock::now();
                        std::cout << '[' << timestamp(false) << "] SELL executed at " << order.fillPrice << " | P&L=" << pnl << " | order=" << order.orderId << "\n";
                    } catch (const std::exception& error) {
                        strategy.setReference(price);
                        std::cerr << '[' << timestamp(false) << "] SELL failed: " << error.what() << "\n";
                    }
                }
            } catch (const std::exception& error) {
                std::cerr << '[' << timestamp(false) << "] Invalid tick: " << error.what() << "\n";
            }
        });

        std::thread timer(timerLoop, std::ref(state));
        int backoffSeconds = 1;
        std::cout << "Starting Binance testnet bot on " << kSymbol
              << " | USDT balance=" << std::fixed << std::setprecision(2)
              << startingBalance << "\n"
              << "Connecting to " << kWsUrl << " (Ctrl+C to stop)\n";
        websocket.start();
        while (!g_stop.load()) {
            std::this_thread::sleep_for(1s);
            if (!connected.load() && !g_stop.load()) {
                std::cerr << '[' << timestamp(false) << "] Reconnecting in " << backoffSeconds << "s...\n";
                std::this_thread::sleep_for(std::chrono::seconds(backoffSeconds));
                if (g_stop.load()) break;
                {
                    std::lock_guard<std::mutex> lock(websocketMutex);
                    websocket.stop();
                    websocket.start();
                }
                backoffSeconds = std::min(backoffSeconds * 2, 30);
            } else if (connected.load()) {
                backoffSeconds = 1;
            }
        }

        websocket.stop();
        timer.join();
        printSummary(state, std::chrono::steady_clock::now() - sessionStart);
    } catch (const std::exception& error) {
        std::cerr << "Fatal startup error: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
