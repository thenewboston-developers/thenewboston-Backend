from django.db import models

from thenewboston.general.models import CreatedModified


class ArtworkTransfer(CreatedModified):
    artwork = models.ForeignKey('art.Artwork', on_delete=models.CASCADE)
    previous_owner = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='transferred_artworks',
    )
    new_owner = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='acquired_artworks',
    )

    def __str__(self):
        previous_owner_username = getattr(self.previous_owner, 'username', 'None')
        new_owner_username = getattr(self.new_owner, 'username', 'None')

        return (
            f'Transfer ID: {self.pk} | '
            f'Artwork: {self.artwork.name} | '
            f'From: {previous_owner_username} | '
            f'To: {new_owner_username}'
        )
