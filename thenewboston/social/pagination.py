from thenewboston.general.pagination import CustomPageNumberPagination


class CommentPagination(CustomPageNumberPagination):
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        if not {self.page_query_param, self.page_size_query_param}.intersection(request.query_params):
            return None
        if not queryset.ordered:
            queryset = queryset.order_by('-created_date', '-id')
        return super().paginate_queryset(queryset, request, view)
