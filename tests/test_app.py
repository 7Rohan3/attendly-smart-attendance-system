import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from app import _research_metrics, create_app
from face_recognition_utils import FaceImageError, encode_face


class AttendanceAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database = str(Path(self.temp_dir.name) / "test.db")
        self.app = create_app({"TESTING": True, "DATABASE": database, "SECRET_KEY": "test"})
        self.client = self.app.test_client()
        image = Image.new("RGB", (32, 32), "white")
        buffer = tempfile.SpooledTemporaryFile()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        self.image = "data:image/png;base64," + base64.b64encode(buffer.read()).decode("ascii")
        buffer.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def register_student(self, student_id="STU-1", full_name="Alex Morgan"):
        with patch("app.encode_face", return_value=np.zeros(128, dtype=np.float64)):
            return self.client.post(
                "/api/students",
                json={"student_id": student_id, "full_name": full_name, "image": self.image},
            )

    def test_pages_render(self):
        for path in ("/", "/register", "/attendance", "/records", "/research"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_registration_and_duplicate_student_id(self):
        response = self.register_student()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["message"], "Alex Morgan was registered successfully.")
        duplicate = self.register_student()
        self.assertEqual(duplicate.status_code, 409)

    def test_rejects_registration_without_face_image(self):
        response = self.client.post(
            "/api/students",
            json={"student_id": "STU-2", "full_name": "Taylor", "image": "not-an-image"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("invalid", response.json["error"].lower())

    def test_attendance_requires_enrolled_students(self):
        response = self.client.post("/api/attendance", json={"image": self.image})
        self.assertEqual(response.status_code, 400)
        self.assertIn("No students are registered", response.json["error"])

    def test_face_pipeline_rejects_image_without_a_face(self):
        with self.assertRaisesRegex(FaceImageError, "No face was found"):
            encode_face(np.full((100, 100, 3), 255, dtype=np.uint8))

    def test_attendance_is_unique_per_student_per_day(self):
        self.register_student()
        with patch("app.encode_face", return_value=np.zeros(128, dtype=np.float64)), patch(
            "app.find_match", return_value=("STU-1", "Alex Morgan")
        ):
            first = self.client.post("/api/attendance", json={"image": self.image})
            duplicate = self.client.post("/api/attendance", json={"image": self.image})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json["student"]["student_id"], "STU-1")
        self.assertEqual(duplicate.status_code, 409)


    def test_date_filters_and_export_filters(self):
        self.register_student()
        from datetime import datetime, timedelta
        from database import add_attendance
        from pathlib import Path
        database = self.app.config["DATABASE"]
        add_attendance(database, "STU-1", datetime.now() - timedelta(days=2))
        add_attendance(database, "STU-1", datetime.now() - timedelta(days=1))
        start = (datetime.now() - timedelta(days=1)).date().isoformat()
        response = self.client.get(f"/records?start_date={start}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(start.encode(), response.data)
        export = self.client.get(f"/records/export.csv?start_date={start}")
        self.assertEqual(export.status_code, 200)
        self.assertIn(start.encode(), export.data)

    def test_records_search_and_csv_export(self):
        self.register_student()
        with patch("app.encode_face", return_value=np.zeros(128, dtype=np.float64)), patch(
            "app.find_match", return_value=("STU-1", "Alex Morgan")
        ):
            self.client.post("/api/attendance", json={"image": self.image})

        results = self.client.get("/records?q=Alex")
        self.assertEqual(results.status_code, 200)
        self.assertIn(b"Alex Morgan", results.data)
        self.assertNotIn(b"STU-2", results.data)
        export = self.client.get("/records/export.csv?q=STU-1")
        self.assertEqual(export.status_code, 200)
        self.assertIn(b"Student ID,Name,Department,Date,Time,Status", export.data)
        self.assertIn(b"STU-1,Alex Morgan", export.data)


if __name__ == "__main__":
    unittest.main()


class AdminAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": False,
            "DATABASE": str(Path(self.temp_dir.name) / "auth.db"),
            "SECRET_KEY": "test-secret",
            "ADMIN_USERNAME": "research-admin",
            "ADMIN_PASSWORD": "test-password-123",
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dashboard_requires_login(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_admin_can_login_and_logout(self):
        response = self.client.post("/login", data={
            "username": "research-admin", "password": "test-password-123"
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)
        with self.client.session_transaction() as session:
            csrf = session["csrf_token"]
        logout = self.client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)
        self.assertEqual(logout.status_code, 302)
        self.assertIn("/login", self.client.get("/", follow_redirects=False).headers["Location"])

    def test_invalid_credentials_are_rejected(self):
        response = self.client.post("/login", data={"username": "admin", "password": "wrong"})
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Incorrect username or password", response.data)

    def test_state_changing_route_requires_csrf_token(self):
        self.client.post("/login", data={"username":"research-admin","password":"test-password-123"})
        response = self.client.post("/api/research/trials", json={"condition":"normal","result":"rejected","processing_ms":10})
        self.assertEqual(response.status_code, 400)


class ResearchMetricTests(unittest.TestCase):
    def test_identification_metrics_use_known_and_unknown_denominators(self):
        metrics = _research_metrics([
            {"expected_identity":"A","predicted_identity":"A","processing_ms":12},
            {"expected_identity":"B","predicted_identity":"","processing_ms":16},
            {"expected_identity":"","predicted_identity":"","processing_ms":8},
            {"expected_identity":"","predicted_identity":"A","processing_ms":14},
        ])
        self.assertEqual((metrics["tp"], metrics["tn"], metrics["fp"], metrics["fn"]), (1,1,1,1))
        self.assertEqual(metrics["accuracy"], .5)
        self.assertEqual(metrics["precision"], .5)
        self.assertEqual(metrics["recall"], .5)
        self.assertEqual(metrics["f1"], .5)
        self.assertEqual(metrics["far"], .5)
        self.assertEqual(metrics["frr"], .5)
        self.assertEqual(metrics["average_ms"], 12.5)
