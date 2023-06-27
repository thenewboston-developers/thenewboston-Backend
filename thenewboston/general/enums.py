from enum import Enum


class MessageType(Enum):
    CREATE_ORDER = 'create.order'
    UPDATE_ORDER = 'update.order'
    UPDATE_WALLET = 'update.wallet'
