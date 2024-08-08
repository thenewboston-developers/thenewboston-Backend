from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from thenewboston.general.clients.llm import LLMClient, make_prompt_kwargs
from thenewboston.general.models import CreatedModified
from thenewboston.general.utils.transfers import change_wallet_balance


class ContributionType(models.IntegerChoices):
    PULL_REQUEST = 1, 'Pull request'
    MANUAL = 2, 'Manual'


class Contribution(CreatedModified):
    core = models.ForeignKey('cores.Core', on_delete=models.CASCADE)
    contribution_type = models.PositiveSmallIntegerField(
        choices=ContributionType.choices,
        default=ContributionType.PULL_REQUEST.value  # type: ignore
    )
    # TODO(dmu) MEDIUM: Technically it is possible to make different GitHubUsers reward the same User
    #                   We keep `github_user`, so we can trace back which github user made the contribution.
    #                   If we do not need such tracing back or we do not need multiple github users to refer
    #                   the same User refactor it by either removing `github_user` field or moving it to
    #                   `User.github_user`. In latter case we might also want to remove `GitHubUser.reward_recipient`
    #                   to avoid bidirectional duplicating link
    github_user = models.ForeignKey('github.GitHubUser', on_delete=models.CASCADE, null=True, blank=True)

    # TODO(dmu) LOW: Consider using GenericForeignKey instead of `issue` and `pull`
    issue = models.ForeignKey('github.Issue', on_delete=models.CASCADE, null=True, blank=True)
    pull = models.ForeignKey(
        'github.Pull',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='contributions',
    )

    # TODO(dmu) MEDIUM: `repo` can be accessed via `issue.issue` or `pull.repo`. Consider removal
    repo = models.ForeignKey('github.Repo', on_delete=models.CASCADE, null=True, blank=True)

    # `rewarded_at` and `reward_amount` also serve as a flag that reward has been granted
    rewarded_at = models.DateTimeField(null=True, blank=True)
    reward_amount = models.PositiveBigIntegerField(null=True, blank=True)
    # TODO(dmu) MEDIUM: users.User is navigatable through both `user` attribute and through
    #                   `github_user->reward_recipient`. Consider keeping just one of them or add a comment
    #                   describing why both should stay. Be aware that now we have manual contributions which
    #                   have `github_user = None`
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)

    description = models.TextField(blank=True)

    assessment_points = models.PositiveIntegerField(null=True, blank=True)
    assessment_explanation = models.TextField(blank=True)

    def __str__(self):
        return f'ID: {self.pk} | Reward Amount: {self.reward_amount}'

    def assess(self, save=True):
        # All potential exceptions must be handled by the caller of the method

        match self.contribution_type:
            case ContributionType.PULL_REQUEST.value:
                pull = self.pull
                assert pull
                assert pull.is_assessed()
                assessment_points = pull.assessment_points
                assessment_explanation = pull.assessment_explanation
            case ContributionType.MANUAL.value:
                result = LLMClient.get_instance().get_chat_completion(
                    input_variables={'description': self.description},
                    tracked_user=self.user,
                    tags=['manual_contribution_assessment'],
                    **make_prompt_kwargs(settings.GITHUB_MANUAL_CONTRIBUTION_ASSESSMENT_PROMPT_NAME),
                )
                assessment_points = result['assessment']
                assessment_explanation = result['explanation']
            case _:
                raise NotImplementedError('Unsupported contribution type')

        self.assessment_points = assessment_points
        self.assessment_explanation = assessment_explanation

        if save:
            self.save()

    def is_assessed(self):
        return self.assessment_points is not None and self.assessment_explanation

    def calculate_reward_amount(self):
        now = timezone.now()
        assessment_points = self.assessment_points
        if (contribution_type := self.contribution_type) == ContributionType.PULL_REQUEST.value:
            return now, assessment_points

        assert contribution_type == ContributionType.MANUAL.value
        today_starts_at = now.replace(hour=0, minute=0, second=0, microsecond=0)

        user = self.user
        total_daily_contributions = Contribution.objects.filter(
            user=user,
            contribution_type=ContributionType.MANUAL.value,
            rewarded_at__gte=today_starts_at,
            rewarded_at__lt=today_starts_at + timedelta(days=1),
        ).aggregate(total_reward_amount=models.Sum('reward_amount'))['total_reward_amount'] or 0

        manual_contribution_reward_daily_limit = user.manual_contribution_reward_daily_limit
        return now, min(max(manual_contribution_reward_daily_limit - total_daily_contributions, 0), assessment_points)

    def reward(self, save=True):
        assert self.is_assessed()

        if self.is_rewarded():
            return

        now, reward_amount = self.calculate_reward_amount()
        change_wallet_balance(self.user.get_reward_wallet_for_core(self.core_id), reward_amount)
        self.rewarded_at = now
        self.reward_amount = reward_amount
        if save:
            self.save()

    def is_rewarded(self):
        return self.rewarded_at is not None and self.reward_amount is not None
