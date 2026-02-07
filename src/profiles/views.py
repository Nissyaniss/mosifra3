from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from accounts.models import CompanyProfile, InstitutionProfile, Offer, StudentProfile, User


class AccountSpaceView(LoginRequiredMixin, TemplateView):
    template_name = "profiles/user_space.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_staff:
            user = request.user
            if user.role == User.Role.COMPANY:
                if hasattr(user, "company_profile") and not user.company_profile.is_approved:
                    self.template_name = "profiles/pending_approval.html"
            elif user.role == User.Role.INSTITUTION:
                if hasattr(user, "institution_profile") and not user.institution_profile.is_approved:
                    self.template_name = "profiles/pending_approval.html"
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        logo_url = None
        if user.role == User.Role.COMPANY and hasattr(user, "company_profile"):
            if user.company_profile.logo:
                logo_url = user.company_profile.logo.url
        elif user.role == User.Role.INSTITUTION and hasattr(user, "institution_profile"):
            if user.institution_profile.logo:
                logo_url = user.institution_profile.logo.url
        context["logo_url"] = logo_url
        
        # Détection du tab actif
        tab = self.request.GET.get("tab", "dashboard")
        if tab == "account":
            context["active_tab"] = "account"
            context["tab_template"] = "profiles/partials/tab_account.html"
        else:
            context["active_tab"] = "dashboard"
            context["tab_template"] = "profiles/partials/tab_dashboard.html"
        return context


class MyStudentsView(LoginRequiredMixin, TemplateView):
    template_name = "profiles/user_space.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role != User.Role.INSTITUTION:
            raise Http404("Réservé aux établissements.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        logo_url = None
        if hasattr(user, "institution_profile") and user.institution_profile.logo:
            logo_url = user.institution_profile.logo.url
        context["logo_url"] = logo_url
        context["students"] = StudentProfile.objects.filter(institution=user).select_related("user")
        context["active_tab"] = "students"
        context["tab_template"] = "profiles/partials/tab_students.html"
        return context


class MyOffersView(LoginRequiredMixin, TemplateView):
    template_name = "profiles/user_space.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.role not in (User.Role.COMPANY, User.Role.INSTITUTION):
            return redirect("profiles:account_space")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["offers"] = Offer.objects.filter(company=self.request.user).order_by("-created_at")
        profile = getattr(self.request.user, "company_profile", None) or getattr(self.request.user, "institution_profile", None)
        if profile and profile.logo:
            context["logo_url"] = profile.logo.url
        context["active_tab"] = "offers"
        context["tab_template"] = "profiles/partials/tab_offers.html"
        return context


class AdminValidationView(LoginRequiredMixin, TemplateView):
    template_name = "profiles/admin_validation.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect("profiles:account_space")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pending_companies = CompanyProfile.objects.filter(is_approved=False).select_related("user")
        pending_institutions = InstitutionProfile.objects.filter(is_approved=False).select_related("user")
        
        pending_accounts = []
        for profile, type_label in [(p, "company") for p in pending_companies] + [(p, "institution") for p in pending_institutions]:
            pending_accounts.append({
                "type": type_label,
                "id": profile.id,
                "name": profile.organisation_name,
                "phone": profile.phone,
                "location": profile.location,
                "country_code": profile.country_code,
                "email": profile.user.email,
                "logo": profile.logo,
            })
        context["pending_accounts"] = pending_accounts
        return context


class AccountDetailView(LoginRequiredMixin, TemplateView):
    template_name = "profiles/account_detail.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect("profiles:account_space")
        return super().dispatch(request, *args, **kwargs)

    def get_profile(self):
        account_type = self.kwargs.get("account_type")
        account_id = self.kwargs.get("account_id")
        if account_type == "company":
            return get_object_or_404(CompanyProfile, id=account_id), account_type
        elif account_type == "institution":
            return get_object_or_404(InstitutionProfile, id=account_id), account_type
        raise Http404("Type de compte invalide")

    def get(self, request, *args, **kwargs):
        profile, account_type = self.get_profile()
        if profile.is_approved:
            messages.info(request, "Ce compte a déjà été validé.")
            return redirect("profiles:admin_validation")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile, account_type = self.get_profile()
        context["account"] = profile
        context["account_type"] = account_type
        return context

    def post(self, request, *args, **kwargs):
        profile, account_type = self.get_profile()
        if profile.is_approved:
            messages.info(request, "Ce compte a déjà été validé.")
            return redirect("profiles:admin_validation")
        action = request.POST.get("action")
        custom_message = request.POST.get("message", "").strip()
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)

        if action == "approve":
            profile.is_approved = True
            profile.save()
            send_mail(
                "Votre compte Mosifra a été validé",
                f"Bonjour {profile.organisation_name},\n\nVotre compte a été validé par notre équipe. Vous pouvez maintenant accéder à toutes les fonctionnalités de Mosifra.\n\nConnectez-vous ici : https://mosifra.com/accounts/login/\n\nL'équipe Mosifra",
                from_email,
                [profile.user.email],
                fail_silently=True,
            )
            messages.success(request, f"Le compte {profile.organisation_name} a été approuvé.")

        elif action == "reject":
            profile.user.delete()
            reject_message = f"Bonjour {profile.organisation_name},\n\nNous sommes au regret de vous informer que votre demande d'inscription sur Mosifra n'a pas été acceptée."
            if custom_message:
                reject_message += f"\n\nMotif : {custom_message}"
            reject_message += "\n\nSi vous pensez qu'il s'agit d'une erreur, n'hésitez pas à nous contacter.\n\nL'équipe Mosifra"
            send_mail(
                "Votre demande d'inscription Mosifra",
                reject_message,
                from_email,
                [profile.user.email],
                fail_silently=True,
            )
            messages.success(request, f"Le compte {profile.organisation_name} a été refusé.")

        return redirect("profiles:admin_validation")


@login_required
@require_GET
def tab_dashboard(request):
    return render(request, "profiles/partials/tab_dashboard.html")


@login_required
@require_GET
def tab_account(request):
    return render(request, "profiles/partials/tab_account.html")


@login_required
@require_GET
def tab_offers(request):
    if request.user.role not in (User.Role.COMPANY, User.Role.INSTITUTION):
        return HttpResponse("", status=403)
    offers = Offer.objects.filter(company=request.user).order_by("-created_at")
    profile = getattr(request.user, "company_profile", None) or getattr(request.user, "institution_profile", None)
    logo_url = profile.logo.url if profile and profile.logo else None
    return render(request, "profiles/partials/tab_offers.html", {
        "offers": offers,
        "logo_url": logo_url,
    })


@login_required
@require_GET
def tab_students(request):
    if request.user.role != User.Role.INSTITUTION:
        return HttpResponse("", status=403)
    students = StudentProfile.objects.filter(institution=request.user).select_related("user")
    return render(request, "profiles/partials/tab_students.html", {
        "students": students,
    })
