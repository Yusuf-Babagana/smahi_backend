from django.http import HttpResponse
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import get_user_model
from django.conf import settings
import uuid
import requests as http_requests
from .serializers import UserRegistrationSerializer, UserSerializer, UserUpdateSerializer
from notifications.services import send_otp, verify_otp, OTPError, OTPCooldown

User = get_user_model()


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()

        # Artisans must pay a registration fee before their account is active.
        # Set account to inactive; it gets activated after Paystack verification.
        # If Paystack isn't configured yet (no secret key), skip this so
        # accounts don't get stuck inactive with no way to pay — the fee stays
        # owed (registration_fee_paid=False) and is collected once payments go live.
        if user.role == 'artisan' and settings.PAYSTACK_SECRET_KEY:
            user.account_status = 'inactive'
            user.save(update_fields=['account_status'])

        # Best-effort: email an OTP so the new user can verify their address.
        # Registration must succeed even if the email provider is down.
        try:
            send_otp(user, 'email_verify')
        except OTPError:
            pass

        refresh = RefreshToken.for_user(user)

        response_data = {
            'user': UserSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }
        }

        # Tell the frontend that an artisan must pay before they can use the app
        if user.role == 'artisan':
            response_data['requires_payment'] = True
            response_data['payment_amount'] = getattr(settings, 'ARTISAN_REGISTRATION_FEE', 2500)

        return Response(response_data, status=status.HTTP_201_CREATED)

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

    response_data = {
        'user': UserSerializer(user).data,
        'tokens': {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
    }

    # Self-heal: an artisan may have PAID without the app managing to verify
    # (connection lost / app closed on the payment page). Check Paystack for
    # their recent pending references before demanding payment again.
    if user.role == 'artisan' and not user.registration_fee_paid:
        _reconcile_pending_payments(user)
        if user.registration_fee_paid:
            response_data['user'] = UserSerializer(user).data

    # Artisans who haven't paid the registration fee need to be redirected
    if user.role == 'artisan' and not user.registration_fee_paid:
        response_data['requires_payment'] = True
        response_data['payment_amount'] = getattr(settings, 'ARTISAN_REGISTRATION_FEE', 2500)

        # Self-heal accounts stuck 'inactive' from before payments were
        # configured (or while they are switched off): they owe the fee but
        # must still be able to use the app and pay later.
        if not settings.PAYSTACK_SECRET_KEY and user.account_status == 'inactive':
            user.account_status = 'active'
            user.save(update_fields=['account_status'])
            response_data['user'] = UserSerializer(user).data

    return Response(response_data)


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


# ---------------------------------------------------------------------------
# Paystack Registration Fee
# ---------------------------------------------------------------------------

PAYSTACK_BASE_URL = 'https://api.paystack.co'


def _resolve_user_from_request(request):
    """Identify the user from a JWT token OR from the ``email`` body field.

    Mobile clients sometimes fail to attach the Authorization header (e.g.
    SecureStore timing issues on Android).  This helper lets the endpoint
    work either way so the payment flow isn't blocked.
    """
    # 1. An email in the body wins. The app sends it explicitly in payment
    # flows, and a stale-but-valid JWT from a PREVIOUS session (e.g. a
    # client account that never logged out) must not override who the
    # payment is actually for — that produced "Registration fee applies to
    # artisans only" right after registering a new artisan.
    # Case-insensitive: registration stores the email as typed.
    email = str((request.data or {}).get('email', '')).strip()
    if email:
        user = User.objects.filter(email__iexact=email).first()
        if user:
            return user

    # 2. Fall back to JWT, validated manually: the payment views disable
    # DRF's automatic authentication so an invalid token degrades to a 401
    # from this helper instead of a hard 401 before the view runs.
    try:
        auth = JWTAuthentication().authenticate(request)
        if auth is not None:
            return auth[0]
    except Exception:
        pass

    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return user

    return None


def _paystack_headers():
    return {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }


def _apply_successful_payment(payment, user):
    """Mark the payment successful and activate the artisan account."""
    payment.status = 'success'
    payment.save(update_fields=['status', 'paystack_response', 'updated_at'])
    user.registration_fee_paid = True
    user.account_status = 'active'
    user.save(update_fields=['registration_fee_paid', 'account_status', 'updated_at'])


def _reconcile_pending_payments(user):
    """Self-heal artisans who PAID but were never verified.

    If the app closed or lost connection before calling the verify endpoint,
    the money left the user's account but registration_fee_paid stayed False,
    trapping them on the payment screen forever. Called at login: check the
    user's recent pending references directly with Paystack and apply any
    completed transaction.
    """
    if user.registration_fee_paid:
        return
    from core.models import RegistrationPayment

    # A payment already recorded as success (e.g. verified earlier, or marked
    # by an admin) is proof enough — activate without asking Paystack.
    recorded = RegistrationPayment.objects.filter(
        user=user, status='success'
    ).order_by('-id').first()
    if recorded:
        _apply_successful_payment(recorded, user)
        return

    if not settings.PAYSTACK_SECRET_KEY:
        return
    pending = RegistrationPayment.objects.filter(
        user=user, status='pending'
    ).order_by('-id')[:3]
    for payment in pending:
        try:
            resp = http_requests.get(
                f'{PAYSTACK_BASE_URL}/transaction/verify/{payment.reference}',
                headers=_paystack_headers(),
                timeout=10,
            )
            data = resp.json()
        except Exception:
            continue  # Paystack unreachable: try again next login
        if data.get('status') and data.get('data', {}).get('status') == 'success':
            payment.paystack_response = data
            _apply_successful_payment(payment, user)
            return


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def initialize_registration_payment(request):
    """Initialize a Paystack transaction for the artisan registration fee.

    Accepts either:
      - A valid JWT in the Authorization header (standard flow), OR
      - An ``email`` field in the request body (fallback for mobile clients
        where the token may not be attached).

    Returns the authorization URL the frontend should open in a WebView.
    """
    user = _resolve_user_from_request(request)
    if user is None:
        return Response(
            {'error': 'Could not identify the user. Please log in again.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if user.role != 'artisan':
        return Response(
            {'error': 'Registration fee applies to artisans only.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if user.registration_fee_paid:
        # Not an error from the user's perspective — their account is settled.
        # Make sure the status reflects that, and tell the client explicitly
        # so it can route to the dashboard instead of showing a failure.
        if user.account_status != 'active':
            user.account_status = 'active'
            user.save(update_fields=['account_status'])
        return Response(
            {'error': 'Registration fee has already been paid.', 'already_paid': True},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Without a Paystack key the API call below can only fail with a
    # confusing "Invalid key" error. Fail cleanly instead; the account
    # stays usable and the fee is collected once payments are configured.
    if not settings.PAYSTACK_SECRET_KEY:
        return Response(
            {'error': 'Payments are not available yet. Your account remains active — you can complete the registration fee later.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    amount_kobo = getattr(settings, 'ARTISAN_REGISTRATION_FEE', 2500) * 100
    reference = f"SMAHI-REG-{uuid.uuid4().hex[:12].upper()}"

    # Where Paystack redirects the browser after payment. The app's WebView
    # watches for 'reference=' in the URL to trigger verification — without
    # a callback_url Paystack never redirects, verification never runs, and
    # paid artisans stay stuck on the payment screen.
    callback_url = request.build_absolute_uri(
        f'/api/auth/payments/callback/?reference={reference}'
    )
    if callback_url.startswith('http://') and not any(
        h in callback_url for h in ('localhost', '127.0.0.1', '192.168.')
    ):
        callback_url = 'https://' + callback_url[len('http://'):]

    payload = {
        'email': user.email,
        'amount': amount_kobo,
        'reference': reference,
        'currency': 'NGN',
        'callback_url': callback_url,
        'metadata': {
            'user_id': user.id,
            'purpose': 'artisan_registration',
        },
    }

    try:
        resp = http_requests.post(
            f'{PAYSTACK_BASE_URL}/transaction/initialize',
            json=payload,
            headers=_paystack_headers(),
            timeout=15,
        )
        data = resp.json()
    except Exception as e:
        return Response(
            {'error': f'Failed to connect to payment provider: {str(e)}'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if not data.get('status'):
        return Response(
            {'error': data.get('message', 'Payment initialization failed.')},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from core.models import RegistrationPayment
    RegistrationPayment.objects.create(
        user=user,
        reference=reference,
        amount=amount_kobo,
        status='pending',
        paystack_response=data,
    )

    return Response({
        'authorization_url': data['data']['authorization_url'],
        'reference': reference,
        'amount': getattr(settings, 'ARTISAN_REGISTRATION_FEE', 2500),
    })


def registration_payment_callback(request):
    """Paystack redirects here after checkout. The app's WebView reacts to
    the 'reference=' query param before this page even renders; the HTML is
    only a fallback for anyone completing payment in a normal browser."""
    return HttpResponse(
        '<html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>S-MAHII Payment</title></head>'
        '<body style="font-family:sans-serif;text-align:center;padding-top:60px">'
        '<h2>&#9989; Payment received</h2>'
        '<p>Return to the S-MAHII app to continue.</p>'
        '</body></html>'
    )


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def verify_registration_payment(request, reference):
    """Verify a Paystack transaction and activate the artisan account."""

    user = _resolve_user_from_request(request)
    if user is None:
        return Response(
            {'error': 'Could not identify the user. Please log in again.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if user.role != 'artisan':
        return Response(
            {'error': 'Registration fee applies to artisans only.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from core.models import RegistrationPayment

    try:
        payment = RegistrationPayment.objects.get(reference=reference, user=user)
    except RegistrationPayment.DoesNotExist:
        return Response(
            {'error': 'Payment record not found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if payment.status == 'success':
        return Response({'message': 'Payment already verified.', 'status': 'success'})

    # Ask Paystack to verify the transaction
    try:
        resp = http_requests.get(
            f'{PAYSTACK_BASE_URL}/transaction/verify/{reference}',
            headers=_paystack_headers(),
            timeout=15,
        )
        data = resp.json()
    except Exception as e:
        return Response(
            {'error': f'Failed to verify payment: {str(e)}'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if not data.get('status'):
        payment.status = 'failed'
        payment.paystack_response = data
        payment.save(update_fields=['status', 'paystack_response', 'updated_at'])
        return Response(
            {'error': data.get('message', 'Payment verification failed.')},
            status=status.HTTP_400_BAD_REQUEST,
        )

    tx_data = data.get('data', {})

    if tx_data.get('status') == 'success':
        payment.status = 'success'
        payment.paystack_response = data
        payment.save(update_fields=['status', 'paystack_response', 'updated_at'])

        # Activate the artisan account
        user.registration_fee_paid = True
        user.account_status = 'active'
        user.save(update_fields=['registration_fee_paid', 'account_status', 'updated_at'])

        return Response({
            'message': 'Payment verified successfully. Your account is now active!',
            'status': 'success',
        })
    else:
        payment.status = 'failed'
        payment.paystack_response = data
        payment.save(update_fields=['status', 'paystack_response', 'updated_at'])
        return Response(
            {'error': 'Payment was not successful. Please try again.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
