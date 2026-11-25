"""Public verification algorithm; only encryption of unrevealed seeds is server-specific."""

import hashlib
import hmac
import json
import secrets

from django.conf import settings
from nacl.encoding import HexEncoder
from nacl.secret import SecretBox

ALGORITHM = 'hmac-sha256-v1'


def _seed_box():
    # Domain-separated encryption key; do not rotate SECRET_KEY with unused commitments outstanding.
    key = hashlib.sha256(('casino-seed-encryption-v1:' + settings.SECRET_KEY).encode()).digest()
    return SecretBox(key)


def generate_seed():
    return secrets.token_hex(32)


def seed_hash(seed):
    return hashlib.sha256(seed.encode('ascii')).hexdigest()


def encrypt_seed(seed):
    return _seed_box().encrypt(seed.encode('ascii'), encoder=HexEncoder).decode('ascii')


def decrypt_seed(encrypted):
    return _seed_box().decrypt(encrypted.encode('ascii'), encoder=HexEncoder).decode('ascii')


class FairRandom:
    def __init__(self, *, server_seed, client_seed, commitment_id, game, rules_version):
        self.key = bytes.fromhex(server_seed)
        self.context = ['casino-v1', game, rules_version, str(commitment_id), client_seed]
        self.counter = 0

    def below(self, bound):
        """First 8 bytes of each HMAC as uint64 big-endian; reject the incomplete upper interval."""
        if type(bound) is not int or not 1 <= bound <= 2**64:
            raise ValueError('Invalid random range')
        limit = 2**64 - (2**64 % bound)
        while True:
            message = json.dumps([*self.context, self.counter], separators=(',', ':'), ensure_ascii=True).encode(
                'ascii'
            )
            self.counter += 1
            candidate = int.from_bytes(hmac.new(self.key, message, hashlib.sha256).digest()[:8], 'big')
            if candidate < limit:
                return candidate % bound
