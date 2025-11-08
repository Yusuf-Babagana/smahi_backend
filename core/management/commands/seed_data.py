from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import Category, ArtisanProfile
from locations.models import Country, State, LGA

User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds the database with sample categories and test users'

    def handle(self, *args, **options):
        self.stdout.write('Seeding sample data...')

        categories_data = [
            {'name': 'Plumbing', 'description': 'Water and sewage system installation and repair', 'icon': 'plumbing'},
            {'name': 'Electrical', 'description': 'Electrical wiring and appliance installation', 'icon': 'electrical'},
            {'name': 'Carpentry', 'description': 'Woodworking and furniture making', 'icon': 'carpentry'},
            {'name': 'Painting', 'description': 'Interior and exterior painting services', 'icon': 'painting'},
            {'name': 'Tiling', 'description': 'Floor and wall tiling services', 'icon': 'tiling'},
            {'name': 'Welding', 'description': 'Metal fabrication and welding services', 'icon': 'welding'},
            {'name': 'HVAC', 'description': 'Heating, ventilation, and air conditioning', 'icon': 'hvac'},
            {'name': 'Masonry', 'description': 'Brickwork and concrete construction', 'icon': 'masonry'},
        ]

        for cat_data in categories_data:
            category, created = Category.objects.get_or_create(
                name=cat_data['name'],
                defaults={'description': cat_data['description'], 'icon': cat_data['icon']}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created category: {category.name}'))

        try:
            nigeria = Country.objects.get(code='NG')
            lagos = State.objects.get(name='Lagos', country=nigeria)
            ikeja = LGA.objects.get(name='Ikeja', state=lagos)
        except:
            self.stdout.write(self.style.WARNING('Location data not found. Run seed_locations first.'))
            nigeria = lagos = ikeja = None

        admin_user, created = User.objects.get_or_create(
            email='admin@smahi.com',
            defaults={
                'first_name': 'Admin',
                'last_name': 'User',
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True,
                'country': nigeria,
                'state': lagos,
                'lga': ikeja,
            }
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
            self.stdout.write(self.style.SUCCESS('Created admin user: admin@smahi.com / admin123'))

        client_user, created = User.objects.get_or_create(
            email='client@smahi.com',
            defaults={
                'first_name': 'John',
                'last_name': 'Client',
                'role': 'client',
                'phone_number': '+2348012345678',
                'country': nigeria,
                'state': lagos,
                'lga': ikeja,
            }
        )
        if created:
            client_user.set_password('client123')
            client_user.save()
            self.stdout.write(self.style.SUCCESS('Created client user: client@smahi.com / client123'))

        artisan_user, created = User.objects.get_or_create(
            email='artisan@smahi.com',
            defaults={
                'first_name': 'Michael',
                'last_name': 'Artisan',
                'role': 'artisan',
                'phone_number': '+2348087654321',
                'is_verified': True,
                'country': nigeria,
                'state': lagos,
                'lga': ikeja,
            }
        )
        if created:
            artisan_user.set_password('artisan123')
            artisan_user.save()
            self.stdout.write(self.style.SUCCESS('Created artisan user: artisan@smahi.com / artisan123'))

            try:
                plumbing = Category.objects.get(name='Plumbing')
                profile, created = ArtisanProfile.objects.get_or_create(
                    user=artisan_user,
                    defaults={
                        'category': plumbing,
                        'bio': 'Professional plumber with 10 years of experience',
                        'experience_years': 10,
                        'hourly_rate': 5000.00,
                        'verification_status': 'approved',
                        'rating': 4.5,
                    }
                )
                if created and lagos:
                    profile.service_states.add(lagos)
                    if ikeja:
                        profile.service_lgas.add(ikeja)
                    self.stdout.write('Created artisan profile')
            except:
                pass

        agent_user, created = User.objects.get_or_create(
            email='agent@smahi.com',
            defaults={
                'first_name': 'Sarah',
                'last_name': 'Agent',
                'role': 'agent',
                'phone_number': '+2348098765432',
                'country': nigeria,
                'state': lagos,
                'lga': ikeja,
            }
        )
        if created:
            agent_user.set_password('agent123')
            agent_user.save()
            self.stdout.write(self.style.SUCCESS('Created agent user: agent@smahi.com / agent123'))

        self.stdout.write(self.style.SUCCESS('\nSample data seeded successfully!'))
        self.stdout.write('\nTest Users:')
        self.stdout.write('  Admin:   admin@smahi.com / admin123')
        self.stdout.write('  Client:  client@smahi.com / client123')
        self.stdout.write('  Artisan: artisan@smahi.com / artisan123')
        self.stdout.write('  Agent:   agent@smahi.com / agent123')
