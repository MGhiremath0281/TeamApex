import psycopg2
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from backend.models import get_db_connection
from datetime import datetime

# Create a Blueprint for appointment routes
appointment_bp = Blueprint('appointment', __name__)

@appointment_bp.route('/manage_appointments')
def manage_appointments():
    """Allows both doctors and patients to view their appointments."""
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    user_role = session['role']
    appointments = []

    conn = get_db_connection()
    if conn is None:
        flash('Database connection error. Please try again later.', 'error')
        return render_template('appointment_form.html', appointments=appointments)

    cur = conn.cursor()
    try:
        if user_role == 'patient':
            # Get patient's UID
            cur.execute("SELECT uid FROM patients WHERE user_id = %s", (user_id,))
            patient_uid = cur.fetchone()[0]

            cur.execute(
                """SELECT a.id, a.appointment_date, a.reason, a.status, u.username as doctor_username
                   FROM appointments a
                   JOIN users u ON a.doctor_id = u.id
                   WHERE a.patient_uid = %s ORDER BY a.appointment_date DESC""",
                (patient_uid,)
            )
        elif user_role == 'doctor':
            cur.execute(
                """SELECT a.id, a.appointment_date, a.reason, a.status, p.name as patient_name, p.uid as patient_uid
                   FROM appointments a
                   JOIN patients p ON a.patient_uid = p.uid
                   WHERE a.doctor_id = %s ORDER BY a.appointment_date DESC""",
                (user_id,)
            )
        appointments = cur.fetchall()
    except psycopg2.Error as e:
        flash(f"Error fetching appointments: {e}", 'error')
    finally:
        if conn:
            cur.close()
            conn.close()

    return render_template('appointment_form.html', appointments=appointments, user_role=user_role)

@appointment_bp.route('/create_appointment', methods=['GET', 'POST'])
def create_appointment():
    """Allows doctors and patients to create appointments."""
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    user_role = session['role']
    patients = [] # For doctors to select a patient
    doctors = []  # For patients to select a doctor
    current_patient_uid = None # For patients to pre-fill their UID

    conn = get_db_connection()
    if conn is None:
        flash('Database connection error. Please try again later.', 'error')
        return render_template('appointment_form.html')

    cur = conn.cursor()
    try:
        if user_role == 'doctor':
            cur.execute("SELECT uid, name FROM patients ORDER BY name")
            patients = cur.fetchall()
        elif user_role == 'patient':
            cur.execute("SELECT id, username FROM users WHERE role = 'doctor' ORDER BY username")
            doctors = cur.fetchall()
            cur.execute("SELECT uid FROM patients WHERE user_id = %s", (user_id,))
            current_patient_uid = cur.fetchone()[0]
    except psycopg2.Error as e:
        flash(f"Error preparing form data: {e}", 'error')
    finally:
        if conn:
            cur.close()
            conn.close()

    if request.method == 'POST':
        if user_role == 'patient':
            patient_uid = current_patient_uid
            doctor_id = request.form['doctor_id']
        elif user_role == 'doctor':
            patient_uid = request.form['patient_uid']
            doctor_id = user_id

        appointment_date_str = request.form['appointment_date'] + ' ' + request.form['appointment_time']
        reason = request.form['reason']

        try:
            appointment_date = datetime.strptime(appointment_date_str, '%Y-%m-%d %H:%M')
        except ValueError:
            flash('Invalid date or time format. Please use YYYY-MM-DD and HH:MM.', 'error')
            return render_template(
                'appointment_form.html',
                patients=patients,
                doctors=doctors,
                user_role=user_role,
                current_patient_uid=current_patient_uid,
                form_data=request.form
            )

        conn = get_db_connection()
        if conn is None:
            flash('Database connection error. Please try again later.', 'error')
            return render_template('appointment_form.html')

        cur = conn.cursor()
        try:
            # Verify patient_uid exists
            cur.execute("SELECT uid FROM patients WHERE uid = %s", (patient_uid,))
            if not cur.fetchone():
                flash('Invalid Patient UID.', 'error')
                return render_template('appointment_form.html', patients=patients, doctors=doctors, user_role=user_role, current_patient_uid=current_patient_uid, form_data=request.form)

            # Verify doctor_id exists and is a doctor
            cur.execute("SELECT id FROM users WHERE id = %s AND role = 'doctor'", (doctor_id,))
            if not cur.fetchone():
                flash('Invalid Doctor selection.', 'error')
                return render_template('appointment_form.html', patients=patients, doctors=doctors, user_role=user_role, current_patient_uid=current_patient_uid, form_data=request.form)


            cur.execute(
                """INSERT INTO appointments (patient_uid, doctor_id, appointment_date, reason, status)
                   VALUES (%s, %s, %s, %s, 'scheduled')""",
                (patient_uid, doctor_id, appointment_date, reason)
            )
            conn.commit()
            flash('Appointment created successfully!', 'success')
            return redirect(url_for('appointment.manage_appointments'))
        except psycopg2.Error as e:
            flash(f'An error occurred: {e}', 'error')
            conn.rollback()
        finally:
            if conn:
                cur.close()
                conn.close()

    return render_template(
        'appointment_form.html',
        patients=patients,
        doctors=doctors,
        user_role=user_role,
        current_patient_uid=current_patient_uid
    )

@appointment_bp.route('/cancel_appointment/<int:appointment_id>')
def cancel_appointment(appointment_id):
    """Allows users to cancel an appointment."""
    if 'user_id' not in session:
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    user_role = session['role']

    conn = get_db_connection()
    if conn is None:
        flash('Database connection error. Please try again later.', 'error')
        return redirect(url_for('appointment.manage_appointments'))

    cur = conn.cursor()
    try:
        # Check ownership before canceling
        if user_role == 'patient':
            cur.execute("SELECT patient_uid FROM appointments WHERE id = %s", (appointment_id,))
            appointment_patient_uid = cur.fetchone()
            if not appointment_patient_uid:
                flash('Appointment not found.', 'error')
                return redirect(url_for('appointment.manage_appointments'))

            cur.execute("SELECT uid FROM patients WHERE user_id = %s", (user_id,))
            current_patient_uid = cur.fetchone()

            if not current_patient_uid or appointment_patient_uid[0] != current_patient_uid[0]:
                flash('You do not have permission to cancel this appointment.', 'error')
                return redirect(url_for('appointment.manage_appointments'))

        elif user_role == 'doctor':
            cur.execute("SELECT doctor_id FROM appointments WHERE id = %s", (appointment_id,))
            appointment_doctor_id = cur.fetchone()
            if not appointment_doctor_id or appointment_doctor_id[0] != user_id:
                flash('You do not have permission to cancel this appointment.', 'error')
                return redirect(url_for('appointment.manage_appointments'))

        cur.execute(
            "UPDATE appointments SET status = 'cancelled' WHERE id = %s",
            (appointment_id,)
        )
        conn.commit()
        flash('Appointment cancelled successfully!', 'success')
    except psycopg2.Error as e:
        flash(f"Error cancelling appointment: {e}", 'error')
        conn.rollback()
    finally:
        if conn:
            cur.close()
            conn.close()

    return redirect(url_for('appointment.manage_appointments'))
