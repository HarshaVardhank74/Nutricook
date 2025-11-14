import os
import io
import logging
import re # Added for parsing text responses
import json # Added for potentially handling JSON data (though not heavily used here yet)
import datetime # Needed by database functions implicitly
from functools import wraps
import urllib.parse
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, send_from_directory, jsonify) # Added jsonify (though not used in final version below, good practice)
from werkzeug.utils import secure_filename # For file uploads
from PIL import Image # For image handling
from dotenv import load_dotenv
import google.generativeai as genai
import database as db # Import our database functions

# --- Configuration ---
load_dotenv() # Load environment variables from .env file
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "default_fallback_secret_key") # Use a fallback if not set

# --- REMOVE or COMMENT OUT the debug print for production ---
print(f"--- Key being used by app.py: {GEMINI_API_KEY} ---")
# --- END DEBUG STEP ---

# Configure Gemini API
if not GEMINI_API_KEY:
    raise ValueError("Gemini API Key not found or empty. Please set GEMINI_API_KEY in your .env file.")
genai.configure(api_key=GEMINI_API_KEY)

# Configure Flask App
app = Flask(__name__) # Ensures 'app' is defined before routes
app.config['SECRET_KEY'] = FLASK_SECRET_KEY
app.config['UPLOAD_FOLDER'] = 'uploads' # Create an 'uploads' folder in nutricook/
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB upload limit
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Database (ensure schema is up-to-date)
# Running 'python database.py' directly is the recommended way to initialize/update.
# Calling init_db() here might be redundant if you run the script, but harmless.
# db.init_db()

# --- Gemini Models ---
# Use the appropriate models
text_model = genai.GenerativeModel('gemini-1.5-flash') # Or another suitable text model
vision_model = genai.GenerativeModel('gemini-1.5-flash') # Or the multimodal model


# --- Helper Functions ---
# Function to check allowed file extensions (from previous version)
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Decorator to require login (from previous version - MUST be defined before routes using it)
def login_required(f):
    """Decorator to require login for certain routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# NEW Helper Function: Scoring Logic
def calculate_meal_score(assessment_text):
    """Calculates a simple score based on Gemini's text assessment."""
    score = 0
    text = assessment_text.lower()
    # Positive keywords
    if "healthy" in text or "good choice" in text or "well-balanced" in text:
        score += 5
    if "low sugar" in text or "low fat" in text or "low sodium" in text:
        score += 2
    if "high fiber" in text or "good source of protein" in text:
         score += 3

    # Negative keywords
    if "high sugar" in text or "high fat" in text or "high sodium" in text or "unhealthy" in text:
        score -= 4
    if "low protein" in text or "low fiber" in text:
        score -= 1
    if "be cautious" in text or "consider alternatives" in text:
        score -= 2

    # Default small positive score if no strong indicators
    if score == 0 and len(text) > 10: # Basic check if assessment exists
        score = 1

    return score
# --- CONCEPTUAL CODE: Rule-Based Engine ---

def apply_rule_engine(estimated_nutrition, user_profile):
    """
    Applies predefined rules based on nutrition and user profile.

    Args:
        estimated_nutrition (dict): Dictionary with keys like 'calories', 'protein', 'fat', 'carbs', 'sugar', 'sodium', 'fiber'.
                                     Values are estimated numerical amounts.
        user_profile (dict): Dictionary with keys like 'age', 'health_conditions'.
                              'health_conditions' could be a string like "diabetes, hypertension".

    Returns:
        tuple: (list of assessment notes, integer score adjustment)
    """
    notes = []
    score_adjustment = 0
    conditions = user_profile.get('health_conditions', '').lower()

    # --- Example Rules ---

    # Rule 1: High Sugar & Diabetes
    estimated_sugar = estimated_nutrition.get('sugar', 0) # Assume 'sugar' is estimated somehow
    if 'diabetes' in conditions and estimated_sugar > 25:
        notes.append("High estimated sugar content; may need caution for diabetes management.")
        score_adjustment -= 3

    # Rule 2: High Sodium & Hypertension
    estimated_sodium = estimated_nutrition.get('sodium', 0) # Assume 'sodium' is estimated
    if 'hypertension' in conditions and estimated_sodium > 800:
        notes.append("High estimated sodium content; consider for hypertension.")
        score_adjustment -= 2

    # Rule 3: Generally High Fat
    if estimated_nutrition.get('fat', 0) > 35:
        notes.append("This meal appears relatively high in fat.")
        score_adjustment -= 1

    # Rule 4: Good Fiber Source
    if estimated_nutrition.get('fiber', 0) > 7:
        notes.append("Good source of dietary fiber.")
        score_adjustment += 2

    # Rule 5: High Protein
    if estimated_nutrition.get('protein', 0) > 30:
        notes.append("High protein content.")
        score_adjustment += 1

    # Add more rules based on allergies, other conditions, calorie ranges etc.

    print(f"--- Rule Engine Applied ---")
    print(f"Input Nutrition (Partial): { {k: v for k, v in estimated_nutrition.items() if k in ['sugar', 'sodium', 'fat', 'fiber', 'protein']} }")
    print(f"User Conditions: {conditions}")
    print(f"Generated Notes: {notes}")
    print(f"Score Adjustment: {score_adjustment}")
    print(f"--- End Rule Engine ---")

    return notes, score_adjustment

# --- Conceptual Usage ---
# nutrition_example = {'calories': 550, 'protein': 25, 'fat': 38, 'carbs': 40, 'sugar': 15, 'sodium': 900, 'fiber': 8}
# profile_example = {'age': 45, 'health_conditions': 'hypertension'}
# rule_notes, rule_score_adj = apply_rule_engine(nutrition_example, profile_example)
# NEW Helper Function: Parse Gemini Recommendations
def parse_multi_recipes(text_response):
    """Parses text containing multiple recipes, including YouTube search terms."""
    recipes = []
    pattern = re.compile(r"---\s*RECIPE START\s*---(.*?)---\s*RECIPE END\s*---", re.DOTALL | re.IGNORECASE)
    matches = pattern.findall(text_response)

    for match in matches:
        recipe_data = {}
        lines = match.strip().split('\n')
        current_key = None
        current_value = []

        # ADD 'youtube_search_terms' to the map
        key_map = {
            "meal name": "name",
            # "image keywords": "image_keywords", # REMOVE or comment out image keywords
            "youtube search terms": "youtube_search_terms", # ADD This
            "preparation time": "prep_time",
            "taste profile": "taste",
            "ingredients": "ingredients",
            "instructions": "instructions",
            "estimated nutrition": "nutrition"
        }

        # --- Parsing Logic (Mostly the same) ---
        for line in lines:
            line = line.strip()
            if not line: continue
            found_key = False
            for key_text, key_json in key_map.items():
                if line.lower().startswith(key_text + ":"):
                    if current_key:
                         recipe_data[current_key] = "\n".join(current_value).strip()
                    current_key = key_json
                    current_value = [line[len(key_text)+1:].strip()]
                    found_key = True
                    break
            if not found_key and current_key:
                current_value.append(line)
        if current_key:
            recipe_data[current_key] = "\n".join(current_value).strip()

        # --- Post-processing and URL Generation ---
        if recipe_data.get("name") and (recipe_data.get("ingredients") or recipe_data.get("instructions")):
            # Clean up ingredients/instructions (same as before)
            if recipe_data.get("ingredients"):
                 recipe_data["ingredients"] = "\n".join([l.strip().lstrip('-* ') for l in recipe_data["ingredients"].split('\n')])
            if recipe_data.get("instructions"):
                 recipe_data["instructions"] = "\n".join([l.strip().lstrip('0123456789.* ') for l in recipe_data["instructions"].split('\n')])

            # *** ADDED: Create YouTube Search URL ***
            search_terms = recipe_data.get("youtube_search_terms")
            if search_terms:
                # URL encode the search terms for safety
                encoded_terms = urllib.parse.quote_plus(search_terms)
                recipe_data["youtube_search_url"] = f"https://www.youtube.com/results?search_query={encoded_terms}"
            # *** END ADDED ***

            recipes.append(recipe_data)

    # --- Fallback Logic (same as before) ---
    if not recipes and len(text_response) > 50:
        logger.warning("Could not parse multi-recipes, returning raw text.")
        return [{"name": "Recipe Details (Parsing Failed)", "instructions": text_response}]

    logger.info(f"Parsed {len(recipes)} recipes.")
    return recipes
# --- Routes ---

# MODIFIED Route: Index / Home Page
@app.route('/')
def index():
    """Home Page - Shows personalized content if logged in."""
    history_suggestions = None
    user_data = None
    recent_checks = []

    if 'user_id' in session:
        user = db.get_user_by_id(session['user_id']) # Fetch user data, including score
        if user:
            user_data = dict(user) # Convert Row to dict to pass to template
            recent_checks = db.get_user_checked_meals(user['id'], limit=5) # Get recent checks

            # --- Generate History-Based Suggestions ---
            if recent_checks:
                # Get names of recent *positively scored* meals
                healthy_meal_names = list(set([ # Use set to get unique names
                    check['meal_name'] for check in recent_checks
                    if check['assigned_score'] > 0 and check['meal_name']
                ]))

                if healthy_meal_names:
                    try:
                        # Construct prompt for Gemini
                        prompt = f"""
                        Based on the fact that the user recently checked and seemed to enjoy meals like: {', '.join(healthy_meal_names[:3])},
                        suggest 2-3 healthy meal ideas (just names and a one-sentence description for each) that they might also like.
                        Focus on healthiness and variety. Format as a simple list using '*' for bullet points.
                        """
                        response = text_model.generate_content(prompt)
                        history_suggestions = response.text
                    except Exception as e:
                        logger.error(f"Gemini API error (Home Suggestions): {e}")
                        history_suggestions = "Could not load suggestions due to an API error."
                else:
                    history_suggestions = "Check more healthy meals to get personalized suggestions!"

            else:
                 history_suggestions = "Check some meals using the Meal Checker to get personalized suggestions here!"

    # Render index template, passing appropriate data
    return render_template('index.html', current_user=user_data, suggestions=history_suggestions, recent_checks=recent_checks)


# UNCHANGED Route: Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login Page"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = db.get_user_by_username(username) # Fetches user data

        if user and db.check_password(user['password_hash'], password):
            # Store user info in session
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash(f'Welcome back, {user["username"]}!', 'success')
            next_page = request.args.get('next') # Handle redirect after login
            return redirect(next_page or url_for('index'))
        elif user:
            flash('Incorrect password. Please try again.', 'danger')
        else:
            flash('Username not found. Please Sign Up.', 'danger')
        # If login fails, redirect back to login page
        return redirect(url_for('login'))

    # Show the login form for GET request or failed POST
    return render_template('login.html')


# UNCHANGED Route: Signup (already included age/conditions)
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

        # Add user to database (add_user handles hashing)
        if db.add_user(username, password, age, health_conditions):
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
        else:
            # Database error (e.g., concurrency issue, although less likely with SQLite)
            flash('An error occurred during signup. Please try again.', 'danger')
            return redirect(url_for('signup'))

    return render_template('signup.html')


# UNCHANGED Route: Logout
@app.route('/logout')
def logout():
    """Logs the user out"""
    session.pop('user_id', None)
    session.pop('username', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# MODIFIED Route: Recipe Recommender
@app.route('/recommender', methods=['GET', 'POST'])
@login_required
def recommender():
    """Recipe Recommender Page - Generates 3 recipes with YouTube search link."""
    recommendations_list = []
    error_message = None

    if request.method == 'POST':
        try:
            protein = request.form.get('protein', 'any')
            fat = request.form.get('fat', 'any')
            carbs = request.form.get('carbs', 'any')
            fiber = request.form.get('fiber', 'any')
            ingredients = request.form.get('ingredients', 'any')

            # *** UPDATED Prompt: Ask for YouTube Search Terms ***
            prompt = f"""
            Find 3 distinct recipes trying to meet these targets per serving:
            Protein: {protein}g, Fat: {fat}g, Carbs: {carbs}g, Fiber: {fiber}g (use 'any' if flexible).
            Preferences/Exclusions: {ingredients}.

            For EACH recipe, provide the response STRICTLY in this format, using the markers:
            --- RECIPE START ---
            Meal Name: [Name]
            YouTube Search Terms: [Provide 3-5 concise keywords for finding a video tutorial for this specific recipe on YouTube, e.g., "easy chicken parmesan recipe", "how to make vegan lentil soup"]
            Preparation Time: [Estimated time, e.g., 30 minutes]
            Taste Profile: [Brief description, e.g., Savory, slightly spicy, citrusy]
            Ingredients:
            - [Ingredient 1 with quantity]
            - [Ingredient 2 with quantity]
            ...
            Instructions:
            1. [Step 1]
            2. [Step 2]
            ...
            Estimated Nutrition (per serving, approximate): [Provide summary if possible, e.g., ~450 kcal, P:30g F:20g C:40g Fib:8g]
            --- RECIPE END ---
            """
            # *** END UPDATED Prompt ***

            response = text_model.generate_content(prompt)
            recommendations_list = parse_multi_recipes(response.text) # Use the updated parser

            if not recommendations_list and response.text:
                 error_message = "Could not fully parse recipes from AI response. Displaying raw text."
                 recommendations_list = [{"name": "Raw AI Response", "instructions": response.text}]

        except Exception as e:
            logger.error(f"Gemini API error (Recommender): {e}")
            error_message = f"Could not get recommendations from AI: {e}"
            recommendations_list = []

    return render_template('recommender.html', recommendations=recommendations_list, error_message=error_message)

# UNCHANGED Route: Recipe Generator (kept from previous version)
@app.route('/generator', methods=['GET', 'POST'])
@login_required # Or remove if login not strictly needed
def generator():
    """Recipe Generator Page"""
    generated_recipes = None
    if request.method == 'POST':
        try:
            description = request.form.get('description', 'a healthy meal')

            # Original prompt from previous version
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

    # Render template, passing the raw generated text
    return render_template('generator.html', recipes=generated_recipes)


# MODIFIED Route: Meal Checker
@app.route('/checker', methods=['GET', 'POST'])
@login_required # Requires user to be logged in
def checker():
    """Meal Checker Page - Now includes scoring and history logging."""
    analysis_result = None # The raw text response from Gemini
    uploaded_filename = None
    score_change = None # To optionally show score feedback on the page (flash is also used)

    if request.method == 'POST':
        # --- File handling (same as before) ---
        if 'meal_image' not in request.files:
            flash('No file part', 'warning')
            return redirect(request.url)
        file = request.files['meal_image']
        if file.filename == '':
            flash('No selected file', 'warning')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            # Generate a secure filename
            filename = secure_filename(file.filename)
            # Consider making filename unique if storing long-term
            # filename = f"{session['user_id']}_{int(time.time())}_{secure_filename(file.filename)}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            try:
                # Save the uploaded file
                file.save(filepath)
                uploaded_filename = filename # Store filename to display image back

                # --- Get user data (needed for prompt and logging) ---
                user_id = session.get('user_id')
                user = db.get_user_by_id(user_id) # Fetch user including age/conditions
                user_age = user['age'] if user and user['age'] else 'Unknown'
                user_conditions = user['health_conditions'] if user and user['health_conditions'] else 'None specified'

                # --- Prepare image and prompt for Gemini Vision model (same as before) ---
                img = Image.open(filepath)
                prompt_parts = [
                    f"Analyze the food items in this image. Assume a standard single serving size.\n",
                    img, # Send the PIL Image object directly
                    f"\nTasks:\n"
                    f"1. Identify the main meal/dish name.\n"
                    f"2. Estimate the primary ingredients visible.\n"
                    f"3. Estimate the approximate nutritional values (Calories, Protein, Fat, Carbohydrates, Fiber) for this serving.\n"
                    f"4. Based ONLY on the estimated nutritional values and common knowledge about the ingredients, provide a brief healthiness assessment paragraph for a user who is {user_age} years old with the following health considerations: '{user_conditions}'. Focus on potential concerns (e.g., high sugar, high fat, high sodium if apparent) or general suitability. Be cautious and mention these are estimations.\n\n"
                    f"Respond in a clear, structured format using Markdown. Include sections titled exactly: ## Meal Name, ## Estimated Ingredients, ## Estimated Nutrition, ## Healthiness Assessment"
                 ]

                # --- Call Gemini Vision model (same as before) ---
                response = vision_model.generate_content(prompt_parts)
                analysis_result = response.text # Store the full response text

                # --- ADDED: Parse, Score, and Log ---
                # Attempt to extract key parts using regex (adapt patterns if Gemini format differs)
                meal_name_match = re.search(r"## Meal Name\s*\n*(.*)", analysis_result, re.IGNORECASE)
                # Nutrition: Capture everything after 'Nutrition' until the next ## or end of string
                nutrition_match = re.search(r"## Estimated Nutrition\s*\n*(.*?)(?=\n## Healthiness Assessment|\Z)", analysis_result, re.DOTALL | re.IGNORECASE)
                # Assessment: Capture everything after 'Assessment' until end of string
                assessment_match = re.search(r"## Healthiness Assessment\s*\n*(.*)", analysis_result, re.DOTALL | re.IGNORECASE)

                # Get extracted values or defaults
                meal_name = meal_name_match.group(1).strip() if meal_name_match else "Unknown Meal (Parsing Failed)"
                nutrition_text = nutrition_match.group(1).strip() if nutrition_match else "Nutrition info could not be extracted."
                assessment_text = assessment_match.group(1).strip() if assessment_match else "Assessment could not be extracted."

                # Calculate score based on the assessment text
                assigned_score = calculate_meal_score(assessment_text)
                score_change = assigned_score # Store for potential display on page

                # Log the checked meal details to the database
                db.add_checked_meal(
                    user_id=user_id,
                    meal_name=meal_name,
                    nutrition=nutrition_text, # Store extracted nutrition part
                    assessment=assessment_text, # Store extracted assessment part
                    score=assigned_score,
                    image_filename=filename # Store image filename for potential later use
                )

                # Update the user's total cumulative score in the users table
                db.update_user_score(user_id, assigned_score)

                # Flash a message to the user about the score change
                flash(f"Meal checked: '{meal_name}'. Your health score changed by {assigned_score:+}", "info") # Shows + or - sign

            except Exception as e:
                logger.error(f"Meal checker error (Upload/API/Processing): {e}")
                flash(f"Could not analyze meal: {e}", "danger")
                # Keep analysis_result as the error message for display
                analysis_result = f"Error analyzing image: {e}"
            finally:
                # Keep the uploaded file so it can be displayed on the results page
                pass
        else:
            flash('Invalid file type. Allowed types: png, jpg, jpeg, gif, webp', 'warning')
            return redirect(request.url)

    # Render the template, passing the full analysis text, filename, and score change
    return render_template('checker.html', analysis=analysis_result, image_filename=uploaded_filename, score_change=score_change)


# UNCHANGED Route: Serve uploaded images
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    # Serves files from the UPLOAD_FOLDER
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# UNCHANGED Route: About page
@app.route('/about')
def about():
    """About Page"""
    # Renders the static about page
    return render_template('about.html')



# --- Run the App ---
if __name__ == '__main__':
    # Runs the Flask development server
    # Turn off debug mode for production deployment
    app.run(debug=True)