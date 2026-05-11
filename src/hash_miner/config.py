from dataclasses import dataclass
import os


@dataclass(frozen=True)
class MinerConfig:
    rpc_url: str
    private_key: str
    contract_address: str
    chain_id: int
    workers: int
    poll_interval: float
    stats_interval: float
    prefer_native_hash: bool
    use_cuda: bool
    cuda_blocks: int
    cuda_threads_per_block: int

    @staticmethod
    def from_env() -> "MinerConfig":
        return MinerConfig(
            rpc_url=os.environ["HASH_RPC_URL"],
            private_key=os.environ["HASH_PRIVATE_KEY"],
            contract_address=os.environ["HASH_CONTRACT_ADDRESS"],
            chain_id=int(os.environ["HASH_CHAIN_ID"]),
            workers=int(os.getenv("HASH_WORKERS", "0")) or max((os.cpu_count() or 2) - 1, 1),
            poll_interval=float(os.getenv("HASH_POLL_INTERVAL", "1.0")),
            stats_interval=float(os.getenv("HASH_STATS_INTERVAL", "10.0")),
            prefer_native_hash=os.getenv("HASH_PREFER_NATIVE_HASH", "1") not in {"0", "false", "False"},
            use_cuda=os.getenv("HASH_USE_CUDA", "1") not in {"0", "false", "False"},
            cuda_blocks=int(os.getenv("HASH_CUDA_BLOCKS", "4096")),
            cuda_threads_per_block=int(os.getenv("HASH_CUDA_THREADS", "256")),
        )
