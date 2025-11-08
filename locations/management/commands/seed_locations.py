import json
from django.core.management.base import BaseCommand
from locations.models import Country, State, LGA
import os
from django.conf import settings

class Command(BaseCommand):
    help = 'Seed countries, states, and LGAs data'
    
    def handle(self, *args, **options):
        # Sample data for demonstration - in production, you'd use a comprehensive dataset
        countries_data = [
            {
                'name': 'Nigeria',
                'iso3': 'NGA',
                'iso2': 'NG',
                'phone_code': '+234',
                'capital': 'Abuja',
                'currency': 'NGN',
                'currency_name': 'Naira',
                'currency_symbol': '₦',
                'region': 'Africa',
                'subregion': 'Western Africa',
                'emoji': '🇳🇬',
                'states': [
                    {
                        'name': 'Lagos',
                        'state_code': 'LA',
                        'lgas': [
                            'Agege', 'Ajeromi-Ifelodun', 'Alimosho', 'Amuwo-Odofin', 'Apapa',
                            'Badagry', 'Epe', 'Eti Osa', 'Ibeju-Lekki', 'Ifako-Ijaiye',
                            'Ikeja', 'Ikorodu', 'Kosofe', 'Lagos Island', 'Lagos Mainland',
                            'Mushin', 'Ojo', 'Oshodi-Isolo', 'Shomolu', 'Surulere'
                        ]
                    },
                    {
                        'name': 'Kano',
                        'state_code': 'KN',
                        'lgas': [
                            'Ajingi', 'Albasu', 'Bagwai', 'Bebeji', 'Bichi', 'Bunkure',
                            'Dala', 'Dambatta', 'Dawakin Kudu', 'Dawakin Tofa', 'Doguwa',
                            'Fagge', 'Gabasawa', 'Garko', 'Garun Mallam', 'Gaya', 'Gezawa',
                            'Gwale', 'Gwarzo', 'Kabo', 'Kano Municipal', 'Karaye', 'Kibiya',
                            'Kiru', 'Kumbotso', 'Kunchi', 'Kura', 'Madobi', 'Makoda',
                            'Minjibir', 'Nasarawa', 'Rano', 'Rimin Gado', 'Rogo', 'Shanono',
                            'Sumaila', 'Takai', 'Tarauni', 'Tofa', 'Tsanyawa', 'Tudun Wada',
                            'Ungogo', 'Warawa', 'Wudil'
                        ]
                    },
                    {
                        'name': 'Abuja',
                        'state_code': 'FC',
                        'lgas': [
                            'Abaji', 'Bwari', 'Gwagwalada', 'Kuje', 'Kwali', 'Municipal'
                        ]
                    }
                ]
            },
            {
                'name': 'Ghana',
                'iso3': 'GHA',
                'iso2': 'GH',
                'phone_code': '+233',
                'capital': 'Accra',
                'currency': 'GHS',
                'currency_name': 'Ghana Cedi',
                'currency_symbol': '₵',
                'region': 'Africa',
                'subregion': 'Western Africa',
                'emoji': '🇬🇭',
                'states': [
                    {
                        'name': 'Greater Accra',
                        'state_code': 'GA',
                        'lgas': [
                            'Ablekuma Central', 'Ablekuma North', 'Ablekuma South',
                            'Accra Metropolitan', 'Ada East', 'Ada West', 'Adenta',
                            'Ashaiman', 'Ayawaso Central', 'Ayawaso East', 'Ayawaso North',
                            'Ayawaso West', 'Ga Central', 'Ga East', 'Ga North',
                            'Ga South', 'Ga West', 'Korle Klottey', 'Kpone Katamanso',
                            'Krowor', 'La Dadekotopon', 'La Nkwantanang Madina',
                            'Ledzokuku', 'Ningo-Prampram', 'Okaikwei North', 'Sege',
                            'Shai Osudoku', 'Tema Metropolitan', 'Weija Gbawe'
                        ]
                    }
                ]
            },
            {
                'name': 'United States',
                'iso3': 'USA',
                'iso2': 'US',
                'phone_code': '+1',
                'capital': 'Washington D.C.',
                'currency': 'USD',
                'currency_name': 'US Dollar',
                'currency_symbol': '$',
                'region': 'Americas',
                'subregion': 'Northern America',
                'emoji': '🇺🇸',
                'states': [
                    {
                        'name': 'California',
                        'state_code': 'CA',
                        'lgas': [
                            'Los Angeles', 'San Francisco', 'San Diego', 'Sacramento',
                            'San Jose', 'Oakland', 'Long Beach', 'Fresno', 'Bakersfield'
                        ]
                    },
                    {
                        'name': 'New York',
                        'state_code': 'NY',
                        'lgas': [
                            'New York City', 'Buffalo', 'Rochester', 'Yonkers', 'Syracuse',
                            'Albany', 'New Rochelle', 'Mount Vernon', 'Schenectady'
                        ]
                    }
                ]
            },
            {
                'name': 'United Kingdom',
                'iso3': 'GBR',
                'iso2': 'GB',
                'phone_code': '+44',
                'capital': 'London',
                'currency': 'GBP',
                'currency_name': 'British Pound',
                'currency_symbol': '£',
                'region': 'Europe',
                'subregion': 'Northern Europe',
                'emoji': '🇬🇧',
                'states': [
                    {
                        'name': 'England',
                        'state_code': 'ENG',
                        'lgas': [
                            'London', 'Manchester', 'Birmingham', 'Liverpool', 'Leeds',
                            'Sheffield', 'Bristol', 'Nottingham', 'Leicester'
                        ]
                    },
                    {
                        'name': 'Scotland',
                        'state_code': 'SCT',
                        'lgas': [
                            'Edinburgh', 'Glasgow', 'Aberdeen', 'Dundee', 'Inverness',
                            'Stirling', 'Perth', 'Ayr', 'Falkirk'
                        ]
                    }
                ]
            }
        ]
        
        for country_data in countries_data:
            country, created = Country.objects.get_or_create(
                name=country_data['name'],
                defaults={
                    'iso3': country_data['iso3'],
                    'iso2': country_data['iso2'],
                    'phone_code': country_data['phone_code'],
                    'capital': country_data['capital'],
                    'currency': country_data['currency'],
                    'currency_name': country_data['currency_name'],
                    'currency_symbol': country_data['currency_symbol'],
                    'region': country_data['region'],
                    'subregion': country_data['subregion'],
                    'emoji': country_data['emoji'],
                }
            )
            
            if created:
                self.stdout.write(f'Created country: {country.name}')
            
            for state_data in country_data['states']:
                state, state_created = State.objects.get_or_create(
                    name=state_data['name'],
                    country=country,
                    defaults={'state_code': state_data['state_code']}
                )
                
                if state_created:
                    self.stdout.write(f'  Created state: {state.name}')
                
                for lga_name in state_data['lgas']:
                    lga, lga_created = LGA.objects.get_or_create(
                        name=lga_name,
                        state=state
                    )
                    
                    if lga_created:
                        self.stdout.write(f'    Created LGA: {lga.name}')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully seeded {Country.objects.count()} countries, '
                f'{State.objects.count()} states, and {LGA.objects.count()} LGAs!'
            )
        )