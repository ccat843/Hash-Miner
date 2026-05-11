from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
from threading import Event
from time import monotonic

from eth_account import Account
from web3 import Web3

from hash_miner.chain.contract_adapter import ContractAdapter
from hash_miner.config import MinerConfig
from hash_miner.mining.challenge import compute_challenge, is_valid, hash_nonce, set_backend
from hash_miner.mining.native_backend import load_backend
from hash_miner.mining.worker import mine_loop
from hash_miner.runtime.stats import MinerStats
from hash_miner.mining.benchmark import benchmark_hashrate
from hash_miner.gpu import CudaKeccakMiner
from hash_miner.types import MiningJob, WorkResult


class HashMiner:
    def __init__(self, cfg: MinerConfig) -> None:
        self.cfg = cfg
        self.log = logging.getLogger("hash_miner")
        self.w3 = Web3(Web3.HTTPProvider(cfg.rpc_url))
        self.account = Account.from_key(cfg.private_key)
        self.miner = self.account.address
        self.adapter = ContractAdapter.build(self.w3, cfg.contract_address)
        backend = load_backend(prefer_native=cfg.prefer_native_hash)
        set_backend(backend)
        self.log.info("Hash backend=%s", backend.name)
        self.stats = MinerStats()
        self.results: Queue[WorkResult] = Queue()
        self.stop_event = Event()
        self.executor = ThreadPoolExecutor(max_workers=cfg.workers)
        self.current_job: MiningJob | None = None
        self.job_stop = Event()
        self.tx_pending_until = 0.0
        self.pending_tx_hash: str | None = None
        self.gpu_nonce_base: int = 0
        self.gpu = CudaKeccakMiner(cfg.cuda_threads_per_block, cfg.cuda_blocks) if cfg.use_cuda else None
        seed_challenge = compute_challenge(cfg.chain_id, cfg.contract_address, self.miner, 0)
        if self.gpu is None:
            self.log.info("Backend single-thread benchmark: %.2f H/s", benchmark_hashrate(seed_challenge, iterations=50000))
        else:
            self.gpu.set_challenge(seed_challenge)
            self.log.info("CUDA benchmark: %.3f GH/s", self.gpu.benchmark(5))

    def _start_workers(self, job: MiningJob) -> None:
        self.job_stop.set()
        self.job_stop = Event()
        for wid in range(self.cfg.workers):
            self.executor.submit(mine_loop, job.job_id, job.challenge, job.difficulty, wid, self.cfg.workers, self.job_stop, self.results)

    def _pending(self) -> bool:
        return monotonic() < self.tx_pending_until

    async def run(self) -> None:
        job_id = 0
        while not self.stop_event.is_set():
            snap = self.adapter.snapshot(self.miner)
            if not snap.genesis_complete:
                self.log.info("Genesis not complete yet; waiting")
                await asyncio.sleep(self.cfg.poll_interval)
                continue
            if snap.remaining == 0:
                self.log.info("Mining supply exhausted")
                return

            local_challenge = compute_challenge(self.cfg.chain_id, self.cfg.contract_address, self.miner, snap.epoch)
            if local_challenge != snap.challenge:
                self.job_stop.set()
                raise RuntimeError("challenge mismatch: local != getChallenge(miner)")

            if self.current_job is None or self.current_job.epoch != snap.epoch or self.current_job.difficulty != snap.difficulty:
                job_id += 1
                self.current_job = MiningJob(job_id=job_id, epoch=snap.epoch, difficulty=snap.difficulty, challenge=snap.challenge)
                if self.gpu is None:
                    self._start_workers(self.current_job)
                else:
                    self.job_stop.set()
                    self.gpu.set_challenge(self.current_job.challenge)
                    self.gpu_nonce_base = 0
                    self.gpu.validate_samples(self.current_job.challenge, 0, samples=64)
                self.log.info("New job id=%s epoch=%s difficulty=%s blocks_left=%s", job_id, snap.epoch, snap.difficulty, snap.epoch_blocks_left)

            if self.gpu is None:
                await self._drain_results(snap)
            else:
                await self._gpu_scan_and_submit(snap)
            await asyncio.sleep(self.cfg.poll_interval)


    async def _gpu_scan_and_submit(self, snap) -> None:
        if self.current_job is None or self.gpu is None:
            return
        if self._pending():
            return
        start_epoch = snap.epoch
        nonce_base = self.gpu_nonce_base
        r = self.gpu.scan_batch(nonce_base, snap.difficulty)
        self.gpu_nonce_base += r.checked
        self.stats.hashes += r.checked
        latest_epoch = self.adapter.snapshot(self.miner).epoch
        if latest_epoch != start_epoch:
            return
        if r.found and r.nonce is not None:
            self.stats.found += 1
            digest = hash_nonce(self.current_job.challenge, r.nonce)
            if is_valid(digest, snap.difficulty):
                await self._submit_nonce(r.nonce)

    async def _drain_results(self, snap) -> None:
        while True:
            try:
                result = self.results.get_nowait()
            except Empty:
                break
            self.stats.found += 1
            self.stats.add_hashes(result.worker_id, result.checked)
            if self.current_job is None or result.job_id != self.current_job.job_id:
                continue
            if self._pending():
                self.log.info("Dropping share nonce=%s because tx pending=%s", result.nonce, self.pending_tx_hash)
                continue
            check_digest = hash_nonce(self.current_job.challenge, result.nonce)
            if check_digest != result.digest or not is_valid(result.digest, snap.difficulty):
                self.log.warning("Local re-validation failed for nonce=%s", result.nonce)
                continue
            await self._submit_nonce(result.nonce)
            break

    async def _submit_nonce(self, solution_nonce: int) -> None:
        try:
            self.adapter.call_mine(self.miner, solution_nonce)
        except Exception as exc:
            self.stats.reverted += 1
            self.log.warning("Preflight mine(%s) reverted: %s", solution_nonce, self.adapter.decode_revert(exc))
            return

        account_nonce = self.w3.eth.get_transaction_count(self.miner, "pending")
        latest = self.w3.eth.get_block("latest")
        base_fee = latest.get("baseFeePerGas", self.w3.to_wei(1, "gwei"))
        max_priority = self.w3.to_wei(1, "gwei")
        max_fee = base_fee * 2 + max_priority
        tx = self.adapter.build_mine_tx(self.miner, solution_nonce, account_nonce, self.cfg.chain_id, max_fee, max_priority)
        tx.setdefault("gas", 240_000)
        signed = self.account.sign_transaction(tx)
        try:
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            self.stats.submitted += 1
            self.pending_tx_hash = tx_hash.hex()
            self.tx_pending_until = monotonic() + 45.0
            self.log.info("Sending transaction nonce=%s tx=%s", solution_nonce, self.pending_tx_hash)
        except Exception as exc:
            self.stats.reverted += 1
            self.log.warning("Broadcast failed nonce=%s reason=%s", solution_nonce, self.adapter.decode_revert(exc))

    async def stats_loop(self) -> None:
        while not self.stop_event.is_set():
            await asyncio.sleep(self.cfg.stats_interval)
            rolling = self.stats.hashrate_rolling()
            total = self.stats.hashrate_total()
            eta = "n/a"
            if self.current_job is not None and rolling > 0:
                p = self.current_job.difficulty / (2**256)
                eta = f"{(1 / max(rolling * p, 1e-30)):.1f}s"
            self.log.info(
                "stats hr_total=%.2f hr_rolling=%.2f found=%s submitted=%s reverted=%s pending=%s eta=%s per_worker=%s",
                total,
                rolling,
                self.stats.found,
                self.stats.submitted,
                self.stats.reverted,
                bool(self._pending()),
                eta,
                self.stats.hashrate_workers(),
            )

    async def start(self) -> None:
        await asyncio.gather(self.run(), self.stats_loop())
