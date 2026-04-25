from rest_framework import serializers
from .models import Country, State, LGA

class LGASerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source='state.name', read_only=True)
    country_name = serializers.CharField(source='state.country.name', read_only=True)
    
    class Meta:
        model = LGA
        fields = ['id', 'name', 'state', 'state_name', 'country_name']

class StateSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source='country.name', read_only=True)
    lgas = LGASerializer(many=True, read_only=True)
    
    class Meta:
        model = State
        fields = ['id', 'name', 'state_code', 'country', 'country_name', 'lgas']

class CountrySerializer(serializers.ModelSerializer):
    states = StateSerializer(many=True, read_only=True)
    
    class Meta:
        model = Country
        fields = ['id', 'name', 'iso3', 'iso2', 'phone_code', 'capital', 
                 'currency', 'currency_name', 'currency_symbol', 'region', 
                 'subregion', 'emoji', 'states']
        

        


class CountryLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        # Only fetch what is needed for the Dropdown
        fields = ['id', 'name', 'emoji', 'phone_code']

class StateLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = ['id', 'name', 'state_code']