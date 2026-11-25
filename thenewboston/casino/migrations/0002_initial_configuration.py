from django.db import migrations


def configure_casino(apps, schema_editor):
    # Create empty infrastructure only. Funding always transfers existing TNB from an admin wallet.
    apps.get_model('casino', 'CasinoFund').objects.get_or_create(pk=1)
    config = apps.get_model('casino', 'CasinoGameConfig')
    for game in ('slots', 'roulette'):
        config.objects.get_or_create(game=game, defaults={'enabled': True, 'rules_version': 1, 'min_bet': 1})


class Migration(migrations.Migration):
    dependencies = [('casino', '0001_initial')]
    operations = [migrations.RunPython(configure_casino, migrations.RunPython.noop)]
