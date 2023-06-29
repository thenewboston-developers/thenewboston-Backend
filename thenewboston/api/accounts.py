import json
import uuid

import requests
from nacl.encoding import HexEncoder
from nacl.signing import SigningKey, VerifyKey

from thenewboston.general.constants import TRANSACTION_FEE


def encode_verify_key(*, verify_key):
    """Return the hexadecimal representation of the binary account number data"""
    if not isinstance(verify_key, VerifyKey):
        raise RuntimeError('verify_key must be of type nacl.signing.VerifyKey')

    return verify_key.encode(encoder=HexEncoder).decode('utf-8')


def fetch_balance(*, account_number, domain):
    response = requests.get(f'https://{domain}/api/accounts/{account_number}')

    if response.status_code == 200:
        data = response.json()
        balance = data.get('balance', 0)
    elif response.status_code == 404:
        balance = 0
    else:
        raise Exception('Could not fetch balance.')

    return balance


def generate_signature(*, message, signing_key):
    """Sign message using signing key and return signature"""
    return signing_key.sign(message).signature.hex()


def get_verify_key(*, signing_key):
    """Return the verify key from the signing key"""
    if not isinstance(signing_key, SigningKey):
        raise RuntimeError('signing_key must be of type nacl.signing.SigningKey')

    return signing_key.verify_key


def post(*, url, body):
    """Send a POST request and return response as Python object"""
    response = requests.post(url, json=body)
    return response.json()


def sort_and_encode(dictionary):
    """Sort dictionary and return encoded data"""
    return json.dumps(dictionary, separators=(',', ':'), sort_keys=True).encode('utf-8')


def transfer_funds(*, amount, domain, recipient_account_number_str, sender_signing_key_str):
    signing_key = SigningKey(sender_signing_key_str.encode('utf-8'), encoder=HexEncoder)
    account_number = get_verify_key(signing_key=signing_key)

    signed_data = {
        'amount': amount,
        'id': str(uuid.uuid4()),
        'payload': {},
        'recipient': recipient_account_number_str,
        'sender': encode_verify_key(verify_key=account_number),
        'transaction_fee': TRANSACTION_FEE,
    }

    signature = generate_signature(message=sort_and_encode(signed_data), signing_key=signing_key)
    request_data = {**signed_data, 'signature': signature}

    server_address = f'https://{domain}/api'
    url = f'{server_address}/blocks'
    return post(url=url, body=request_data)
