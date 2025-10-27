import asyncio
from src.data.market_fetcher import MarketFetcher

async def main():
    async with MarketFetcher() as fetcher:
        data = await fetcher.get_all_assets()
        print("Market data:")
        for symbol, info in data.items():
            print(f"{symbol}: {info}")

if __name__ == "__main__":
    asyncio.run(main())