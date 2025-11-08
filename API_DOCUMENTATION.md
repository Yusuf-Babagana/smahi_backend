# SmahiApp API Documentation

Base URL: `https://yourdomain.com/api/`

## Authentication

All authenticated endpoints require a JWT Bearer token in the Authorization header:

```
Authorization: Bearer <your_access_token>
```

### Token Refresh

When access token expires, use refresh token to get a new one.

## API Endpoints

### 1. Authentication

#### Register User
```
POST /api/auth/register/
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword",
  "password_confirm": "securepassword",
  "first_name": "John",
  "last_name": "Doe",
  "role": "client",
  "phone_number": "+2348012345678",
  "address": "123 Main Street",
  "country": 1,
  "state": 1,
  "lga": 1
}
```

**Response (201):**
```json
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "role": "client",
    "phone_number": "+2348012345678",
    "address": "123 Main Street",
    "country": 1,
    "state": 1,
    "lga": 1,
    "is_verified": false
  },
  "tokens": {
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
  }
}
```

#### Login
```
POST /api/auth/login/
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response (200):**
```json
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "role": "client"
  },
  "tokens": {
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
    "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
  }
}
```

#### Refresh Token
```
POST /api/auth/token/refresh/
```

**Request Body:**
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response (200):**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

#### Get Profile
```
GET /api/auth/profile/
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "role": "client",
  "phone_number": "+2348012345678",
  "address": "123 Main Street",
  "profile_picture": null,
  "country": 1,
  "state": 1,
  "lga": 1,
  "country_details": {
    "id": 1,
    "name": "Nigeria",
    "code": "NG",
    "phone_code": "+234"
  },
  "state_details": {
    "id": 1,
    "name": "Lagos",
    "country": 1,
    "country_name": "Nigeria"
  },
  "lga_details": {
    "id": 1,
    "name": "Ikeja",
    "state": 1,
    "state_name": "Lagos",
    "country_name": "Nigeria"
  },
  "is_verified": false
}
```

#### Update Profile
```
PUT /api/auth/profile/
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**Request Body:**
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "phone_number": "+2348012345678",
  "address": "456 New Street",
  "country": 1,
  "state": 1,
  "lga": 2,
  "profile_picture": <file>
}
```

### 2. Locations

#### List Countries
```
GET /api/locations/countries/
```

**Response (200):**
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Nigeria",
      "code": "NG",
      "phone_code": "+234"
    },
    {
      "id": 2,
      "name": "Ghana",
      "code": "GH",
      "phone_code": "+233"
    }
  ]
}
```

#### List States
```
GET /api/locations/states/?country_id=1
```

**Response (200):**
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Lagos",
      "country": 1,
      "country_name": "Nigeria"
    },
    {
      "id": 2,
      "name": "Abuja",
      "country": 1,
      "country_name": "Nigeria"
    }
  ]
}
```

#### List LGAs
```
GET /api/locations/lgas/?state_id=1
```

**Response (200):**
```json
{
  "count": 10,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Ikeja",
      "state": 1,
      "state_name": "Lagos",
      "country_name": "Nigeria"
    },
    {
      "id": 2,
      "name": "Surulere",
      "state": 1,
      "state_name": "Lagos",
      "country_name": "Nigeria"
    }
  ]
}
```

### 3. Categories

#### List Categories
```
GET /api/categories/
```

**Response (200):**
```json
{
  "count": 8,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Plumbing",
      "description": "Water and sewage system installation and repair",
      "icon": "plumbing",
      "created_at": "2024-01-01T00:00:00Z"
    },
    {
      "id": 2,
      "name": "Electrical",
      "description": "Electrical wiring and appliance installation",
      "icon": "electrical",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### 4. Artisans

#### List Artisans
```
GET /api/artisans/?category_id=1&state_id=1
```

**Query Parameters:**
- `category_id` - Filter by category
- `country_id` - Filter by service country
- `state_id` - Filter by service state
- `lga_id` - Filter by service LGA

**Response (200):**
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "user": 3,
      "user_details": {
        "id": 3,
        "email": "artisan@example.com",
        "first_name": "Michael",
        "last_name": "Artisan",
        "phone_number": "+2348087654321"
      },
      "category": 1,
      "category_name": "Plumbing",
      "bio": "Professional plumber with 10 years of experience",
      "experience_years": 10,
      "hourly_rate": "5000.00",
      "service_countries": [1],
      "service_states": [1],
      "service_lgas": [1, 2, 3],
      "verification_status": "approved",
      "rating": "4.50",
      "total_reviews": 25,
      "total_bookings": 150,
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

#### Get Artisan Details
```
GET /api/artisans/{id}/
```

#### Get/Update Artisan Profile (Own)
```
GET /api/artisan/profile/
Authorization: Bearer <token>
```

**Only accessible to users with 'artisan' role**

```
PUT /api/artisan/profile/
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "category": 1,
  "bio": "Professional plumber with 10 years of experience",
  "experience_years": 10,
  "hourly_rate": "5000.00",
  "service_countries": [1],
  "service_states": [1, 2],
  "service_lgas": [1, 2, 3, 4, 5]
}
```

### 5. Bookings

#### List Bookings
```
GET /api/bookings/
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "count": 10,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "client": 1,
      "client_details": {
        "id": 1,
        "email": "client@example.com",
        "first_name": "John",
        "last_name": "Client"
      },
      "artisan": 3,
      "artisan_details": {
        "id": 3,
        "email": "artisan@example.com",
        "first_name": "Michael",
        "last_name": "Artisan"
      },
      "service_description": "Fix leaking pipe in kitchen",
      "address": "123 Main Street, Ikeja",
      "country": 1,
      "state": 1,
      "lga": 1,
      "scheduled_date": "2024-02-01T10:00:00Z",
      "duration_hours": "2.00",
      "total_cost": "10000.00",
      "status": "pending",
      "cancellation_reason": "",
      "created_at": "2024-01-15T00:00:00Z"
    }
  ]
}
```

#### Create Booking
```
POST /api/bookings/
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "artisan": 3,
  "service_description": "Fix leaking pipe in kitchen",
  "address": "123 Main Street, Ikeja",
  "country": 1,
  "state": 1,
  "lga": 1,
  "scheduled_date": "2024-02-01T10:00:00Z",
  "duration_hours": "2.00",
  "total_cost": "10000.00"
}
```

**Response (201):** Same as booking detail

#### Get Booking Details
```
GET /api/bookings/{id}/
Authorization: Bearer <token>
```

#### Update Booking Status
```
PUT /api/bookings/{id}/
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "status": "confirmed",
  "cancellation_reason": ""
}
```

**Status Options:**
- `pending`
- `confirmed`
- `in_progress`
- `completed`
- `cancelled`

### 6. Verification

#### Submit Verification Request
```
POST /api/verification/
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

**Request Body:**
```
document_image_1: <file>
document_image_2: <file> (optional)
document_image_3: <file> (optional)
additional_info: "Additional verification information"
```

**Only accessible to users with 'artisan' role**

#### List Verification Requests
```
GET /api/verification/
Authorization: Bearer <token>
```

**Response varies based on role:**
- Artisans: See their own requests
- Agents: See pending requests

#### Process Verification (Agents Only)
```
POST /api/verification/{id}/process/
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "status": "approved",
  "rejection_reason": ""
}
```

OR

```json
{
  "status": "rejected",
  "rejection_reason": "Documents are not clear enough"
}
```

### 7. Reviews

#### List Reviews
```
GET /api/reviews/
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "count": 5,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "booking": 1,
      "booking_details": {
        "id": 1,
        "artisan_details": {
          "first_name": "Michael",
          "last_name": "Artisan"
        }
      },
      "rating": 5,
      "comment": "Excellent service! Very professional and punctual.",
      "created_at": "2024-01-20T00:00:00Z"
    }
  ]
}
```

#### Create Review
```
POST /api/reviews/
Authorization: Bearer <token>
```

**Request Body:**
```json
{
  "booking": 1,
  "rating": 5,
  "comment": "Excellent service! Very professional and punctual."
}
```

**Requirements:**
- Booking must be completed
- Booking must not already have a review
- User must be the client of the booking

## Error Responses

### 400 Bad Request
```json
{
  "field_name": [
    "Error message"
  ]
}
```

### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```

### 403 Forbidden
```json
{
  "detail": "You do not have permission to perform this action."
}
```

### 404 Not Found
```json
{
  "detail": "Not found."
}
```

## Role-Based Access

### Client
- Can register and update profile
- Can browse artisans
- Can create bookings
- Can add reviews for completed bookings

### Artisan
- Can register and update profile
- Can manage artisan profile
- Can submit verification requests
- Can view and update their bookings

### Agent
- Can view and process verification requests
- Can approve/reject artisan verifications

### Admin
- Full access to all endpoints
- Access to Django admin panel

## Rate Limiting

Currently no rate limiting is implemented. Consider implementing for production.

## CORS

Configure allowed origins in settings:
```python
CORS_ALLOWED_ORIGINS = [
    "https://yourapp.com",
    "http://localhost:19006"  # React Native development
]
```

## Pagination

All list endpoints support pagination:

```
GET /api/artisans/?page=2
```

Default page size: 20 items

## Filtering and Search

Most list endpoints support filtering:

```
GET /api/artisans/?category=1&state=2&search=plumber
```

## Image Upload

For endpoints accepting images:
- Content-Type: `multipart/form-data`
- Max file size: Check your server configuration
- Accepted formats: JPG, PNG, GIF
- Images are stored in `/media/` directory

## Testing

Use tools like:
- Postman
- cURL
- HTTPie
- Thunder Client (VS Code)

Example cURL request:
```bash
curl -X POST https://yourdomain.com/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"securepassword"}'
```

## Support

For API issues, contact: support@smahi.com
