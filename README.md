
# NutriCook: Your Personalized Health & Recipe Assistant

NutriCook is a comprehensive web application designed to help users manage their dietary intake, discover new recipes, and track their health progress. It leverages advanced AI capabilities to provide personalized recommendations and insights, making healthy eating accessible and enjoyable.

## Features

### User Profiles
- **Secure Sign-up and Login:** Users can create secure accounts and log in to access their personalized features.
- **Health Data Storage:** Stores essential user information, including age and health conditions, to tailor recommendations.
- **Health Score Tracking:** Monitors and displays individual health scores, providing a clear overview of progress over time.

### Recipe Recommender
- **Personalized Suggestions:** Recommends recipes based on user-defined nutritional targets (e.g., protein, fat, carbohydrates).
- **Ingredient-Based Search:** Helps users find recipes that can be made with ingredients they currently have on hand, minimizing waste and simplifying meal planning.

### Recipe Generator
- **Unique Recipe Ideas:** Generates innovative and unique recipe concepts, inspiring culinary creativity.
- **Flexible Input:** Supports both text and voice descriptions for generating new recipe ideas, offering convenience and accessibility.

### AI Meal Checker
- **Photo Analysis:** Allows users to upload photos of their meals for intelligent analysis.
- **Dish Identification & Nutrition Estimation:** Accurately identifies dishes and provides estimated nutritional information (calories, macros, etc.).
- **Personalized Health Assessments:** Offers tailored feedback and health assessments based on the analyzed meals, guiding users towards better dietary choices.

### Health Tracking
- **Nutritional Scoring:** Automatically scores meals based on their nutritional quality, helping users understand the impact of their food choices.
- **Homepage Suggestions:** Provides personalized health and dietary suggestions directly on the user's homepage, ensuring continuous guidance.

## Technologies Used

- **Frontend:** HTML, CSS, JavaScript (based on the `static` and `templates` folders)
- **Backend:** Python (with `app.py`, `database.py`)
- **Database:** SQLite (with `nutricook.db`)
- **Web Framework:** Flask (commonly used with this file structure)

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git
    cd YOUR_REPOSITORY_NAME
    ```
2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: `venv\Scripts\activate`
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    (Ensure you have a `requirements.txt` file listing all your Python dependencies.)
4.  **Run the application:**
    ```bash
    python app.py
    ```

## Contributing

We welcome contributions! Please feel free to fork the repository, make changes, and submit a pull request.

