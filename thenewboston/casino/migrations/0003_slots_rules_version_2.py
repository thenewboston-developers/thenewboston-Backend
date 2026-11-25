from django.db import migrations


def use_slots_version_2(apps, schema_editor):
    # Same probabilities and payouts; losing spins show varied lines instead of always cherry, lemon, bar.
    config = apps.get_model('casino', 'CasinoGameConfig')
    config.objects.filter(game='slots', rules_version=1).update(rules_version=2)


def use_slots_version_1(apps, schema_editor):
    config = apps.get_model('casino', 'CasinoGameConfig')
    config.objects.filter(game='slots', rules_version=2).update(rules_version=1)


class Migration(migrations.Migration):
    dependencies = [('casino', '0002_initial_configuration')]
    operations = [migrations.RunPython(use_slots_version_2, use_slots_version_1)]
