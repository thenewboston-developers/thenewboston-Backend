import json

from django.http import QueryDict
from rest_framework import serializers

from thenewboston.currencies.models import Currency
from thenewboston.currencies.serializers.currency import CurrencyTinySerializer
from thenewboston.general.utils.image import process_image

from .bonsai_highlight import BonsaiHighlightSerializer
from .bonsai_image import BonsaiImageSerializer
from ..models import Bonsai, BonsaiHighlight, BonsaiImage


class BonsaiSerializer(serializers.ModelSerializer):
    highlights = BonsaiHighlightSerializer(many=True, required=False, default=list)
    images = BonsaiImageSerializer(many=True, read_only=True, default=list)
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

    def to_internal_value(self, data):
        data = self._ensure_mutable_data(data)
        self._prepare_nested_json(data, 'highlights')
        self._images_payload = self._extract_images_payload(data)
        return super().to_internal_value(data)

    def create(self, validated_data):
        highlights_data = validated_data.pop('highlights', [])
        images_data = getattr(self, '_images_payload', None)
        if images_data is None:
            images_data = []
        bonsai = super().create(validated_data)
        self._upsert_related(bonsai, highlights_data, BonsaiHighlight, 'highlights', ('text',))
        self._upsert_related(bonsai, images_data, BonsaiImage, 'images', ('image',))
        self._clear_prefetched_cache(bonsai, ('highlights', 'images'))
        return bonsai

    def update(self, instance, validated_data):
        highlights_data = validated_data.pop('highlights', None)
        images_data = getattr(self, '_images_payload', None)
        bonsai = super().update(instance, validated_data)

        if highlights_data is not None:
            self._upsert_related(bonsai, highlights_data, BonsaiHighlight, 'highlights', ('text',))
            self._clear_prefetched_cache(bonsai, ('highlights',))

        if images_data is not None:
            self._upsert_related(bonsai, images_data, BonsaiImage, 'images', ('image',))
            self._clear_prefetched_cache(bonsai, ('images',))

        return bonsai

    @staticmethod
    def _ensure_mutable_data(data):
        if isinstance(data, QueryDict):
            data = data.copy()
            data._mutable = True
        return data

    def _prepare_nested_json(self, data, field_name):
        value = data.get(field_name, serializers.empty)
        parsed_value = self._parse_json_array(value, field_name)
        if parsed_value is not None:
            data[field_name] = parsed_value

    def _extract_images_payload(self, data):
        value = data.get('images', serializers.empty)
        parsed_value = self._parse_json_array(value, 'images')
        if parsed_value is None:
            return None

        request = self.context.get('request')
        payload = []

        for index, item in enumerate(parsed_value):
            if not isinstance(item, dict):
                raise serializers.ValidationError({'images': 'Invalid JSON structure.'})

            entry = {
                'id': item.get('id'),
                'order': item.get('order', index),
            }

            if (image_file := item.get('image')) is not None:
                entry['image'] = image_file
            else:
                file_field = item.get('image_field')
                if file_field and request:
                    uploaded_file = request.FILES.get(file_field)
                    if uploaded_file:
                        entry['image'] = uploaded_file

            if not entry.get('id') and 'image' not in entry:
                raise serializers.ValidationError({'images': 'Image file is required for new images.'})

            payload.append(entry)

        data.pop('images', None)
        return payload

    @staticmethod
    def _parse_json_array(value, field_name):
        if value in (serializers.empty, None):
            return None

        parsed_value = value
        if isinstance(value, str):
            if not value.strip():
                return []
            try:
                parsed_value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError({field_name: 'Invalid JSON format.'}) from exc

        if parsed_value is None:
            return []

        if not isinstance(parsed_value, list):
            raise serializers.ValidationError({field_name: 'Invalid JSON structure.'})

        return parsed_value

    def _upsert_related(self, bonsai, related_data, model, related_name, allowed_fields):
        existing_ids = []
        for index, item in enumerate(related_data):
            if not isinstance(item, dict):
                continue
            item_id = item.get('id')
            data = {field: item.get(field) for field in allowed_fields if item.get(field) is not None}
            order = item.get('order', index)

            if 'image' in data and data['image']:
                data['image'] = process_image(data['image'])
            else:
                data.pop('image', None)

            if item_id:
                obj = model.objects.filter(id=item_id, bonsai=bonsai).first()
                if not obj:
                    continue
                update_fields = []
                if 'image' in data:
                    obj.image = data['image']
                    update_fields.append('image')
                if obj.order != order:
                    obj.order = order
                    update_fields.append('order')
                if update_fields:
                    obj.save(update_fields=update_fields)
                existing_ids.append(obj.id)
            else:
                if 'image' not in data or not data['image']:
                    raise serializers.ValidationError({'images': 'Image file is required for new images.'})
                data['order'] = order
                obj = model.objects.create(bonsai=bonsai, **data)
                existing_ids.append(obj.id)

        getattr(bonsai, related_name).exclude(id__in=existing_ids).delete()

    @staticmethod
    def _clear_prefetched_cache(instance, related_names):
        cache = getattr(instance, '_prefetched_objects_cache', None)
        if not cache:
            return
        for name in related_names:
            cache.pop(name, None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._images_payload = None
