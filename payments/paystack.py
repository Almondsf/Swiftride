import requests
from django.conf import settings

PAYSTACK_BASE_URL = 'https://api.paystack.co'

def inititalize_payment(email, amount_naira):
    url = f"{PAYSTACK_BASE_URL}/transaction/initialize"
    headers = {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        'content-type': 'application/json',
    }
    data = {
        'email': email,
        'amount': int(amount_naira * 100),  # Convert to kobo
    }
    response = requests.post(url, json=data, headers=headers)
    return response.json()

def verify_payment(reference):
    url = f'{PAYSTACK_BASE_URL}/transaction/verify/{reference}'
    headers = {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
    }
    response = requests.get(url, headers=headers)
    return response.json()