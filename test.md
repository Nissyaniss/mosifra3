# Test Suite Explanation

This document explains the purpose and utility of the new tests added to the project.

## 1. Invitations Tests (`tests/test_invitations.py`)

These tests focus on the stability of the CSV parsing logic, which was identified as complex and prone to errors (encoding issues, delimiter confusion).

- **`test_detect_encoding_utf8` / `test_detect_encoding_latin1`**:
  - **Why:** Excel and legacy systems often export in different encodings (UTF-8, Latin-1, CP1252). If we don't detect this correctly, names like "Hélène" become "HÃ©lÃ¨ne" or crash the parser. These tests ensure the detection logic works for both standard and legacy cases.

- **`test_detect_delimiter_comma` / `test_detect_delimiter_semicolon`**:
  - **Why:** CSVs are not standard. US/UK use commas (`,`), while France/Europe often use semicolons (`;`) because the comma is a decimal separator. This logic ensures the app "sniffs" the right delimiter automatically so users don't have to choose manually.

- **`test_parse_csv_rows_standard`**:
  - **Why:** Ensures the basic "happy path" works: a valid CSV file produces the expected list of data.

- **`test_parse_csv_rows_bom`**:
  - **Why:** Some tools add a specialized invisible character (Byte Order Mark) at the start of a file. If not stripped, the first column header `email` becomes `\ufeffemail`, causing field mapping errors. This test ensures we clean it up.

- **`test_cleanup_rows_nested`**:
  - **Why:** Sometimes the delimiter sniffing fails or the file is quoted strangely, causing a whole line `user,email` to end up in one cell `["user,email"]` instead of two `["user", "email"]`. The cleanup logic attempts to rescue this; this test verifies that rescue mechanism.

- **`test_preview_csv_post_required` / `test_download_csv_model_get_required`**:
  - **Why:** Security regression testing. We explicitly restricted these views to specific HTTP methods. These tests ensure that those restrictions are active and that future developers don't accidentally remove the decorators.

## 2. Profiles Tests (`tests/test_profiles.py`)

These tests ensure the Admin interface works correctly after our refactoring to remove code duplication.

- **`test_admin_validation_context_merging`**:
  - **Why:** We refactored the code to treat Companies and Institutions generically. This test proves that both types still appear correctly in the list, ensuring the refactoring didn't accidentally drop one type of user.

- **`test_tab_*_get_only` (dashboard, account, offers, students)**:
  - **Why:** These views are read-only partials for the UI. Ensuring they only accept GET requests prevents them from being used as vectors for state-changing attacks and enforces correct usage.

- **`test_admin_validation_view_access`**:
  - **Why:** Critical security test. Ensures that a regular user (or unauthenticated user) cannot access the admin validation page.

## 3. Accounts Tests (`tests/test_accounts.py`)

These tests focus on the Critical Security Control of authentication.

- **`test_send_two_factor_code_uses_secrets`**:
  - **Why:** We moved from `random` to `secrets` for security. This test *mocks* the secrets module to ensure that our code is actually calling the secure generator and not silently falling back to the insecure one.

- **`test_send_two_factor_code_structure`**:
  - **Why:** Reliability. We expect a 6-digit code (e.g., "012345"). If we broke the formatting (e.g., getting "12345"), users would be confused. This test guards the format.

- **`test_login_view_sends_code`**:
  - **Why:** Integration test. It verifies the critical user flow: Login -> 2FA sent -> Redirect to input code. If this breaks, no one can log in.
