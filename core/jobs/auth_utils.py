import jwt
import datetime
from functools import wraps
from django.http import JsonResponse
from django.conf import settings
from jobs.models import User

JWT_SECRET = settings.JWT_SECRET
JWT_ALGORITHM = settings.JWT_ALGORITHM
ACCESS_EXP_MIN = settings.ACCESS_TOKEN_EXP_MIN
REFRESH_EXP_DAYS = settings.REFRESH_TOKEN_EXP_DAYS

def generate_access_token(user):
    payload = {
        "user_id": user.id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_EXP_MIN),
        "type": "access"
    }
    
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def generate_refresh_token(user):
    payload = {
        "user_id": user.id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=REFRESH_EXP_DAYS),
        "type": "refresh"
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token):
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {"ok": True, "payload": payload}
    except jwt.ExpiredSignatureError:
        return {"ok": False, "error": "expired"}
    except jwt.InvalidTokenError:
        return {"ok": False, "error": "invalid"}

def login_required(view_func):
    
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        auth = request.META.get("HTTP_AUTHORIZATION", "") or ""
        if not auth or not auth.startswith("Bearer "):
            return JsonResponse({"detail": "Authentication credentials were not provided."}, status=401)

        token = auth.split(" ", 1)[1].strip()
        res = decode_token(token)
        if not res["ok"]:
            if res.get("error") == "expired":
                return JsonResponse({"detail": "Token expired."}, status=401)
            return JsonResponse({"detail": "Invalid token."}, status=401)

        payload = res["payload"]
        if payload.get("type") != "access":
            return JsonResponse({"detail": "Token is not an access token."}, status=401)

        try:
            user = User.objects.get(id=payload["user_id"])
        except User.DoesNotExist:
            return JsonResponse({"detail": "User not found."}, status=401)

        
        request.user = user
        return view_func(request, *args, **kwargs)

    return _wrapped
