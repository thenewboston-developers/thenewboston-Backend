from django.db import migrations

BATCH_SIZE = 1000


def copy_post_images(apps, schema_editor):
    """Give every post that has an image in the deprecated `Post.image` column a `PostImage` row for the same file."""
    Post = apps.get_model('social', 'Post')
    PostImage = apps.get_model('social', 'PostImage')

    posts = (
        Post.objects.exclude(image='')
        # Makes the migration safe to run again after being reversed without the table having been dropped
        .exclude(images__isnull=False)
        .values_list('id', 'owner_id', 'image')
    )
    batch = []
    for post_id, owner_id, image in posts.iterator(chunk_size=BATCH_SIZE):
        batch.append(PostImage(post_id=post_id, owner_id=owner_id, image=image, position=0))
        if len(batch) >= BATCH_SIZE:
            PostImage.objects.bulk_create(batch)
            batch = []

    if batch:
        PostImage.objects.bulk_create(batch)


class Migration(migrations.Migration):
    dependencies = [
        ('social', '0007_post_image'),
    ]

    operations = [
        # Nothing to undo: `Post.image` keeps its values and reversing 0007 drops the copied rows
        migrations.RunPython(copy_post_images, migrations.RunPython.noop),
    ]
