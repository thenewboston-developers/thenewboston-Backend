from django.db import migrations


def use_roulette_version_2(apps, schema_editor):
    # Same wheel and payouts; one spin now settles chips on several spots. Version 1 receipts keep verifying.
    config = apps.get_model('casino', 'CasinoGameConfig')
    config.objects.filter(game='roulette', rules_version=1).update(rules_version=2)


def use_roulette_version_1(apps, schema_editor):
    config = apps.get_model('casino', 'CasinoGameConfig')
    config.objects.filter(game='roulette', rules_version=2).update(rules_version=1)


class Migration(migrations.Migration):
    dependencies = [('casino', '0003_slots_rules_version_2')]
    operations = [migrations.RunPython(use_roulette_version_2, use_roulette_version_1)]
