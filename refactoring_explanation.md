# Security Refactoring Report

This document outlines five security-focused refactorings performed on the Mosifra codebase. These changes were guided by SonarQube recommendations to improve the application's security posture.

## 1. Secure Random Number Generation
**File:** `src/accounts/views.py`

**Change:** Replaced the standard `random` module with the `secrets` module for generating 2FA (Two-Factor Authentication) codes.

**Why:**
The Python `random` module uses a Mersenne Twister algorithm which is not verifying cryptographically secure. This means a sophisticated attacker could potentially predict future values if they observe enough past values. For sensitive data like authentication codes, we must use `secrets` (which typically uses the OS's randomness source) to ensure the codes are truly unpredictable.

## 2. Preventing Cross-Site Scripting (XSS) in Offer Details
**File:** `src/offers/templates/offers/offer_detail.html`

**Change:** Removed the `|safe` filter from the `offer.description` and `company.description` fields.

**Why:**
The `|safe` filter tells Django *not* to escape HTML characters. This allows anyone who can edit an offer description to insert malicious JavaScript tags (Cross-Site Scripting). If an attacker posted an offer with `<script>alert('hacked')</script>`, it would execute in the browser of anyone viewing the offer. By removing `|safe`, Django automatically escapes special characters (converting `<` to `&lt;`), rendering the script harmless as plain text.

## 3. Preventing XSS in Private Offer Details
**File:** `src/offers/templates/offers/offer_detail_private.html`

**Change:** Removed the `|safe` filter from the `offer.description` and `company.description` fields (same as above).

**Why:**
This view is used for the private preview of the offer. Even if this page is only accessible to the author, removing `|safe` is a best practice. It prevents "Self-XSS" and ensures consistency across the application. It also protects against scenarios where an attacker might trick a user into previewing malicious content they didn't create.

## 4. Restricting HTTP Methods for CSV Operations
**File:** `src/invitations/views.py`

**Change:** Added explicit decorators `@require_GET` to `download_csv_model` and `@require_POST` to `preview_csv`.

**Why:**
Web views should strictly enforce the HTTP methods they support.
- `download_csv_model` is a read-only operation that delivers a file, so it should only accept `GET` requests.
- `preview_csv` is a state-changing operation (processing a file upload), so it should only accept `POST` requests.
Enforcing this prevents potential misuse (like CSRF attacks that might try to trigger actions via a simple image tag GET request) and clearly signals the intended use of the endpoint.

## 5. Restricting HTTP Methods for Profile Tabs
**File:** `src/profiles/views.py`

**Change:** Added `@require_GET` to the tab rendering functions (`tab_dashboard`, `tab_account`, etc.).

**Why:**
These views are responsible for fetching valid HTML fragments to update the UI (likely via HTMX or AJAX). They do not modify data on the server. Restricting them to `GET` requests ensures they are idempotent and safe. It also mitigates the risk of these views being inadvertently used as targets for modification attacks.

## 6. Reducing Code Duplication in Admin Validation
**File:** `src/profiles/views.py`

**Change:** Refactored `AdminValidationView` to iterate over different profile types generically instead of duplicating the loop for companies and institutions.

**Why:**
This adheres to the DRY (Don't Repeat Yourself) principle. It reduces the risk of bugs where a change might be applied to one loop but forgotten in the other. It also makes the code more concise and easier to maintain.

## 7. Reducing Cognitive Complexity in CSV Preview
**File:** `src/invitations/views.py`

**Change:** Extracted logic from `preview_csv` into helper functions: `_detect_encoding`, `_detect_delimiter`, `_parse_csv_rows`, and `_cleanup_rows`.

**Why:**
The original function was doing too many things at once (reading, decoding, parsing, cleaning). This high "cognitive complexity" makes the code hard to read and test. Breaking it down makes each step clear, isolated, and potentially reusable/testable in the future.
