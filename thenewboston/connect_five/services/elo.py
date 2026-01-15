import math

from ..constants import ELO_K_PROVISIONAL, ELO_K_STANDARD, ELO_MINIMUM, ELO_PROVISIONAL_MATCHES, ELO_STARTING_SCORE
from ..models import ConnectFiveStats


def get_or_create_stats(*, user, for_update=False):
    queryset = ConnectFiveStats.objects
    if for_update:
        queryset = queryset.select_for_update()

    stats, _ = queryset.get_or_create(user=user, defaults={'elo': ELO_STARTING_SCORE})
    return stats


def get_k_factor(*, stats):
    return ELO_K_PROVISIONAL if stats.matches_played < ELO_PROVISIONAL_MATCHES else ELO_K_STANDARD


def get_expected_score(*, player_elo, opponent_elo):
    return 1 / (1 + math.pow(10, (opponent_elo - player_elo) / 400))


def calculate_new_elo(*, player_elo, opponent_elo, score, k_factor):
    expected_score = get_expected_score(player_elo=player_elo, opponent_elo=opponent_elo)
    updated_elo = round(player_elo + k_factor * (score - expected_score))
    return max(updated_elo, ELO_MINIMUM)


def apply_match_result(*, match, winner=None, is_draw=False):
    stats_a = get_or_create_stats(user=match.player_a, for_update=True)
    stats_b = get_or_create_stats(user=match.player_b, for_update=True)

    player_a_before = stats_a.elo
    player_b_before = stats_b.elo

    if is_draw:
        player_a_after = player_a_before
        player_b_after = player_b_before
        stats_a.draws += 1
        stats_b.draws += 1
    else:
        if not winner:
            raise ValueError('Winner is required for non-draw match results.')

        player_a_score = 1 if winner.id == match.player_a_id else 0
        player_b_score = 1 if winner.id == match.player_b_id else 0
        player_a_after = calculate_new_elo(
            player_elo=player_a_before,
            opponent_elo=player_b_before,
            score=player_a_score,
            k_factor=get_k_factor(stats=stats_a),
        )
        player_b_after = calculate_new_elo(
            player_elo=player_b_before,
            opponent_elo=player_a_before,
            score=player_b_score,
            k_factor=get_k_factor(stats=stats_b),
        )

        if player_a_score:
            stats_a.wins += 1
            stats_b.losses += 1
        else:
            stats_a.losses += 1
            stats_b.wins += 1

    stats_a.elo = player_a_after
    stats_b.elo = player_b_after
    stats_a.matches_played += 1
    stats_b.matches_played += 1
    stats_a.save(update_fields=['draws', 'elo', 'losses', 'matches_played', 'modified_date', 'wins'])
    stats_b.save(update_fields=['draws', 'elo', 'losses', 'matches_played', 'modified_date', 'wins'])

    return {
        'player_a': {'after': player_a_after, 'before': player_a_before},
        'player_b': {'after': player_b_after, 'before': player_b_before},
    }
