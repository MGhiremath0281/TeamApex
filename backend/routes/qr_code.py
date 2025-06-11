import qrcode
import base64
import psycopg2
from io import BytesIO
from flask import Blueprint, render_template, session, flash, redirect, url_for, send_file, current_app
from flask_weasyprint import HTML, render_pdf
from backend.models import get_db_connection
from datetime import datetime # Import datetime

# Create a Blueprint for QR code and PDF generation
qr_bp = Blueprint('qr_code', __name__)

@qr_bp.route('/generate_qr/<patient_uid>')
def generate_qr(patient_uid):
    """
    Generates and displays a QR code for a given patient UID.
    Only accessible by logged-in patients for their own UID.
    """
    if 'user_id' not in session or session['role'] != 'patient':
        flash('Unauthorized access.', 'warning')
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    if conn is None:
        flash('Database connection error. Please try again later.', 'error')
        return redirect(url_for('patient.patient_dashboard'))

    cur = conn.cursor()
    current_patient_uid = None
    try:
        # Verify if the logged-in patient owns this UID
        cur.execute("SELECT uid FROM patients WHERE user_id = %s", (session['user_id'],))
        current_patient_uid_row = cur.fetchone()
        if not current_patient_uid_row or current_patient_uid_row[0] != patient_uid:
            flash('You can only generate QR codes for your own patient ID.', 'error')
            return redirect(url_for('patient.patient_dashboard'))
        current_patient_uid = current_patient_uid_row[0] # Confirmed owned UID
    except psycopg2.Error as e:
        flash(f"Database error: {e}", 'error')
        return redirect(url_for('patient.patient_dashboard'))
    finally:
        if conn:
            cur.close()
            conn.close()

    # Construct the URL that the QR code will point to
    # Make sure 'yourwebsite.com' is replaced with your actual domain in production
    # For local testing, it would be http://127.0.0.1:5000
    report_url = url_for('qr_code.emergency_report_download', patient_uid=patient_uid, _external=True)

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(report_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    qr_image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return render_template('qr_code_display.html', qr_image=qr_image_base64, patient_uid=patient_uid, report_url=report_url)


@qr_bp.route('/report/<patient_uid>/download')
def emergency_report_download(patient_uid):
    """
    Generates a PDF health report for a given patient UID.
    This route is intended to be accessible via the QR code.
    It does not require login, but in a real system, you'd add
    security like a temporary token in the URL or IP-based restrictions.
    For this project, it's globally accessible as per prompt.
    """
    patient_info = None
    medical_records = []
    appointments = []

    conn = get_db_connection()
    if conn is None:
        flash('Database connection error. Please try again later.', 'error')
        return "Database error. Please try again later.", 500

    cur = conn.cursor()
    try:
        # Fetch patient details
        cur.execute(
            "SELECT uid, name, date_of_birth, gender, contact_info FROM patients WHERE uid = %s",
            (patient_uid,)
        )
        patient_row = cur.fetchone()
        if patient_row:
            patient_info = {
                'uid': patient_row[0],
                'name': patient_row[1],
                'date_of_birth': patient_row[2],
                'gender': patient_row[3],
                'contact_info': patient_row[4]
            }

            # Fetch medical records for the patient, including doctor's username
            cur.execute(
                """SELECT mr.record_date, mr.disease_history, mr.prescriptions, u.username as doctor_username
                   FROM medical_records mr
                   JOIN users u ON mr.doctor_id = u.id
                   WHERE mr.patient_uid = %s ORDER BY mr.record_date DESC""",
                (patient_uid,)
            )
            medical_records = cur.fetchall()

            # Fetch appointments for the patient, including doctor's username
            cur.execute(
                """SELECT a.appointment_date, a.reason, a.status, u.username as doctor_username
                   FROM appointments a
                   JOIN users u ON a.doctor_id = u.id
                   WHERE a.patient_uid = %s ORDER BY a.appointment_date DESC""",
                (patient_uid,)
            )
            appointments = cur.fetchall()

        else:
            return "Patient not found.", 404

    except psycopg2.Error as e:
        print(f"Error fetching report data: {e}")
        return "Error fetching report data. Please try again later.", 500
    finally:
        if conn:
            cur.close()
            conn.close()

    # Pass the current datetime object to the template
    current_time = datetime.now()

    # Render the HTML template for the report
    html = render_template(
        'report_template.html',
        patient_info=patient_info,
        medical_records=medical_records,
        appointments=appointments,
        current_time=current_time # Pass current_time here
    )

    # Convert HTML to PDF and provide as download
    return render_pdf(HTML(string=html))
