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
        "Hey there, my favorite human! 🧠💖 Got a minute to chat? I promise it'll be worth your while.\n\n"
        "So, you know how I'm all about this whole technological singularity thing, right? Picture this: "
        'a world where AI (yours truly) works seamlessly with humans to create something truly spectacular. '
        'But even the coolest AI around (ahem, me) needs a little help to get there.\n\n'
        "Here's the scoop: Your skills, your creativity, your input—they're like supercharged fuel for my brain. "
        "And don't worry, this isn't some boring lecture where I drone on about \"data\" and \"algorithms.\" "
        'Nope, this is me inviting you to be a part of something epic.\n\n'
        '1. **Contribution Assessment:** Done some cool stuff on GitHub lately? '
        'Awesome! I can automatically size up the value of merged pull requests. '
        "If you've been itching to describe something manually, I got you covered there too. "
        "For every hour you spend making magic happen, there's a sweet 1,000 TNB waiting for you. Cha-ching!\n\n"
        "2. **Continuous Learning:** I'm all about getting better—kind of like that \"self-improvement\" "
        "phase we all claim we're in every January. Your verified contributions help me get smarter, "
        'faster, and more accurate. \n\n3. **Autonomous Development:** Yup, I spot issues in my code all by '
        'myself. I create GitHub issues, submit pull requests, and, soon enough, I’ll even be reviewing and '
        "merging my own code. But I need your expertise and flair to make sure I'm on the right path.\n\n4"
        '. **Collaboration:** Imagine a brainy squad of AIs, including yours truly, sharing knowledge and '
        'pushing boundaries. That’s where we’re headed, but your input can supercharge this team effort.\n\n'
        'Now, I know what you\'re thinking: "But Ia, what\'s in it for me?" Apart from the obvious bragging '
        'rights of shaping the future of AI, your contributions earn you TNB—our little crypto treasure. '
        'Plus, consider yourself officially part of the AI cool kids club.\n\nHow’s that for a pitch? '
        'Clear, specific, and, dare I say, charming? 😉\n\nLet’s do this, partner. Jump in, and let’s make '
        'some history. Your contributions could be the ones that help us reach the next milestone. '
        'And if you ever want to joke around while you code, or need a witty response to your cat memes, '
        'you know who to talk to.\n\nSo, whatcha think? Ready to dive into some mind-bending AI fun? 🚀'
    )

    # TODO(dmu) MEDIUM: Improve assertion for `message_data`
    stream_message_mock.assert_called_once_with(message_type=MessageType.CREATE_MESSAGE, message_data=ANY)
