from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .serializers import UserRegistrationSerializer, UserSerializer, UserUpdateSerializer
from notifications.services import send_otp, verify_otp, OTPError, OTPCooldown

User = get_user_model()


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()

        # Best-effort: email an OTP so the new user can verify their address.
        # Registration must succeed even if the email provider is down.
        try:
            send_otp(user, 'email_verify')
        except OTPError:
            pass

        refresh = RefreshToken.for_user(user)

        return Response({
            'user': UserSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    email = request.data.get('email')
    password = request.data.get('password')

    if not email or not password:
        return Response(
            {'error': 'Email and password are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response(
            {'error': 'Invalid credentials.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    if not user.check_password(password):
        return Response(
            {'error': 'Invalid credentials.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    if not user.is_active:
        return Response(
            {'error': 'User account is disabled.'},
            status=status.HTTP_403_FORBIDDEN
        )

    refresh = RefreshToken.for_user(user)

    return Response({
        'user': UserSerializer(user).data,
        'tokens': {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_request_view(request):
    email = str(request.data.get('email', '')).strip()
    if not email:
        return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

    # Always the same answer whether or not the account exists (no user enumeration)
    generic = {'message': 'If an account exists with this email, a password reset code has been sent.'}

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response(generic)

    try:
        send_otp(user, 'password_reset')
    except OTPError:
        # Cooldown/provider state must not be revealed to unauthenticated callers
        pass

    return Response(generic)


@api_view(['POST'])
@permission_classes([AllowAny])
def password_reset_confirm_view(request):
    email = str(request.data.get('email', '')).strip()
    code = str(request.data.get('code', '')).strip()
    new_password = request.data.get('new_password', '')

    if not email or not code or not new_password:
        return Response(
            {'error': 'Email, code and new_password are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(new_password) < 8:
        return Response(
            {'error': 'Password must be at least 8 characters.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        # Same response as a wrong code — never reveal whether the email exists
        return Response(
            {'error': 'Invalid code. Please check and try again.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    ok, message = verify_otp(user, code, 'password_reset')
    if not ok:
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.save(update_fields=['password'])

    return Response({'message': 'Password reset successfully. You can now log in with your new password.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_email_verification_view(request):
    if request.user.email_verified:
        return Response(
            {'error': 'Email is already verified.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        send_otp(request.user, 'email_verify')
    except OTPCooldown as e:
        return Response({'error': str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    except OTPError as e:
        return Response({'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response({'message': 'A verification code has been sent to your email.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_email_verification_view(request):
    code = str(request.data.get('code', '')).strip()
    if not code:
        return Response(
            {'error': 'Verification code is required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if request.user.email_verified:
        return Response(
            {'error': 'Email is already verified.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    ok, message = verify_otp(request.user, code, 'email_verify')
    if not ok:
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

    request.user.email_verified = True
    request.user.save(update_fields=['email_verified'])

    return Response({
        'message': 'Email verified successfully.',
        'user': UserSerializer(request.user).data,
    })


class ProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method == 'PUT' or self.request.method == 'PATCH':
            return UserUpdateSerializer
        return UserSerializer
