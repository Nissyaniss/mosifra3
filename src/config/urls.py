from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import logout
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import include, path
from django.views.decorators.http import require_GET, require_POST


@require_get
def home(request):
    return render(request, "home.html")


@require_get
def ping(request):
    return HttpResponse(
        "<p class='text-emerald-700 font-medium'>HTMX a bien chargé ce message ✅</p>"
    )


@require_get
def logout_view(request):
    logout(request)
    return redirect("home")


urlpatterns = [
    path("", home, name="home"),
    path("offres/", include("offers.urls")),
    path("ping/", ping, name="ping"),
    path("logout/", logout_view, name="logout"),
    path("accounts/", include("accounts.urls")),
    path("espace/", include("profiles.urls")),
    path("invitations/", include("invitations.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
