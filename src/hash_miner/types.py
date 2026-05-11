from dataclasses import dataclass


@dataclass(frozen=True)
class MiningSnapshot:
    era: int
    reward: int
    difficulty: int
    minted: int
    remaining: int
    epoch: int
    epoch_blocks_left: int
    genesis_complete: bool
    challenge: bytes


@dataclass(frozen=True)
class MiningJob:
    job_id: int
    epoch: int
    difficulty: int
    challenge: bytes


@dataclass(frozen=True)
class WorkResult:
    job_id: int
    nonce: int
    digest: bytes
    checked: int
    worker_id: int
