from __future__ import annotations

import threading
from dataclasses import dataclass


class KeccakBackend:
    name: str = "python"

    def keccak(self, payload: bytes) -> bytes:
        raise NotImplementedError


class PyCryptodomeBackend(KeccakBackend):
    name = "pycryptodome"

    def __init__(self) -> None:
        from Crypto.Hash import keccak  # type: ignore

        self._keccak_mod = keccak
        self._local = threading.local()

    def keccak(self, payload: bytes) -> bytes:
        h = self._keccak_mod.new(digest_bits=256)
        h.update(payload)
        return h.digest()


class Web3Backend(KeccakBackend):
    name = "web3"

    def keccak(self, payload: bytes) -> bytes:
        from web3 import Web3

        return Web3.keccak(payload)


@dataclass(frozen=True)
class Backends:
    preferred: KeccakBackend
    fallback: KeccakBackend


def load_backend(prefer_native: bool = True) -> KeccakBackend:
    if prefer_native:
        try:
            return PyCryptodomeBackend()
        except Exception:
            pass
    return Web3Backend()
