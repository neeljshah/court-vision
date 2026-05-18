"""Chain & wallet abstraction.

Execution happens on two different chains:
  - Polymarket CLOB orders settle on Polygon (USDC.e), signed EIP-712
  - SX Bet orders settle on SX Chain (USDC), signed EIP-712 with a different domain

A syndicate running ParlayX needs one order intent to flow through both
without the execution engine caring which chain it lands on. The Wallet
protocol is that seam. Concrete impls would wrap eth_account / web3.py;
here they're stubbed to keep the router read-only.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ChainCtx:
    name: str                # "polygon" | "sx"
    rpc_url: str
    chain_id: int
    settlement_token: str    # USDC address
    gas_token: str           # MATIC | SX


POLYGON = ChainCtx(
    name="polygon",
    rpc_url="https://polygon-rpc.com",
    chain_id=137,
    settlement_token="0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC.e
    gas_token="MATIC",
)

SX_CHAIN = ChainCtx(
    name="sx",
    rpc_url="https://rpc.sx.technology",
    chain_id=416,
    settlement_token="0xaa99bE3356a11eE92c3f099BD7a038399633566f",  # USDC on SX
    gas_token="SX",
)


class Wallet(Protocol):
    """One interface, two chains. Execution engine doesn't branch on venue."""
    address: str
    chain: ChainCtx

    def balance(self) -> float: ...                     # settlement-token USD
    def sign_order(self, payload: dict) -> str: ...     # EIP-712 signature
    def estimate_gas_usd(self, payload: dict) -> float: ...


class DryRunWallet:
    """Stub that logs instead of signing. Swap for a real eth_account wallet
    when live trading is enabled. Keeps the router capital-safe by default."""

    def __init__(self, address: str, chain: ChainCtx, balance_usd: float = 0.0):
        self.address = address
        self.chain = chain
        self._balance = balance_usd

    def balance(self) -> float:
        return self._balance

    def sign_order(self, payload: dict) -> str:
        return f"0xDRYRUN_{self.chain.name}_{hash(frozenset(payload.items())) & 0xFFFFFF:06x}"

    def estimate_gas_usd(self, payload: dict) -> float:
        # Polygon ~ $0.01/tx, SX Chain ~ free-ish. Rough constants.
        return 0.01 if self.chain.name == "polygon" else 0.001


def wallet_for(chain_name: str, address: str = "0xDRYRUN", balance_usd: float = 1_000_000) -> DryRunWallet:
    ctx = {"polygon": POLYGON, "sx": SX_CHAIN}.get(chain_name)
    if not ctx:
        raise ValueError(f"unknown chain: {chain_name}")
    return DryRunWallet(address=address, chain=ctx, balance_usd=balance_usd)
