from rest_framework.pagination import PageNumberPagination

from thenewboston.general.constants import DEFAULT_PAGE_SIZE


class CustomPageNumberPagination(PageNumberPagination):
    page_size = DEFAULT_PAGE_SIZE
    page_size_query_param = 'page_size'
