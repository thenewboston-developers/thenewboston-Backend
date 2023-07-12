from enum import Enum


class MessageType(Enum):
    CREATE_EXCHANGE_ORDER = 'create.exchange_order'
    UPDATE_EXCHANGE_ORDER = 'update.exchange_order'
    UPDATE_WALLET = 'update.wallet'
