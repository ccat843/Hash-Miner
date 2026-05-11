from __future__ import annotations

from dataclasses import dataclass
from web3 import Web3
from web3.contract import Contract

from hash_miner.types import MiningSnapshot

_MINER_ABI = [
    {"inputs": [], "name": "miningState", "outputs": [
        {"internalType": "uint256", "name": "era", "type": "uint256"},
        {"internalType": "uint256", "name": "reward", "type": "uint256"},
        {"internalType": "uint256", "name": "difficulty", "type": "uint256"},
        {"internalType": "uint256", "name": "minted", "type": "uint256"},
        {"internalType": "uint256", "name": "remaining", "type": "uint256"},
        {"internalType": "uint256", "name": "epoch", "type": "uint256"},
        {"internalType": "uint256", "name": "epochBlocksLeft_", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "genesisComplete", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "miner", "type": "address"}], "name": "getChallenge", "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "nonce", "type": "uint256"}], "name": "mine", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
]

_ERROR_SELECTORS = {
    Web3.keccak(text="InsufficientWork()").hex()[:10]: "InsufficientWork",
    Web3.keccak(text="ProofAlreadyUsed()").hex()[:10]: "ProofAlreadyUsed",
    Web3.keccak(text="BlockCapReached()").hex()[:10]: "BlockCapReached",
    Web3.keccak(text="GenesisNotComplete()").hex()[:10]: "GenesisNotComplete",
    Web3.keccak(text="SupplyExhausted()").hex()[:10]: "SupplyExhausted",
}


@dataclass
class ContractAdapter:
    w3: Web3
    contract: Contract

    @classmethod
    def build(cls, w3: Web3, contract_address: str) -> "ContractAdapter":
        return cls(w3=w3, contract=w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=_MINER_ABI))

    def snapshot(self, miner: str) -> MiningSnapshot:
        era, reward, difficulty, minted, remaining, epoch, left = self.contract.functions.miningState().call()
        complete = self.contract.functions.genesisComplete().call()
        challenge = self.contract.functions.getChallenge(Web3.to_checksum_address(miner)).call()
        return MiningSnapshot(era, reward, difficulty, minted, remaining, epoch, left, complete, challenge)

    def call_mine(self, miner: str, nonce: int) -> None:
        self.contract.functions.mine(nonce).call({"from": Web3.to_checksum_address(miner)})

    def build_mine_tx(self, miner: str, nonce: int, account_nonce: int, chain_id: int, max_fee_per_gas: int, max_priority_fee_per_gas: int) -> dict:
        return self.contract.functions.mine(nonce).build_transaction({
            "from": Web3.to_checksum_address(miner),
            "nonce": account_nonce,
            "chainId": chain_id,
            "maxFeePerGas": max_fee_per_gas,
            "maxPriorityFeePerGas": max_priority_fee_per_gas,
        })

    @staticmethod
    def decode_revert(exc: Exception) -> str:
        msg = str(exc)
        for selector, name in _ERROR_SELECTORS.items():
            if selector in msg:
                return name
        return msg.splitlines()[0][:180]
