import uuid
import psycopg2
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from backend.models import get_db_connection, hash_password, check_password

# Create a Blueprint for authentication routes
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    if 'user_id' in session: # Already logged in
        # Redirect based on role if already logged in
        if session['role'] == 'patient':
            return redirect(url_for('patient.patient_dashboard'))
        elif session['role'] == 'doctor':
            return redirect(url_for('doctor.doctor_dashboard'))
        return redirect(url_for('index')) # Fallback for unknown roles

    # Get the intended role from query parameters for display purposes
    target_role = request.args.get('role', 'unknown') # Default to 'unknown' if not specified

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        if conn is None:
            flash('Database connection error. Please try again later.', 'error')
            return render_template('login.html', target_role=target_role) # Pass role back on error

        cur = conn.cursor()
        try:
            cur.execute("SELECT id, username, password, role FROM users WHERE username = %s", (username,))
            user = cur.fetchone()
            cur.close()
            conn.close()

            if user and check_password(user[2], password): # Use check_password from models
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['role'] = user[3] # The actual role from the DB

                flash(f'Logged in successfully as {session["role"]}!', 'success')
                if session['role'] == 'patient':
                    return redirect(url_for('patient.patient_dashboard'))
                elif session['role'] == 'doctor':
                    return redirect(url_for('doctor.doctor_dashboard'))
            else:
                flash('Invalid username or password.', 'error')
        except psycopg2.Error as e:
            flash(f'An error occurred during login: {e}', 'error')
            conn.rollback() # Rollback any potential incomplete transactions
        finally:
            if conn:
                conn.close()

    return render_template('login.html', target_role=target_role)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Handles both patient and doctor registration."""
    if 'user_id' in session: # Already logged in
        return redirect(url_for('index'))

    # Get the intended role from query parameters (from landing page link)
    target_role = request.args.get('role')

    if request.method == 'POST':
        # Get role from hidden form field
        user_role = request.form.get('role')
        username = request.form['username']
        password = request.form['password']
        name = request.form['name']
        contact_info = request.form['contact_info']

        # Doctor-specific fields
        specialization = request.form.get('specialization')
        license_number = request.form.get('license_number')

        # Patient-specific fields
        date_of_birth = request.form.get('date_of_birth')
        gender = request.form.get('gender')
        emergency_contact_name = request.form.get('emergency_contact_name')
        emergency_contact_relationship = request.form.get('emergency_contact_relationship')
        emergency_contact_phone = request.form.get('emergency_contact_phone')


        conn = get_db_connection()
        if conn is None:
            flash('Database connection error. Please try again later.', 'error')
            # Pass form data back to template on error
            return render_template(
                'register.html',
                form_data=request.form,
                target_role=user_role # Use the role from the form submission
            )

        cur = conn.cursor()
        try:
            # Check if username already exists
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cur.fetchone():
                flash('Username already exists. Please choose a different one.', 'error')
                return render_template(
                    'register.html',
                    form_data=request.form,
                    target_role=user_role
                )

            hashed_password = hash_password(password)

            # Insert into users table
            cur.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s) RETURNING id",
                (username, hashed_password, user_role)
            )
            user_id = cur.fetchone()[0]

            if user_role == 'patient':
                # Generate a unique patient ID (UUID)
                patient_uid = str(uuid.uuid4())
                # Insert into patients table
                cur.execute(
                    """INSERT INTO patients (uid, user_id, name, date_of_birth, gender, contact_info,
                                           emergency_contact_name, emergency_contact_relationship, emergency_contact_phone)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (patient_uid, user_id, name, date_of_birth, gender, contact_info,
                     emergency_contact_name, emergency_contact_relationship, emergency_contact_phone)
                )
                conn.commit()
                flash('Patient registration successful! You can now log in.', 'success')
                return redirect(url_for('auth.login', role='patient'))

            elif user_role == 'doctor':
                # Check for unique license number for doctors
                cur.execute("SELECT id FROM doctors WHERE license_number = %s", (license_number,))
                if cur.fetchone():
                    # Rollback user creation as doctor details cannot be added
                    conn.rollback()
                    flash('Medical license number already registered. Please use a unique one.', 'error')
                    return render_template(
                        'register.html',
                        form_data=request.form,
                        target_role=user_role
                    )

                # Insert into doctors table
                cur.execute(
                    """INSERT INTO doctors (user_id, name, specialization, license_number, contact_info)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (user_id, name, specialization, license_number, contact_info)
                )
                conn.commit()
                flash('Doctor registration successful! You can now log in.', 'success')
                return redirect(url_for('auth.login', role='doctor'))
            else:
                flash('Invalid registration role.', 'error')
                conn.rollback() # Rollback user creation
                return render_template(
                    'register.html',
                    form_data=request.form,
                    target_role='unknown'
                )

        except psycopg2.Error as e:
            flash(f'An error occurred during registration: {e}', 'error')
            conn.rollback() # Rollback any potential incomplete transactions
        finally:
            if conn:
                cur.close()
                conn.close()

    # Initial GET request (or error re-render)
    # Determine the title and default fields based on target_role from URL args
    if target_role == 'patient':
        page_title = "Patient Self-Registration"
        # No special fields, just basic patient fields
    elif target_role == 'doctor':
        page_title = "Doctor Self-Registration"
        # Specialization, License Number
    else:
        page_title = "User Registration"
        target_role = 'patient' # Default to patient registration if role not specified

    return render_template('register.html', page_title=page_title, target_role=target_role, form_data={})

@auth_bp.route('/logout')
def logout():
    """Logs out the current user."""
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('role', None)
    session.pop('patient_uid', None) # Clear patient_uid from session
    flash('You have been logged out.', 'info')
    return redirect(url_for('index')) # Redirect to the new landing page
