import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from model_bakery import baker

from thenewboston.connect_five.models import ConnectFiveStats
from thenewboston.invitations.models import Invitation

User = get_user_model()


@pytest.mark.django_db
def test_invitations_join_recipient_stats_without_extra_queries(authenticated_api_client):
    owner = authenticated_api_client.forced_user
    first = baker.make(User)
    baker.make(ConnectFiveStats, user=first, elo=1400)
    baker.make(Invitation, owner=owner, recipient=first)
    with CaptureQueriesContext(connection) as queries:
        response = authenticated_api_client.get('/api/invitations')
    assert response.status_code == 200
    single_count = len(queries)
    for _ in range(7):
        baker.make(Invitation, owner=owner, recipient=baker.make(User))
    unused = baker.make(Invitation, owner=owner, recipient=None)
    baker.make(Invitation, owner=baker.make(User), recipient=baker.make(User))

    with CaptureQueriesContext(connection) as queries:
        response = authenticated_api_client.get('/api/invitations')

    assert response.status_code == 200
    assert len(queries) == single_count
    assert single_count <= 3
    assert len(response.data) == 9
    for invitation in response.data:
        assert invitation['owner'] == owner.pk
        if invitation['id'] == unused.pk:
            assert invitation['recipient'] is None
        else:
            recipient = invitation['recipient']
            assert recipient['connect_five_elo'] == (1400 if recipient['id'] == first.pk else None)
