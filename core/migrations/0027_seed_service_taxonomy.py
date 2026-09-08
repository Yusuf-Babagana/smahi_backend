from django.db import migrations

# Starter taxonomy — "Start small... add rows here as S-MAHII grows" (the
# whole point of ServiceTaxonomy being a DB table, not a code constant).
# Each entry: (service_slug, service_label, profession, provider_type, group,
# category_label_or_None). category_label is what gets get_or_create'd as
# the real, searchable Category this row resolves to — the same
# case-insensitive get_or_create pattern UserRegistrationSerializer already
# uses for a free-text "Other" profession at registration (_resolve_category_id),
# so a fresh install ends up with exactly the categories these professions
# need, and a second run (or an existing category with the same name) never
# creates a duplicate. Several service_slugs deliberately share one
# category_label (electrical_installation/electrical_repair -> "Electrical
# Services") since they're the same searchable trade, just different tasks.
# provider_type='professional' rows get no category — nothing in this app's
# data model represents that yet (no doctor/professional role or profile),
# so linking one now would mean pointing to a category type that doesn't
# exist. The taxonomy row still gets recorded, ready for whenever that
# support lands, rather than blocked on it.
TAXONOMY = [
    # --- Home & Trades ---
    ('plumbing', 'Plumbing', 'plumber', 'artisan', 'Home & Trades', 'Plumbing'),
    ('electrical_installation', 'Electrical Installation', 'electrician', 'artisan', 'Home & Trades', 'Electrical Services'),
    ('electrical_repair', 'Electrical Repair', 'electrician', 'artisan', 'Home & Trades', 'Electrical Services'),
    ('furniture_making', 'Furniture Making', 'carpenter', 'artisan', 'Home & Trades', 'Carpentry'),
    ('furniture_repair', 'Furniture Repair', 'carpenter', 'artisan', 'Home & Trades', 'Carpentry'),
    ('painting', 'Painting', 'painter', 'artisan', 'Home & Trades', 'Painting'),
    ('masonry', 'Masonry', 'mason', 'artisan', 'Home & Trades', 'Masonry'),
    ('welding', 'Welding', 'welder', 'artisan', 'Home & Trades', 'Welding'),
    ('generator_repair', 'Generator Repair', 'generator_technician', 'artisan', 'Home & Trades', 'Generator Repair'),
    ('tailoring', 'Tailoring', 'tailor', 'artisan', 'Home & Trades', 'Tailoring'),
    ('hairdressing', 'Hairdressing', 'hairdresser', 'artisan', 'Home & Trades', 'Hairdressing'),
    ('barbing', 'Barbing', 'barber', 'artisan', 'Home & Trades', 'Barbing'),
    ('cleaning', 'Cleaning', 'cleaner', 'artisan', 'Home & Trades', 'Cleaning Services'),
    # --- Automotive ---
    ('car_repair', 'Car Repair', 'mechanic', 'artisan', 'Automotive', 'Auto Mechanic'),
    ('car_hire', 'Car Hire', 'car_rental_business', 'business', 'Automotive', 'Car Rental'),
    ('driving', 'Driving', 'driver', 'artisan', 'Automotive', 'Driving Services'),
    # --- Health ---
    ('pharmacy', 'Pharmacy', 'pharmacy', 'business', 'Health', 'Pharmacy'),
    ('medical_consultation', 'Medical Consultation', 'doctor', 'professional', 'Health', None),
]


def seed_taxonomy(apps, schema_editor):
    Category = apps.get_model('core', 'Category')
    ServiceTaxonomy = apps.get_model('core', 'ServiceTaxonomy')

    # One Category per unique (category_label, provider_type) pair, shared
    # across every taxonomy row that names it — avoids creating "Electrical
    # Services" twice for electrical_installation/electrical_repair.
    category_cache = {}

    def get_category(label, provider_type):
        if not label:
            return None
        key = (label.lower(), provider_type)
        if key not in category_cache:
            category, _ = Category.objects.get_or_create(
                name__iexact=label, category_type=provider_type,
                defaults={'name': label, 'category_type': provider_type},
            )
            category_cache[key] = category
        return category_cache[key]

    for service_slug, service_label, profession, provider_type, group, category_label in TAXONOMY:
        category = get_category(category_label, provider_type) if provider_type != 'professional' else None
        ServiceTaxonomy.objects.get_or_create(
            service_slug=service_slug,
            defaults={
                'service_label': service_label,
                'profession': profession,
                'provider_type': provider_type,
                'group': group,
                'category': category,
                'is_active': True,
            },
        )


def noop_reverse(apps, schema_editor):
    # Deliberately not deleting the seeded rows on reverse — an admin may
    # have already edited/relied on them by the time anyone reverses this,
    # and the Category rows created alongside them may be in real use.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_servicetaxonomy'),
    ]

    operations = [
        migrations.RunPython(seed_taxonomy, noop_reverse),
    ]
