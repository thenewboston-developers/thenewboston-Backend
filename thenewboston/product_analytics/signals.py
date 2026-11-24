from django.apps import apps
from django.conf import settings
from django.db.models.signals import post_save, pre_save

from .events import (
    MATCHES,
    record_deposit,
    record_engagement,
    record_invitation,
    record_match,
    record_reward,
    safely_record,
)


def before_match_save(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw or not settings.POSTHOG_ENABLED:
        return
    if update_fields is not None and 'status' not in update_fields:
        instance._analytics_status_written = False
        instance._analytics_skip_status = False
        return
    instance._analytics_status_written = True
    instance._analytics_skip_status = True

    def read_status():
        instance._analytics_previous_status = (
            sender.objects.filter(pk=instance.pk).values_list('status', flat=True).first()
        )
        instance._analytics_skip_status = False

    safely_record(read_status)


def after_match_save(sender, instance, created=False, raw=False, **kwargs):
    if raw or getattr(instance, '_analytics_skip_status', False):
        return
    safely_record(
        record_match,
        sender._meta.app_label,
        instance,
        created=created,
        previous_status=getattr(instance, '_analytics_previous_status', None),
        status_written=getattr(instance, '_analytics_status_written', True),
    )


def after_reward_save(sender, instance, created=False, raw=False, **kwargs):
    if created and not raw:
        safely_record(record_reward, instance)


def after_deposit_save(sender, instance, created=False, raw=False, **kwargs):
    if created and not raw:
        safely_record(record_deposit, instance)


def after_invitation_save(sender, instance, raw=False, **kwargs):
    if not raw:
        safely_record(record_invitation, instance)


def after_game_event_save(sender, instance, created=False, raw=False, **kwargs):
    if created and not raw:
        safely_record(record_engagement, sender._meta.app_label, instance)


def connect_signals():
    for game, (model, *_) in MATCHES.items():
        sender = apps.get_model(game, model)
        pre_save.connect(before_match_save, sender=sender, dispatch_uid=f'analytics.before.{game}')
        post_save.connect(after_match_save, sender=sender, dispatch_uid=f'analytics.after.{game}')
        event_model = model + 'Event' if game == 'connect_five' else model.replace('Match', 'Event')
        post_save.connect(
            after_game_event_save,
            sender=apps.get_model(game, event_model),
            dispatch_uid=f'analytics.action.{game}',
        )
    post_save.connect(after_reward_save, sender='game_rewards.GameRewardDecision', dispatch_uid='analytics.reward')
    post_save.connect(after_deposit_save, sender='game_rewards.GameFundDeposit', dispatch_uid='analytics.deposit')
    post_save.connect(
        after_invitation_save, sender='connect_five.ConnectFiveChallenge', dispatch_uid='analytics.invitation'
    )
