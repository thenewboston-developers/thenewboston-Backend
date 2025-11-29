from django.db import models


class BonsaiHighlight(models.Model):
    bonsai = models.ForeignKey('bonsais.Bonsai', related_name='highlights', on_delete=models.CASCADE)
    text = models.CharField(max_length=500)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.bonsai.name} highlight'
