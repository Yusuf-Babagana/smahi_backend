import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smahi_backend.settings')
django.setup()

from core.models import Category

# Business types, not individual professions — see Category.category_type
# and BusinessProfile's own docstring for why these are kept in a
# separate lane from seed_categories.py's artisan/trade list.
BUSINESS_CATEGORIES = [
    {"name": "Hospital / Clinic", "icon": "local-hospital", "description": "Hospitals, clinics, and healthcare providers."},
    {"name": "Hotel", "icon": "hotel", "description": "Hotels, lodges, and guest houses."},
    {"name": "Restaurant", "icon": "restaurant", "description": "Restaurants and eateries."},
    {"name": "Grocery / Retail Store", "icon": "storefront", "description": "Grocery, provisions, and general retail stores."},
    {"name": "Pharmacy", "icon": "medication", "description": "Pharmacies and chemists."},
    {"name": "Supermarket", "icon": "local-grocery-store", "description": "Supermarkets and large retail outlets."},
    {"name": "Bakery", "icon": "bakery-dining", "description": "Bakeries and confectioneries."},
    {"name": "Salon & Spa", "icon": "spa", "description": "Beauty salons and spas (business premises, not an individual stylist)."},
    {"name": "Event Center", "icon": "celebration", "description": "Event centers and venues for hire."},
    {"name": "Transport & Logistics", "icon": "local-shipping", "description": "Transport companies, logistics, and courier services."},
]


def seed_business_categories():
    print("Seeding business categories...")
    for cat_data in BUSINESS_CATEGORIES:
        category, created = Category.objects.get_or_create(
            name=cat_data["name"],
            category_type='business',
            defaults={
                "icon": cat_data["icon"],
                "description": cat_data["description"],
            }
        )
        if created:
            print(f"Created: {category.name}")
        else:
            print(f"Already exists: {category.name}")
    print("Seeding complete!")


if __name__ == "__main__":
    seed_business_categories()
