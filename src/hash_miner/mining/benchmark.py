from __future__ import annotations

from time import perf_counter

from hash_miner.mining.challenge import hash_nonce


def benchmark_hashrate(challenge: bytes, iterations: int = 200_000) -> float:
    start = perf_counter()
    nonce = 0
    for _ in range(iterations):
        hash_nonce(challenge, nonce)
        nonce += 1
    dt = max(perf_counter() - start, 1e-9)
    return iterations / dt
