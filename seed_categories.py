import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smahi_backend.settings')
django.setup()

from core.models import Category

CATEGORIES = [
    {"name": "Plumbing", "icon": "water-outline", "description": "Pipe fixing, leak repairs, and installations."},
    {"name": "Electrical", "icon": "flash-outline", "description": "Wiring, lighting, and electrical repairs."},
    {"name": "Carpentry", "icon": "hammer-outline", "description": "Furniture repair, woodwork, and construction."},
    {"name": "Cleaning", "icon": "trash-outline", "description": "House cleaning, office sanitization, and laundry."},
    {"name": "Mechanic", "icon": "car-outline", "description": "Vehicle repairs and maintenance."},
    {"name": "Painting", "icon": "brush-outline", "description": "Interior and exterior wall painting."},
    {"name": "Tailoring", "icon": "cut-outline", "description": "Sewing, repairs, and fashion design."},
    {"name": "Photography", "icon": "camera-outline", "description": "Event coverage and professional photoshoots."},
    {"name": "Barber", "icon": "content-cut", "description": "Haircuts and grooming services."},
    {"name": "Hairdressing", "icon": "woman", "description": "Salon services and hair styling."},
]

def seed_categories():
    print("Seed Categories...")
    for cat_data in CATEGORIES:
        category, created = Category.objects.get_or_create(
            name=cat_data["name"],
            defaults={
                "icon": cat_data["icon"],
                "description": cat_data["description"]
            }
        )
        if created:
            print(f"Created: {category.name}")
        else:
            print(f"Already exists: {category.name}")
    print("Seeding complete!")

if __name__ == "__main__":
    seed_categories()
