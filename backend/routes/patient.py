import psycopg2
from flask import Blueprint, render_template, session, flash, redirect, url_for, request, jsonify, current_app
from backend.models import get_db_connection
from datetime import datetime, timedelta, time
# REMOVED: from backend.utils.encryption import encrypt_uid

patient_bp = Blueprint('patient', __name__)

def parse_disease_history(history_text):
    """
    Parses the disease history text to extract symptoms/diagnosis and allergies.
    """
    symptoms_diagnosis = ""
    allergies = ""
    if history_text:
        parts = history_text.split('\n--- Allergies:', 1)
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

    # Initialize all variables that will be passed to the template
    patient_uid = None
    patient_data = {}
    medical_records_display = []
    appointments = []
    medications = [] # List of active medications (structured) for the card
    allergies_list = []
    conditions_list = []
    upcoming_appointment = None
    searched_uid = None
    patient_info = None
    next_medication_dose = None

    # Default vitals summary - always available
    # In a real application, this data would be fetched from the database for the specific patient.
    vitals_summary = {
        'last_blood_pressure': '120/80 mmHg',
        'last_heart_rate': '72 bpm',
        'body_temperature': '36.8°C (98.2°F)',
        'weight': '75 kg',
        'last_updated': '2025-06-11'
    }

    conn = get_db_connection()
    if conn is None:
        flash('Database connection error. Please try again later.', 'error')
        # Ensure all variables are passed even on DB connection failure
        return render_template(
            'patient_dashboard.html',
            username=session['username'],
            patient_uid=patient_uid,
            patient_data=patient_data,
            vitals_summary=vitals_summary,
            upcoming_appointment=upcoming_appointment,
            medications=medications,
            allergies=allergies_list,
            conditions=conditions_list,
            medical_records=medical_records_display,
            appointments=appointments,
            searched_uid=searched_uid,
            patient_info=patient_info,
            next_medication_dose=next_medication_dose,
            message=None
        )

    cur = conn.cursor()
    try:
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
                'emergency_contact_phone': patient_row[7],
                'encrypted_uid': patient_uid # Using plain UID as per request
            }
            session['patient_uid'] = patient_uid # Store patient_uid in session

            # --- Fetch and process active medications for the "My Active Medications" card and Next Dose ---
            cur.execute(
                """SELECT medication_name, dosage, instructions, frequency, alert_times
                   FROM prescribed_medications
                   WHERE patient_uid = %s AND is_active = TRUE AND (end_date IS NULL OR end_date >= CURRENT_DATE)
                   ORDER BY medication_name""",
                (patient_uid,)
            )
            active_meds = cur.fetchall()

            current_datetime = datetime.now()
            soonest_next_dose_time = None

            for med_item in active_meds:
                med_name, dosage, instructions, frequency, alert_times_str = med_item

                medications.append({ # For 'My Active Medications' card
                    'name': med_name,
                    'dosage': dosage,
                    'instructions': instructions,
                    'frequency': frequency,
                    'alert_times': alert_times_str
                })

                if alert_times_str:
                    times = [t.strip() for t in alert_times_str.split(',') if t.strip()]
                    for time_str in times:
                        try:
                            # Combine today's date with the alert time
                            alert_time_obj = datetime.strptime(time_str, '%H:%M').time()
                            alert_datetime_candidate = datetime.combine(current_datetime.date(), alert_time_obj)

                            # If the alert time for today has passed, consider it for tomorrow
                            if alert_datetime_candidate <= current_datetime:
                                next_alert_occurrence = alert_datetime_candidate + timedelta(days=1)
                            else:
                                next_alert_occurrence = alert_datetime_candidate

                            # Find the absolute soonest upcoming dose among all medications
                            if soonest_next_dose_time is None or next_alert_occurrence < soonest_next_dose_time:
                                soonest_next_dose_time = next_alert_occurrence
                                next_medication_dose = { # This assigns to the outer scope variable
                                    'name': med_name,
                                    'dosage': dosage,
                                    'instructions': instructions,
                                    'frequency': frequency,
                                    # Convert to Unix timestamp in milliseconds for JavaScript countdown
                                    'due_datetime_unix': int(next_alert_occurrence.timestamp() * 1000)
                                }
                        except ValueError:
                            # Log malformed time string, but don't stop processing
                            current_app.logger.warning(
                                f"Malformed alert_time '{time_str}' for medication '{med_name}' "
                                f"for patient {patient_uid}"
                            )
                            pass # Skip this malformed time and continue

            # --- Get full medical records for 'My Health Records' section ---
            cur.execute(
                """SELECT mr.id, mr.record_date, mr.disease_history, u.username as doctor_username
                   FROM medical_records mr
                   JOIN users u ON mr.doctor_id = u.id
                   WHERE mr.patient_uid = %s ORDER BY mr.record_date DESC""",
                (patient_uid,)
            )
            raw_medical_records = cur.fetchall()

            for record_row in raw_medical_records:
                record_id, record_date, disease_history_text, doctor_username = record_row
                symptoms_diagnosis, current_allergies = parse_disease_history(disease_history_text)

                # Fetch prescribed medications specifically linked to this medical record
                cur.execute(
                    """SELECT medication_name, dosage, instructions, frequency, alert_times, is_active
                       FROM prescribed_medications
                       WHERE medical_record_id = %s ORDER BY created_at DESC""",
                    (record_id,)
                )
                prescribed_meds_for_record = cur.fetchall()

                medications_list_for_display = []
                for med_item in prescribed_meds_for_record:
                    medications_list_for_display.append({
                        'name': med_item[0],
                        'dosage': med_item[1],
                        'instructions': med_item[2],
                        'frequency': med_item[3],
                        'alert_times': med_item[4],
                        'is_active': med_item[5]
                    })

                # Populate allergies_list and conditions_list
                if current_allergies and current_allergies.lower() != 'none':
                    allergies_list.extend([a.strip() for a in current_allergies.split(',') if a.strip()])

                # Simple keyword-based condition detection (can be more sophisticated)
                if symptoms_diagnosis:
                    if 'diabetes' in symptoms_diagnosis.lower(): conditions_list.append('Diabetes')
                    if 'hypertension' in symptoms_diagnosis.lower(): conditions_list.append('Hypertension')
                    # Add more conditions as needed

                medical_records_display.append({
                    'record_id': record_id,
                    'record_date': record_date,
                    'symptoms_diagnosis': symptoms_diagnosis,
                    'allergies': current_allergies,
                    'doctor_username': doctor_username,
                    'prescriptions': medications_list_for_display
                })

            # Remove duplicates from lists
            allergies_list = list(set(allergies_list))
            conditions_list = list(set(conditions_list))

            # Fetch the single soonest upcoming appointment
            cur.execute(
                """SELECT a.appointment_date, a.reason, a.status, u.username as doctor_username, u.id as doctor_id
                   FROM appointments a
                   JOIN users u ON a.doctor_id = u.id
                   WHERE a.patient_uid = %s AND a.status = 'scheduled' AND a.appointment_date >= NOW()
                   ORDER BY a.appointment_date ASC LIMIT 1""",
                (patient_uid,)
            )
            upcoming_appointment = cur.fetchone()

            # Fetch all appointments (for 'My Health Records' or a separate 'My Appointments' view)
            cur.execute(
                """SELECT a.id, a.appointment_date, a.reason, a.status, u.username as doctor_username
                   FROM appointments a
                   JOIN users u ON a.doctor_id = u.id
                   WHERE a.patient_uid = %s ORDER BY a.appointment_date DESC""",
                (patient_uid,)
            )
            appointments = cur.fetchall()

        else:
            # If patient profile not found for the logged-in user, ensure all relevant variables are explicitly empty/None
            flash("Patient profile not found. Please contact support.", 'error')
            patient_uid = None
            patient_data = {}
            medical_records_display = []
            appointments = []
            medications = []
            allergies_list = []
            conditions_list = []
            upcoming_appointment = None
            next_medication_dose = None

    except psycopg2.Error as e:
        current_app.logger.error(f"Error fetching patient data: {e}")
        flash(f"Error fetching patient data: {e}", 'error')
        # In case of DB error, ensure all variables are explicitly empty/None
        patient_uid = None
        patient_data = {}
        medical_records_display = []
        appointments = []
        medications = []
        allergies_list = []
        conditions_list = []
        upcoming_appointment = None
        next_medication_dose = None
    finally:
        if conn:
            cur.close()
            conn.close()

    # Final return template, all variables should now be guaranteed to be associated with a value
    return render_template(
        'patient_dashboard.html',
        username=session['username'],
        patient_uid=patient_uid,
        patient_data=patient_data,
        vitals_summary=vitals_summary,
        upcoming_appointment=upcoming_appointment,
        medications=medications, # Contains list of dictionaries for active meds card
        allergies=allergies_list,
        conditions=conditions_list,
        medical_records=medical_records_display, # Contains list of dictionaries with nested prescriptions
        appointments=appointments,
        searched_uid=searched_uid,
        patient_info=patient_info,
        next_medication_dose=next_medication_dose,
        message=None # Message handled by flash messages usually, but can be passed explicitly if needed
    )

@patient_bp.route('/patient_search_record', methods=['GET', 'POST'])
def patient_search_record():
    """
    Allows a patient to search for their own records by UID.
    This route is typically accessed from a form within the dashboard.
    """
    if 'user_id' not in session or session['role'] != 'patient':
        flash('Please log in as a patient to access this page.', 'warning')
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    current_patient_uid = session.get('patient_uid') # Get the patient's own UID from session

    searched_uid = None
    patient_info = None
    medical_records_display = []
    appointments = []
    message = None
    next_medication_dose = None # Ensure this is always defined for the template

    if request.method == 'POST':
        input_uid = request.form.get('uid')
        if not input_uid:
            message = "Please enter a UID to search."
        elif input_uid != current_patient_uid:
            message = "You can only view your own records. Please enter your correct UID."
            searched_uid = None # Reset searched_uid if it's not the current patient's
        else:
            searched_uid = input_uid

        if searched_uid: # Only proceed if a valid UID for the current patient is provided
            conn = get_db_connection()
            if conn is None:
                flash('Database connection error. Please try again later.', 'error')
                # Ensure all variables are passed to the template even on DB error
                return render_template(
                    'patient_dashboard.html',
                    username=session['username'],
                    patient_uid=current_patient_uid,
                    searched_uid=searched_uid,
                    patient_info=patient_info,
                    medical_records=[],
                    appointments=[],
                    message=message,
                    vitals_summary={ # Placeholder vitals for search context
                        'last_blood_pressure': '120/80 mmHg',
                        'last_heart_rate': '72 bpm',
                        'body_temperature': '36.8°C (98.2°F)',
                        'weight': '75 kg',
                        'last_updated': '2025-06-11'
                    },
                    upcoming_appointment=None,
                    medications=[],
                    allergies=[],
                    conditions=[],
                    next_medication_dose=next_medication_dose
                )

            cur = conn.cursor()
            try:
                cur.execute(
                    """SELECT uid, name, date_of_birth, gender, contact_info,
                              emergency_contact_name, emergency_contact_relationship, emergency_contact_phone
                       FROM patients WHERE uid = %s""",
                    (searched_uid,)
                )
                patient_row = cur.fetchone()
                if patient_row:
                    # No encryption is needed as per the REMOVED comment in imports
                    patient_info = {
                        'uid': patient_row[0],
                        'name': patient_row[1],
                        'date_of_birth': patient_row[2],
                        'gender': patient_row[3],
                        'contact_info': patient_row[4],
                        'emergency_contact_name': patient_row[5],
                        'emergency_contact_relationship': patient_row[6],
                        'emergency_contact_phone': patient_row[7],
                        'encrypted_uid': patient_row[0] # Use plain UID
                    }

                    cur.execute(
                        """SELECT mr.id, mr.record_date, mr.disease_history, u.username AS doctor_username
                           FROM medical_records mr
                           JOIN users u ON mr.doctor_id = u.id
                           WHERE mr.patient_uid = %s ORDER BY mr.record_date DESC""",
                        (searched_uid,)
                    )
                    raw_medical_records = cur.fetchall()
                    for record_row in raw_medical_records:
                        record_id, record_date, disease_history_text, doctor_username = record_row
                        symptoms_diagnosis, current_allergies = parse_disease_history(disease_history_text)

                        cur.execute(
                            """SELECT medication_name, dosage, instructions, frequency, alert_times, is_active
                               FROM prescribed_medications
                               WHERE medical_record_id = %s ORDER BY created_at DESC""",
                            (record_id,)
                        )
                        prescribed_meds_for_record = cur.fetchall()

                        medications_list_for_display = []
                        for med_item in prescribed_meds_for_record:
                            medications_list_for_display.append({
                                'name': med_item[0],
                                'dosage': med_item[1],
                                'instructions': med_item[2],
                                'frequency': med_item[3],
                                'alert_times': med_item[4],
                                'is_active': med_item[5]
                            })

                        medical_records_display.append({
                            'record_id': record_id,
                            'record_date': record_date,
                            'symptoms_diagnosis': symptoms_diagnosis,
                            'allergies': current_allergies,
                            'doctor_username': doctor_username,
                            'prescriptions': medications_list_for_display
                        })

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
                current_app.logger.error(f"Error searching patient records: {e}")
                flash(f"Error searching records: {e}", 'error')
            finally:
                if conn:
                    cur.close()
                    conn.close()

    # This route will likely always render the dashboard, but with search results if applicable
    return render_template(
        'patient_dashboard.html',
        username=session['username'],
        patient_uid=current_patient_uid, # Pass the logged-in patient's UID
        searched_uid=searched_uid,
        patient_info=patient_info,
        medical_records=medical_records_display,
        appointments=appointments,
        message=message,
        vitals_summary={ # Placeholder vitals for general display or search context
            'last_blood_pressure': '120/80 mmHg',
            'last_heart_rate': '72 bpm',
            'body_temperature': '36.8°C (98.2°F)',
            'weight': '75 kg',
            'last_updated': '2025-06-11'
        },
        upcoming_appointment=None, # In search context, this is not directly populated, so keep None
        medications=[], # Empty for search context as active medications are on primary dashboard load
        allergies=[],
        conditions=[],
        next_medication_dose=next_medication_dose # Pass initialized value
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
            'name': patient_row[0],
            'date_of_birth': patient_row[1].isoformat() if patient_row[1] else '', # Format date for HTML input
            'gender': patient_row[2],
            'contact_info': patient_row[3],
            'emergency_contact_name': patient_row[4],
            'emergency_contact_relationship': patient_row[5],
            'emergency_contact_phone': patient_row[6]
        }

        if request.method == 'POST':
            # Retrieve updated data from the form
            updated_date_of_birth = request.form['date_of_birth']
            updated_gender = request.form['gender']
            updated_contact_info = request.form['contact_info']
            updated_emergency_contact_name = request.form.get('emergency_contact_name')
            updated_emergency_contact_relationship = request.form.get('emergency_contact_relationship')
            updated_emergency_contact_phone = request.form.get('emergency_contact_phone')

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
        current_app.logger.error(f"Error updating patient profile for user {user_id}: {e}")
        flash(f'An error occurred while updating your profile: {e}', 'error')
        conn.rollback() # Rollback changes on error
    finally:
        if conn:
            cur.close()
            conn.close()

    return render_template('patient_edit_profile.html', patient_data=patient_data)


@patient_bp.route('/patient/api/due_medications')
def get_due_medications():
    """
    API endpoint to return a list of active medications that are due or upcoming for the patient.
    Called by client-side JavaScript to power the alert system.
    """
    if 'user_id' not in session or session['role'] != 'patient':
        return jsonify({"error": "Unauthorized access"}), 403

    patient_uid = session.get('patient_uid')
    if not patient_uid:
        return jsonify({"error": "Patient UID not found in session"}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"error": "Database connection error"}), 500

    cur = conn.cursor()
    medications_due = []
    try:
        cur.execute(
            """SELECT medication_name, dosage, instructions, frequency, alert_times
               FROM prescribed_medications
               WHERE patient_uid = %s AND is_active = TRUE AND (end_date IS NULL OR end_date >= CURRENT_DATE)
               ORDER BY medication_name""",
            (patient_uid,)
        )
        active_meds = cur.fetchall()

        current_time_dt = datetime.now()

        for med in active_meds:
            med_name, dosage, instructions, frequency, alert_times_str = med
            if alert_times_str:
                times = [t.strip() for t in alert_times_str.split(',') if t.strip()]
                for time_str in times:
                    try:
                        # Combine today's date with the alert time
                        alert_datetime = datetime.combine(current_time_dt.date(), datetime.strptime(time_str, '%H:%M').time())

                        # If the alert time for today has already passed, set it for tomorrow
                        if alert_datetime < current_time_dt:
                            alert_datetime += timedelta(days=1)

                        # Calculate the time difference from now
                        time_difference = alert_datetime - current_time_dt

                        # Check if the medication is due within a specific window (e.g., 1 minute before to 5 minutes after current time)
                        # This window can be adjusted based on desired alert timing.
                        if timedelta(minutes=-1) <= time_difference <= timedelta(minutes=5):
                             medications_due.append({
                                'name': med_name,
                                'dosage': dosage,
                                'instructions': instructions,
                                'frequency': frequency,
                                'due_time': time_str # Pass the original time string for display
                            })

                    except ValueError:
                        current_app.logger.warning(f"Malformed alert_time '{time_str}' for medication '{med_name}' for patient {patient_uid}")
                        continue # Skip this malformed time and continue with others
    except psycopg2.Error as e:
        current_app.logger.error(f"Database error fetching due medications for {patient_uid}: {e}")
        return jsonify({"error": "Failed to fetch medications"}), 500
    finally:
        if conn:
            cur.close()
            conn.close()

    return jsonify({"due_medications": medications_due})

@patient_bp.route('/patient/diet_planner')
def diet_planner():
    """
    Renders a generic diet planner page for patients.
    Currently redirects to the disease-specific recommender as per the overall flow.
    """
    if 'user_id' not in session or session['role'] != 'patient':
        flash('Please log in as a patient to access this page.', 'warning')
        return redirect(url_for('auth.login'))
    # This route is now a direct alias/redirect for the disease diet recommender
    return redirect(url_for('patient.disease_diet_recommender'))

@patient_bp.route('/patient/disease_diet_recommender')
def disease_diet_recommender():
    """Renders the disease-specific diet recommender page."""
    if 'user_id' not in session or session['role'] != 'patient':
        flash('Please log in as a patient to access this page.', 'warning')
        return redirect(url_for('auth.login'))
    return render_template('diseases.html') # This will render your diseases.html