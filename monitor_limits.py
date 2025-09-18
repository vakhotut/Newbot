import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from blockchain import BlockchainManager
from config import BLOCKCYPHER_TOKEN, LITECOIN_API_KEY

async def main():
    blockchain = BlockchainManager(BLOCKCYPHER_TOKEN, LITECOIN_API_KEY)
    limits = await blockchain.check_api_limits()
    
    if limits:
        print("=== BlockCypher API Limits ===")
        print(f"Limit per hour: {limits['limit']}")
        print(f"Used this hour: {limits['used']}")
        print(f"Remaining: {limits['remaining']}")
        print(f"Usage: {limits['used']/limits['limit']*100:.1f}%")
        
        if limits['remaining'] < 50:
            print("\n⚠️  WARNING: Low API limits remaining!")
    else:
        print("Failed to retrieve API limits")

if __name__ == "__main__":
    asyncio.run(main())
