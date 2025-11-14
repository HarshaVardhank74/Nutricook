import os
import io
import logging
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, send_from_directory)
from werkzeug.utils import secure_filename # For file uploads
from PIL import Image # For image handling
from dotenv import load_dotenv
import google.generativeai as genai
import database as db # Import our database functions

# --- Configuration ---
load_dotenv() # Load environment variables from .env file
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "default_fallback_secret_key") # Use a fallback if not set
# --- VERY IMPORTANT DEBUG STEP ---
print(f"--- Key being used by app.py: {GEMINI_API_KEY} ---")
# logger.info(f"--- Key being used by app.py: {GEMINI_API_KEY} ---") # Alternative if you prefer logging
# --- END DEBUG STEP ---
# Configure Gemini API
if not GEMINI_API_KEY:
    raise ValueError("Gemini API Key not found. Please set GEMINI_API_KEY in your .env file.")
genai.configure(api_key=GEMINI_API_KEY)

# Configure Flask App
app = Flask(__name__)
app.config['SECRET_KEY'] = FLASK_SECRET_KEY
app.config['UPLOAD_FOLDER'] = 'uploads' # Create an 'uploads' folder in nutricook/
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB upload limit
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Database (create table if it doesn't exist)
db.init_db()

# --- Gemini Models ---
# Use the appropriate models
text_model = genai.GenerativeModel('gemini-1.5-flash') # Or another suitable text model
vision_model = genai.GenerativeModel('gemini-1.5-flash') # Or the multimodal model

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    """Decorator to require login for certain routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---
@app.route('/')
def index():
    """Home Page"""
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login Page"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = db.get_user_by_username(username)

        if user and db.check_password(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash(f'Welcome back, {user["username"]}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        elif user:
            flash('Incorrect password. Please try again.', 'danger')
        else:
            flash('Username not found. Please Sign Up.', 'danger')
        return redirect(url_for('login')) # Redirect back to login on failure

    # If GET request or failed POST, show the login form
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Signup Page"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        age_str = request.form.get('age') # Use .get for optional fields
        health_conditions = request.form.get('health_conditions', '') # Default to empty string

        # Basic Validation
        if not username or not password or not confirm_password:
            flash('Username and password fields are required.', 'danger')
            return redirect(url_for('signup'))
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('signup'))
        if db.get_user_by_username(username):
             flash('Username already exists. Please choose another.', 'warning')
             return redirect(url_for('signup'))

        age = None
        if age_str:
            try:
                age = int(age_str)
                if age <= 0:
                     flash('Please enter a valid age.', 'danger')
                     return redirect(url_for('signup'))
            except ValueError:
                flash('Age must be a number.', 'danger')
                return redirect(url_for('signup'))

        # Add user to database
        if db.add_user(username, password, age, health_conditions):
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash('An error occurred during signup. Please try again.', 'danger')
            return redirect(url_for('signup')) # Stay on signup page on DB error

    return render_template('signup.html')

@app.route('/logout')
def logout():
    """Logs the user out"""
    session.pop('user_id', None)
    session.pop('username', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/recommender', methods=['GET', 'POST'])
@login_required
def recommender():
    """Recipe Recommender Page"""
    recommendation_result = None
    if request.method == 'POST':
        try:
            protein = request.form.get('protein', 'any')
            fat = request.form.get('fat', 'any')
            carbs = request.form.get('carbs', 'any')
            fiber = request.form.get('fiber', 'any')
            ingredients = request.form.get('ingredients', 'any')

            prompt = f"""
            Find a recipe that tries to meet these nutritional targets per serving:
            Protein: {protein}g (if specified, otherwise flexible)
            Fat: {fat}g (if specified, otherwise flexible)
            Carbohydrates: {carbs}g (if specified, otherwise flexible)
            Fiber: {fiber}g (if specified, otherwise flexible)
            Consider these ingredient preferences/exclusions: {ingredients}

            Please provide the response in the following structured format:
            Meal Name: [Name of the meal]
            Preparation Time: [Estimated time]
            Taste Profile: [e.g., Savory, slightly spicy, sweet]
            Ingredients:
            - [Ingredient 1 with quantity]
            - [Ingredient 2 with quantity]
            ...
            Instructions:
            1. [Step 1]
            2. [Step 2]
            ...
            Estimated Nutrition (per serving, approximate):
            - Calories: X kcal
            - Protein: Y g
            - Fat: Z g
            - Carbs: A g
            - Fiber: B g
            """

            response = text_model.generate_content(prompt)
            recommendation_result = response.text

        except Exception as e:
            logger.error(f"Gemini API error (Recommender): {e}")
            flash(f"Could not get recommendation from AI: {e}", "danger")
            recommendation_result = f"Error: {e}" # Show error on page too

    return render_template('recommender.html', recommendation=recommendation_result)


@app.route('/generator', methods=['GET', 'POST'])
@login_required # Or remove if login not strictly needed
def generator():
    """Recipe Generator Page"""
    generated_recipes = None
    if request.method == 'POST':
        try:
            description = request.form.get('description', 'a healthy meal')

            prompt = f"""
            Generate 3 distinct meal recipe ideas based on the following description: "{description}".
            For each recipe, provide clearly separated sections for:
            1.  **Meal Name:**
            2.  **Brief Description:**
            3.  **Key Ingredients:** (List format)
            4.  **Simple Instructions:** (Numbered list format)

            Make the output easy to read. Separate each recipe clearly (e.g., using --- or Recipe X).
            """

            response = text_model.generate_content(prompt)
            generated_recipes = response.text

        except Exception as e:
            logger.error(f"Gemini API error (Generator): {e}")
            flash(f"Could not generate recipes from AI: {e}", "danger")
            generated_recipes = f"Error: {e}"

    return render_template('generator.html', recipes=generated_recipes)


@app.route('/checker', methods=['GET', 'POST'])
@login_required
def checker():
    """Meal Checker Page"""
    analysis_result = None
    uploaded_filename = None

    if request.method == 'POST':
        # Check if the post request has the file part
        if 'meal_image' not in request.files:
            flash('No file part', 'warning')
            return redirect(request.url)
        file = request.files['meal_image']
        # If the user does not select a file, the browser submits an empty file without a filename.
        if file.filename == '':
            flash('No selected file', 'warning')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(filepath)
                uploaded_filename = filename # To potentially display the image back

                # Get user data
                user_id = session.get('user_id')
                user = db.get_user_by_id(user_id)
                user_age = user['age'] if user and user['age'] else 'Unknown'
                user_conditions = user['health_conditions'] if user and user['health_conditions'] else 'None specified'

                # Prepare image for Gemini
                img = Image.open(filepath)
                # Convert image to bytes (Gemini API often needs bytes)
                # img_byte_arr = io.BytesIO()
                # img_format = img.format if img.format else 'JPEG' # Use original format or default
                # img.save(img_byte_arr, format=img_format)
                # img_byte_arr = img_byte_arr.getvalue()

                # Prepare prompt for multimodal model
                prompt_parts = [
                    f"Analyze the food items in this image. Assume a standard single serving size.\n",
                    img, # Send the PIL Image object directly
                    f"\nTasks:\n"
                    f"1. Identify the main meal/dish name.\n"
                    f"2. Estimate the primary ingredients visible.\n"
                    f"3. Estimate the approximate nutritional values (Calories, Protein, Fat, Carbohydrates, Fiber) for this serving.\n"
                    f"4. Based ONLY on the estimated nutritional values and common knowledge about the ingredients, provide a brief healthiness assessment for a user who is {user_age} years old with the following health considerations: '{user_conditions}'. Focus on potential concerns (e.g., high sugar, high fat, high sodium if apparent) or general suitability. Be cautious and mention these are estimations.\n\n"
                    f"Respond in a clear, structured format. Use Markdown for clarity if possible. Example section headings: Meal Name, Estimated Ingredients, Estimated Nutrition, Healthiness Assessment."
                 ]


                # Call Gemini Vision model
                response = vision_model.generate_content(prompt_parts)
                analysis_result = response.text

            except Exception as e:
                logger.error(f"Meal checker error (Upload/API): {e}")
                flash(f"Could not analyze meal: {e}", "danger")
                analysis_result = f"Error analyzing image: {e}"
            finally:
                # Optional: Clean up uploaded file after analysis?
                # Or keep it if you want to display it
                # if os.path.exists(filepath):
                #     os.remove(filepath)
                pass

        else:
            flash('Invalid file type. Allowed types: png, jpg, jpeg, gif, webp', 'warning')
            return redirect(request.url)

    return render_template('checker.html', analysis=analysis_result, image_filename=uploaded_filename)

# Route to serve uploaded images (needed for checker results page)
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/about')
def about():
    """About Page"""
    return render_template('about.html')


# --- Run the App ---
if __name__ == '__main__':
    app.run(debug=True) # Turn off debug mode for production