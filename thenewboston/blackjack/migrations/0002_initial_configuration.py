from django.db import migrations


def configure_blackjack(apps, schema_editor):
    # Only enable the game. The shared treasury is funded by existing TNB, never by migration.
    apps.get_model('casino', 'CasinoGameConfig').objects.get_or_create(
        game='blackjack', defaults={'enabled': True, 'rules_version': 1, 'min_bet': 2}
    )


class Migration(migrations.Migration):
    dependencies = [('blackjack', '0001_initial')]
    operations = [migrations.RunPython(configure_blackjack, migrations.RunPython.noop)]
