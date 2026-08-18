"""Registration security tests — the public, unauthenticated
POST /api/auth/register/ endpoint must never be able to mint a
privileged (admin/agent/state_coordinator) account. See
UserRegistrationSerializer.validate_role for the fix.
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

REGISTER_URL = '/api/auth/register/'


class PublicRegistrationRoleTests(APITestCase):
    def register(self, **overrides):
        payload = {
            'email': 'newuser@test.com',
            'password': 'password123',
            'password_confirm': 'password123',
            'first_name': 'New',
            'last_name': 'User',
            'role': 'client',
        }
        payload.update(overrides)
        return self.client.post(REGISTER_URL, payload)

    def test_client_role_is_allowed(self):
        response = self.register(role='client')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.get(email='newuser@test.com').role, 'client')

    def test_artisan_role_is_allowed(self):
        response = self.register(role='artisan', email='newartisan@test.com')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(User.objects.get(email='newartisan@test.com').role, 'artisan')

    def test_admin_role_is_rejected(self):
        response = self.register(role='admin')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='newuser@test.com').exists())

    def test_agent_role_is_rejected(self):
        response = self.register(role='agent')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='newuser@test.com').exists())

    def test_state_coordinator_role_is_rejected(self):
        response = self.register(role='state_coordinator')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='newuser@test.com').exists())

    def test_unrecognized_role_is_rejected(self):
        # Not even a real role, but proves the check runs before any
        # choices-based rejection would (defense in depth).
        response = self.register(role='lga_admin')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_role_defaults_to_client(self):
        payload = {
            'email': 'defaultrole@test.com',
            'password': 'password123',
            'password_confirm': 'password123',
            'first_name': 'Default',
            'last_name': 'Role',
        }
        response = self.client.post(REGISTER_URL, payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(User.objects.get(email='defaultrole@test.com').role, 'client')
