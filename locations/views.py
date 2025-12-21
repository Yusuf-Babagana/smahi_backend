from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny 
from .models import Country, State, LGA
from .serializers import CountrySerializer, StateSerializer, LGASerializer

# --- COUNTRIES ---
class CountryListView(generics.ListAPIView):
    queryset = Country.objects.all().prefetch_related('states')
    serializer_class = CountrySerializer
    permission_classes = [AllowAny]
    pagination_class = None          # <--- Fix 1: Fetch ALL countries (250+)

class CountryDetailView(generics.RetrieveAPIView):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    permission_classes = [AllowAny]

# --- STATES ---
class StateListView(generics.ListAPIView):
    serializer_class = StateSerializer
    permission_classes = [AllowAny]
    pagination_class = None          # <--- Fix 1: Fetch ALL states (e.g. all 36+1 for Nigeria)
    
    def get_queryset(self):
        queryset = State.objects.all().select_related('country').prefetch_related('lgas')
        
        # <--- Fix 2: Only fetch states that correspond to the selected country
        country_id = self.request.query_params.get('country_id')
        if country_id:
            queryset = queryset.filter(country_id=country_id)
            
        return queryset

class StateDetailView(generics.RetrieveAPIView):
    queryset = State.objects.all()
    serializer_class = StateSerializer
    permission_classes = [AllowAny]

# --- LGAs ---
class LGAListView(generics.ListAPIView):
    serializer_class = LGASerializer
    permission_classes = [AllowAny]
    pagination_class = None          # <--- Fix 1: Fetch ALL LGAs (e.g. all 20+ for a state)
    
    def get_queryset(self):
        queryset = LGA.objects.all().select_related('state', 'state__country')
        
        # <--- Fix 2: Only fetch LGAs that correspond to the selected state
        state_id = self.request.query_params.get('state_id')
        if state_id:
            queryset = queryset.filter(state_id=state_id)
            
        return queryset

# --- SEARCH ---
@api_view(['GET'])
@permission_classes([AllowAny])
def location_search(request):
    query = request.GET.get('q', '')
    results = {}
    
    if query:
        countries = Country.objects.filter(name__icontains=query)[:5]
        results['countries'] = CountrySerializer(countries, many=True).data
        
        states = State.objects.filter(name__icontains=query)[:10]
        results['states'] = StateSerializer(states, many=True).data
        
        lgas = LGA.objects.filter(name__icontains=query)[:10]
        results['lgas'] = LGASerializer(lgas, many=True).data
    
    return Response(results)