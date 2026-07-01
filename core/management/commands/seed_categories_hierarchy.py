from django.core.management.base import BaseCommand
from core.models import Category


PARENTS = [
    {"name": "Home & Tech Repairs", "icon": "home-outline", "description": "Home maintenance, repairs, and technology services"},
    {"name": "Food & Provisions", "icon": "restaurant-outline", "description": "Food preparation, catering, and provisions"},
    {"name": "Fashion & Beauty", "icon": "shirt-outline", "description": "Clothing, styling, and personal care services"},
    {"name": "Metalwork & Construction", "icon": "construct-outline", "description": "Building, metal fabrication, and construction services"},
    {"name": "Professional Services", "icon": "briefcase-outline", "description": "Business, creative, and professional support services"},
]

SUBCATEGORIES = {
    "Home & Tech Repairs": [
        "Plumbing", "Electrical", "Carpentry", "Painting", "Cleaning",
        "AC Technician", "Mechanic", "TV & Electronics Repair",
        "Computer & Phone Repair", "Furniture Repair & Assembly",
        "Generator Repair", "Pest Control", "Interior Decoration",
        "Tiling", "HVAC", "Solar Installation", "Smart Home Setup",
    ],
    "Food & Provisions": [
        "Catering", "Baking & Confectionery", "Grilling & Suya",
        "Food Delivery", "Butchery", "Poultry & Livestock",
        "Farming & Provisions", "Waiters & Event Staff",
        "Meal Prep & Meal Plans", "Juice & Beverages",
    ],
    "Fashion & Beauty": [
        "Tailoring", "Barber", "Hairdressing", "Makeup & Cosmetics",
        "Nail Technician", "Fashion Design", "Shoemaking & Repairs",
        "Laundry & Dry Cleaning", "Spa & Massage",
        "Tattoo & Piercing", "Wig & Hair Extensions",
    ],
    "Metalwork & Construction": [
        "Mason", "Welding", "Aluminum Fabrication", "Roofing",
        "Iron Bending & Steel Work", "POP Ceiling Installation",
        "Glasswork & Mirror", "Gate & Automation",
        "POP & Plastering", "Concrete & Block Work",
    ],
    "Professional Services": [
        "Photography", "Videography", "Graphic Design",
        "Web & App Development", "Logistics & Delivery",
        "Security Services", "Tutoring & Education",
        "Event Planning", "Consulting", "Legal Services",
        "Accounting & Tax", "Digital Marketing",
        "Translation & Interpretation", "Music & Entertainment",
        "Virtual Assistant",
    ],
}

EXISTING_MERGE_MAP = {
    "Plumber": "Plumbing",
    "Electrician": "Electrical",
    "Carpenter": "Carpentry",
    "Painter": "Painting",
    "Cleaner": "Cleaning",
    "Tailor": "Tailoring",
}

CATEGORIES_TO_DELETE = ["Cleaner", "Painter", "Tailor", "Plumber", "Electrician", "Carpenter"]


class Command(BaseCommand):
    help = "Seeds the 5 parent categories with ~50 sub-categories, cleaning up duplicates"

    def handle(self, *args, **options):
        self.stdout.write("Seeding hierarchical categories...")

        existing_cats = {c.name: c for c in Category.objects.all()}

        for old_name, new_name in EXISTING_MERGE_MAP.items():
            if old_name in existing_cats and new_name in existing_cats:
                old_cat = existing_cats[old_name]
                ArtisanProfile = None
                try:
                    from core.models import ArtisanProfile
                    ArtisanProfile.objects.filter(category=old_cat).update(category=existing_cats[new_name])
                except Exception:
                    pass
                old_cat.delete()
                self.stdout.write(f"  Merged '{old_name}' into '{new_name}'")
            elif old_name in existing_cats:
                existing_cats[old_name].name = new_name
                existing_cats[old_name].save()
                self.stdout.write(f"  Renamed '{old_name}' to '{new_name}'")

        existing_cats = {c.name: c for c in Category.objects.all()}

        parent_objects = {}
        for parent_data in PARENTS:
            cat, created = Category.objects.get_or_create(
                name=parent_data["name"],
                defaults={
                    "icon": parent_data["icon"],
                    "description": parent_data["description"],
                }
            )
            if created:
                self.stdout.write(f"  Created parent: {cat.name}")
            else:
                cat.icon = parent_data["icon"]
                cat.description = parent_data["description"]
                cat.save()
                self.stdout.write(f"  Updated parent: {cat.name}")
            parent_objects[parent_data["name"]] = cat

        for parent_name, sub_names in SUBCATEGORIES.items():
            parent = parent_objects[parent_name]
            for sub_name in sub_names:
                sub, created = Category.objects.get_or_create(
                    name=sub_name,
                    defaults={
                        "parent": parent,
                        "icon": "",
                        "description": "",
                    }
                )
                if created:
                    self.stdout.write(f"    Created sub: {sub_name} -> {parent_name}")
                else:
                    if sub.parent != parent:
                        sub.parent = parent
                        sub.save()
                        self.stdout.write(f"    Re-parented: {sub_name} -> {parent_name}")
                    else:
                        self.stdout.write(f"    Already exists: {sub_name}")

        uncategorized = Category.objects.filter(parent__isnull=True).exclude(
            name__in=[p["name"] for p in PARENTS]
        )
        if uncategorized.exists():
            self.stdout.write(self.style.WARNING(
                f"  Uncategorized top-level items remain: {[c.name for c in uncategorized]}"
            ))

        self.stdout.write(self.style.SUCCESS("Category hierarchy seeded successfully!"))
