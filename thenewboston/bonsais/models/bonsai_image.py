from django.db import models


class BonsaiImage(models.Model):
    bonsai = models.ForeignKey('bonsais.Bonsai', related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='bonsai_images/', blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.bonsai.name} image'
