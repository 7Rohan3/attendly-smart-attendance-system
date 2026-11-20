import csv
import io
import os
import secrets
import hmac
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import (add_attendance, add_student, add_trial, deactivate_student, get_attendance,
                      get_dashboard_data, get_student_encodings, get_students, get_trials,
                      init_database, student_exists, update_student)
from face_recognition_utils import FaceImageError, decode_face_image, encode_face, find_match, find_match_with_distance


def _research_metrics(rows):
    # Identification protocol: known trials count as TP only for the expected identity,
    # wrong/rejected known identity is FN; unknown accepted identity is FP, rejected is TN.
    known = [r for r in rows if r["expected_identity"]]
    unknown = [r for r in rows if not r["expected_identity"]]
    tp = sum(r["predicted_identity"] == r["expected_identity"] for r in known)
    fn = len(known) - tp
    fp = sum(bool(r["predicted_identity"]) for r in unknown)
    tn = len(unknown) - fp
    div = lambda a, b: round(a / b, 4) if b else None
    times = [float(r["processing_ms"]) for r in rows]
    return {"tp":tp,"tn":tn,"fp":fp,"fn":fn,"trials":len(rows),"accuracy":div(tp+tn,len(rows)),
            "precision":div(tp,tp+fp),"recall":div(tp,tp+fn),
            "f1":div(2*div(tp,tp+fp)*div(tp,tp+fn),div(tp,tp+fp)+div(tp,tp+fn)) if div(tp,tp+fp) is not None and div(tp,tp+fn) is not None and div(tp,tp+fp)+div(tp,tp+fn) else None,
            "far":div(fp,fp+tn),"frr":div(fn,fn+tp),
            "average_ms":round(sum(times)/len(times),2) if times else None,
            "minimum_ms":min(times) if times else None,"maximum_ms":max(times) if times else None}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.environ.get("DATABASE_URL") or os.environ.get("ATTENDANCE_DATABASE",str(Path(app.root_path)/"attendance.db")),
        MAX_CONTENT_LENGTH=5*1024*1024, FACE_MATCH_THRESHOLD=float(os.environ.get("FACE_MATCH_THRESHOLD","0.48")),
        ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME"), ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD"),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE","0")=="1")
    if test_config: app.config.update(test_config)
    init_database(app.config["DATABASE"])
    password = app.config.get("ADMIN_PASSWORD") or ""
    app.config["ADMIN_PASSWORD_HASH"] = generate_password_hash(password) if password else None

    @app.before_request
    def security():
        if app.config.get("TESTING") or app.config.get("AUTH_DISABLED"): return None
        if request.endpoint not in {"login", "login_submit", "static"} and not session.get("admin_authenticated"):
            return redirect(url_for("login", next=request.full_path if request.query_string else request.path))
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.endpoint != "login_submit":
            token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not token or not hmac.compare_digest(token, session.get("csrf_token", "")):
                if request.path.startswith("/api/"): return jsonify(error="Your session token expired. Refresh the page and try again."), 400
                return "Invalid or expired form token. Refresh the page and try again.", 400

    @app.context_processor
    def context():
        return {"now": datetime.now, "csrf_token": _csrf_token}

    def admin_template(token):
        if "csrf_token" not in session: session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    def _csrf_token(): return admin_template(None)

    @app.get("/login")
    def login(): return render_template("login.html", error=None)

    @app.post("/login")
    def login_submit():
        username=request.form.get("username","").strip(); supplied=request.form.get("password","")
        expected=app.config.get("ADMIN_PASSWORD_HASH")
        ok=bool(expected and app.config.get("ADMIN_USERNAME") and hmac.compare_digest(username,app.config["ADMIN_USERNAME"]) and check_password_hash(expected,supplied))
        if ok:
            session.clear(); session["admin_authenticated"]=True; session["admin_username"]=username; session["csrf_token"]=secrets.token_urlsafe(32)
            destination=request.args.get("next","")
            if not destination.startswith("/") or destination.startswith("//"): destination=url_for("index")
            return redirect(destination)
        reason="Admin credentials are not configured. Set ADMIN_USERNAME and ADMIN_PASSWORD, then restart." if not expected else "Incorrect username or password."
        return render_template("login.html",error=reason),401

    @app.post("/logout")
    def logout(): session.clear(); return redirect(url_for("login"))

    @app.get("/")
    def index(): return render_template("index.html", **get_dashboard_data(app.config["DATABASE"]))

    @app.get("/register")
    def register_page(): return render_template("register.html", students=get_students(app.config["DATABASE"],request.args.get("q","")), query=request.args.get("q",""))

    @app.get("/attendance")
    def attendance_page(): return render_template("attendance.html")

    @app.get("/records")
    def records_page():
        filters={k:request.args.get(k,"").strip() for k in ("q","start_date","end_date","department","status")}
        records=get_attendance(app.config["DATABASE"],query=filters["q"],start_date=filters["start_date"],end_date=filters["end_date"],department=filters["department"],status=filters["status"])
        return render_template("records.html",records=records,**filters)

    @app.get("/records/export.csv")
    def export_records():
        filters={k:request.args.get(k,"").strip() for k in ("q","start_date","end_date","department","status")}
        output=io.StringIO(); writer=csv.writer(output); writer.writerow(("Student ID","Name","Department","Date","Time","Status"))
        for r in get_attendance(app.config["DATABASE"],query=filters["q"],start_date=filters["start_date"],end_date=filters["end_date"],department=filters["department"],status=filters["status"]): writer.writerow((r["student_id"],r["full_name"],r["department"],r["date"],r["time"],r["status"]))
        return Response(output.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=attendance-records.csv"})

    @app.post("/api/students")
    def register_student():
        p=request.get_json(silent=True)
        if not isinstance(p,dict): return jsonify(error="Send registration as JSON."),400
        sid=str(p.get("student_id","")).strip(); name=str(p.get("full_name","")).strip(); email=str(p.get("email","")).strip(); dept=str(p.get("department","")).strip()
        if not sid or len(sid)>64 or not name or len(name)>120 or len(email)>254 or len(dept)>120: return jsonify(error="Check required fields and their lengths."),400
        if student_exists(app.config["DATABASE"],sid): return jsonify(error="That student ID is already registered."),409
        try: encoding=encode_face(decode_face_image(p.get("image")))
        except FaceImageError as e: return jsonify(error=str(e)),400
        try: add_student(app.config["DATABASE"],sid,name,encoding,email,dept)
        except ValueError: return jsonify(error="That student ID is already registered."),409
        return jsonify(message=f"{name} was registered successfully."),201

    @app.post("/api/students/<student_id>/edit")
    def edit_student(student_id):
        p=request.get_json(silent=True) or {}
        name=str(p.get("full_name","")).strip(); email=str(p.get("email","")).strip(); dept=str(p.get("department","")).strip()
        if not name or len(name)>120 or len(email)>254 or len(dept)>120: return jsonify(error="Check the student details."),400
        if not update_student(app.config["DATABASE"],student_id,name,email,dept): return jsonify(error="Student not found."),404
        return jsonify(message="Student details updated.")

    @app.post("/api/students/<student_id>/deactivate")
    def remove_student(student_id):
        if not deactivate_student(app.config["DATABASE"],student_id): return jsonify(error="Student not found."),404
        return jsonify(message="Student deactivated. Attendance history has been retained.")

    @app.post("/api/attendance")
    def mark_attendance():
        p=request.get_json(silent=True)
        if not isinstance(p,dict): return jsonify(error="Send captured image as JSON."),400
        students=get_student_encodings(app.config["DATABASE"])
        if not students: return jsonify(error="No students are registered yet. Register a student first."),400
        try: encoding=encode_face(decode_face_image(p.get("image")))
        except FaceImageError as e: return jsonify(error=str(e)),400
        match=find_match_with_distance(encoding,students,threshold=app.config["FACE_MATCH_THRESHOLD"])
        if match is None: return jsonify(error="No registered student matched that face. Try again in good lighting."),404
        sid,name,distance=match
        try: record=add_attendance(app.config["DATABASE"],sid)
        except ValueError: return jsonify(error="That student's attendance has already been recorded today."),409
        return jsonify(message=f"Attendance marked for {name}.",student={"student_id":sid,"full_name":name},date=record["date"],time=record["time"],distance=round(distance,4)),201

    @app.get("/research")
    def research_page():
        rows=get_trials(app.config["DATABASE"]); identification=[r for r in rows if r["trial_type"]=="identification"]; grouped={}
        for row in identification: grouped.setdefault(row["condition"],[]).append(row)
        return render_template("research.html", trials=rows, metrics=_research_metrics(identification), verification_count=sum(r["trial_type"]=="verification" for r in rows), by_condition={name:_research_metrics(group) for name,group in grouped.items()})

    @app.post("/api/research/trials")
    def create_trial():
        p=request.get_json(silent=True) or {}
        expected=str(p.get("expected_identity","")).strip() or None; predicted=str(p.get("predicted_identity","")).strip() or None
        condition=str(p.get("condition","")).strip(); result=str(p.get("result","")).strip()
        try: ms=float(p.get("processing_ms"))
        except (TypeError,ValueError): return jsonify(error="Processing time must be a number."),400
        if not condition or result not in {"accepted","rejected"} or ms<0: return jsonify(error="Provide condition, result, and a non-negative processing time."),400
        trial_type=str(p.get("trial_type","identification"))
        if trial_type not in {"identification","verification"}: return jsonify(error="Choose identification or verification."),400
        if (result=="accepted") != bool(predicted): return jsonify(error="Accepted trials need a predicted identity; rejected trials must leave it blank."),400
        add_trial(app.config["DATABASE"],(expected,predicted,condition,str(p.get("lighting", ""))[:80],str(p.get("distance", ""))[:80],str(p.get("orientation", ""))[:80],result,ms,trial_type))
        return jsonify(message="Experiment trial recorded."),201

    @app.get("/research/export.csv")
    def export_trials():
        output=io.StringIO(); rows=get_trials(app.config["DATABASE"]); writer=csv.DictWriter(output,fieldnames=list(rows[0]) if rows else ["expected_identity","predicted_identity","condition","lighting","distance","orientation","result","processing_ms","trial_type","created_at"])
        writer.writeheader(); writer.writerows(rows)
        return Response(output.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=research-trials.csv"})

    @app.errorhandler(413)
    def too_large(_): return (jsonify(error="Image is too large. Choose one smaller than 5 MB."),413) if request.path.startswith("/api/") else ("Request too large.",413)
    return app


app=create_app()
if __name__=="__main__": app.run(host="127.0.0.1",port=int(os.environ.get("PORT","5000")),debug=False)
