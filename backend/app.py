import os
from flask import Flask, render_template, session, redirect, url_for
from flask_session import Session # Import Flask-Session
from backend.config import Config # Import your Config class

# Import Blueprints
from backend.routes.auth import auth_bp
from backend.routes.patient import patient_bp, parse_disease_history # Import parse_disease_history
from backend.routes.doctor import doctor_bp
from backend.routes.appointment import appointment_bp
from backend.routes.qr_code import qr_bp

def create_app():
    app = Flask(__name__,
                template_folder='templates', # Specify templates folder relative to backend/
                static_folder='static')      # Specify static folder relative to backend/
    app.config.from_object(Config)

    # Initialize Flask-Session
    Session(app)

    # Ensure the session file directory exists
    if not os.path.exists(app.config['SESSION_FILE_DIR']):
        os.makedirs(app.config['SESSION_FILE_DIR'])
        print(f"Created session directory: {app.config['SESSION_FILE_DIR']}") # For debugging

    # Make parse_disease_history available as a global function in Jinja2 templates
    app.jinja_env.globals['parse_disease_history'] = parse_disease_history


    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(appointment_bp)
    app.register_blueprint(qr_bp)

    # Main application routes
    @app.route('/')
    def index():
        """
        Renders the landing page for role selection.
        If already logged in, redirects to the respective dashboard.
        """
        if 'user_id' in session:
            if session['role'] == 'patient':
                return redirect(url_for('patient.patient_dashboard'))
            elif session['role'] == 'doctor':
                return redirect(url_for('doctor.doctor_dashboard'))
        return render_template('landing_page.html') # Render the new landing page

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
