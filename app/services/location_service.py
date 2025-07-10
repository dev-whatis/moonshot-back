"""
(location_service.py) A self-contained service to resolve a client's IP address
to geographic location data using an external API.
"""
import httpx
from typing import Optional, Dict, Any
from fastapi import Request

# Import the API key from the central configuration
from app.config import IPGEOLOCATION_API_KEY

async def get_location_from_request(request: Request) -> Optional[Dict[str, Any]]:
    """
    Fetches geolocation data based on the client's IP address from a request.

    This function is designed to be called from the router layer, as it requires
    the FastAPI Request object to access the client's IP.

    Args:
        request: The FastAPI Request object.

    Returns:
        A dictionary containing curated location information if successful,
        otherwise None.
    """
    # 1. Check if the API key has been configured.
    if not IPGEOLOCATION_API_KEY or IPGEOLOCATION_API_KEY == "your_ipgeolocation_api_key_here":
        print("WARNING: IPGEOLOCATION_API_KEY is not configured. Skipping location lookup.")
        return None

    # 2. Extract the client's IP address.
    # FastAPI's `request.client.host` correctly handles the X-Forwarded-For header,
    # which is essential when running behind a proxy like Google Cloud Run.
    client_ip = request.client.host
    print(f"Attempting location lookup for IP: {client_ip}")

    # 3. Handle local development cases where the IP is a loopback address.
    if client_ip in ["127.0.0.1", "::1"]:
        print("INFO: Client IP is a loopback address. Using test IP '8.8.8.8' for local development.")
        client_ip = "8.8.8.8"

    # 4. Construct the API request URL.
    api_url = f"https://api.ipgeolocation.io/v2/ipgeo?apiKey={IPGEOLOCATION_API_KEY}&ip={client_ip}"

    # 5. Perform the external API call with robust error handling.
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, timeout=5.0)
            # Raise an exception for 4xx or 5xx status codes.
            response.raise_for_status()
            data = response.json()

        # 6. Safely parse the response and extract only the required fields.
        location_data = data.get("location", {})
        if not location_data:
            print(f"Warning: Geolocation API response for IP {client_ip} was successful but contained no 'location' data.")
            return None
        
        curated_location = {
            "country_name": location_data.get("country_name"),
            "state_prov": location_data.get("state_prov"),
            "district": location_data.get("district"),
            "city": location_data.get("city"),
            "zipcode": location_data.get("zipcode"),
        }

        print(f"Successfully retrieved location for IP {client_ip}: {curated_location.get('city')}, {curated_location.get('state_prov')}")
        return curated_location

    except httpx.HTTPStatusError as e:
        print(f"ERROR: Geolocation API returned a non-200 status code for IP {client_ip}. Status: {e.response.status_code}, Response: {e.response.text}")
        return None
    except httpx.RequestError as e:
        print(f"ERROR: A network error occurred while calling geolocation API for IP {client_ip}: {e}")
        return None
    except Exception as e:
        # Catch any other potential errors (e.g., JSON decoding).
        print(f"ERROR: An unexpected error occurred during location lookup for IP {client_ip}: {e}")
        return None