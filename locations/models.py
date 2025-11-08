from django.db import models

class Country(models.Model):
    name = models.CharField(max_length=100)
    iso3 = models.CharField(max_length=3, null=True, blank=True)
    iso2 = models.CharField(max_length=2, null=True, blank=True)
    phone_code = models.CharField(max_length=10, null=True, blank=True)
    capital = models.CharField(max_length=100, null=True, blank=True)
    currency = models.CharField(max_length=10, null=True, blank=True)
    currency_name = models.CharField(max_length=50, null=True, blank=True)
    currency_symbol = models.CharField(max_length=10, null=True, blank=True)
    region = models.CharField(max_length=50, null=True, blank=True)
    subregion = models.CharField(max_length=50, null=True, blank=True)
    emoji = models.CharField(max_length=10, null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "Countries"
        ordering = ['name']
    
    def __str__(self):
        return self.name

class State(models.Model):
    name = models.CharField(max_length=100)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='states')
    state_code = models.CharField(max_length=10, null=True, blank=True)
    
    class Meta:
        ordering = ['name']
        unique_together = ['name', 'country']
    
    def __str__(self):
        return f"{self.name}, {self.country.name}"

class LGA(models.Model):
    name = models.CharField(max_length=100)
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name='lgas')
    
    class Meta:
        verbose_name = "LGA"
        verbose_name_plural = "LGAs"
        ordering = ['name']
        unique_together = ['name', 'state']
    
    def __str__(self):
        return f"{self.name}, {self.state.name}"
    
    