from django.urls import path

from .views import GameEarningsLeaderboardView, GameFundDepositView, GameFundView

urlpatterns = [
    path('game-fund', GameFundView.as_view(), name='game-fund'),
    path('game-fund/deposits', GameFundDepositView.as_view(), name='game-fund-deposits'),
    path('game-rewards/leaderboard', GameEarningsLeaderboardView.as_view(), name='game-earnings-leaderboard'),
]
