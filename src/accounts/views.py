import secrets
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.hashers import make_password
from django.contrib.auth.views import LoginView
from django.core.files.base import File
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import FormView, TemplateView

from .forms import (
    EmailAuthenticationForm,
    InvitationAcceptForm,
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    RegistrationForm,
    TwoFactorForm,
)
from .models import CompanyProfile, InstitutionProfile, StudentInvitation, StudentProfile, User

SESSION_USER_KEY = "two_factor_user_id"
SESSION_CODE_KEY = "two_factor_code"
SESSION_EXPIRY_KEY = "two_factor_expiry"
SESSION_BACKEND_KEY = "two_factor_backend"
SESSION_PENDING_USER_DATA = "two_factor_pending_user"
SESSION_PENDING_INVITE_ID = "two_factor_pending_invite"
SESSION_EMAIL_KEY = "two_factor_email"
SESSION_SUBJECT_KEY = "two_factor_subject"
SESSION_TEMPLATE_KEY = "two_factor_template"
SESSION_RESET_EMAIL = "password_reset_email"


def _send_two_factor_code(session, email, subject, message_template):
    code = f"{secrets.SystemRandom().randint(0, 999999):06d}"
    session[SESSION_CODE_KEY] = code
    session[SESSION_EXPIRY_KEY] = (timezone.now() + timedelta(minutes=10)).isoformat()
    session[SESSION_EMAIL_KEY] = email
    session[SESSION_SUBJECT_KEY] = subject
    session[SESSION_TEMPLATE_KEY] = message_template
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    send_mail(subject, message_template.format(code=code), from_email, [email], fail_silently=True)


def _create_student_profile(user, invitation=None):
    if user.role != User.Role.STUDENT:
        return None
    profile, _ = StudentProfile.objects.get_or_create(user=user)
    if invitation:
        profile.institution = invitation.institution
        profile.filiere = invitation.filiere
        profile.level = invitation.level
        profile.academic_year = invitation.academic_year
        profile.save()
    return profile


def _create_company_profile(user, data=None):
    if user.role != User.Role.COMPANY:
        return None
    data = data or {}
    profile, _ = CompanyProfile.objects.get_or_create(user=user)
    profile.organisation_name = data.get("organisation_name") or profile.organisation_name
    profile.location = data.get("location") or profile.location
    profile.country_code = data.get("country_code") or profile.country_code
    profile.phone = data.get("phone") or profile.phone
    profile.website = data.get("site") or profile.website
    profile.description = data.get("description") or profile.description
    logo_path = data.get("logo_path")
    if logo_path and default_storage.exists(logo_path):
        with default_storage.open(logo_path, "rb") as logo_file:
            profile.logo.save(Path(logo_path).name.split("/")[-1], File(logo_file), save=False)
        default_storage.delete(logo_path)
    profile.save()
    return profile


def _create_institution_profile(user, data=None):
    if user.role != User.Role.INSTITUTION:
        return None
    data = data or {}
    profile, _ = InstitutionProfile.objects.get_or_create(user=user)
    profile.organisation_name = data.get("organisation_name") or profile.organisation_name
    profile.location = data.get("location") or profile.location
    profile.country_code = data.get("country_code") or profile.country_code
    profile.phone = data.get("phone") or profile.phone
    profile.website = data.get("site") or profile.website
    profile.description = data.get("description") or profile.description
    logo_path = data.get("logo_path")
    if logo_path and default_storage.exists(logo_path):
        with default_storage.open(logo_path, "rb") as logo_file:
            profile.logo.save(Path(logo_path).name.split("/")[-1], File(logo_file), save=False)
        default_storage.delete(logo_path)
    profile.save()
    return profile


class SimpleLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm

    def form_valid(self, form):
        user = form.get_user()
        backend = getattr(user, "backend", settings.AUTHENTICATION_BACKENDS[0])
        self._store_pending(user, backend)
        _send_two_factor_code(
            self.request.session,
            user.email,
            subject="Code de vérification",
            message_template="Ton code de connexion est : {code}",
        )
        return redirect("accounts:two_factor")

    def _store_pending(self, user, backend):
        session = self.request.session
        session[SESSION_USER_KEY] = str(user.id)
        session[SESSION_BACKEND_KEY] = backend
        session.pop(SESSION_PENDING_USER_DATA, None)
        session.pop(SESSION_PENDING_INVITE_ID, None)


class RegisterView(FormView):
    template_name = "accounts/register.html"
    form_class = RegistrationForm
    success_url = reverse_lazy("accounts:two_factor")

    def get_initial(self):
        initial = super().get_initial()
        role = self.request.GET.get("role")
        valid_roles = {choice[0] for choice in User.Role.choices}
        if role in valid_roles:
            initial["role"] = role
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role = self._get_role()
        if role == User.Role.INSTITUTION:
            org_word = "l'établissement"
            title = "Créer un compte Établissement"
            account_word = "établissement"
        else:
            org_word = "l'entreprise"
            title = "Créer un compte Entreprise"
            account_word = "recruteur"
        context["org_word"] = org_word
        context["org_word_cap"] = org_word.replace("l'", "").capitalize()
        context["signup_title"] = title
        context["account_word"] = account_word
        context["email_hint"] = "Utilisez votre email professionnel pour faciliter la validation."
        return context

    def _get_role(self):
        role = self.request.GET.get("role")
        if role in {choice[0] for choice in User.Role.choices}:
            return role
        form_role = getattr(self.get_form(), "initial", {}).get("role")
        if form_role in {choice[0] for choice in User.Role.choices}:
            return form_role
        return None

    def form_invalid(self, form):
        return super().form_invalid(form)

    def form_valid(self, form):
        user = form.save(commit=False)
        session = self.request.session
        session[SESSION_BACKEND_KEY] = settings.AUTHENTICATION_BACKENDS[0]
        session.pop(SESSION_USER_KEY, None)
        session.pop(SESSION_PENDING_INVITE_ID, None)
        company_profile = {
            "organisation_name": (form.cleaned_data.get("organisation_name") or "").strip(),
            "location": (form.cleaned_data.get("organisation_location") or "").strip(),
            "country_code": (form.cleaned_data.get("country_code") or "").strip().upper(),
            "phone": (form.cleaned_data.get("organisation_phone") or "").strip(),
            "site": (form.cleaned_data.get("organisation_site") or "").strip(),
            "description": (form.cleaned_data.get("organisation_description") or "").strip(),
        }
        logo_path = self._store_temp_logo(form.cleaned_data.get("organisation_logo"))
        if logo_path:
            company_profile["logo_path"] = logo_path
        session[SESSION_PENDING_USER_DATA] = {
            "username": user.username,
            "email": user.email,
            "password": user.password,
            "role": form.cleaned_data["role"],
            "organisation_name": (form.cleaned_data.get("organisation_name") or "").strip(),
            "country_code": (form.cleaned_data.get("country_code") or "").strip().upper(),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "organisation_profile": company_profile,
        }
        _send_two_factor_code(
            session,
            user.email,
            subject="Code de vérification",
            message_template="Ton code d'inscription est : {code}",
        )
        return redirect("accounts:two_factor")

    def _store_temp_logo(self, logo):
        if not logo:
            return None
        ext = Path(logo.name).suffix or ".png"
        filename = f"tmp/company/{uuid.uuid4()}{ext}"
        return default_storage.save(filename, logo)


class RegisterStudentInfoView(TemplateView):
    template_name = "accounts/register_student_info.html"


class RegisterSelectView(TemplateView):
    template_name = "accounts/register_select.html"


class InvitationAcceptView(FormView):
    template_name = "accounts/invitation_accept.html"
    form_class = InvitationAcceptForm
    success_url = reverse_lazy("accounts:two_factor")

    def dispatch(self, request, *args, **kwargs):
        self.invitation = get_object_or_404(StudentInvitation, token=kwargs["token"])
        if self.invitation.status == StudentInvitation.Status.USED:
            messages.error(request, "Cette invitation a déjà été utilisée.")
            return redirect("accounts:login")
        if timezone.now() > self.invitation.expires_at:
            self.invitation.status = StudentInvitation.Status.EXPIRED
            self.invitation.save(update_fields=["status"])
            messages.error(request, "Invitation expirée. Contacte ton établissement.")
            return redirect("accounts:login")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["invitation"] = self.invitation
        institution_name = self.invitation.institution.email
        if hasattr(self.invitation.institution, "institution_profile"):
            institution_name = self.invitation.institution.institution_profile.organisation_name or institution_name
        context["institution_name"] = institution_name
        return context

    def form_valid(self, form):
        session = self.request.session
        session[SESSION_BACKEND_KEY] = settings.AUTHENTICATION_BACKENDS[0]
        session.pop(SESSION_USER_KEY, None)
        session[SESSION_PENDING_INVITE_ID] = str(self.invitation.id)
        session[SESSION_PENDING_USER_DATA] = {
            "username": self.invitation.email,
            "email": self.invitation.email,
            "password": make_password(form.cleaned_data["password1"]),
            "role": User.Role.STUDENT,
            "organisation_name": "",
            "country_code": "",
            "first_name": self.invitation.first_name,
            "last_name": self.invitation.last_name,
        }
        _send_two_factor_code(
            session,
            self.invitation.email,
            subject="Code de vérification",
            message_template="Ton code pour activer ton compte est : {code}",
        )
        return redirect("accounts:two_factor")


class TwoFactorView(FormView):
    template_name = "accounts/two_factor.html"
    form_class = TwoFactorForm
    success_url = reverse_lazy("home")

    def dispatch(self, request, *args, **kwargs):
        if (
            SESSION_USER_KEY not in request.session
            and SESSION_PENDING_USER_DATA not in request.session
            and SESSION_PENDING_INVITE_ID not in request.session
        ):
            return redirect("accounts:login")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if "resend_code" in request.POST:
            self._resend_code()
            return redirect("accounts:two_factor")
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        email = self._get_target_email()
        if not email and getattr(self.request.user, "is_authenticated", False):
            email = self.request.user.email
        context["target_email"] = email
        return context

    def form_valid(self, form):
        session = self.request.session
        code = session.get(SESSION_CODE_KEY)
        expiry_raw = session.get(SESSION_EXPIRY_KEY)
        if not code or not expiry_raw:
            form.add_error(None, "Code expiré, reconnecte-toi.")
            return self.form_invalid(form)

        expiry = timezone.datetime.fromisoformat(expiry_raw)
        if timezone.now() > expiry:
            self._clear_session()
            form.add_error(None, "Code expiré, reconnecte-toi.")
            return self.form_invalid(form)

        if form.cleaned_data["code"] != code:
            form.add_error("code", "Code invalide.")
            return self.form_invalid(form)

        user = None
        user_id = session.get(SESSION_USER_KEY)
        if user_id:
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                self._clear_session()
                form.add_error(None, "Utilisateur introuvable.")
                return self.form_invalid(form)

        backend = session.get(SESSION_BACKEND_KEY, settings.AUTHENTICATION_BACKENDS[0])
        pending_invite_id = session.get(SESSION_PENDING_INVITE_ID)

        organisation_profile_data = None
        if SESSION_PENDING_USER_DATA in session:
            pending = session.pop(SESSION_PENDING_USER_DATA)
            username = pending.get("username") or pending.get("email")
            role = pending.get("role", User.Role.STUDENT)
            organisation_name = (pending.get("organisation_name") or "").strip()
            country_code = (pending.get("country_code") or "").strip().upper() or "FR"
            organisation_profile_data = pending.get("organisation_profile")

            create_kwargs = {
                "username": username,
                "email": pending["email"],
                "password": pending["password"],
                "role": role,
            }
            if role in {User.Role.COMPANY, User.Role.INSTITUTION} and organisation_name:
                create_kwargs["first_name"] = organisation_name[:150]
            user = User.objects.create(**create_kwargs)
            user.first_name = pending.get("first_name") or user.first_name
            user.last_name = pending.get("last_name") or user.last_name
            if pending_invite_id:
                user.is_verified = True
            user.save(update_fields=["first_name", "last_name", "is_verified"])
            session[SESSION_USER_KEY] = str(user.id)

        elif not user:
            self._clear_session()
            form.add_error(None, "Session invalide, merci de recommencer.")
            return self.form_invalid(form)

        if user.role == User.Role.STUDENT:
            invitation_obj = None
            if pending_invite_id:
                invitation_obj = StudentInvitation.objects.filter(id=pending_invite_id).first()
                if invitation_obj:
                    invitation_obj.mark_used()
            _create_student_profile(user, invitation_obj)
        elif user.role == User.Role.COMPANY:
            _create_company_profile(user, organisation_profile_data)
        elif user.role == User.Role.INSTITUTION:
            _create_institution_profile(user, organisation_profile_data)

        login(self.request, user, backend=backend)
        self._clear_session()
        return super().form_valid(form)

    def _clear_session(self):
        session = self.request.session
        pending = session.get(SESSION_PENDING_USER_DATA) or {}
        logo_path = (pending.get("organisation_profile") or {}).get("logo_path")
        if logo_path and default_storage.exists(logo_path):
            default_storage.delete(logo_path)
        for key in (
            SESSION_USER_KEY,
            SESSION_CODE_KEY,
            SESSION_EXPIRY_KEY,
            SESSION_BACKEND_KEY,
            SESSION_PENDING_USER_DATA,
            SESSION_PENDING_INVITE_ID,
            SESSION_EMAIL_KEY,
            SESSION_SUBJECT_KEY,
            SESSION_TEMPLATE_KEY,
        ):
            session.pop(key, None)

    def _resend_code(self):
        email = self._get_target_email()
        if not email:
            messages.error(self.request, "Impossible d'envoyer un nouveau code pour le moment.")
            return
        session = self.request.session
        subject = session.get(SESSION_SUBJECT_KEY) or "Code de vérification"
        template = session.get(SESSION_TEMPLATE_KEY) or "Ton code de connexion est : {code}"
        _send_two_factor_code(session, email, subject, template)
        messages.success(self.request, "Un nouveau code vient de t'être envoyé.")

    def _get_target_email(self):
        session = self.request.session
        email = session.get(SESSION_EMAIL_KEY)
        if email:
            return email
        pending = session.get(SESSION_PENDING_USER_DATA) or {}
        pending_email = pending.get("email")
        if pending_email:
            return pending_email
        user_id = session.get(SESSION_USER_KEY)
        if user_id:
            return User.objects.filter(pk=user_id).values_list("email", flat=True).first()
        return None


class PasswordResetRequestView(FormView):
    template_name = "accounts/password_reset_request.html"
    form_class = PasswordResetRequestForm
    success_url = reverse_lazy("accounts:password_reset_confirm")

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        self.request.session[SESSION_RESET_EMAIL] = email
        _send_two_factor_code(
            self.request.session,
            email,
            subject="Code de réinitialisation",
            message_template="Ton code de réinitialisation est : {code}",
        )
        return super().form_valid(form)


class PasswordResetConfirmView(FormView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = PasswordResetConfirmForm
    success_url = reverse_lazy("accounts:login")

    def dispatch(self, request, *args, **kwargs):
        if SESSION_RESET_EMAIL not in request.session:
            return redirect("accounts:password_reset_request")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["email"] = self.request.session.get(SESSION_RESET_EMAIL, "")
        return context

    def form_valid(self, form):
        session = self.request.session
        code = session.get(SESSION_CODE_KEY)
        expiry_raw = session.get(SESSION_EXPIRY_KEY)

        if not code or not expiry_raw:
            form.add_error(None, "Code expiré, recommence la procédure.")
            return self.form_invalid(form)

        expiry = timezone.datetime.fromisoformat(expiry_raw)
        if timezone.now() > expiry:
            self._clear_session()
            form.add_error(None, "Code expiré, recommence la procédure.")
            return self.form_invalid(form)

        if form.cleaned_data["code"] != code:
            form.add_error("code", "Code invalide.")
            return self.form_invalid(form)

        email = session.get(SESSION_RESET_EMAIL)
        try:
            user = User.objects.get(email__iexact=email)
            user.set_password(form.cleaned_data["password1"])
            user.save()
            messages.success(self.request, "Mot de passe modifié avec succès.")
        except User.DoesNotExist:
            form.add_error(None, "Utilisateur introuvable.")
            return self.form_invalid(form)

        self._clear_session()
        return super().form_valid(form)

    def _clear_session(self):
        for key in (SESSION_RESET_EMAIL, SESSION_CODE_KEY, SESSION_EXPIRY_KEY, SESSION_EMAIL_KEY):
            self.request.session.pop(key, None)