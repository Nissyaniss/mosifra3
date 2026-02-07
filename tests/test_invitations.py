from django.test import SimpleTestCase, RequestFactory
from django.core.files.uploadedfile import SimpleUploadedFile
from invitations.views import _detect_encoding, _detect_delimiter, _parse_csv_rows, _cleanup_rows, preview_csv, download_csv_model

class InvitationsUtilsTest(SimpleTestCase):
    def test_detect_encoding_utf8(self):
        """Verify that standard UTF-8 content is correctly identified."""
        data = "prénom,nom".encode("utf-8")
        self.assertEqual(_detect_encoding(data), "prénom,nom")

    def test_detect_encoding_latin1(self):
        """Verify that legacy Latin-1 content is correctly decoded."""
        data = b"pr\xe9nom,nom"
        self.assertEqual(_detect_encoding(data), "prénom,nom")

    def test_detect_delimiter_comma(self):
        """Verify comma detection for standard CSVs."""
        text = "email,first_name,last_name"
        self.assertEqual(_detect_delimiter(text), ",")

    def test_detect_delimiter_semicolon(self):
        """Verify semicolon detection (common in Excel/French CSVs)."""
        text = "email;first_name;last_name"
        self.assertEqual(_detect_delimiter(text), ";")

    def test_parse_csv_rows_standard(self):
        """Verify basic parsing of valid CSV text."""
        text = "email,nom\ntest@test.com,Doe"
        rows = _parse_csv_rows(text, ",")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1], ["test@test.com", "Doe"])

    def test_parse_csv_rows_bom(self):
        """Verify that BOM characters form Excel are stripped from the first cell."""
        text = "\ufeffemail,nom"
        rows = _parse_csv_rows(text, ",")
        self.assertEqual(rows[0][0], "email")

    def test_cleanup_rows_nested(self):
        """Verify fix for rows incorrectly identified as single cells containing delimiters."""
        bad_rows = [["\"email,nom\""], ["\"test@test.com,Doe\""]]
        cleaned = _cleanup_rows(bad_rows, ",")
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(cleaned[0], ["email", "nom"])

class InvitationsViewsTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_preview_csv_post_required(self):
        """Verify that GET requests to preview_csv are rejected."""
        request = self.factory.get("/invitations/preview/")
        response = preview_csv(request)
        self.assertEqual(response.status_code, 405)

    def test_download_csv_model_get_required(self):
        """Verify that POST requests to download model are rejected."""
        request = self.factory.post("/invitations/download/")
        response = download_csv_model(request)
        self.assertEqual(response.status_code, 405)

    def test_preview_csv_success(self):
        """Verify the success path for a valid CSV upload."""
        content = b"email,nom\ntest@example.com,Test"
        csv_file = SimpleUploadedFile("test.csv", content)
        request = self.factory.post("/invitations/preview/", {"csv_file": csv_file})
        response = preview_csv(request)
        self.assertEqual(response.status_code, 200)
