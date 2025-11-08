# SmahiApp Backend

A Django REST Framework backend for SmahiApp - an artisan booking platform.

## Features

- Multi-role user system (Client, Artisan, Agent, Admin)
- Location-based user registration (Country, State, LGA)
- Artisan profile management with service areas
- Service booking system
- Artisan verification workflow
- JWT authentication
- Role-based permissions
- RESTful APIs for React Native frontend

## Tech Stack

- Django 4.2
- Django REST Framework
- SQLite (development) / PostgreSQL (production recommended)
- JWT Authentication (Simple JWT)
- CORS Headers

## Installation

### Prerequisites

- Python 3.8+
- pip

### Setup

1. Clone the repository:
```bash
cd smahi_backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create environment file:
```bash
cp .env.example .env
```

5. Update `.env` with your settings:
```
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

6. Run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

7. Seed location data:
```bash
python manage.py seed_locations
```

8. Seed sample data (optional):
```bash
python manage.py seed_data
```

9. Create superuser (optional):
```bash
python manage.py createsuperuser
```

10. Run development server:
```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000/`

## API Endpoints

### Authentication
- `POST /api/auth/register/` - User registration
- `POST /api/auth/login/` - User login
- `POST /api/auth/token/refresh/` - Refresh JWT token
- `GET/PUT /api/auth/profile/` - Get/update user profile

### Locations
- `GET /api/locations/countries/` - List countries
- `GET /api/locations/states/?country_id=1` - List states by country
- `GET /api/locations/lgas/?state_id=1` - List LGAs by state

### Categories
- `GET /api/categories/` - List service categories

### Artisans
- `GET /api/artisans/` - List approved artisans (with filters)
- `GET /api/artisans/{id}/` - Get artisan details
- `GET/PUT /api/artisan/profile/` - Artisan's own profile

### Bookings
- `GET /api/bookings/` - List user's bookings
- `POST /api/bookings/` - Create new booking
- `GET /api/bookings/{id}/` - Get booking details
- `PUT /api/bookings/{id}/` - Update booking

### Verification
- `POST /api/verification/` - Submit verification request
- `GET /api/verification/` - List verification requests
- `POST /api/verification/{id}/process/` - Approve/reject verification (agents)

### Reviews
- `GET /api/reviews/` - List reviews
- `POST /api/reviews/` - Add review for booking

## Test Users

After running `seed_data` command:

- **Admin**: admin@smahi.com / admin123
- **Client**: client@smahi.com / client123
- **Artisan**: artisan@smahi.com / artisan123
- **Agent**: agent@smahi.com / agent123

## Deployment to PythonAnywhere

### 1. Upload Code

Upload your project to PythonAnywhere using Git or the Files tab.

### 2. Create Virtual Environment

```bash
mkvirtualenv --python=/usr/bin/python3.10 smahi_env
pip install -r requirements.txt
```

### 3. Configure WSGI

Edit `/var/www/yourusername_pythonanywhere_com_wsgi.py`:

```python
import os
import sys

path = '/home/yourusername/smahi_backend'
if path not in sys.path:
    sys.path.append(path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'smahi_backend.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

### 4. Configure Settings

Update `settings.py` for production:

```python
DEBUG = False
ALLOWED_HOSTS = ['yourusername.pythonanywhere.com']

STATIC_ROOT = '/home/yourusername/smahi_backend/staticfiles'
MEDIA_ROOT = '/home/yourusername/smahi_backend/media'
```

### 5. Run Migrations

```bash
cd ~/smahi_backend
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py seed_locations
python manage.py seed_data
python manage.py createsuperuser
```

### 6. Configure Static/Media Files

In PythonAnywhere Web tab:
- Static files: URL `/static/` → Directory `/home/yourusername/smahi_backend/staticfiles`
- Static files: URL `/media/` → Directory `/home/yourusername/smahi_backend/media`

### 7. Reload Web App

Click "Reload" button in the Web tab.

## Project Structure

```
smahi_backend/
├── smahi_backend/          # Project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── accounts/               # User authentication
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── locations/              # Location management
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── core/                   # Business logic
│   ├── models.py
│   ├── serializers.py
│   ├── views.py
│   ├── permissions.py
│   └── urls.py
├── media/                  # Uploaded files
├── static/                 # Static files
├── manage.py
├── requirements.txt
└── .env
```

## Models

### User (accounts)
- Custom user model with email login
- Roles: client, artisan, agent, admin
- Location fields (country, state, LGA)

### Location (locations)
- Country, State, LGA models
- Hierarchical relationship

### Category (core)
- Service categories for artisans

### ArtisanProfile (core)
- Extended profile for artisans
- Service locations (multiple states/LGAs)
- Verification status
- Rating and reviews

### Booking (core)
- Service bookings between clients and artisans
- Location-based booking
- Status workflow

### VerificationRequest (core)
- Artisan verification workflow
- Document uploads
- Agent approval

### Review (core)
- Booking reviews and ratings
- Automatic artisan rating update

## License

Proprietary - All rights reserved

## Support

For support, email support@smahi.com
