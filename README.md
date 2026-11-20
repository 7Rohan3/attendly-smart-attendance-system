# Attendly — Smart Attendance System

Attendly is a local Flask prototype for administrator-managed student enrollment, face recognition check-in, attendance reporting, and controlled recognition evaluation. It uses the existing OpenCV/face_recognition pipeline and SQLite data store.

## Features

- Admin login with Werkzeug password hashing, signed Flask sessions, HTTP-only/SameSite cookies, and CSRF tokens on state-changing requests.
- Student enrollment by webcam or image upload, one-face validation, unique IDs, optional email/department, roster search, edit API, and soft deactivation that retains attendance history.
- Browser camera selection/switching and face matching with a configurable distance threshold. Distance is not displayed as a probability. Unknown faces and uncertain matches are rejected.
- Daily attendance uniqueness enforced by SQLite; dashboard values and attendance trends are calculated from the database.
- Search, date range, and department filters with CSV export using the same filters.
- Research Evaluation records actual trial observations and exports them. No sample measurements are inserted.

## Requirements and installation (Windows 11, Python 3.10)

The Dlib dependency may require a compatible prebuilt wheel or native build tools on Windows. Use a Python 3.10 environment.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configure and run

Set credentials and a persistent random session secret in PowerShell before startup. No default administrator password is configured.

```powershell
$env:ADMIN_USERNAME = "your-admin-name"
$env:ADMIN_PASSWORD = "a-long-unique-password"
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
# Optional: $env:ATTENDANCE_DATABASE = "C:\AttendlyData\attendance.db"
# Optional: $env:FACE_MATCH_THRESHOLD = "0.48"
python app.py
```

Open http://127.0.0.1:5000 and sign in using the configured credentials. Keep `SECRET_KEY` stable across restarts. Set `COOKIE_SECURE=1` only when served over HTTPS. The built-in Flask server is for local demonstration; use a production WSGI server and HTTPS for network use.

The default database path is `attendance.db` beside `app.py`. Startup performs additive SQLite migrations and retains existing student and attendance rows. Back up that file before upgrades. A student deactivation removes the identity from future recognition while preserving history.

## Use

1. Sign in as administrator and register each student with a unique ID, optional contact/department details, and a clear one-face image. The original image is processed in memory and discarded.
2. Open **Take attendance**, grant browser camera permission, select a camera if needed, and capture. Only a sufficiently close known identity is recorded, at most once per local calendar day.
3. Search and filter **Records** by student, dates, and department, then export the filtered rows.
4. Use **Research Evaluation** to record controlled, consented trials and measured processing times. Export raw observations as CSV.

Camera access works on localhost or HTTPS. Browser device selection appears when multiple cameras are available. The app does not implement liveness detection; printed photos and replay attacks are not reliably prevented.

## Research protocol and limitations

Each saved trial is a single observation. Current identification metrics treat known expected identities as positive trials: correct identity = TP, rejection or wrong known identity = FN. Unknown-person rejection = TN and any accepted identity = FP. Accuracy uses all recorded trials; precision denominator is TP+FP; recall denominator is TP+FN; FAR denominator is FP+TN; FRR denominator is FN+TP. Undefined zero-denominator ratios display as unavailable. Record sufficiently large, balanced trial groups and report environmental condition breakdowns separately; do not present small convenience samples as general accuracy. Verification trials must use a separately designed genuine/impostor protocol and must not be interpreted with identification denominators.

The prototype stores face encodings as SQLite BLOBs. Restrict OS access to the database and backups, obtain informed consent, and delete/deactivate records according to institutional policy. Embeddings remain sensitive biometric data; the prototype does not provide cryptographic field-level encryption, multi-admin roles, liveness detection, or a student self-service consent/deletion workflow. It is not a production biometric security system.

## Tests

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

The automated suite mocks the heavy face embedding operation for route tests and contains a real no-face pipeline check. Webcam/device behavior and recognition performance require manual verification using consented subjects and the target hardware.

## Configuration

| Variable | Purpose |
|---|---|
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | Required administrator credentials; password is hashed for comparison at runtime. |
| `SECRET_KEY` | Persistent Flask session signing secret. |
| `ATTENDANCE_DATABASE` | Optional SQLite file location. |
| `FACE_MATCH_THRESHOLD` | Maximum face distance accepted (default `0.48`; smaller is stricter). |
| `PORT` | Local port (default `5000`). |
| `COOKIE_SECURE` | Set to `1` when served via HTTPS. |
