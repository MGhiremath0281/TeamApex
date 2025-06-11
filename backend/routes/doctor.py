import psycopg2
from flask import Blueprint, render_template, session, flash, redirect, url_for, request
from backend.models import get_db_connection, hash_password
from datetime import datetime
import uuid # For generating patient UIDs

# Create a Blueprint for doctor routes
doctor_bp = Blueprint('doctor', __name__)

@doctor_bp.route('/doctor_dashboard')
def doctor_dashboard():
    """Renders the doctor dashboard."""
    if 'user_id' not in session or session['role'] != 'doctor':
        flash('Please log in as a doctor to access this page.', 'warning')
        return redirect(url_for('auth.login'))

    # Initialize variables for patient search results
    searched_uid = None
    patient_info = None
    medical_records = []
    appointments = []
    message = None

    # Check if this request is a redirect from a search
    if request.method == 'GET' and 'uid_search' in request.args:
        searched_uid = request.args.get('uid_search')
        # If there's a UID in the query, perform the lookup logic here
        if searched_uid:
            conn = get_db_connection()
            if conn is None:
                flash('Database connection error. Please try again later.', 'error')
            else:
                cur = conn.cursor()
                try:
                    # Fetch patient details including emergency contact
                    cur.execute(
                        """SELECT uid, name, date_of_birth, gender, contact_info,
                                  emergency_contact_name, emergency_contact_relationship, emergency_contact_phone
                           FROM patients WHERE uid = %s""",
                        (searched_uid,)
                    )
                    patient_row = cur.fetchone()
                    if patient_row:
                        patient_info = {
                            'uid': patient_row[0],
                            'name': patient_row[1],
                            'date_of_birth': patient_row[2],
                            'gender': patient_row[3],
                            'contact_info': patient_row[4],
                            'emergency_contact_name': patient_row[5],
                            'emergency_contact_relationship': patient_row[6],
                            'emergency_contact_phone': patient_row[7]
                        }

                        # Fetch medical records for the patient
                        cur.execute(
                            """SELECT mr.record_date, mr.disease_history, mr.prescriptions, u.username AS doctor_username
                               FROM medical_records mr
                               JOIN users u ON mr.doctor_id = u.id
                               WHERE mr.patient_uid = %s ORDER BY mr.record_date DESC""",
                            (searched_uid,)
                        )
                        medical_records = cur.fetchall()

                        cur.execute(
                            """SELECT a.appointment_date, a.reason, a.status, u.username AS doctor_username
                               FROM appointments a
                               JOIN users u ON a.doctor_id = u.id
                               WHERE a.patient_uid = %s ORDER BY a.appointment_date DESC""",
                            (searched_uid,)
                        )
                        appointments = cur.fetchall()
                    else:
                        message = "No patient found with that UID."
                except psycopg2.Error as e:
                    flash(f"Error fetching patient details: {e}", 'error')
                finally:
                    if conn:
                        cur.close()
                        conn.close()

    return render_template(
        'doctor_dashboard.html',
        username=session['username'],
        searched_uid=searched_uid,
        patient_info=patient_info,
        medical_records=medical_records,
        appointments=appointments,
        message=message
    )

@doctor_bp.route('/doctor_initiate_new_patient', methods=['POST'])
def doctor_initiate_new_patient():
    """Handles the initial UID check for new patient registration by a doctor."""
    if 'user_id' not in session or session['role'] != 'doctor':
        flash('Unauthorized access.', 'warning')
        return redirect(url_for('auth.login'))

    new_patient_uid = request.form.get('new_patient_uid_input')
    if not new_patient_uid:
        flash('Please enter a UID for the new patient.', 'error')
        return redirect(url_for('doctor.doctor_dashboard'))

    conn = get_db_connection()
    if conn is None:
        flash('Database connection error. Please try again later.', 'error')
        return redirect(url_for('doctor.doctor_dashboard'))

    cur = conn.cursor()
    try:
        # Check if UID already exists in patients table
        cur.execute("SELECT uid FROM patients WHERE uid = %s", (new_patient_uid,))
        if cur.fetchone():
            flash(f'Patient with UID "{new_patient_uid}" already exists. Please use "Existing Patient Management" or choose a different UID.', 'error')
            return redirect(url_for('doctor.doctor_dashboard', uid_search=new_patient_uid)) # Redirect to dashboard, show existing patient

        # If UID is unique, proceed to the detailed registration form
        return redirect(url_for('doctor.doctor_register_new_patient_form', patient_uid=new_patient_uid))
    except psycopg2.Error as e:
        flash(f'Database error: {e}', 'error')
    finally:
        if conn:
            cur.close()
            conn.close()
    return redirect(url_for('doctor.doctor_dashboard'))


@doctor_bp.route('/doctor_register_new_patient_form')
def doctor_register_new_patient_form():
    """Renders the form for doctors to fill patient details for a new patient."""
    if 'user_id' not in session or session['role'] != 'doctor':
        flash('Unauthorized access.', 'warning')
        return redirect(url_for('auth.login'))

    patient_uid = request.args.get('patient_uid')
    if not patient_uid:
        flash('Patient UID is missing for new registration.', 'error')
        return redirect(url_for('doctor.doctor_dashboard'))

    # Check if the UID might have been registered in another tab/process
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        try:
            cur.execute("SELECT uid FROM patients WHERE uid = %s", (patient_uid,))
            if cur.fetchone():
                flash(f'Patient with UID "{patient_uid}" already exists. Cannot register again.', 'error')
                return redirect(url_for('doctor.doctor_dashboard', uid_search=patient_uid))
        except psycopg2.Error as e:
            flash(f'Database error: {e}', 'error')
        finally:
            cur.close()
            conn.close()

    return render_template('doctor_new_patient_form.html', patient_uid=patient_uid)


@doctor_bp.route('/doctor_complete_new_patient_registration', methods=['POST'])
def doctor_complete_new_patient_registration():
    """Handles the submission of a new patient's details by a doctor."""
    if 'user_id' not in session or session['role'] != 'doctor':
        flash('Unauthorized access.', 'warning')
        return redirect(url_for('auth.login'))

    patient_uid = request.form['patient_uid']
    name = request.form['name']
    date_of_birth = request.form['date_of_birth']
    gender = request.form['gender']
    contact_info = request.form['contact_info']
    # NEW: Emergency Contact Details
    emergency_contact_name = request.form.get('emergency_contact_name')
    emergency_contact_relationship = request.form.get('emergency_contact_relationship')
    emergency_contact_phone = request.form.get('emergency_contact_phone')

    # For simplicity, assign a default username/password for doctor-registered patients
    username = patient_uid # Use UID as username for simplicity for doctor-added patients
    password = str(uuid.uuid4()) # Generate a random password, not given to patient directly
    hashed_password = hash_password(password) # Hash this generated password

    conn = get_db_connection()
    if conn is None:
        flash('Database connection error. Please try again later.', 'error')
        return render_template('doctor_new_patient_form.html', form_data=request.form, patient_uid=patient_uid)

    cur = conn.cursor()
    try:
        # Re-check if UID already exists (race condition check)
        cur.execute("SELECT uid FROM patients WHERE uid = %s", (patient_uid,))
        if cur.fetchone():
            flash(f'Patient with UID "{patient_uid}" already exists. Cannot register again.', 'error')
            return render_template('doctor_new_patient_form.html', form_data=request.form, patient_uid=patient_uid)

        # Check if username exists (less critical for doctor-registered, but good practice)
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            flash(f'Internal error: Generated username "{username}" already exists. Please try again.', 'error')
            return render_template('doctor_new_patient_form.html', form_data=request.form, patient_uid=patient_uid)

        # Insert into users table
        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, 'patient') RETURNING id",
            (username, hashed_password)
        )
        user_id = cur.fetchone()[0]

        # Insert into patients table with new emergency contact fields
        cur.execute(
            """INSERT INTO patients (uid, user_id, name, date_of_birth, gender, contact_info,
                                   emergency_contact_name, emergency_contact_relationship, emergency_contact_phone)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (patient_uid, user_id, name, date_of_birth, gender, contact_info,
             emergency_contact_name, emergency_contact_relationship, emergency_contact_phone)
        )

        conn.commit()
        flash(f'Patient "{name}" registered successfully with UID: {patient_uid}. Now add initial consultation.', 'success')
        # Redirect to add medical record with the new patient's UID pre-selected
        return redirect(url_for('doctor.doctor_add_medical_record', patient_uid=patient_uid))

    except psycopg2.Error as e:
        flash(f'An error occurred during patient registration: {e}', 'error')
        conn.rollback()
    finally:
        if conn:
            cur.close()
            conn.close()

    return render_template('doctor_new_patient_form.html', form_data=request.form, patient_uid=patient_uid)


@doctor_bp.route('/doctor_edit_patient_details/<patient_uid>', methods=['GET', 'POST'])
def doctor_edit_patient_details(patient_uid):
    """Allows a doctor to edit an existing patient's personal details."""
    if 'user_id' not in session or session['role'] != 'doctor':
        flash('Unauthorized access.', 'warning')
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    if conn is None:
        flash('Database connection error. Please try again later.', 'error')
        return redirect(url_for('doctor.doctor_dashboard'))

    cur = conn.cursor()
    patient_data = None

    try:
        # Fetch all patient details including emergency contact
        cur.execute(
            """SELECT uid, name, date_of_birth, gender, contact_info,
                      emergency_contact_name, emergency_contact_relationship, emergency_contact_phone
               FROM patients WHERE uid = %s""",
            (patient_uid,)
        )
        patient_row = cur.fetchone()
        if not patient_row:
            flash('Patient not found.', 'error')
            return redirect(url_for('doctor.doctor_dashboard'))

        patient_data = {
            'uid': patient_row[0],
            'name': patient_row[1],
            'date_of_birth': patient_row[2].isoformat() if patient_row[2] else '', # Format date for HTML input
            'gender': patient_row[3],
            'contact_info': patient_row[4],
            'emergency_contact_name': patient_row[5],
            'emergency_contact_relationship': patient_row[6],
            'emergency_contact_phone': patient_row[7]
        }

        if request.method == 'POST':
            name = request.form['name'] # Though name is not editable, it's passed for consistency if needed.
            date_of_birth = request.form['date_of_birth']
            gender = request.form['gender']
            contact_info = request.form['contact_info']
            # NEW: Emergency Contact Details from form
            emergency_contact_name = request.form.get('emergency_contact_name')
            emergency_contact_relationship = request.form.get('emergency_contact_relationship')
            emergency_contact_phone = request.form.get('emergency_contact_phone')

            cur.execute(
                """UPDATE patients SET name = %s, date_of_birth = %s, gender = %s, contact_info = %s,
                                     emergency_contact_name = %s, emergency_contact_relationship = %s, emergency_contact_phone = %s
                   WHERE uid = %s""",
                (name, date_of_birth, gender, contact_info,
                 emergency_contact_name, emergency_contact_relationship, emergency_contact_phone,
                 patient_uid)
            )
            conn.commit()
            flash('Patient details updated successfully!', 'success')
            return redirect(url_for('doctor.doctor_dashboard', uid_search=patient_uid)) # Redirect to dashboard with updated info
    except psycopg2.Error as e:
        flash(f'An error occurred during update: {e}', 'error')
        conn.rollback()
    finally:
        if conn:
            cur.close()
            conn.close()

    return render_template('doctor_edit_patient_details.html', patient_data=patient_data)

@doctor_bp.route('/doctor_add_medical_record', methods=['GET', 'POST'])
def doctor_add_medical_record():
    """Allows a doctor to add medical records for a patient."""
    if 'user_id' not in session or session['role'] != 'doctor':
        flash('Please log in as a doctor to access this page.', 'warning')
        return redirect(url_for('auth.login'))

    patients = []
    preselected_patient_uid = request.args.get('patient_uid') # Get pre-selected UID from query param

    conn = get_db_connection()
    if conn is None:
        flash('Database connection error. Please try again later.', 'error')
        return render_template('prescription_form.html', patients=patients)

    cur = conn.cursor()
    try:
        cur.execute("SELECT uid, name FROM patients ORDER BY name")
        patients = cur.fetchall()
    except psycopg2.Error as e:
        flash(f"Error fetching patient list: {e}", 'error')
    finally:
        if conn:
            cur.close()
            conn.close()

    if request.method == 'POST':
        patient_uid = request.form['patient_uid']
        symptoms_diagnosis = request.form['symptoms_diagnosis'] # Get symptoms & diagnosis
        allergies = request.form['allergies'] # Get allergies
        prescriptions = request.form['prescriptions']
        doctor_id = session['user_id']

        # Combine symptoms_diagnosis and allergies into disease_history with a clear separator
        # This is a pragmatic solution given the current single 'disease_history' column.
        # For a more robust solution, 'allergies' should be a separate column in the DB.
        combined_disease_history = f"Symptoms & Diagnosis: {symptoms_diagnosis}\n--- Allergies: {allergies}"

        conn = get_db_connection()
        if conn is None:
            flash('Database connection error. Please try again later.', 'error')
            return render_template('prescription_form.html', patients=patients, preselected_patient_uid=preselected_patient_uid, form_data=request.form)

        cur = conn.cursor()
        try:
            # Check if patient_uid exists
            cur.execute("SELECT uid FROM patients WHERE uid = %s", (patient_uid,))
            if not cur.fetchone():
                flash('Patient with the provided UID does not exist. Please register the patient first.', 'error')
                return render_template('prescription_form.html', patients=patients, form_data=request.form, preselected_patient_uid=preselected_patient_uid)

            cur.execute(
                """INSERT INTO medical_records (patient_uid, doctor_id, disease_history, prescriptions)
                   VALUES (%s, %s, %s, %s)""",
                (patient_uid, doctor_id, combined_disease_history, prescriptions) # Use combined string here
            )
            conn.commit()
            flash('Medical record added successfully!', 'success')
            return redirect(url_for('doctor.doctor_dashboard', uid_search=patient_uid)) # Redirect to search result
        except psycopg2.Error as e:
            flash(f'An error occurred: {e}', 'error')
            conn.rollback()
        finally:
            if conn:
                cur.close()
                conn.close()

    return render_template('prescription_form.html', patients=patients, preselected_patient_uid=preselected_patient_uid)
