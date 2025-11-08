from django.contrib import admin
from .models import Country, State, LGA

@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ['name', 'iso3', 'phone_code', 'currency', 'region']
    list_filter = ['region', 'subregion']
    search_fields = ['name', 'iso3', 'iso2']
    readonly_fields = ['emoji']

@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = ['name', 'country', 'state_code']
    list_filter = ['country']
    search_fields = ['name', 'state_code']

@admin.register(LGA)
class LGAAdmin(admin.ModelAdmin):
    list_display = ['name', 'state', 'country_name']
    list_filter = ['state', 'state__country']
    search_fields = ['name']
    
    def country_name(self, obj):
        return obj.state.country.name
    country_name.short_description = 'Country'