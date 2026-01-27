from django.db import models


class ChallengeStatus(models.TextChoices):
    ACCEPTED = 'accepted', 'Accepted'
    CANCELLED = 'cancelled', 'Cancelled'
    DECLINED = 'declined', 'Declined'
    EXPIRED = 'expired', 'Expired'
    PENDING = 'pending', 'Pending'


class MatchStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    CANCELLED = 'cancelled', 'Cancelled'
    DRAW = 'draw', 'Draw'
    FINISHED_CONNECT5 = 'finished_connect5', 'Finished (Connect 5)'
    FINISHED_RESIGN = 'finished_resign', 'Finished (Resign)'
    FINISHED_TIMEOUT = 'finished_timeout', 'Finished (Timeout)'


class MoveType(models.TextChoices):
    BOMB = 'BOMB', 'Bomb'
    H2 = 'H2', 'Horizontal 2'
    SINGLE = 'SINGLE', 'Single'
    V2 = 'V2', 'Vertical 2'


class SpecialType(models.TextChoices):
    BOMB = 'BOMB', 'Bomb'
    H2 = 'H2', 'Horizontal 2'
    V2 = 'V2', 'Vertical 2'


class MatchEventType(models.TextChoices):
    CHALLENGE_ACCEPTED = 'challenge_accepted', 'Challenge Accepted'
    CHALLENGE_CANCELLED = 'challenge_cancelled', 'Challenge Cancelled'
    CHALLENGE_EXPIRED = 'challenge_expired', 'Challenge Expired'
    MOVE = 'move', 'Move'
    PURCHASE = 'purchase', 'Purchase'
    RESIGN = 'resign', 'Resign'
    SETTLEMENT = 'settlement', 'Settlement'
    TIMEOUT = 'timeout', 'Timeout'


class EscrowStatus(models.TextChoices):
    LOCKED = 'locked', 'Locked'
    SETTLED = 'settled', 'Settled'


class LedgerAction(models.TextChoices):
    CHALLENGE_REFUND = 'challenge_refund', 'Challenge Refund'
    PURCHASE = 'purchase', 'Purchase'
    STAKE_ACCEPT = 'stake_accept', 'Stake Accept'
    STAKE_LOCK = 'stake_lock', 'Stake Lock'
    WIN_PAYOUT = 'win_payout', 'Win Payout'
    DRAW_REFUND = 'draw_refund', 'Draw Refund'


class LedgerDirection(models.TextChoices):
    CREDIT = 'credit', 'Credit'
    DEBIT = 'debit', 'Debit'
