from enum import Enum


class MessageType(Enum):
    CREATE_EXCHANGE_ORDER = 'create.exchange_order'
    CREATE_MESSAGE = 'create.message'
    CREATE_NOTIFICATION = 'create.notification'
    UPDATE_EXCHANGE_ORDER = 'update.exchange_order'
    UPDATE_WALLET = 'update.wallet'
