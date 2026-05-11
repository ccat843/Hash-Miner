# HASH Native CPU Miner

Production-oriented native Python miner for the HASH ERC-20 PoW contract.

This miner is designed for **correctness-first live operation**: it continuously verifies challenge parity with the contract, rotates work on epoch/difficulty changes, preflights `mine(nonce)` via `eth_call`, suppresses duplicate submissions while a tx is pending, and logs actionable diagnostics.

---

## Table of Contents

1. [What this miner is](#what-this-miner-is)
2. [How HASH mining works](#how-hash-mining-works)
3. [Architecture](#architecture)
4. [Safety systems](#safety-systems)
5. [Requirements](#requirements)
6. [Installation](#installation)
7. [Configuration](#configuration)
8. [Running the miner](#running-the-miner)
9. [Expected lifecycle](#expected-lifecycle)
10. [Telemetry and logs](#telemetry-and-logs)
11. [Performance tuning](#performance-tuning)
12. [Transaction handling](#transaction-handling)
13. [Revert diagnostics](#revert-diagnostics)
14. [Troubleshooting](#troubleshooting)
15. [Security best practices](#security-best-practices)
16. [Deployment guides](#deployment-guides)
17. [Advanced usage](#advanced-usage)
18. [Profitability estimation](#profitability-estimation)
19. [FAQ](#faq)
20. [Future GPU roadmap](#future-gpu-roadmap)

---

## What this miner is

- Native **Python 3.11** CPU miner for HASH.
- Uses deterministic multithreaded nonce search.
- Uses Solidity-compatible ABI encoding semantics.
- Uses pluggable hashing backend:
  - Preferred: `pycryptodome` (native C-backed Keccak).
  - Fallback: `web3` keccak.
- Integrates with contract via `web3.py`.

This repository is designed as a modular codebase (`chain`, `mining`, `runtime`) rather than a single monolithic script.

---

## How HASH mining works

### Challenge

```solidity
challenge = keccak256(abi.encode(chainId, contractAddress, minerAddress, epoch))
```

### Valid proof

```solidity
keccak256(abi.encode(challenge, nonce)) < currentDifficulty
```

### Epoch

```text
epoch = block.number // 100
```

### Important implications

- Challenge changes whenever epoch changes.
- Difficulty may change independently of epoch.
- Proofs are miner- and epoch-specific; stale proofs become invalid.

---

## Architecture

### Component diagram

```text
+------------------+       +----------------------+       +------------------+
| runtime/miner.py | ----> | chain/contract_adapter| ---> | Ethereum RPC     |
|  coordinator     |       | read/write contract  |       | (HTTP endpoint)  |
+---------+--------+       +----------------------+       +------------------+
          |
          v
+------------------+       +----------------------+       +------------------+
| mining/worker.py | ----> | mining/challenge.py | ----> | native_backend.py|
| thread workers   |       | abi-accurate hashing|       | keccak backend   |
+------------------+       +----------------------+       +------------------+

          |
          v
+------------------+
| runtime/stats.py |
| telemetry state  |
+------------------+
```

### Mining loop lifecycle

```text
poll chain snapshot
  -> verify genesis complete
  -> compute local challenge
  -> compare with getChallenge(miner)
      -> mismatch => stop and raise
  -> if epoch/difficulty changed => cancel old workers and restart
  -> workers search nonces (deterministic stride)
  -> result found => local revalidation
  -> if tx pending => discard share
  -> preflight eth_call mine(nonce)
  -> build/sign/send tx
  -> mark tx pending window
  -> continue polling and stats logging
```

---

## Safety systems

This miner includes operational protections:

1. **Challenge mismatch kill-switch**  
   If local challenge differs from `getChallenge(miner)`, mining halts.

2. **Epoch/difficulty job rotation**  
   Workers are restarted when epoch or difficulty changes.

3. **Pending transaction suppression**  
   While a tx is in-flight, new shares are dropped to avoid duplicate spend.

4. **Preflight call validation**  
   `eth_call mine(nonce)` is executed before broadcast.

5. **Local share revalidation**  
   Found nonce is rehashed and compared against current difficulty.

6. **Revert decoding**  
   Known custom errors are decoded in logs for faster diagnosis.

---

## Requirements

- Python 3.11+
- Reliable Ethereum RPC endpoint (private preferred)
- Funded wallet for gas
- HASH miner contract address

---

## Installation

### Linux / macOS / WSL

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

### Windows (PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
```

---

## Configuration

Set environment variables before run.

### Example `.env`

```env
HASH_RPC_URL=https://your-private-rpc.example
HASH_PRIVATE_KEY=0xYOUR_PRIVATE_KEY
HASH_CONTRACT_ADDRESS=0xYourHashContract
HASH_CHAIN_ID=1

# optional tuning
HASH_WORKERS=8
HASH_POLL_INTERVAL=1.0
HASH_STATS_INTERVAL=10.0
HASH_PREFER_NATIVE_HASH=1
```

### Variable reference

- `HASH_RPC_URL` — RPC endpoint.
- `HASH_PRIVATE_KEY` — miner signing key.
- `HASH_CONTRACT_ADDRESS` — HASH contract address.
- `HASH_CHAIN_ID` — network chain ID.
- `HASH_WORKERS` — CPU worker count; default is `cpu_count()-1`.
- `HASH_POLL_INTERVAL` — state refresh interval in seconds.
- `HASH_STATS_INTERVAL` — telemetry print interval.
- `HASH_PREFER_NATIVE_HASH` — `1` prefer native backend, `0` force fallback.

---

## Running the miner

```bash
python -m hash_miner.main
```

### Example startup output

```text
INFO | hash_miner | Hash backend=pycryptodome
INFO | hash_miner | Backend single-thread benchmark: 184523.37 H/s
INFO | hash_miner | New job id=12 epoch=223847 difficulty=9458123... blocks_left=77
INFO | hash_miner | stats hr_total=612345.02 hr_rolling=598442.88 found=4 submitted=1 reverted=0 pending=True eta=132.8s per_worker={0: 76544.2, ...}
```

---

## Expected lifecycle

1. Load config and connect RPC.
2. Select keccak backend.
3. Benchmark local hashing quickly.
4. Poll mining state.
5. Verify challenge parity.
6. Launch/restart worker threads on new job.
7. Search and validate nonces.
8. Preflight + send transaction.
9. Continue until stopped or supply exhausted.

---

## Telemetry and logs

The miner logs:

- backend in use
- current epoch / difficulty / blocks left
- total hashrate
- rolling hashrate
- per-worker rates
- shares found
- submissions / reverts
- pending tx state
- ETA estimate (probabilistic)

### How to interpret ETA

ETA is a statistical estimate from current rolling hashrate and target probability. It is **not deterministic**.

---

## Performance tuning

### Worker count recommendations

- Start with `workers = physical_cores` or `physical_cores - 1`.
- Avoid maxing logical threads on small VPS nodes if system becomes unstable.
- Measure rolling hashrate for each change.

### RPC recommendations

- Prefer low-latency private RPC.
- Keep consistent endpoint (avoid flapping providers).
- Avoid heavily rate-limited public endpoints for production mining.

### Native hashing backend

- Default path prefers `pycryptodome` for C-backed keccak.
- If unavailable, falls back to `web3` keccak.
- Hot path uses manual fixed-width ABI-equivalent encoding to reduce Python overhead.

---

## Transaction handling

- Found share is revalidated locally.
- Preflight `eth_call mine(nonce)` is executed.
- If preflight passes, tx is built with EIP-1559 fields and broadcast.
- Pending suppression window blocks additional submissions for a short window.

This reduces wasted gas from duplicate/stale proofs.

---

## Revert diagnostics

The miner attempts to decode common custom errors including:

- `InsufficientWork`
- `ProofAlreadyUsed`
- `BlockCapReached`
- `GenesisNotComplete`
- `SupplyExhausted`

Use these to classify failures quickly.

---

## Troubleshooting

### 1) Challenge mismatch error

Symptoms:
- runtime stops with challenge mismatch

Actions:
- verify `HASH_CHAIN_ID`
- verify `HASH_CONTRACT_ADDRESS`
- verify wallet address used for mining
- verify you are on intended network

### 2) Frequent `InsufficientWork`

- usually stale difficulty/epoch race
- lower polling interval
- reduce submission latency

### 3) Frequent `ProofAlreadyUsed`

- another tx already consumed nonce/epoch proof
- ensure single miner instance per wallet unless coordinated

### 4) Frequent `BlockCapReached`

- block mint cap reached
- retry next block window
- use lower latency/private RPC

### 5) High revert rate

- inspect preflight failures in logs
- ensure gas funding and sane fee caps
- validate system clock and RPC health

### 6) Low hashrate

- reduce workers (contention may be too high)
- confirm native backend is active
- isolate CPU (noisy neighbors on shared VPS reduce throughput)

---

## Security best practices

- Use a dedicated hot wallet with minimal funds.
- Never reuse cold-wallet private keys.
- Store secrets in environment, not committed files.
- Restrict SSH access on VPS (keys only, disable password auth).
- Consider process-level secret injection (systemd environment files with restricted perms).

---

## Deployment guides

### Linux VPS (recommended)

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
# export env vars
python -m hash_miner.main
```

For long-running service, use `systemd` or a process manager.

### Google Colab

Colab is not ideal for persistent mining due to session resets.

If testing:

```bash
!python -m pip install -e .
```

Then set environment variables in notebook and run module. Expect interruptions.

### Windows

Use PowerShell steps from Installation section. Keep terminal open or run via Task Scheduler for persistence.

### Docker

If you add a Dockerfile later, run container with env vars and CPU pinning. Example command shape:

```bash
docker run --rm -it \
  -e HASH_RPC_URL=... \
  -e HASH_PRIVATE_KEY=... \
  -e HASH_CONTRACT_ADDRESS=... \
  -e HASH_CHAIN_ID=1 \
  -e HASH_WORKERS=8 \
  your/hash-miner:latest
```

---

## Advanced usage

### Safe stop / restart

- Send `SIGINT`/Ctrl+C to stop.
- On restart, miner re-derives challenge from chain state.
- No local nonce database is required for correctness.

### Private RPC and latency strategy

- colocate miner geographically near RPC provider POP.
- maintain persistent low-jitter network path.
- consider dedicated endpoints for high submission reliability.

### Gas fee guidance

- use dynamic EIP-1559 strategy.
- monitor inclusion delays and adjust priority fee.
- if inclusion lags, stale risk increases.

---

## Profitability estimation

Basic expected success rate estimate:

```text
probability_per_hash ≈ difficulty / 2^256
expected_hashes_per_solution ≈ 1 / probability_per_hash
expected_time_seconds ≈ expected_hashes_per_solution / hashrate
```

You must also include:
- gas costs per successful/failed tx
- revert waste rate
- hardware/power cost
- opportunity cost vs other workloads

---

## FAQ

### Is this GPU miner?
No, currently CPU-focused.

### Why does pending suppression drop valid shares?
To reduce duplicate tx broadcasting and gas waste while a previous submission is unresolved.

### Why preflight if local hash is valid?
Chain state can change between local validation and broadcast; preflight catches staleness.

### Why can tx still revert after preflight?
Mempool and block races: other miners may submit first, difficulty can update, or per-block cap may be hit.

### Should I run multiple miner processes with one key?
Not recommended unless you coordinate tx nonce and share deduplication externally.

---

## Future GPU roadmap

Likely evolution path:

1. keep current correctness model (challenge checks, preflight, suppression)
2. replace CPU nonce hashing core with GPU backend
3. preserve same coordinator and submission layers
4. add batched nonce pipelines and async result channels
5. tune relay/RPC strategy for lower stale rate

The current architecture is intentionally modular so hashing backend can be swapped without rewriting chain safety logic.

---

## Disclaimer

Mining outcomes are probabilistic. This software is provided as-is. You are responsible for private key security, operational risk, and legal/regulatory compliance in your jurisdiction.
