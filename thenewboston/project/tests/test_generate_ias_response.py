from unittest.mock import ANY, patch

from thenewboston.general.enums import MessageType
from thenewboston.general.tests.vcr import assert_played, yield_cassette
from thenewboston.ia.models import Message
from thenewboston.ia.models.message import SenderType
from thenewboston.project.tasks import generate_ias_response


def test_generate_ias_response(ia_user, sample_conversation):
    assert Message.objects.count() == 0
    with (
        patch('thenewboston.ia.consumers.message.MessageConsumer.stream_message') as stream_message_mock,
        yield_cassette('generate_ias_response.yaml') as cassette,
        assert_played(cassette, count=3),
    ):
        generate_ias_response(sample_conversation.id)

    assert Message.objects.count() == 1
    message = Message.objects.get()
    assert message.conversation == sample_conversation
    assert message.sender == ia_user
    assert message.sender_type == SenderType.IA
    assert message.text == (
        "That sounds great! Let's start with some basics to get to know you a bit better. "
        'What are some of your hobbies or interests?'
    )

    # TODO(dmu) MEDIUM: Improve assertion for `message_data`
    stream_message_mock.assert_called_once_with(message_type=MessageType.CREATE_MESSAGE, message_data=ANY)
