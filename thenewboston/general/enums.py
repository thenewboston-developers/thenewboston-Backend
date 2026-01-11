from enum import Enum


class MessageType(Enum):
    CREATE_EXCHANGE_ORDER = 'create.exchange_order'
    CREATE_NOTIFICATION = 'create.notification'
    CREATE_TRADE = 'create.trade'
    UPDATE_CONNECT_FIVE_CHALLENGE = 'update.connect_five_challenge'
    UPDATE_CONNECT_FIVE_MATCH = 'update.connect_five_match'
    UPDATE_EXCHANGE_ORDER = 'update.exchange_order'
    UPDATE_FRONTEND_DEPLOYMENT = 'update.frontend_deployment'
    UPDATE_WALLET = 'update.wallet'


class NotificationType(Enum):
    COMMENT_MENTION = 'COMMENT_MENTION'
    CONNECT_FIVE_CHALLENGE = 'CONNECT_FIVE_CHALLENGE'
    EXCHANGE_ORDER_FILLED = 'EXCHANGE_ORDER_FILLED'
    POST_COIN_TRANSFER = 'POST_COIN_TRANSFER'
    POST_COMMENT = 'POST_COMMENT'
    POST_LIKE = 'POST_LIKE'
    POST_MENTION = 'POST_MENTION'
    PROFILE_FOLLOW = 'PROFILE_FOLLOW'
