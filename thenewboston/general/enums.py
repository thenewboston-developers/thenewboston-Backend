from enum import Enum


class MessageType(Enum):
    CREATE_EXCHANGE_ORDER = 'create.exchange_order'
    CREATE_NOTIFICATION = 'create.notification'
    CREATE_TRADE = 'create.trade'
    UPDATE_EXCHANGE_ORDER = 'update.exchange_order'
    UPDATE_FRONTEND_DEPLOYMENT = 'update.frontend_deployment'
    UPDATE_WALLET = 'update.wallet'


class NotificationType(Enum):
    EXCHANGE_ORDER_FILLED = 'EXCHANGE_ORDER_FILLED'
    POST_COIN_TRANSFER = 'POST_COIN_TRANSFER'
    POST_COMMENT = 'POST_COMMENT'
    POST_LIKE = 'POST_LIKE'
    USER_MENTION = 'USER_MENTION'
