from django.shortcuts import render
import json
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseNotAllowed
from django.contrib.auth.hashers import make_password, check_password
from django.conf import settings
from django.core.paginator import Paginator
from django.utils import timezone
import requests

from .models import User, JobListing, JobApplication
from .auth_utils import generate_access_token, generate_refresh_token, login_required
from django.conf import settings
GOOGLE_CLIENT_ID = getattr(settings, "GOOGLE_CLIENT_ID", None)
def parse_json(request):
    try:
        return json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        return {}

@csrf_exempt
def register(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    data = parse_json(request)
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    if not (username and email and password):
        return JsonResponse({"detail": "username, email, and password are required."}, status=400)
    if User.objects.filter(username=username).exists():
        return JsonResponse({"detail": "username already taken."}, status=400)
    if User.objects.filter(email=email).exists():
        return JsonResponse({"detail": "email already registered."}, status=400)
    user = User.objects.create(
        username=username,
        email=email,
        password=make_password(password)
    )
    return JsonResponse({"id": user.id, "username": user.username, "email": user.email}, status=201)

@csrf_exempt
def login(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    data = parse_json(request)
    username = data.get("username")
    password = data.get("password")
    if not (username and password):
        return JsonResponse({"detail": "username and password required."}, status=400)
    # allow login by username OR email
    user = User.objects.filter(username=username).first() or User.objects.filter(email=username).first()
    if not user or not check_password(password, user.password):
        return JsonResponse({"detail": "Invalid credentials."}, status=401)
    access = generate_access_token(user)
    refresh = generate_refresh_token(user)
    return JsonResponse({"access": access, "refresh": refresh, "user": {"id":user.id, "username":user.username, "email":user.email}})

@csrf_exempt
def oauth_google(request):
    
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    data = parse_json(request)
    id_token = data.get("id_token")
    if not id_token:
        return JsonResponse({"detail": "id_token required."}, status=400)


    tokeninfo_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
    try:
        r = requests.get(tokeninfo_url, timeout=5)
        if r.status_code != 200:
            return JsonResponse({"detail": "Invalid ID token."}, status=400)
        info = r.json()
    except Exception:
        return JsonResponse({"detail": "Failed to verify token with Google."}, status=500)

    
    aud = info.get("aud")
    if GOOGLE_CLIENT_ID and aud != GOOGLE_CLIENT_ID:
        return JsonResponse({"detail": "Token audience mismatch."}, status=400)

    google_sub = info.get("sub")  
    email = info.get("email")
    name = info.get("name") or email.split("@")[0]

    if not email or not google_sub:
        return JsonResponse({"detail": "Missing data in token."}, status=400)

    
    user = User.objects.filter(google_id=google_sub).first()
    if not user:
        
        existing = User.objects.filter(email=email).first()
        if existing:
            existing.google_id = google_sub
            existing.save()
            user = existing
        else:
            
            user = User.objects.create(username=name, email=email, google_id=google_sub)
            user.set_unusable_password()
            user.save()

    access = generate_access_token(user)
    refresh = generate_refresh_token(user)
    return JsonResponse({"access": access, "refresh": refresh, "user": {"id": user.id, "username": user.username, "email": user.email}})
from .auth_utils import login_required as auth_required

@csrf_exempt
def jobs_list_create(request):
    if request.method == "GET":
        qs = JobListing.objects.all().order_by("-created_at")
        # simple pagination
        page = int(request.GET.get("page", 1))
        per = int(request.GET.get("per", 20))
        paginator = Paginator(qs, per)
        page_obj = paginator.get_page(page)

        results = []
        for job in page_obj:
            results.append({
                "id": job.id,
                "title": job.title,
                "description": job.description,
                "company": job.company,
                "location": job.location,
                "posted_by": job.posted_by.username,
                "posted_by_id": job.posted_by.id,
                "created_at": job.created_at.isoformat(),
                "updated_at": job.updated_at.isoformat(),
            })
        return JsonResponse({"count": paginator.count, "page": page, "results": results})

    
    elif request.method == "POST":
        return auth_required(_create_job)(request)
    else:
        return HttpResponseNotAllowed(["GET", "POST"])

def _create_job(request):
    data = parse_json(request)
    title = data.get("title")
    description = data.get("description")
    company = data.get("company")
    location = data.get("location")
    if not all([title, description, company, location]):
        return JsonResponse({"detail": "title, description, company, location are required."}, status=400)
    job = JobListing.objects.create(
        title=title,
        description=description,
        company=company,
        location=location,
        posted_by=request.user
    )
    return JsonResponse({
        "id": job.id, "title": job.title, "company": job.company, "location": job.location,
        "posted_by": job.posted_by.username, "created_at": job.created_at.isoformat()
    }, status=201)

@csrf_exempt
def jobs_detail(request, id):
    try:
        job = JobListing.objects.get(id=id)
    except JobListing.DoesNotExist:
        return JsonResponse({"detail": "Job not found."}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": job.id,
            "title": job.title,
            "description": job.description,
            "company": job.company,
            "location": job.location,
            "posted_by": {"id": job.posted_by.id, "username": job.posted_by.username},
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        })

    elif request.method in ("PUT", "PATCH", "DELETE"):
        return auth_required(lambda req, *a, **k: _job_modify(req, job, method=request.method))(request)
    else:
        return HttpResponseNotAllowed(["GET", "PUT", "PATCH", "DELETE"])

def _job_modify(request, job, method):
    if job.posted_by.id != request.user.id:
        return JsonResponse({"detail": "You do not have permission to modify this job."}, status=403)

    if method == "DELETE":
        job.delete()
        # return JsonResponse({"detail": "Deleted."}, status=204)
        from django.http import HttpResponse
        return HttpResponse(status=204)

    data = parse_json(request)
    if method == "PUT":
        required = ["title", "description", "company", "location"]
        if not all(k in data for k in required):
            return JsonResponse({"detail": f"For PUT, provide {required}."}, status=400)
    for field in ("title", "description", "company", "location"):
        if field in data:
            setattr(job, field, data[field])
    job.updated_at = timezone.now()
    job.save()
    return JsonResponse({
        "id": job.id,
        "title": job.title,
        "description": job.description,
        "company": job.company,
        "location": job.location,
        "updated_at": job.updated_at.isoformat()
    }, status=200)




@csrf_exempt
def applications_list_create(request):
    if request.method == "GET":
        return auth_required(_list_user_applications)(request)
    elif request.method == "POST":
        return auth_required(_create_application)(request)
    else:
        return HttpResponseNotAllowed(["GET", "POST"])

def _list_user_applications(request):
    apps = JobApplication.objects.filter(applicant=request.user).order_by("-applied_at")
    results = []
    for a in apps:
        results.append({
            "id": a.id,
            "job_listing_id": a.job_listing.id,
            "job_title": a.job_listing.title,
            "resume_link": a.resume_link,
            "cover_letter": a.cover_letter,
            "status": a.status,
            "applied_at": a.applied_at.isoformat()
        })
    return JsonResponse({"count": len(results), "results": results})

def _create_application(request):
    data = parse_json(request)
    job_id = data.get("job_listing")
    if not job_id:
        return JsonResponse({"detail": "job_listing id is required."}, status=400)
    try:
        job = JobListing.objects.get(id=job_id)
    except JobListing.DoesNotExist:
        return JsonResponse({"detail": "Job listing not found."}, status=404)

   
    if JobApplication.objects.filter(job_listing=job, applicant=request.user).exists():
        return JsonResponse({"detail": "You have already applied to this job."}, status=400)

    resume_link = data.get("resume_link")
    cover_letter = data.get("cover_letter")
    app = JobApplication.objects.create(
        job_listing=job,
        applicant=request.user,
        resume_link=resume_link,
        cover_letter=cover_letter
    )
    return JsonResponse({
        "id": app.id,
        "job_listing_id": job.id,
        "applicant_id": request.user.id,
        "status": app.status,
        "applied_at": app.applied_at.isoformat()
    }, status=201)

@csrf_exempt
def application_detail(request, id):
    try:
        app = JobApplication.objects.get(id=id)
    except JobApplication.DoesNotExist:
        return JsonResponse({"detail": "Application not found."}, status=404)

    if request.method == "GET":
        
        return auth_required(lambda req,*a,**k: _ensure_owner_and_return(req, app))(request)
    elif request.method in ("PUT", "PATCH", "DELETE"):
        return auth_required(lambda req,*a,**k: _app_modify(req, app, method=request.method))(request)
    else:
        return HttpResponseNotAllowed(["GET", "PUT", "PATCH", "DELETE"])

def _ensure_owner_and_return(request, app):
    if app.applicant.id != request.user.id:
        return JsonResponse({"detail": "You do not have permission to view this application."}, status=403)
    return JsonResponse({
        "id": app.id,
        "job_listing_id": app.job_listing.id,
        "resume_link": app.resume_link,
        "cover_letter": app.cover_letter,
        "status": app.status,
        "applied_at": app.applied_at.isoformat()
    })

def _app_modify(request, app, method):
    if app.applicant.id != request.user.id:
        return JsonResponse({"detail": "You do not have permission to modify this application."}, status=403)
    if method == "DELETE":
        app.delete()
        return JsonResponse({"detail": "Deleted."}, status=204)
    data = parse_json(request)
    if method == "PUT":
        
        required = []  
    for field in ("resume_link", "cover_letter"):
        if field in data:
            setattr(app, field, data[field])
    
    app.updated_at = timezone.now()
    app.save()
    return JsonResponse({
        "id": app.id,
        "resume_link": app.resume_link,
        "cover_letter": app.cover_letter,
        "status": app.status,
        "updated_at": app.updated_at.isoformat()
    }, status=200)
