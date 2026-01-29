from thenewboston.general.pagination import CustomPageNumberPagination

from .constants import CHAT_MESSAGE_PAGE_SIZE


class ConnectFiveChatPagination(CustomPageNumberPagination):
    page_size = CHAT_MESSAGE_PAGE_SIZE
