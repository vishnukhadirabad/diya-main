from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import json
import subprocess
import os
from functools import wraps
from datetime import datetime
import logging
from paths import BASE_DIR, project_path

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Needed for flashing messages
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{project_path('users.db').as_posix()}"
app.config['SECRET_KEY'] = 'your_secret_key_here'


def run_project_script(script_name):
    return subprocess.call(f'./{script_name}', shell=True, cwd=BASE_DIR)

# Database connection
def get_db_connection():
    conn = sqlite3.connect(project_path('database.db'))
    conn.row_factory = sqlite3.Row
    return conn


# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            flash('You need to be logged in to access this page.', 'warning')
            return redirect(url_for('sensor_check'))
        return f(*args, **kwargs)
    return decorated_function



# Route for Sign-Up Page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('signup'))

        # Check if the user already exists
        conn = get_db_connection()
        existing_user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if existing_user:
            flash('Username already exists!', 'danger')
            return redirect(url_for('signup'))

        # Hash the password before storing it
        hashed_password = generate_password_hash(password)

        # Create new user and store in the database
        conn = get_db_connection()
        conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)', 
                     (username, email, hashed_password))
        conn.commit()
        conn.close()

        flash('Sign-Up Successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user and check_password_hash(user['password'], password):
            # Save login time
            login_time = datetime.now()
            conn.execute('UPDATE users SET login_time = ? WHERE username = ?', (login_time, username))
            conn.commit()

            # Store user information in the session
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['logged_in'] = True

            conn.close()
            flash('Login successful!', 'success')
            return redirect(url_for('instructions'))  # Redirect to instructions page
        else:
            conn.close()
            flash('Login failed. Please check your credentials and try again.', 'danger')
            return redirect(url_for('login'))

    # If GET method, render the login page
    return render_template('login.html')


# Logout Route
@app.route('/logout', methods=['POST'])
@login_required
def logout():
    # Update the user's logout time in the database
    user_id = session.get('user_id')
    if user_id:
        logout_time = datetime.now()

        conn = get_db_connection()
        conn.execute('UPDATE users SET logout_time = ? WHERE id = ?', (logout_time, user_id))
        conn.commit()
        conn.close()

    session.clear()  # Clear all session data
    flash('You have been logged out.', 'info')
    return redirect(url_for('sensor_check'))

@app.route('/instructions')
def instructions():
    return render_template('instructions.html')

@app.route('/view_users')
def view_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()
    conn.close()
    return render_template('view_users.html', users=users)


def verify_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
    user = cursor.fetchone()
    conn.close()
    return user

def log_meditation_session(user_id, date_time, duration, score):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO meditation_sessions (user_id, date_time, duration, score) VALUES (?, ?, ?, ?)',
                   (user_id, date_time, duration, score))
    conn.commit()
    conn.close()

def log_feedback(user_id, session_id, before_meditation, after_meditation, helpful, suggestions):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO feedback (user_id, session_id, before_meditation, after_meditation, helpful, suggestions) VALUES (?, ?, ?, ?, ?, ?)',
                   (user_id, session_id, before_meditation, after_meditation, helpful, suggestions))
    conn.commit()
    conn.close()



@app.route('/log_session', methods=['POST'])
def log_session():
    user_id = request.form['user_id']
    date_time = request.form['date_time']
    duration = request.form['duration']
    score = request.form['score']
    log_meditation_session(user_id, date_time, duration, score)
    return redirect(url_for('meditation_score'))

@app.route('/submit_feedback', methods=['POST'])
@login_required
def submit_feedback():
    # Try to get user_id from the form, otherwise fall back to session
    user_id = request.form.get('user_id') or session.get('user_id')

    if not user_id:
        logging.error(f"User ID not found in form or session.")
        flash('User ID is missing, please try again.', 'danger')
        return redirect(url_for('feedback'))

    session_id = request.form.get('session_id')
    before_meditation = request.form.get('q1')
    after_meditation = request.form.get('q2')
    helpful = request.form.get('q3')
    suggestions = request.form.get('q4')

    # Fetch user information (username) from the database
    conn = get_db_connection()
    user_info = conn.execute('SELECT username, feedback FROM users WHERE id = ?', (user_id,)).fetchone()

    if user_info:
        username = user_info['username']
        user_feedback = user_info['feedback']
        logging.info(f"User ID: {user_id}, Username: {username}, Session ID: {session_id}")
    else:
        logging.error(f"User ID {user_id} not found.")
        flash('User not found.', 'danger')
        return redirect(url_for('feedback'))

    # Create new feedback entry
    new_feedback = {
        'session_id': session_id,
        'before_meditation': before_meditation,
        'after_meditation': after_meditation,
        'helpful': helpful,
        'suggestions': suggestions
    }

    # Parse or initialize the feedback list
    if user_feedback:
        try:
            feedback_list = json.loads(user_feedback)
            logging.info(f"Existing feedback for user {username}: {feedback_list}")
        except json.JSONDecodeError:
            logging.error(f"Failed to parse existing feedback for user {username}, initializing empty list")
            feedback_list = []
    else:
        logging.info(f"No existing feedback found for user {username}, initializing empty list")
        feedback_list = []

    # Append the new feedback to the list
    feedback_list.append(new_feedback)

    # Log feedback after appending
    logging.info(f"New feedback for user {username} after appending: {feedback_list}")

    # Update the user's feedback field in the database with the appended list
    conn.execute('UPDATE users SET feedback = ? WHERE id = ?', (json.dumps(feedback_list), user_id))
    conn.commit()
    conn.close()

    return redirect(url_for('feedback'))




# Home route

# Home route (modified to redirect to sensor_check directly)
@app.route('/')
def home():
    return redirect(url_for('sensor_check'))  # Redirect directly to sensor_check page


# Sensor check route
@app.route('/sensor_check')
def sensor_check():
    return render_template('sensor_check.html')

# Start meditation route
@app.route('/start_meditation')
def start_meditation():
    return render_template('start_meditation.html')

# Analysis page route
@app.route('/analysis')
def analysis():
    return render_template('analysis.html')

# Analysis page route
@app.route('/depthanalysis')
def deothanalysis():
    return render_template('depthanalysis.html')

# Feedback route
@app.route('/feedback')
def feedback():
    return render_template('feedback.html')


# Define your routes for the buttons
@app.route('/start')
def start():
    run_project_script('start')
    return redirect(url_for('main'))

@app.route('/posture_analysis')
def analyze_posture():
    run_project_script('analyze_posture')
    return redirect(url_for('main'))

@app.route('/thermal_analysis')
def thermal_analysis():
    return render_template('thermal_analysis.html')

@app.route('/radar_analysis')
def radar_analysis():
    return render_template('radar_analysis.html')

@app.route('/check_radar', methods=['POST'])
def check_radar():
    run_project_script('check_radar')
    return redirect(url_for('sensor_check'))

@app.route('/check_visual1', methods=['POST'])
def check_visual1():
    run_project_script('checkvisual1.sh')
    return redirect(url_for('sensor_check'))

@app.route('/check_thermal', methods=['POST'])
def check_thermal():
    run_project_script('Check_thermalupdated')
    return redirect(url_for('sensor_check'))

@app.route('/check_visual2', methods=['POST'])
def check_visual2():
    run_project_script('checkvisual2.sh')
    return redirect(url_for('sensor_check'))

@app.route('/check_depth', methods=['POST'])
def check_depth():
    run_project_script('depthstart')
    return redirect(url_for('sensor_check'))



@app.route('/check_all_sensors', methods=['POST'])
def check_all_sensors():
    run_project_script('run_all_cam.sh')
    return redirect(url_for('sensor_check'))

@app.route('/next', methods=['POST'])
def next():
    run_project_script('next')
    return redirect(url_for('sensor_check'))


@app.route('/radar_analysis', methods=['POST'])
def radar_analysis1():
        # Call the bash script
        run_project_script('Radar_analysis')
        # Redirect to a different route after execution
        return redirect(url_for('radar_analysis'))  
  

@app.route('/start-background-task', methods=['POST'])
def start_background_task():
    try:
        # Run the bash script and wait for it to complete
        subprocess.run('./sequence9', shell=True, check=True, cwd=BASE_DIR)
        return redirect('/sensor_check')  # Redirect to another endpoint after completion
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/posture_analysis', methods=['POST'])
def posture_analysis1():
        # Call the bash script
        run_project_script('posture')
        # Redirect to a different route after execution
        return redirect(url_for('analysis'))  

@app.route('/gaze_analysis', methods=['POST'])
def gaze_analysis():
        # Call the bash script
        run_project_script('gaze')
        # Redirect to a different route after execution
        return redirect(url_for('analysis')) 


@app.route('/thermal_analysis', methods=['POST'])
def thermal_analysis1():
        # Call the bash script
        run_project_script('morphing')
        # Redirect to a different route after execution
        return redirect(url_for('thermal_analysis')) 

@app.route('/depthanalysis', methods=['POST'])
def depthanalysis():
        # Call the bash script
        run_project_script('checking')
        # Redirect to a different route after execution
        return redirect(url_for('depthanalysis')) 

@app.route('/score_analysis', methods=['POST'])
def depth_analysis():
    # Call the bash script
    run_project_script('show_score')
    # Redirect to a different route after execution
    return redirect(url_for('depthanalysis'))  # Use the function name, not the URL



@app.route('/meditation_score')
def meditation_score():
    return render_template('meditation_score.html')

@app.route('/get_meditation_score')
def get_meditation_score():
    with open(project_path('meditation_score.json'), 'r') as f:
        data = json.load(f)
    return jsonify(data)

@app.route('/exit')
def exit_app():
    return redirect(url_for('sensor_check'))

if __name__ == '__main__':
    app.run(debug=True)

