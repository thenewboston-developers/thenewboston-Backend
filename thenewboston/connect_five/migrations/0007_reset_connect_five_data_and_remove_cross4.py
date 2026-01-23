from django.db import migrations

from thenewboston.connect_five.constants import ELO_STARTING_SCORE


def wipe_connect_five_data(apps, schema_editor):
    ConnectFiveChallenge = apps.get_model('connect_five', 'ConnectFiveChallenge')
    ConnectFiveEscrow = apps.get_model('connect_five', 'ConnectFiveEscrow')
    ConnectFiveLedgerEntry = apps.get_model('connect_five', 'ConnectFiveLedgerEntry')
    ConnectFiveMatch = apps.get_model('connect_five', 'ConnectFiveMatch')
    ConnectFiveMatchEvent = apps.get_model('connect_five', 'ConnectFiveMatchEvent')
    ConnectFiveMatchPlayer = apps.get_model('connect_five', 'ConnectFiveMatchPlayer')
    ConnectFiveStats = apps.get_model('connect_five', 'ConnectFiveStats')

    ConnectFiveMatchEvent.objects.all().delete()
    ConnectFiveMatchPlayer.objects.all().delete()
    ConnectFiveMatch.objects.all().delete()
    ConnectFiveLedgerEntry.objects.all().delete()
    ConnectFiveEscrow.objects.all().delete()
    ConnectFiveChallenge.objects.all().delete()

    ConnectFiveStats.objects.update(
        draws=0,
        elo=ELO_STARTING_SCORE,
        losses=0,
        matches_played=0,
        wins=0,
    )


class Migration(migrations.Migration):
    dependencies = [
        ('connect_five', '0006_alter_connectfivechallenge_status'),
    ]

    operations = [
        migrations.RunPython(wipe_connect_five_data, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='connectfivematchplayer',
            name='inventory_cross4',
        ),
    ]
