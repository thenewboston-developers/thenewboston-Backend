from django import forms
from django.contrib import admin
from django.db import transaction

from .models import CasinoBet, CasinoCommitment, CasinoFund, CasinoGameConfig, CasinoLedgerEntry
from .rules import RULES


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class FundForm(forms.ModelForm):
    class Meta:
        model = CasinoFund
        fields = ['enabled', 'risk_limit_bps']

    def clean_risk_limit_bps(self):
        value = self.cleaned_data['risk_limit_bps']
        if not 1 <= value <= 10000:
            raise forms.ValidationError('Choose 1 to 10,000 basis points.')
        return value


@admin.register(CasinoFund)
class CasinoFundAdmin(ReadOnlyAdmin):
    form = FundForm
    list_display = ('id', 'balance', 'reserved', 'available', 'enabled', 'risk_limit_bps')
    readonly_fields = ('id', 'currency', 'balance', 'reserved', 'available', 'created_date', 'modified_date')

    def has_change_permission(self, request, obj=None):
        return admin.ModelAdmin.has_change_permission(self, request, obj)

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        locked = CasinoFund.objects.select_for_update().get(pk=obj.pk)
        locked.enabled = obj.enabled
        locked.risk_limit_bps = obj.risk_limit_bps
        locked.save(update_fields=['enabled', 'risk_limit_bps', 'modified_date'])


class GameConfigForm(forms.ModelForm):
    class Meta:
        model = CasinoGameConfig
        fields = ['enabled', 'min_bet', 'rules_version']

    def clean(self):
        data = super().clean()
        if (self.instance.game, data.get('rules_version')) not in RULES:
            raise forms.ValidationError('This rules version is not installed.')
        return data


@admin.register(CasinoGameConfig)
class CasinoGameConfigAdmin(ReadOnlyAdmin):
    form = GameConfigForm
    list_display = ('game', 'enabled', 'min_bet', 'rules_version')
    readonly_fields = ('game', 'created_date', 'modified_date')

    def has_change_permission(self, request, obj=None):
        return admin.ModelAdmin.has_change_permission(self, request, obj)

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        CasinoFund.objects.select_for_update().get(pk=1)
        locked = CasinoGameConfig.objects.select_for_update().get(pk=obj.pk)
        for field in ('enabled', 'min_bet', 'rules_version'):
            setattr(locked, field, getattr(obj, field))
        locked.save(update_fields=['enabled', 'min_bet', 'rules_version', 'modified_date'])


@admin.register(CasinoBet)
class CasinoBetAdmin(ReadOnlyAdmin):
    list_display = ('id', 'user', 'game', 'amount', 'status', 'payout', 'house_exposure', 'created_date')
    list_filter = ('game', 'status')
    list_select_related = ('user',)
    exclude = ('request_fingerprint', 'commitment', 'client_seed', 'revealed_server_seed', 'result')


@admin.register(CasinoLedgerEntry)
class CasinoLedgerAdmin(ReadOnlyAdmin):
    list_display = ('id', 'user', 'kind', 'amount', 'bet_id', 'request_id', 'created_date')
    list_filter = ('kind',)
    list_select_related = ('user',)


@admin.register(CasinoCommitment)
class CasinoCommitmentAdmin(ReadOnlyAdmin):
    list_display = ('id', 'user', 'server_seed_hash', 'expires_at', 'used_at')
    list_select_related = ('user',)
    exclude = ('encrypted_server_seed',)
