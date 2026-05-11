import asyncio

from hash_miner.config import MinerConfig
from hash_miner.logging_setup import setup_logging
from hash_miner.runtime.miner import HashMiner


def main() -> None:
    setup_logging()
    cfg = MinerConfig.from_env()
    miner = HashMiner(cfg)
    asyncio.run(miner.start())


if __name__ == "__main__":
    main()
