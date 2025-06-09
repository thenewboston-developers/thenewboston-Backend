from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from thenewboston.general.pagination import CustomPageNumberPagination
from thenewboston.social.models import Comment, Post

from ..serializers.transfer import TransferSerializer


class TransferListView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get(self, request):
        user = request.user
        currency_id = request.query_params.get('currency')

        if not currency_id:
            return Response({'error': 'currency parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        transfers = []

        # Get posts where user sent or received funds
        posts = Post.objects.filter(
            Q(owner=user) | Q(recipient=user), price_amount__isnull=False, price_currency_id=currency_id
        ).select_related('owner', 'recipient', 'price_currency').order_by('-created_date')

        for post in posts:
            is_sent = post.owner == user
            transfer = {
                'post_id': post.id,
                'comment_id': None,
                'amount': -post.price_amount if is_sent else post.price_amount,
                'currency': post.price_currency_id,
                'timestamp': post.created_date,
                'content': post.content,
                'counterparty': post.recipient if is_sent else post.owner
            }
            transfers.append(transfer)

        # Get comments where user sent funds
        comments = Comment.objects.filter(owner=user, price_amount__isnull=False, price_currency_id=currency_id
                                          ).select_related('owner', 'post__owner',
                                                           'price_currency').order_by('-created_date')

        for comment in comments:
            transfer = {
                'post_id': comment.post_id,
                'comment_id': comment.id,
                'amount': -comment.price_amount,  # Negative for sent
                'currency': comment.price_currency_id,
                'timestamp': comment.created_date,
                'content': comment.content,
                'counterparty': comment.post.owner
            }
            transfers.append(transfer)

        # Get comments where user received funds (as post owner)
        received_comments = Comment.objects.filter(
            post__owner=user, price_amount__isnull=False, price_currency_id=currency_id
        ).exclude(owner=user).select_related('owner', 'price_currency').order_by('-created_date')

        for comment in received_comments:
            transfer = {
                'post_id': comment.post_id,
                'comment_id': comment.id,
                'amount': comment.price_amount,  # Positive for received
                'currency': comment.price_currency_id,
                'timestamp': comment.created_date,
                'content': comment.content,
                'counterparty': comment.owner
            }
            transfers.append(transfer)

        transfers.sort(key=lambda x: x['timestamp'], reverse=True)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(transfers, request, view=self)

        if page is not None:
            serializer = TransferSerializer(page, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)

        serializer = TransferSerializer(transfers, many=True, context={'request': request})
        return Response(serializer.data)
