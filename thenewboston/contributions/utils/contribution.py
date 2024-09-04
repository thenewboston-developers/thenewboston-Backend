from collections import defaultdict
from datetime import datetime, timedelta


def get_top_contributors(queryset, days_back=7, top_n=5):
    """
    Get the top contributors from the list of contributions over a specified number of days.
    Args:
        days_back (int): The number of days in the past to consider for contributions.
        top_n (int): The number of top contributors to retrieve.
    Returns:
        list: A list of dictionaries representing the top contributors, each with
              user information, core information, total reward amount, and position.
    """
    contributions = queryset

    if days_back is not None:
        start_date = datetime.today() - timedelta(days=int(days_back))
        contributions = contributions.filter(created_date__date__gte=start_date)

    contribution_sum_by_user = defaultdict(
        lambda: {
            'total_reward_amount': 0,
            'user': None,
            'core': None,
            'position': ''
        }
    )

    for contribution in contributions:
        user_id = contribution.user.id
        reward_amount = contribution.reward_amount or 0
        if contribution_sum_by_user[user_id]['user'] is None:
            contribution_sum_by_user[user_id]['user'] = contribution.user
            contribution_sum_by_user[user_id]['core'] = contribution.core
        contribution_sum_by_user[user_id]['total_reward_amount'] += reward_amount

    # Sort contributors by total reward amount in descending order and take the top_n
    top_contributors = sorted(contribution_sum_by_user.values(), key=lambda x: x['total_reward_amount'],
                              reverse=True)[:top_n]

    for index, contributor in enumerate(top_contributors):
        contributor['position'] = index + 1

    return top_contributors


def get_cumulative_contributions(queryset):
    """
    Computes cumulative reward amounts for a list of contributions.
    Returns:
        list: A list of dictionaries, each containing the contribution's creation date, reward amount,
        cumulative total rewards, and core logo URL.
    The contributions are sorted by their creation date, and each entry in the returned list is appended
    with a cumulative reward total.
    """
    contributions = queryset.order_by('created_date')
    cumulative_total = 0
    result = []
    for contribution in contributions:
        reward_amount = contribution.reward_amount or 0
        cumulative_total += reward_amount
        result.append({
            'created_date': contribution.created_date,
            'reward_amount': reward_amount,
            'total_rewards': cumulative_total,
        })
    return result
