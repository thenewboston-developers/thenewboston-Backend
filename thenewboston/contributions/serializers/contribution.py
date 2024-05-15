from django_restql.fields import NestedField
from rest_framework.serializers import IntegerField

from thenewboston.contributions.models.contribution import ContributionType
from thenewboston.cores.serializers.core import CoreReadSerializer
from thenewboston.general.fields import FixedField
from thenewboston.general.serializers import BaseModelSerializer, CreateOnlyCurrentUserDefault
from thenewboston.github.serializers.github_user import GitHubUserSerializer
from thenewboston.github.serializers.issue import IssueSerializer
from thenewboston.github.serializers.pull import PullSerializer
from thenewboston.github.serializers.repo import RepoSerializer
from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Contribution


class ContributionSerializer(BaseModelSerializer):
    core = NestedField(CoreReadSerializer, accept_pk_only=True)
    # TODO(dmu) LOW: Consider adding validation for `github_user.reward_recipient == user`
    github_user = NestedField(GitHubUserSerializer, accept_pk_only=True, required=False)
    # TODO(dmu) LOW: Allow providing `issue` for manual contributions
    issue = NestedField(IssueSerializer, accept_pk_only=True, required=False)
    repo = NestedField(RepoSerializer, accept_pk_only=True, required=False)
    pull = PullSerializer(read_only=True)
    user = FixedField(UserReadSerializer, default=CreateOnlyCurrentUserDefault())
    contribution_type = FixedField(IntegerField, default=ContributionType.MANUAL.value)  # type: ignore

    class Meta:
        model = Contribution
        # Providing list of fields explicitly to avoid accidental exposure of new fields for read or modification
        fields = (
            'id',
            'contribution_type',
            'github_user',
            'issue',
            'pull',
            'reward_amount',
            'assessment_explanation',
            'assessment_points',
            'description',
            'created_date',
            'modified_date',
            'repo',
            'user',
            'core',
        )
        extra_kwargs = {'description': {'required': True}}
        read_only_fields = (
            'id',
            'pull',
            'reward_amount',
            'assessment_explanation',
            'assessment_points',
            'created_date',
            'modified_date',
        )
