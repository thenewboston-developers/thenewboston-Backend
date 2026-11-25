from django.db import migrations


def configure_let_it_ride(apps, schema_editor):
    # Only enables the game against the existing casino fund; a migration never mints or moves coins.
    apps.get_model('casino', 'CasinoGameConfig').objects.get_or_create(
        game='let_it_ride', defaults={'enabled': True, 'rules_version': 1, 'min_bet': 3}
    )


def disable_let_it_ride(apps, schema_editor):
    # Keep the configuration row and every financial record on rollback.
    apps.get_model('casino', 'CasinoGameConfig').objects.filter(game='let_it_ride').update(enabled=False)


class Migration(migrations.Migration):
    dependencies = [('casino', '0002_initial_configuration')]
    operations = [migrations.RunPython(configure_let_it_ride, disable_let_it_ride)]
