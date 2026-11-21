from rest_framework.pagination import PageNumberPagination

from thenewboston.general.constants import ANONYMOUS_MAX_PAGE_SIZE, DEFAULT_PAGE_SIZE


class CustomPageNumberPagination(PageNumberPagination):
    page_size = DEFAULT_PAGE_SIZE
    page_size_query_param = 'page_size'

    def get_page_size(self, request):
        page_size = super().get_page_size(request)

        # Public read endpoints are open to signed-out visitors, so the page size they can request is bounded
        if page_size and not request.user.is_authenticated:
            return min(page_size, ANONYMOUS_MAX_PAGE_SIZE)

        return page_size
