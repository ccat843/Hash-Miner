from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import cupy as cp

from hash_miner.mining.challenge import hash_nonce


@dataclass
class GpuMiningResult:
    found: bool
    nonce: int | None
    checked: int
    elapsed_s: float


class CudaKeccakMiner:
    def __init__(self, threads_per_block: int = 256, blocks: int = 4096) -> None:
        self.threads_per_block = threads_per_block
        self.blocks = blocks
        src = Path(__file__).with_name("kernel.cu").read_text()
        self.module = cp.RawModule(code=src, options=("--std=c++14",), name_expressions=["mine_keccak_kernel", "sample_hashes_kernel"])
        self.kernel = self.module.get_function("mine_keccak_kernel")
        self.sample_kernel = self.module.get_function("sample_hashes_kernel")
        self.challenge_symbol, _ = self.module.get_global("d_challenge")

    def set_challenge(self, challenge: bytes) -> None:
        if len(challenge) != 32:
            raise ValueError("challenge must be 32 bytes")
        cp.cuda.runtime.memcpyHtoD(self.challenge_symbol, challenge, 32)

    def scan_batch(self, nonce_base: int, difficulty: int) -> GpuMiningResult:
        total = self.threads_per_block * self.blocks
        out_nonce = cp.zeros((1,), dtype=cp.uint64)
        found_flag = cp.zeros((1,), dtype=cp.int32)
        d0 = difficulty & ((1 << 64) - 1)
        d1 = (difficulty >> 64) & ((1 << 64) - 1)
        d2 = (difficulty >> 128) & ((1 << 64) - 1)
        d3 = (difficulty >> 192) & ((1 << 64) - 1)
        t0 = perf_counter()
        self.kernel((self.blocks,), (self.threads_per_block,), (cp.uint64(nonce_base), cp.uint64(total), cp.uint64(d3), cp.uint64(d2), cp.uint64(d1), cp.uint64(d0), out_nonce, found_flag))
        cp.cuda.runtime.deviceSynchronize()
        elapsed = perf_counter() - t0
        found = int(found_flag.get()[0]) == 1
        nonce = int(out_nonce.get()[0]) if found else None
        return GpuMiningResult(found=found, nonce=nonce, checked=total, elapsed_s=elapsed)

    def benchmark(self, batches: int = 20) -> float:
        total_hashes = 0
        total_time = 0.0
        for i in range(batches):
            r = self.scan_batch(i * self.threads_per_block * self.blocks, (1 << 256) - 1)
            total_hashes += r.checked
            total_time += r.elapsed_s
        return (total_hashes / max(total_time, 1e-9)) / 1e9

    def validate_samples(self, challenge: bytes, nonce_base: int, samples: int = 256) -> None:
        self.set_challenge(challenge)
        nonces = cp.arange(nonce_base, nonce_base + samples, dtype=cp.uint64)
        out = cp.zeros((samples, 32), dtype=cp.uint8)
        threads = 128
        blocks = (samples + threads - 1) // threads
        self.sample_kernel((blocks,), (threads,), (nonces, cp.uint64(samples), out))
        cp.cuda.runtime.deviceSynchronize()
        gpu_hashes = out.get()
        for i in range(samples):
            n = int(nonce_base + i)
            cpu = hash_nonce(challenge, n)
            if cpu != bytes(gpu_hashes[i].tolist()):
                raise RuntimeError(f"GPU hash mismatch at nonce={n}")
