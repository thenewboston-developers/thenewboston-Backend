from django.urls import path

from .views import (
    ActiveBetView,
    BetActionView,
    BetsView,
    BetView,
    CasinoView,
    CommitmentView,
    FundDepositView,
    FundWithdrawalView,
)

urlpatterns = [
    path('casino', CasinoView.as_view(), name='casino'),
    path('casino/commitments', CommitmentView.as_view(), name='casino-commitments'),
    path('casino/bets', BetsView.as_view(), name='casino-bets'),
    path('casino/bets/active', ActiveBetView.as_view(), name='casino-active-bet'),
    path('casino/bets/<uuid:request_id>', BetView.as_view(), name='casino-bet'),
    path('casino/bets/<uuid:request_id>/actions', BetActionView.as_view(), name='casino-bet-action'),
    path('casino/fund/deposits', FundDepositView.as_view(), name='casino-deposits'),
    path('casino/fund/withdrawals', FundWithdrawalView.as_view(), name='casino-withdrawals'),
]
