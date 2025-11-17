from rest_framework import serializers

from thenewboston.currencies.models import Currency
from thenewboston.currencies.serializers.currency import CurrencyTinySerializer

from .bonsai_highlight import BonsaiHighlightSerializer
from .bonsai_image import BonsaiImageSerializer
from ..models import Bonsai, BonsaiHighlight, BonsaiImage


class BonsaiSerializer(serializers.ModelSerializer):
    highlights = BonsaiHighlightSerializer(many=True, required=False, default=list)
    images = BonsaiImageSerializer(many=True, required=False, default=list)
    price_currency = CurrencyTinySerializer(read_only=True)
    price_currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(),
        write_only=True,
        source='price_currency',
    )

    class Meta:
        model = Bonsai
        fields = (
            'id',
            'slug',
            'name',
            'species',
            'genus',
            'cultivar',
            'style',
            'size',
            'origin',
            'pot',
            'teaser',
            'description',
            'price_amount',
            'price_currency',
            'price_currency_id',
            'status',
            'highlights',
            'images',
            'created_date',
            'modified_date',
        )
        read_only_fields = (
            'id',
            'created_date',
            'modified_date',
        )

    def create(self, validated_data):
        highlights_data = validated_data.pop('highlights', [])
        images_data = validated_data.pop('images', [])
        bonsai = super().create(validated_data)
        self._upsert_related(bonsai, highlights_data, BonsaiHighlight, 'highlights', ('text',))
        self._upsert_related(bonsai, images_data, BonsaiImage, 'images', ('url',))
        return bonsai

    def update(self, instance, validated_data):
        highlights_data = validated_data.pop('highlights', None)
        images_data = validated_data.pop('images', None)
        bonsai = super().update(instance, validated_data)

        if highlights_data is not None:
            self._upsert_related(bonsai, highlights_data, BonsaiHighlight, 'highlights', ('text',))

        if images_data is not None:
            self._upsert_related(bonsai, images_data, BonsaiImage, 'images', ('url',))

        return bonsai

    def _upsert_related(self, bonsai, related_data, model, related_name, allowed_fields):
        existing_ids = []
        for index, item in enumerate(related_data):
            item_id = item.get('id')
            data = {field: item.get(field) for field in allowed_fields if item.get(field) is not None}
            data['order'] = item.get('order', index)

            if item_id:
                model.objects.filter(id=item_id, bonsai=bonsai).update(**data)
                existing_ids.append(item_id)
            else:
                obj = model.objects.create(bonsai=bonsai, **data)
                existing_ids.append(obj.id)

        getattr(bonsai, related_name).exclude(id__in=existing_ids).delete()
