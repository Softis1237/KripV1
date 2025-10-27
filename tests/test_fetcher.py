from src.data.market_fetcher import MarketFetcher

fetcher = MarketFetcher()
data = fetcher.get_all_assets()
print("BTC Price:", data["BTC"]["current_price"])
print("ETH Funding Rate:", data["ETH"]["funding_rate"])
print("SOL RSI 7 (3m):", data["SOL"]["rsi7_3m"])