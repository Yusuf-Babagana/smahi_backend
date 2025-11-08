from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Country, State, LGA
from .serializers import CountrySerializer, StateSerializer, LGASerializer

class CountryListView(generics.ListAPIView):
    queryset = Country.objects.all().prefetch_related('states')
    serializer_class = CountrySerializer

class CountryDetailView(generics.RetrieveAPIView):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer

class StateListView(generics.ListAPIView):
    serializer_class = StateSerializer
    
    def get_queryset(self):
        queryset = State.objects.all().select_related('country').prefetch_related('lgas')
        country_id = self.request.query_params.get('country_id')
        if country_id:
            queryset = queryset.filter(country_id=country_id)
        return queryset

class StateDetailView(generics.RetrieveAPIView):
    queryset = State.objects.all()
    serializer_class = StateSerializer

class LGAListView(generics.ListAPIView):
    serializer_class = LGASerializer
    
    def get_queryset(self):
        queryset = LGA.objects.all().select_related('state', 'state__country')
        state_id = self.request.query_params.get('state_id')
        if state_id:
            queryset = queryset.filter(state_id=state_id)
        return queryset

@api_view(['GET'])
def location_search(request):
    query = request.GET.get('q', '')
    results = {}
    
    if query:
        # Search countries
        countries = Country.objects.filter(name__icontains=query)[:5]
        results['countries'] = CountrySerializer(countries, many=True).data
        
        # Search states
        states = State.objects.filter(name__icontains=query)[:10]
        results['states'] = StateSerializer(states, many=True).data
        
        # Search LGAs
        lgas = LGA.objects.filter(name__icontains=query)[:10]
        results['lgas'] = LGASerializer(lgas, many=True).data
    
    return Response(results)