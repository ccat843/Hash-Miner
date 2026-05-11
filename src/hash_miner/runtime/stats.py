from collections import deque
from dataclasses import dataclass, field
from time import monotonic


@dataclass
class MinerStats:
    start: float = field(default_factory=monotonic)
    hashes: int = 0
    found: int = 0
    submitted: int = 0
    confirmed: int = 0
    reverted: int = 0
    worker_hashes: dict[int, int] = field(default_factory=dict)
    hr_window: deque[tuple[float, int]] = field(default_factory=lambda: deque(maxlen=120))

    def add_hashes(self, worker_id: int, count: int) -> None:
        self.hashes += count
        self.worker_hashes[worker_id] = self.worker_hashes.get(worker_id, 0) + count
        self.hr_window.append((monotonic(), self.hashes))

    def hashrate_total(self) -> float:
        elapsed = max(monotonic() - self.start, 1e-9)
        return self.hashes / elapsed

    def hashrate_rolling(self) -> float:
        if len(self.hr_window) < 2:
            return 0.0
        t0, h0 = self.hr_window[0]
        t1, h1 = self.hr_window[-1]
        dt = max(t1 - t0, 1e-9)
        return (h1 - h0) / dt

    def hashrate_workers(self) -> dict[int, float]:
        elapsed = max(monotonic() - self.start, 1e-9)
        return {wid: c / elapsed for wid, c in sorted(self.worker_hashes.items())}
