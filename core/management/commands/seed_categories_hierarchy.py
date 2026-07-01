from django.core.management.base import BaseCommand
from core.models import Category


PARENTS = [
    {"name": "Home & Tech Repairs",        "name_ha": "Gyaran Gida da Fasaha",       "icon": "home-outline",        "description": "Home maintenance, repairs, and technology services"},
    {"name": "Food & Provisions",          "name_ha": "Abinci da Kayayyaki",          "icon": "restaurant-outline",  "description": "Food preparation, catering, and provisions"},
    {"name": "Fashion & Beauty",           "name_ha": "Kayayyaki da Kyau",            "icon": "shirt-outline",       "description": "Clothing, styling, and personal care services"},
    {"name": "Metalwork & Construction",   "name_ha": "Aikin Karfe da Gina",          "icon": "construct-outline",   "description": "Building, metal fabrication, and construction services"},
    {"name": "Professional Services",      "name_ha": "Sabis na Kwararru",            "icon": "briefcase-outline",   "description": "Business, creative, and professional support services"},
]

SUBCATEGORIES = {
    "Home & Tech Repairs": [
        ("Plumbing",                 "Aikin Ruwa"),
        ("Electrical",               "Aikin Wuta"),
        ("Carpentry",                "Kafinta"),
        ("Painting",                 "Fenti"),
        ("Cleaning",                 "Tsaftacewa"),
        ("AC Technician",            "Mai Gyaran AC"),
        ("AC Repair & Maintenance",  "Gyaran AC da Kulawa"),
        ("Mechanic",                 "Makanike"),
        ("Auto Electrician",         "Mai Aikin Wutar Mota"),
        ("Auto Mechanic",            "Makanin Mota"),
        ("Borehole Driller",         "Mai Hako Rijiya"),
        ("CCTV & Security Installer","Saka CCTV da Tsaro"),
        ("TV & Electronics Repair",  "Gyaran TV da Lantarki"),
        ("Computer & Phone Repair",  "Gyaran Kwamfuta da Wayar"),
        ("Furniture Repair & Assembly", "Gyaran Kayan Daki"),
        ("Generator Repair",         "Gyaran Janareta"),
        ("Home Appliance Repairer",  "Gyaran Na'urorin Gida"),
        ("Pest Control",             "Kawar da Kwari"),
        ("Interior Decoration",      "Kayan Ado na Cikin Gida"),
        ("Tiling",                   "Tile"),
        ("HVAC",                     "HVAC"),
        ("Landscaper / Gardener",    "Gyaran Lambu"),
        ("Locksmith",                "Makulli"),
        ("Satellite / DSTV Installer","Saka Satellite da DSTV"),
        ("Solar Installation",       "Saka Hasken Rana"),
        ("Smart Home Setup",         "Saka Na'urorin Gida"),
        ("Watch Repairer",           "Mai Gyaran Agogo"),
    ],
    "Food & Provisions": [
        ("Catering",                 "Aikin Abinci"),
        ("Baking & Confectionery",   "Biredi da Kayan Zaki"),
        ("Grilling & Suya",          "Gasasshe da Suya"),
        ("Food Delivery",            "Isar da Abinci"),
        ("Butchery",                 "Aikin Mahauci"),
        ("Poultry & Livestock",      "Kiwon Kaji da Dabbobi"),
        ("Farming & Provisions",     "Noma da Kayayyaki"),
        ("Waiters & Event Staff",    "Masu Hidimar Taro"),
        ("Meal Prep & Meal Plans",   "Shirya Abinci"),
        ("Juice & Beverages",        "Ruwan 'Ya'yan Itace"),
        ("Canopy & Chair Rental",    "Hayar Tanti da Kujera"),
    ],
    "Fashion & Beauty": [
        ("Tailoring",                "Dinki"),
        ("Barber",                   "Wanzami"),
        ("Hairdressing",             "Gyaran Gashi"),
        ("Makeup & Cosmetics",       "Kayan Shafa"),
        ("Nail Technician",          "Gyaran Farce"),
        ("Fashion Design",           "Zanen Tufafi"),
        ("Shoemaking & Repairs",     "Gyaran Takalma"),
        ("Laundry & Dry Cleaning",   "Wanki"),
        ("Spa & Massage",            "Spa da Tausa"),
        ("Tattoo & Piercing",        "Tattoo da Huda"),
        ("Wig & Hair Extensions",    "Gashi na Roko"),
        ("Henna / Lali Artist",      "Mai Zanen Lalle"),
    ],
    "Metalwork & Construction": [
        ("Mason",                    "Magoni"),
        ("Welding",                  "Waldi"),
        ("Aluminum Fabrication",     "Aikin Aluminum"),
        ("Roofing",                  "Rufin Gida"),
        ("Iron Bending & Steel Work", "Lankwashe Karfe"),
        ("POP Ceiling Installation", "Saka POP"),
        ("Glasswork & Mirror",       "Gilashi da Madubi"),
        ("Gate & Automation",        "Kofa da Automation"),
        ("POP & Plastering",         "POP da Plasta"),
        ("Concrete & Block Work",    "Aikin Siminti"),
        ("Panel Beater",             "Mai Gyaran Mota"),
        ("Vulcanizer",               "Mai Gyaran Taya"),
        ("Water Tanker Supplier",    "Mai Samar da Ruwa"),
        ("Glass Worker",             "Mai Aikin Gilashi"),
    ],
    "Professional Services": [
        ("Photography",              "Daukar Hoto"),
        ("Videography",              "Daukar Bidiyo"),
        ("Graphic Design",           "Zanen Hotuna"),
        ("Web & App Development",    "Shafukan Yanar Gizo"),
        ("Logistics & Delivery",     "Jigilar Kaya"),
        ("Security Services",        "Tsaro"),
        ("Tutoring & Education",     "Koyarwa"),
        ("Event Planning",           "Shirya Taro"),
        ("Consulting",               "Shawarwari"),
        ("Legal Services",           "Aikin Lauya"),
        ("Accounting & Tax",         "Lissafin Kudi"),
        ("Digital Marketing",        "Tallan Yanar Gizo"),
        ("Translation & Interpretation", "Fassara"),
        ("Music & Entertainment",    "Kida da Nishaɗi"),
        ("Virtual Assistant",        "Mataimaki na Yanar Gizo"),
        ("DJ (Disc Jockey)",         "DJ"),
        ("Errand / Personal Shopper","Mai Siyayya"),
        ("Event Decorator",          "Mai Adon Taro"),
        ("Event MC / Compere",       "Mai Gabatarwa"),
        ("Moving & Relocation Service", "Mai Taimakawa ƙaura"),
        ("Professional Driver",      "Direba"),
        ("Sign Writer / Banner Printer", "Mai Rubutun allo"),
        ("Sound & Equipment Rental", "Hayar Sauti"),
        ("Towing Service",           "Janyar Mota"),
        ("Upholstery Maker",         "Mai Dinki Kujera"),
        ("Waste Disposal Service",   "Sharar Gida"),
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
    help = "Seeds the 5 parent categories with ~50 sub-categories and their Hausa translations"

    def handle(self, *args, **options):
        self.stdout.write("Seeding hierarchical categories with Hausa translations...")

        existing_cats = {c.name: c for c in Category.objects.all()}

        for old_name, new_name in EXISTING_MERGE_MAP.items():
            if old_name in existing_cats and new_name in existing_cats:
                old_cat = existing_cats[old_name]
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

        for dup_name, canonical_name in DUPLICATES_TO_DELETE.items():
            if dup_name in existing_cats and canonical_name in existing_cats:
                dup = existing_cats[dup_name]
                try:
                    from core.models import ArtisanProfile
                    ArtisanProfile.objects.filter(category=dup).update(category=existing_cats[canonical_name])
                except Exception:
                    pass
                dup.delete()
                self.stdout.write(f"  Deleted duplicate: {dup_name} -> {canonical_name}")

        existing_cats = {c.name: c for c in Category.objects.all()}

        parent_objects = {}
        for parent_data in PARENTS:
            cat, created = Category.objects.get_or_create(
                name=parent_data["name"],
                defaults={
                    "name_ha": parent_data["name_ha"],
                    "icon": parent_data["icon"],
                    "description": parent_data["description"],
                }
            )
            if created:
                self.stdout.write(f"  Created parent: {cat.name}")
            else:
                cat.name_ha = parent_data["name_ha"]
                cat.icon = parent_data["icon"]
                cat.description = parent_data["description"]
                cat.save()
                self.stdout.write(f"  Updated parent: {cat.name} (name_ha seeded)")
            parent_objects[parent_data["name"]] = cat

        for parent_name, sub_list in SUBCATEGORIES.items():
            parent = parent_objects[parent_name]
            for sub_name, sub_ha in sub_list:
                sub, created = Category.objects.get_or_create(
                    name=sub_name,
                    defaults={
                        "parent": parent,
                        "name_ha": sub_ha,
                        "icon": "",
                        "description": "",
                    }
                )
                if created:
                    self.stdout.write(f"    Created sub: {sub_name} -> {parent_name}")
                else:
                    sub.name_ha = sub_ha
                    sub.parent = parent
                    sub.save()
                    self.stdout.write(f"    Updated sub: {sub_name} (name_ha seeded)")
        self.stdout.write(self.style.SUCCESS("Category hierarchy with Hausa translations seeded successfully!"))
