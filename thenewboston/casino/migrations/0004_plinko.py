from django.db import migrations


def configure_plinko(apps, schema_editor):
    # Enables the game against the existing casino fund; never mints or moves money.
    apps.get_model('casino', 'CasinoGameConfig').objects.get_or_create(
        game='plinko', defaults={'enabled': True, 'rules_version': 1, 'min_bet': 1}
    )


def disable_plinko(apps, schema_editor):
    # Retain configuration and historical financial records on rollback.
    apps.get_model('casino', 'CasinoGameConfig').objects.filter(game='plinko').update(enabled=False)


class Migration(migrations.Migration):
    dependencies = [('casino', '0003_slots_rules_version_2')]
    operations = [migrations.RunPython(configure_plinko, disable_plinko)]
