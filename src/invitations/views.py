import csv
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import FormView

from accounts.forms import InvitationUploadForm
from accounts.models import StudentInvitation, User


def _send_invitation_email(request, invitation):
    link = request.build_absolute_uri(
        reverse("accounts:invitation_accept", args=[invitation.token])
    )
    subject = "Invitation Mosifra"
    message = (
        f"Bonjour {invitation.first_name},\n\n"
        f"Ton établissement t'invite à rejoindre Mosifra.\n"
        f"Profil : {invitation.filiere} / {invitation.level} / {invitation.academic_year}\n\n"
        f"Clique sur ce lien pour créer ton compte (valide jusqu'au {invitation.expires_at:%d/%m/%Y}) :\n{link}\n"
    )
    send_mail(
        subject,
        message,
        getattr(settings, "DEFAULT_FROM_EMAIL", None),
        [invitation.email],
        fail_silently=True,
    )


class InvitationUploadView(LoginRequiredMixin, FormView):
    template_name = "invitations/invitations_upload.html"
    form_class = InvitationUploadForm
    success_url = reverse_lazy("invitations:upload")
    report = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role != User.Role.INSTITUTION:
            raise Http404("Réservé aux établissements.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        rows = form.read_rows()
        self.report = self._process_rows(rows)
        return self.render_to_response(self.get_context_data(form=self.form_class()))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["report"] = self.report
        user = self.request.user
        logo_url = None
        if hasattr(user, "institution_profile") and user.institution_profile.logo:
            logo_url = user.institution_profile.logo.url
        context["logo_url"] = logo_url
        return context

    def _process_rows(self, rows):
        report = {"sent": 0, "failed": 0, "errors": []}
        now = timezone.now()
        for idx, row in enumerate(rows, start=2):
            email = (row.get("email") or "").strip().lower()
            try:
                validate_email(email)
            except Exception:
                report["failed"] += 1
                report["errors"].append(f"Ligne {idx}: email invalide ({email}).")
                continue
            if User.objects.filter(email__iexact=email).exists():
                report["failed"] += 1
                report["errors"].append(f"Ligne {idx}: email déjà utilisé ({email}).")
                continue

            first_name = (row.get("prenom") or "").strip().title()
            last_name = (row.get("nom") or "").strip().upper()
            filiere = (row.get("filiere_ou_parcours") or "").strip()
            level = (row.get("niveau") or "").strip()
            academic_year = (row.get("annee_academique") or "").strip()

            token = uuid.uuid4().hex
            invitation = StudentInvitation.objects.create(
                institution=self.request.user,
                email=email,
                first_name=first_name or "Étudiant",
                last_name=last_name or "",
                filiere=filiere or "N/A",
                level=level or "N/A",
                academic_year=academic_year or "N/A",
                token=token,
                expires_at=now + timedelta(days=7),
            )
            try:
                _send_invitation_email(self.request, invitation)
                invitation.mark_sent()
                report["sent"] += 1
            except Exception:
                invitation.mark_failed("Erreur d'envoi")
                report["failed"] += 1
                report["errors"].append(f"Ligne {idx}: envoi impossible pour {email}.")
        return report


@require_GET
def download_csv_model(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="modele_etudiants.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow([
        "email",
        "prenom",
        "nom",
        "filiere_ou_parcours",
        "niveau",
        "annee_academique"
    ])
    rows = [
        ["lilian.olliver@gmail.com", "Lilian", "Olliver", "BUT Informatique", "BUT2", "2025-2026"],
        ["alexielajoigne@etu.unilim.fr", "Alexie", "Lajoigne", "Ingénierie Mécanique", "Master 1", "2025-2026"],
        ["shaune.cepin@orange.fr", "Shaune", "Cepin", "Licence Économie", "L3", "2025-2026"],
        ["dixmille.paule@etu.unilim.fr", "Paule", "Dixmillé", "Business Management", "Parcours International", "2025-2026"],
    ]
    writer.writerows(rows)
    return response


@require_POST
def preview_csv(request):
    if request.FILES.get("csv_file"):
        file = request.FILES["csv_file"]
        raw_data = file.read(4096)
        file.seek(0)

        text = _detect_encoding(raw_data)
        if not text:
             return render(request, "invitations/partials/csv_preview.html", {"rows": []})

        delimiter = _detect_delimiter(text)
        rows = _parse_csv_rows(text, delimiter)
        rows = _cleanup_rows(rows, delimiter)

        return render(request, "invitations/partials/csv_preview.html", {"rows": rows})

    return HttpResponse("")


def _detect_encoding(raw_data):
    try:
        return raw_data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw_data.decode("cp1252")
            if "\u201a" in text or "\u2026" in text or "\u2021" in text:
                return raw_data.decode("cp850")
            return text
        except UnicodeDecodeError:
            return raw_data.decode("latin-1", errors="replace")


def _detect_delimiter(text):
    first_line = text.splitlines()[0] if text else ""
    delimiter = ","
    if first_line:
        semi = first_line.count(";")
        comma = first_line.count(",")
        tab = first_line.count("\t")
        if semi > comma and semi > tab:
            delimiter = ";"
        elif tab > comma and tab > semi:
            delimiter = "\t"
    return delimiter


def _parse_csv_rows(text, delimiter):
    rows = []
    if text:
        lines = text.splitlines()
        reader = csv.reader(lines, delimiter=delimiter)
        try:
            for i, row in enumerate(reader):
                if i >= 6:
                    break
                if row:
                    if i == 0 and row and row[0].startswith("\ufeff"):
                        row[0] = row[0].replace("\ufeff", "")
                    rows.append(row)
        except csv.Error:
            pass
    return rows


def _cleanup_rows(rows, delimiter):
    # Handle case where delimiter sniffer failed and everything is in one cell
    if rows and len(rows[0]) == 1:
        first_cell = rows[0][0]
        if delimiter in first_cell:
            new_rows = []
            for row in rows:
                if len(row) == 1:
                    content = row[0]
                    if content.startswith('"') and content.endswith('"'):
                        content = content[1:-1]
                    sub_reader = csv.reader([content], delimiter=delimiter)
                    try:
                        new_row = next(sub_reader)
                        new_rows.append(new_row)
                    except StopIteration:
                        new_rows.append(row)
                else:
                    new_rows.append(row)
            return new_rows
    return rows
