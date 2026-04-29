from .serializers import RegistrationSerializer
from rest_framework import generics
from .models import CustomUser
from rest_framework.permissions import AllowAny

class RegistrationView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = RegistrationSerializer
    permission_classes = [AllowAny]