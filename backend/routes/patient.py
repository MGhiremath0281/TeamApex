import psycopg2
from flask import Blueprint, render_template, session, flash, redirect, url_for, request
from backend.models import get_db_connection
from datetime import datetime

# Create a Blueprint for patient routes
patient_bp = Blueprint('patient', __name__)

# Helper function to parse disease_history (moved here from patient.py for app.py import)
def parse_disease_history(history_text):
    symptoms_diagnosis = ""
    allergies = ""
    if history_text:
        parts = history_text.split('\n--- Allergies:', 1) # Split only on the first occurrence
        symptoms_diagnosis = parts[0].replace("Symptoms & Diagnosis: ", "").strip()
        if len(parts) > 1:
            allergies = parts[1].strip()
    return symptoms_diagnosis, allergies

@patient_bp.route('/patient_dashboard')
def patient_dashboard():
    """Renders the patient dashboard."""
    if 'user_id' not in session or session['role'] != 'patient':
        flash('Please log in as a patient to access this page.', 'warning')
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    patient_uid = None
    patient_data = {}
    medical_records_display = [] # For full history list
    appointments = []
    # --- New: Placeholder for Vitals, Medications, Allergies/Conditions ---
    vitals_summary = {
        'last_blood_pressure': '120/80 mmHg',
        'last_heart_rate': '72 bpm',
        'body_temperature': '36.8°C (98.2°F)',
        'weight': '75 kg',
        'last_updated': '2025-06-11' # Mock date
    }
    medications = []
    allergies_list = [] # For display in Allergies & Conditions card
    conditions_list = [] # For display in Allergies & Conditions card


    conn = get_db_connection()
    if conn is None:
        flash('Database connection error. Please try again later.', 'error')
        return render_template('patient_dashboard.html', username=session['username'])

    cur = conn.cursor()
    try:
        # Get patient UID and details, including emergency contact
        cur.execute(
            """SELECT uid, name, date_of_birth, gender, contact_info,
                      emergency_contact_name, emergency_contact_relationship, emergency_contact_phone
               FROM patients WHERE user_id = %s""",
            (user_id,)
        )
        patient_row = cur.fetchone()
        if patient_row:
            patient_uid = patient_row[0]
            patient_data = {
                'uid': patient_row[0],
                'name': patient_row[1],
                'date_of_birth': patient_row[2],
                'gender': patient_row[3],
                'contact_info': patient_row[4],
                'emergency_contact_name': patient_row[5],
                'emergency_contact_relationship': patient_row[6],
                'emergency_contact_phone': patient_row[7]
            }
            # Store patient_uid in session for base.html sidebar link
            session['patient_uid'] = patient_uid


            # Get medical records for the patient (to extract meds, allergies, conditions)
            cur.execute(
                """SELECT mr.record_date, mr.disease_history, mr.prescriptions, u.username as doctor_username
                   FROM medical_records mr
                   JOIN users u ON mr.doctor_id = u.id
                   WHERE mr.patient_uid = %s ORDER BY mr.record_date DESC""",
                (patient_uid,)
            )
            all_records = cur.fetchall()

            # Process records for display
            for record in all_records:
                record_date, disease_history_text, prescriptions_text, doctor_username = record
                symptoms_diagnosis, current_allergies = parse_disease_history(disease_history_text)

                medical_records_display.append({
                    'record_date': record_date,
                    'symptoms_diagnosis': symptoms_diagnosis,
                    'allergies': current_allergies,
                    'prescriptions': prescriptions_text,
                    'doctor_username': doctor_username
                })

                # Aggregate medications, allergies, and conditions from all records for dashboard cards
                if prescriptions_text:
                    medications.extend([m.strip() for m in prescriptions_text.split('\n') if m.strip()])

                # Basic parsing for conditions (you might want more refined logic)
                if symptoms_diagnosis:
                    if 'diabetes' in symptoms_diagnosis.lower(): conditions_list.append('Diabetes')
                    if 'hypertension' in symptoms_diagnosis.lower(): conditions_list.append('Hypertension')
                    # Add more keyword-based conditions here

                if current_allergies and current_allergies.lower() != 'none':
                    allergies_list.extend([a.strip() for a in current_allergies.split(',') if a.strip()])


            # Remove duplicates for aggregated lists
            medications = list(set(medications))
            allergies_list = list(set(allergies_list))
            conditions_list = list(set(conditions_list))


            # Get upcoming appointment for the patient
            cur.execute(
                """SELECT a.appointment_date, a.reason, a.status, u.username as doctor_username, u.id as doctor_id
                   FROM appointments a
                   JOIN users u ON a.doctor_id = u.id
                   WHERE a.patient_uid = %s AND a.status = 'scheduled'
                   ORDER BY a.appointment_date ASC LIMIT 1""",
                (patient_uid,)
            )
            upcoming_appointment = cur.fetchone()

            # Get all appointments for "Manage Appointments" link
            cur.execute(
                """SELECT a.id, a.appointment_date, a.reason, a.status, u.username as doctor_username
                   FROM appointments a
                   JOIN users u ON a.doctor_id = u.id
                   WHERE a.patient_uid = %s ORDER BY a.appointment_date DESC""",
                (patient_uid,)
            )
            appointments = cur.fetchall() # All appointments for the list

    except psycopg2.Error as e:
        flash(f"Error fetching patient data: {e}", 'error')
    finally:
        if conn:
            cur.close()
            conn.close()

    return render_template(
        'patient_dashboard.html',
        username=session['username'],
        patient_uid=patient_uid,
        patient_data=patient_data,
        vitals_summary=vitals_summary, # Pass vitals
        upcoming_appointment=upcoming_appointment, # Pass upcoming appointment
        medications=medications, # Pass parsed medications
        allergies=allergies_list,     # Pass parsed allergies
        conditions=conditions_list,   # Pass parsed conditions
        medical_records=medical_records_display, # Full records for "My Health Records" link
        appointments=appointments # All appointments for manage link
    )

@patient_bp.route('/patient_search_record', methods=['GET', 'POST'])
def patient_search_record():
    """Allows patient to search for their own records by UID (via patient dashboard link)."""
    if 'user_id' not in session or session['role'] != 'patient':
        flash('Please log in as a patient to access this page.', 'warning')
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    current_patient_uid = session.get('patient_uid') # Retrieve from session

    searched_uid = None
    patient_info = None
    medical_records_display = []
    appointments = []
    message = None

    if request.method == 'POST':
        # Patient can only search their own UID
        input_uid = request.form.get('uid')
        if not input_uid:
            message = "Please enter a UID to search."
        elif input_uid != current_patient_uid:
            message = "You can only view your own records. Please enter your correct UID."
            searched_uid = None # Clear for security
        else:
            searched_uid = input_uid

        if searched_uid:
            conn = get_db_connection()
            if conn is None:
                flash('Database connection error. Please try again later.', 'error')
                return render_template('patient_dashboard.html', username=session['username'], patient_uid=current_patient_uid)

            cur = conn.cursor()
            try:
                # Fetch patient details
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

                    # Fetch medical records
                    cur.execute(
                        """SELECT mr.record_date, mr.disease_history, mr.prescriptions, u.username AS doctor_username
                           FROM medical_records mr
                           JOIN users u ON mr.doctor_id = u.id
                           WHERE mr.patient_uid = %s ORDER BY mr.record_date DESC""",
                        (searched_uid,)
                    )
                    all_records = cur.fetchall()
                    for record in all_records:
                        record_date, disease_history_text, prescriptions_text, doctor_username = record
                        symptoms_diagnosis, current_allergies = parse_disease_history(disease_history_text)
                        medical_records_display.append({
                            'record_date': record_date,
                            'symptoms_diagnosis': symptoms_diagnosis,
                            'allergies': current_allergies,
                            'prescriptions': prescriptions_text,
                            'doctor_username': doctor_username
                        })


                    # Fetch appointments
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
                flash(f"Error searching records: {e}", 'error')
            finally:
                if conn:
                    cur.close()
                    conn.close()

    # Pass the data relevant to the current user's UID for display on the dashboard
    return render_template(
        'patient_dashboard.html',
        username=session['username'],
        patient_uid=current_patient_uid, # Always display current user's UID on dashboard
        searched_uid=searched_uid,
        patient_info=patient_info,
        medical_records=medical_records_display,
        appointments=appointments,
        message=message,
        # Pass dashboard specific data here too if we want to retain it after a search
        vitals_summary=getattr(patient_bp, '_temp_vitals_summary', None), # Retrieve temp data
        upcoming_appointment=getattr(patient_bp, '_temp_upcoming_appointment', None),
        medications=getattr(patient_bp, '_temp_medications', []),
        allergies=getattr(patient_bp, '_temp_allergies', []),
        conditions=getattr(patient_bp, '_temp_conditions', [])
    )

@patient_bp.route('/patient/edit_profile', methods=['GET', 'POST'])
def patient_edit_profile():
    """Allows a patient to edit their own profile details (excluding name)."""
    if 'user_id' not in session or session['role'] != 'patient':
        flash('Please log in as a patient to access this page.', 'warning')
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    patient_data = None

    conn = get_db_connection()
    if conn is None:
        flash('Database connection error. Please try again later.', 'error')
        return redirect(url_for('patient.patient_dashboard'))

    cur = conn.cursor()
    try:
        # Fetch current patient data including emergency contact
        cur.execute(
            """SELECT name, date_of_birth, gender, contact_info,
                      emergency_contact_name, emergency_contact_relationship, emergency_contact_phone
               FROM patients WHERE user_id = %s""",
            (user_id,)
        )
        patient_row = cur.fetchone()

        if not patient_row:
            flash('Your patient profile could not be found.', 'error')
            return redirect(url_for('patient.patient_dashboard'))

        patient_data = {
            'name': patient_row[0], # Name displayed but not editable
            'date_of_birth': patient_row[1].isoformat() if patient_row[1] else '', # Format for HTML date input
            'gender': patient_row[2],
            'contact_info': patient_row[3],
            'emergency_contact_name': patient_row[4],      # NEW
            'emergency_contact_relationship': patient_row[5], # NEW
            'emergency_contact_phone': patient_row[6]       # NEW
        }

        if request.method == 'POST':
            # Retrieve updated data from form
            updated_date_of_birth = request.form['date_of_birth']
            updated_gender = request.form['gender']
            updated_contact_info = request.form['contact_info']
            updated_emergency_contact_name = request.form.get('emergency_contact_name')
            updated_emergency_contact_relationship = request.form.get('emergency_contact_relationship')
            updated_emergency_contact_phone = request.form.get('emergency_contact_phone')


            # Update patient record in database
            cur.execute(
                """UPDATE patients SET date_of_birth = %s, gender = %s, contact_info = %s,
                                     emergency_contact_name = %s, emergency_contact_relationship = %s, emergency_contact_phone = %s
                   WHERE user_id = %s""",
                (updated_date_of_birth, updated_gender, updated_contact_info,
                 updated_emergency_contact_name, updated_emergency_contact_relationship, updated_emergency_contact_phone,
                 user_id)
            )
            conn.commit()
            flash('Your profile has been updated successfully!', 'success')
            return redirect(url_for('patient.patient_dashboard'))

    except psycopg2.Error as e:
        flash(f'An error occurred while updating your profile: {e}', 'error')
        conn.rollback()
    finally:
        if conn:
            cur.close()
            conn.close()

    # For GET request or if POST fails
    return render_template('patient_edit_profile.html', patient_data=patient_data)
