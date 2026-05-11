from __future__ import annotations

from threading import Event

from hash_miner.mining.challenge import hash_nonce, is_valid
from hash_miner.types import WorkResult


def mine_loop(job_id: int, challenge: bytes, difficulty: int, worker_id: int, workers: int, stop: Event, out_queue) -> None:
    nonce = worker_id
    checked = 0
    while not stop.is_set():
        digest = hash_nonce(challenge, nonce)
        checked += 1
        if is_valid(digest, difficulty):
            out_queue.put(WorkResult(job_id=job_id, nonce=nonce, digest=digest, checked=checked, worker_id=worker_id))
            checked = 0
        nonce += workers
