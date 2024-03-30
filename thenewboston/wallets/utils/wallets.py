from thenewboston.general.utils.cryptography import generate_key_pair
from thenewboston.wallets.models import Wallet


def get_or_create_wallet(owner, core_id, balance=0, in_transaction=False):
	"""
	Retrieves an existing wallet or creates a new one for the given owner and core_id.
	A key pair is generated only when creating a new wallet.
	If `in_transaction` is True, the wallet is locked for update via select_for_update.
	"""

	def get_defaults():
		"""
		Default values for a new wallet.
		"""
		key_pair = generate_key_pair()
		return {
			'balance': balance,
			'deposit_account_number': key_pair.public,
			'deposit_signing_key': key_pair.private,
		}

	if in_transaction:
		wallet, created = Wallet.objects.select_for_update().get_or_create(
			owner=owner,
			core_id=core_id,
			defaults=get_defaults(),
		)
	else:
		wallet, created = Wallet.objects.get_or_create(
			owner=owner,
			core_id=core_id,
			defaults=get_defaults(),
		)

	return wallet, created
