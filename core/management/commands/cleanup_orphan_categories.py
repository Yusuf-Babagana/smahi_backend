from django.core.management.base import BaseCommand
from core.models import Category


ORPHAN_MAP = {
    "Home & Tech Repairs": [
        "AC Repair & Maintenance",
        "Auto Electrician",
        "Auto Mechanic",
        "Borehole Driller",
        "CCTV & Security Installer",
        "Home Appliance Repairer",
        "Landscaper / Gardener",
        "Locksmith",
        "Satellite / DSTV Installer",
        "Watch Repairer",
    ],
    "Food & Provisions": [
        "Canopy & Chair Rental",
    ],
    "Fashion & Beauty": [
        "Henna / Lali Artist",
    ],
    "Metalwork & Construction": [
        "Panel Beater",
        "Vulcanizer",
        "Water Tanker Supplier",
        "Glass Worker",
    ],
    "Professional Services": [
        "DJ (Disc Jockey)",
        "Errand / Personal Shopper",
        "Event Decorator",
        "Event MC / Compere",
        "Moving & Relocation Service",
        "Professional Driver",
        "Sign Writer / Banner Printer",
        "Sound & Equipment Rental",
        "Towing Service",
        "Upholstery Maker",
        "Waste Disposal Service",
    ],
}

DUPLICATES_TO_DELETE = {
    "Computer & Laptop Repairer": "Computer & Phone Repair",
    "Phone Repair Technician": "Computer & Phone Repair",
    "Fumigation & Pest Control": "Pest Control",
    "Generator Mechanic": "Generator Repair",
    "House Cleaning Service": "Cleaning",
    "Interior Decorator": "Interior Decoration",
    "Solar Panel & Inverter Installer": "Solar Installation",
    "TV & Audio System Repairer": "TV & Electronics Repair",
    "Tiler": "Tiling",
    "Baker / Cake Maker": "Baking & Confectionery",
    "Caterer / Local Food Chef": "Catering",
    "Hairstylist": "Hairdressing",
    "Makeup Artist": "Makeup & Cosmetics",
    "Shoemaker / Cobbler": "Shoemaking & Repairs",
    "Tailor / Fashion Designer": "Tailoring",
    "Spa / Massage Therapist": "Spa & Massage",
    "Aluminum Fabricator": "Aluminum Fabrication",
    "Mason / Bricklayer": "Mason",
    "POP / Plasterer": "POP & Plastering",
    "Roofer": "Roofing",
    "Welder / Iron Bender": "Welding",
    "Photographer": "Photography",
    "Videographer": "Videography",
    "Logistics / Dispatch Rider": "Logistics & Delivery",
    "Carpenter / Furniture Maker": "Carpentry",
}


class Command(BaseCommand):
    help = "Maps or deletes orphaned top-level categories into the correct parent"

    def handle(self, *args, **options):
        self.stdout.write("Cleaning up orphaned categories...")

        parents = {p.name: p for p in Category.objects.filter(parent__isnull=True)}
        all_cats = {c.name: c for c in Category.objects.all()}

        # 1. Delete duplicates - reassign any artisan profiles first, then delete
        for dup_name, canonical_name in DUPLICATES_TO_DELETE.items():
            if dup_name in all_cats:
                dup = all_cats[dup_name]
                if canonical_name in all_cats:
                    canonical = all_cats[canonical_name]
                    try:
                        from core.models import ArtisanProfile
                        ArtisanProfile.objects.filter(category=dup).update(category=canonical)
                    except Exception:
                        pass
                dup.delete()
                self.stdout.write(f"  Deleted duplicate: {dup_name} -> {canonical_name}")

        all_cats = {c.name: c for c in Category.objects.all()}

        # 2. Map orphans to their parents
        for parent_name, orphan_names in ORPHAN_MAP.items():
            parent = parents.get(parent_name)
            if not parent:
                self.stdout.write(self.style.WARNING(f"  Parent '{parent_name}' not found"))
                continue
            for name in orphan_names:
                if name in all_cats:
                    cat = all_cats[name]
                    cat.parent = parent
                    cat.save()
                    self.stdout.write(f"  Mapped: {name} -> {parent_name}")
                else:
                    self.stdout.write(f"  Not found: {name}")

        # 3. Check remaining orphans
        remaining = Category.objects.filter(parent__isnull=True).exclude(
            name__in=[p.name for p in parents.values()]
        )
        if remaining.exists():
            self.stdout.write(self.style.WARNING(
                f"  Still orphaned: {[c.name for c in remaining]}"
            ))
        else:
            self.stdout.write(self.style.SUCCESS("All categories are now under a parent!"))
