from __future__ import annotations

from functools import lru_cache
from web3 import Web3

from hash_miner.mining.native_backend import KeccakBackend, load_backend

_backend: KeccakBackend = load_backend(prefer_native=True)


def set_backend(backend: KeccakBackend) -> None:
    global _backend
    _backend = backend


def _u256(x: int) -> bytes:
    return int(x).to_bytes(32, "big", signed=False)


def _addr(a: str) -> bytes:
    raw = bytes.fromhex(Web3.to_checksum_address(a)[2:])
    return b"\x00" * 12 + raw


@lru_cache(maxsize=8192)
def challenge_prefix(chain_id: int, contract_address: str, miner_address: str, epoch: int) -> bytes:
    return _u256(chain_id) + _addr(contract_address) + _addr(miner_address) + _u256(epoch)


def compute_challenge(chain_id: int, contract_address: str, miner_address: str, epoch: int) -> bytes:
    return _backend.keccak(challenge_prefix(chain_id, contract_address, miner_address, epoch))


def nonce_payload(challenge: bytes, nonce: int) -> bytes:
    return challenge + _u256(nonce)


def hash_nonce(challenge: bytes, nonce: int) -> bytes:
    return _backend.keccak(nonce_payload(challenge, nonce))


def is_valid(pow_hash: bytes, difficulty: int) -> bool:
    return int.from_bytes(pow_hash, "big") < difficulty
