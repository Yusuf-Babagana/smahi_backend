from rest_framework import serializers
from django.contrib.auth import get_user_model
from locations.serializers import CountrySerializer, StateSerializer, LGASerializer

User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    # Force the API to require these fields to be filled out
    first_name = serializers.CharField(required=True, allow_blank=False)
    last_name = serializers.CharField(required=True, allow_blank=False)

    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm', 'first_name', 'last_name',
            'role', 'phone_number', 'address', 'country', 'state', 'lga'
        ]

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password": "Passwords do not match."})

        # Block the specific "User User" placeholder from being saved
        if attrs.get('first_name') == 'User' and attrs.get('last_name') == 'User':
            raise serializers.ValidationError({"first_name": "Please enter your actual name instead of 'User'."})

        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = User.objects.create_user(password=password, **validated_data)
        return user


class UserSerializer(serializers.ModelSerializer):
    country_details = CountrySerializer(source='country', read_only=True)
    state_details = StateSerializer(source='state', read_only=True)
    lga_details = LGASerializer(source='lga', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'role', 'phone_number',
            'address', 'profile_picture', 'country', 'state', 'lga',
            'country_details', 'state_details', 'lga_details',
            'is_verified', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'role', 'is_verified', 'created_at', 'updated_at']


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone_number', 'address',
            'profile_picture', 'country', 'state', 'lga'
        ]
