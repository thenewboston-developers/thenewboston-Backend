from django.db import migrations


def configure_video_poker(apps, schema_editor):
    # Only enable the game. The shared treasury is funded by existing TNB, never by migration.
    apps.get_model('casino', 'CasinoGameConfig').objects.get_or_create(
        game='video_poker', defaults={'enabled': True, 'rules_version': 1, 'min_bet': 1}
    )


def disable_video_poker(apps, schema_editor):
    # Retain configuration and historical financial records on rollback.
    apps.get_model('casino', 'CasinoGameConfig').objects.filter(game='video_poker').update(enabled=False)


class Migration(migrations.Migration):
    dependencies = [('video_poker', '0001_initial')]
    operations = [migrations.RunPython(configure_video_poker, disable_video_poker)]
