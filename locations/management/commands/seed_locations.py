import csv
import requests
import os
from django.core.management.base import BaseCommand
from locations.models import Country, State, LGA
from django.db import transaction

class Command(BaseCommand):
    help = 'Seed comprehensive countries, states, and LGAs (Cities) data via CSV'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Starting global location seeding (CSV Mode)..."))
        
        # 1. Seed Nigeria (Priority: Hardcoded for accuracy of 774 LGAs)
        self.seed_nigeria()

        # 2. Seed the rest of the world using stable CSVs
        self.seed_rest_of_world()

    def seed_nigeria(self):
        self.stdout.write("Seeding Nigeria specific data...")
        
        # Nigeria Data (Kept strict as requested for your main market)
        nigeria_data = {
            "name": "Nigeria",
            "iso3": "NGA", "iso2": "NG", "phone_code": "+234",
            "capital": "Abuja", "currency": "NGN", "currency_name": "Naira",
            "currency_symbol": "₦", "region": "Africa", "subregion": "Western Africa",
            "emoji": "🇳🇬",
            "states": [
                {"name": "Abia", "code": "AB", "lgas": ["Aba North", "Aba South", "Arochukwu", "Bende", "Ikwuano", "Isiala Ngwa North", "Isiala Ngwa South", "Isuikwuato", "Obi Ngwa", "Ohafia", "Osisioma", "Ugwunagbo", "Ukwa East", "Ukwa West", "Umuahia North", "Umuahia South", "Umu Nneochi"]},
                {"name": "Adamawa", "code": "AD", "lgas": ["Demsa", "Fufure", "Ganye", "Gayuk", "Gombi", "Grie", "Hong", "Jada", "Lamurde", "Madagali", "Maiha", "Mayo Belwa", "Michika", "Mubi North", "Mubi South", "Numan", "Shelleng", "Song", "Toungo", "Yola North", "Yola South"]},
                {"name": "Akwa Ibom", "code": "AK", "lgas": ["Abak", "Eastern Obolo", "Eket", "Esit Eket", "Essien Udim", "Etim Ekpo", "Etinan", "Ibeno", "Ibesikpo Asutan", "Ibiono-Ibom", "Ika", "Ikono", "Ikot Abasi", "Ikot Ekpene", "Ini", "Itu", "Mbo", "Mkpat-Enin", "Nsit-Atai", "Nsit-Ibom", "Nsit-Ubium", "Obot Akara", "Okobo", "Onna", "Oron", "Oruk Anam", "Udung-Uko", "Ukanafun", "Uruan", "Urue-Offong/Oruko", "Uyo"]},
                {"name": "Anambra", "code": "AN", "lgas": ["Aguata", "Anambra East", "Anambra West", "Anaocha", "Awka North", "Awka South", "Ayamelum", "Dunukofia", "Ekwusigo", "Idemili North", "Idemili South", "Ihiala", "Njikoka", "Nnewi North", "Nnewi South", "Ogbaru", "Onitsha North", "Onitsha South", "Orumba North", "Orumba South", "Oyi"]},
                {"name": "Bauchi", "code": "BA", "lgas": ["Alkaleri", "Bauchi", "Bogoro", "Damban", "Darazo", "Dass", "Gamawa", "Ganjuwa", "Giade", "Itas/Gadau", "Jama'are", "Katagum", "Kirfi", "Misau", "Ningi", "Shira", "Tafawa Balewa", "Toro", "Warji", "Zaki"]},
                {"name": "Bayelsa", "code": "BY", "lgas": ["Brass", "Ekeremor", "Kolokuma/Opokuma", "Nembe", "Ogbia", "Sagbama", "Southern Ijaw", "Yenagoa"]},
                {"name": "Benue", "code": "BE", "lgas": ["Ado", "Agatu", "Apa", "Buruku", "Gboko", "Guma", "Gwer East", "Gwer West", "Katsina-Ala", "Konshisha", "Kwande", "Logo", "Makurdi", "Obi", "Ogbadibo", "Ohimini", "Oju", "Okpokwu", "Otukpo", "Tarka", "Ukum", "Ushongo", "Vandeikya"]},
                {"name": "Borno", "code": "BO", "lgas": ["Abadam", "Askira/Uba", "Bama", "Bayo", "Biu", "Chibok", "Damboa", "Dikwa", "Gubio", "Guzamala", "Gwoza", "Hawul", "Jere", "Kaga", "Kala/Balge", "Konduga", "Kukawa", "Kwaya Kusar", "Mafa", "Magumeri", "Maiduguri", "Marte", "Mobbar", "Monguno", "Ngala", "Nganzai", "Shani"]},
                {"name": "Cross River", "code": "CR", "lgas": ["Abi", "Akamkpa", "Akpabuyo", "Bakassi", "Bekwarra", "Biase", "Boki", "Calabar Municipal", "Calabar South", "Etung", "Ikom", "Obanliku", "Obubra", "Obudu", "Odukpani", "Ogoja", "Yakuur", "Yala"]},
                {"name": "Delta", "code": "DE", "lgas": ["Aniocha North", "Aniocha South", "Bomadi", "Burutu", "Ethiope East", "Ethiope West", "Ika North East", "Ika South", "Isoko North", "Isoko South", "Ndokwa East", "Ndokwa West", "Okpe", "Oshimili North", "Oshimili South", "Patani", "Sapele", "Udu", "Ughelli North", "Ughelli South", "Ukwuani", "Uvwie", "Warri North", "Warri South", "Warri South West"]},
                {"name": "Ebonyi", "code": "EB", "lgas": ["Abakaliki", "Afikpo North", "Afikpo South", "Ebonyi", "Ezza North", "Ezza South", "Ikwo", "Ishielu", "Ivo", "Izzi", "Ohaozara", "Ohaukwu", "Onicha"]},
                {"name": "Edo", "code": "ED", "lgas": ["Akoko-Edo", "Egor", "Esan Central", "Esan North-East", "Esan South-East", "Esan West", "Etsako Central", "Etsako East", "Etsako West", "Igueben", "Ikpoba Okha", "Oredo", "Orhionmwon", "Ovia North-East", "Ovia South-West", "Owan East", "Owan West", "Uhunmwonde"]},
                {"name": "Ekiti", "code": "EK", "lgas": ["Ado Ekiti", "Efon", "Ekiti East", "Ekiti South-West", "Ekiti West", "Emure", "Gbonyin", "Ido Osi", "Ijero", "Ikere", "Ikole", "Ilejemeje", "Irepodun/Ifelodun", "Ise/Orun", "Moba", "Oye"]},
                {"name": "Enugu", "code": "EN", "lgas": ["Aninri", "Awgu", "Enugu East", "Enugu North", "Enugu South", "Ezeagu", "Igbo Etiti", "Igbo Eze North", "Igbo Eze South", "Isi Uzo", "Nkanu East", "Nkanu West", "Nsukka", "Oji River", "Udenu", "Udi", "Uzo Uwani"]},
                {"name": "Abuja (FCT)", "code": "FC", "lgas": ["Abaji", "Bwari", "Gwagwalada", "Kuje", "Kwali", "Municipal Area Council"]},
                {"name": "Gombe", "code": "GO", "lgas": ["Akko", "Balanga", "Billiri", "Dukku", "Funakaye", "Gombe", "Kaltungo", "Kwami", "Nafada", "Shongom", "Yamaltu/Deba"]},
                {"name": "Imo", "code": "IM", "lgas": ["Aboh Mbaise", "Ahiazu Mbaise", "Ehime Mbano", "Ezinihitte", "Ideato North", "Ideato South", "Ihitte/Uboma", "Ikeduru", "Isiala Mbano", "Isu", "Mbaitoli", "Ngor Okpala", "Njaba", "Nkwerre", "Nwangele", "Obowo", "Oguta", "Ohaji/Egbema", "Okigwe", "Orlu", "Orsu", "Oru East", "Oru West", "Owerri Municipal", "Owerri North", "Owerri West"]},
                {"name": "Jigawa", "code": "JI", "lgas": ["Auyo", "Babura", "Biriniwa", "Birnin Kudu", "Buji", "Dutse", "Gagarawa", "Garki", "Gumel", "Guri", "Gwaram", "Gwiwa", "Hadejia", "Jahun", "Kafin Hausa", "Kaugama", "Kazaure", "Kiri Kasama", "Kiyawa", "Maigatari", "Malam Madori", "Miga", "Ringim", "Roni", "Sule Tankarkar", "Taura", "Yankwashi"]},
                {"name": "Kaduna", "code": "KD", "lgas": ["Birnin Gwari", "Chikun", "Giwa", "Igabi", "Ikara", "Jaba", "Jema'a", "Kachia", "Kaduna North", "Kaduna South", "Kagarko", "Kajuru", "Kaura", "Kauru", "Kubau", "Kudan", "Lere", "Makarfi", "Sabon Gari", "Sanga", "Soba", "Zangon Kataf", "Zaria"]},
                {"name": "Kano", "code": "KN", "lgas": ["Ajingi", "Albasu", "Bagwai", "Bebeji", "Bichi", "Bunkure", "Dala", "Dambatta", "Dawakin Kudu", "Dawakin Tofa", "Doguwa", "Fagge", "Gabasawa", "Garko", "Garun Mallam", "Gaya", "Gezawa", "Gwale", "Gwarzo", "Kabo", "Kano Municipal", "Karaye", "Kibiya", "Kiru", "Kumbotso", "Kunchi", "Kura", "Madobi", "Makoda", "Minjibir", "Nasarawa", "Rano", "Rimin Gado", "Rogo", "Shanono", "Sumaila", "Takai", "Tarauni", "Tofa", "Tsanyawa", "Tudun Wada", "Ungogo", "Warawa", "Wudil"]},
                {"name": "Katsina", "code": "KT", "lgas": ["Bakori", "Batagarawa", "Batsari", "Baure", "Bindawa", "Charanchi", "Dandume", "Danja", "Dan Musa", "Daura", "Dutsi", "Dutsin Ma", "Faskari", "Funtua", "Ingawa", "Jibia", "Kafur", "Kaita", "Kankara", "Kankia", "Katsina", "Kurfi", "Kusada", "Mai'Adua", "Malumfashi", "Mani", "Mashi", "Matazu", "Musawa", "Rimi", "Sabuwa", "Safana", "Sandamu", "Zango"]},
                {"name": "Kebbi", "code": "KE", "lgas": ["Aleiro", "Arewa Dandi", "Argungu", "Augie", "Bagudo", "Birnin Kebbi", "Bunza", "Dandi", "Fakai", "Gwandu", "Jega", "Kalgo", "Koko/Besse", "Maiyama", "Ngaski", "Sakaba", "Shanga", "Suru", "Wasagu/Danko", "Yauri", "Zuru"]},
                {"name": "Kogi", "code": "KO", "lgas": ["Adavi", "Ajaokuta", "Ankpa", "Bassa", "Dekina", "Ibaji", "Idah", "Igalamela Odolu", "Ijumu", "Kabba/Bunu", "Kogi", "Lokoja", "Mopa Muro", "Ofu", "Ogori/Magongo", "Okehi", "Okene", "Olamaboro", "Omala", "Yagba East", "Yagba West"]},
                {"name": "Kwara", "code": "KW", "lgas": ["Asa", "Baruten", "Edu", "Ekiti", "Ifelodun", "Ilorin East", "Ilorin South", "Ilorin West", "Irepodun", "Isin", "Kaiama", "Moro", "Offa", "Oke Ero", "Oyun", "Pategi"]},
                {"name": "Lagos", "code": "LA", "lgas": ["Agege", "Ajeromi-Ifelodun", "Alimosho", "Amuwo-Odofin", "Apapa", "Badagry", "Epe", "Eti Osa", "Ibeju-Lekki", "Ifako-Ijaiye", "Ikeja", "Ikorodu", "Kosofe", "Lagos Island", "Lagos Mainland", "Mushin", "Ojo", "Oshodi-Isolo", "Shomolu", "Surulere"]},
                {"name": "Nasarawa", "code": "NA", "lgas": ["Akwanga", "Awe", "Doma", "Karu", "Keana", "Keffi", "Kokona", "Lafia", "Nasarawa", "Nasarawa Egon", "Obi", "Toto", "Wamba"]},
                {"name": "Niger", "code": "NI", "lgas": ["Agaie", "Agwara", "Bida", "Borgu", "Bosso", "Chanchaga", "Edati", "Gbako", "Gurara", "Katcha", "Kontagora", "Lapai", "Lavun", "Magama", "Mariga", "Mashegu", "Mokwa", "Moya", "Paikoro", "Rafi", "Rijau", "Shiroro", "Suleja", "Tafa", "Wushishi"]},
                {"name": "Ogun", "code": "OG", "lgas": ["Abeokuta North", "Abeokuta South", "Ado-Odo/Ota", "Egbado North", "Egbado South", "Ewekoro", "Ifo", "Ijebu East", "Ijebu North", "Ijebu North East", "Ijebu Ode", "Ikenne", "Imeko Afon", "Ipokia", "Obafemi Owode", "Odeda", "Odogbolu", "Ogun Waterside", "Remo North", "Shagamu"]},
                {"name": "Ondo", "code": "ON", "lgas": ["Akoko North-East", "Akoko North-West", "Akoko South-East", "Akoko South-West", "Akure North", "Akure South", "Ese Odo", "Idanre", "Ifedore", "Ilaje", "Ile Oluji/Okeigbo", "Irele", "Odigbo", "Okitipupa", "Ondo East", "Ondo West", "Ose", "Owo"]},
                {"name": "Osun", "code": "OS", "lgas": ["Atakunmosa East", "Atakunmosa West", "Ayedaade", "Ayedire", "Boluwaduro", "Boripe", "Ede North", "Ede South", "Egbedore", "Ejigbo", "Ife Central", "Ife East", "Ife North", "Ife South", "Ifedayo", "Ifelodun", "Ila", "Ilesa East", "Ilesa West", "Irepodun", "Irewole", "Isokan", "Iwo", "Obokun", "Odo Otin", "Ola Oluwa", "Olorunda", "Oriade", "Orolu", "Osogbo"]},
                {"name": "Oyo", "code": "OY", "lgas": ["Afijio", "Akinyele", "Atiba", "Atisbo", "Egbeda", "Ibadan North", "Ibadan North-East", "Ibadan North-West", "Ibadan South-East", "Ibadan South-West", "Ibarapa Central", "Ibarapa East", "Ibarapa North", "Ido", "Irepo", "Iseyin", "Itesiwaju", "Iwajowa", "Kajola", "Lagelu", "Ogbomosho North", "Ogbomosho South", "Ogo Oluwa", "Olorunsogo", "Oluyole", "Ona Ara", "Orelope", "Ori Ire", "Oyo East", "Oyo West", "Saki East", "Saki West", "Surulere"]},
                {"name": "Plateau", "code": "PL", "lgas": ["Barkin Ladi", "Bassa", "Bokkos", "Jos East", "Jos North", "Jos South", "Kanam", "Kanke", "Langtang North", "Langtang South", "Mangu", "Mikang", "Pankshin", "Qua'an Pan", "Riyom", "Shendam", "Wase"]},
                {"name": "Rivers", "code": "RI", "lgas": ["Abua/Odual", "Ahoada East", "Ahoada West", "Akuku-Toru", "Andoni", "Asari-Toru", "Bonny", "Degema", "Eleme", "Emohua", "Etche", "Gokana", "Ikwerre", "Khana", "Obio/Akpor", "Ogba/Egbema/Ndoni", "Ogu/Bolo", "Okrika", "Omuma", "Opobo/Nkoro", "Oyigbo", "Port Harcourt", "Tai"]},
                {"name": "Sokoto", "code": "SO", "lgas": ["Binji", "Bodinga", "Dange Shuni", "Gada", "Goronyo", "Gudu", "Gwadabawa", "Illela", "Isa", "Kebbe", "Kware", "Rabah", "Sabon Birni", "Shagari", "Silame", "Sokoto North", "Sokoto South", "Tambuwal", "Tangaza", "Tureta", "Wamako", "Wurno", "Yabo"]},
                {"name": "Taraba", "code": "TA", "lgas": ["Ardo Kola", "Bali", "Donga", "Gashaka", "Gassol", "Ibi", "Jalingo", "Karim Lamido", "Kurmi", "Lau", "Sardauna", "Takum", "Ussa", "Wukari", "Yorro", "Zing"]},
                {"name": "Yobe", "code": "YO", "lgas": ["Bade", "Bursari", "Damaturu", "Fika", "Fune", "Geidam", "Gujba", "Gulani", "Jakusko", "Karasuwa", "Machina", "Nangere", "Nguru", "Potiskum", "Tarmuwa", "Yunusari", "Yusufari"]},
                {"name": "Zamfara", "code": "ZA", "lgas": ["Anka", "Bakura", "Birnin Magaji/Kiyaw", "Bukkuyum", "Bungudu", "Chafe", "Gummi", "Gusau", "Kaura Namoda", "Maradun", "Maru", "Shinkafi", "Talata Mafara", "Zurmi"]}
            ]
        }
        self.save_country_data(nigeria_data)

    def seed_rest_of_world(self):
        base_url = "https://raw.githubusercontent.com/dr5hn/countries-states-cities-database/master/csv"
        
        files = {
            "countries": f"{base_url}/countries.csv",
            "states": f"{base_url}/states.csv",
            "cities": f"{base_url}/cities.csv"
        }
        
        data_files = {}

        # 1. Download Files
        for key, url in files.items():
            self.stdout.write(f"Downloading {key} from {url}...")
            cache_file = f"{key}.csv"
            
            if not os.path.exists(cache_file):
                try:
                    with requests.get(url, stream=True) as r:
                        r.raise_for_status()
                        with open(cache_file, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to download {key}: {str(e)}"))
                    return
            
            data_files[key] = cache_file

        # 2. Process & Insert
        self.stdout.write("Processing Global Data (this will take time)...")
        
        # A. Load Countries
        countries_map = {} # id -> country_obj
        with open(data_files['countries'], 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['iso3'] == 'NGA': continue # Skip Nigeria
                
                # Check for phonecode vs phone_code
                p_code = row.get('phonecode') or row.get('phone_code') or ""

                country, _ = Country.objects.update_or_create(
                    name=row['name'],
                    defaults={
                        'iso3': row['iso3'],
                        'iso2': row['iso2'],
                        'phone_code': "+" + p_code,
                        'capital': row['capital'],
                        'currency': row['currency'],
                        'currency_name': row['currency_name'],
                        'currency_symbol': row['currency_symbol'],
                        'region': row['region'],
                        'subregion': row['subregion'],
                        'emoji': row['emoji'],
                    }
                )
                countries_map[row['id']] = country

        # B. Load States
        states_map = {} # id -> state_obj
        with open(data_files['states'], 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                country = countries_map.get(row['country_id'])
                if not country: continue
                
                # FIX: Use 'iso2' as state_code if 'state_code' missing
                # Some versions of this CSV use 'iso2' for the state code
                s_code = row.get('state_code') or row.get('iso2') or row.get('code') or ""

                state, _ = State.objects.update_or_create(
                    name=row['name'],
                    country=country,
                    defaults={'state_code': s_code}
                )
                states_map[row['id']] = state

        # C. Load Cities (LGAs)
        batch_size = 5000
        lga_batch = []
        
        with open(data_files['cities'], 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                state = states_map.get(row['state_id'])
                if not state: continue
                
                lga_batch.append(LGA(name=row['name'], state=state))
                
                if len(lga_batch) >= batch_size:
                    LGA.objects.bulk_create(lga_batch, ignore_conflicts=True)
                    lga_batch = []
                    self.stdout.write(".", ending='') 

            if lga_batch:
                LGA.objects.bulk_create(lga_batch, ignore_conflicts=True)

        self.stdout.write(self.style.SUCCESS("\nGlobal seeding completed successfully!"))

    def save_country_data(self, data):
        with transaction.atomic():
            country, _ = Country.objects.update_or_create(
                name=data['name'],
                defaults={
                    'iso3': data.get('iso3'),
                    'iso2': data.get('iso2'),
                    'phone_code': data.get('phone_code'),
                    'capital': data.get('capital'),
                    'currency': data.get('currency'),
                    'currency_name': data.get('currency_name'),
                    'currency_symbol': data.get('currency_symbol'),
                    'region': data.get('region'),
                    'subregion': data.get('subregion'),
                    'emoji': data.get('emoji'),
                }
            )

            for s_data in data['states']:
                state, _ = State.objects.update_or_create(
                    name=s_data['name'],
                    country=country,
                    defaults={'state_code': s_data.get('code')}
                )

                if s_data['lgas']:
                    LGA.objects.filter(state=state).delete()
                    lga_objs = [LGA(name=lga_name, state=state) for lga_name in s_data['lgas']]
                    LGA.objects.bulk_create(lga_objs)