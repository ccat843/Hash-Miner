from web3 import Web3

from hash_miner.mining.challenge import compute_challenge


def test_compute_challenge_matches_solidity_keccak():
    chain_id = 1
    contract = "0x0000000000000000000000000000000000001234"
    miner = "0x0000000000000000000000000000000000005678"
    epoch = 42
    expected = Web3.solidity_keccak(["uint256", "address", "address", "uint256"], [chain_id, contract, miner, epoch])
    got = compute_challenge(chain_id, contract, miner, epoch)
    assert got == expected
