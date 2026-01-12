from thenewboston.general.enums import MessageType

from ..consumers import ConnectFiveConsumer
from ..serializers import ConnectFiveChallengeReadSerializer, ConnectFiveMatchReadSerializer


def stream_challenge_update(*, challenge, request=None, challenge_data=None):
    if challenge_data is None:
        challenge_data = ConnectFiveChallengeReadSerializer(challenge, context={'request': request}).data

    ConnectFiveConsumer.stream_challenge(
        message_type=MessageType.UPDATE_CONNECT_FIVE_CHALLENGE,
        challenge_data=challenge_data,
        user_ids=[challenge.challenger_id, challenge.opponent_id],
    )

    return challenge_data


def stream_match_update(*, match, request=None, match_data=None):
    if match_data is None:
        match_data = ConnectFiveMatchReadSerializer(match, context={'request': request}).data

    ConnectFiveConsumer.stream_match(
        message_type=MessageType.UPDATE_CONNECT_FIVE_MATCH,
        match_data=match_data,
        user_ids=[match.player_a_id, match.player_b_id],
    )

    return match_data
