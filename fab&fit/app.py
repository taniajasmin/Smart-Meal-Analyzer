import google.generativeai as genai
import io
from PIL import Image
import re
import os
from dotenv import load_dotenv
from datetime import datetime
import logging
import time
from tenacity import retry, stop_after_attempt, wait_exponential
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('fab_and_fit.log'),
        logging.StreamHandler()
    ]
)

load_dotenv()

try:
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY not found in .env file.")
    genai.configure(api_key=gemini_api_key)
    logging.info("Gemini API configured successfully.")
except Exception as e:
    logging.error(f"Error loading Gemini API key: {str(e)}")
    exit(1)

gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# Flask app setup
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Replace with a secure key
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def analyze_food_image(image_data):
    if not image_data:
        logging.warning("No image data provided for analysis.")
        return None
    
    try:
        image = Image.open(io.BytesIO(image_data))
        if image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        logging.info("Image processed in memory for analysis.")
        
        prompt = """
        You are a professional nutritionist analyzing a high-resolution image of a meal. Your task is to:
        1. Identify the primary food item(s) in the image and provide a descriptive name for the meal.
        2. Estimate the total serving size in grams based on visual cues (e.g., plate size, food proportions).
        3. List the visible ingredients with their approximate quantities in grams or common measurements (e.g., 1 slice, 2 tbsp).
        4. Avoid generic descriptions or disclaimers; provide only the requested data.

        Format your response strictly as follows (no additional text or notes):
        Meal Name: [Descriptive Meal Name] ([Estimated Total Weight] g)
        Ingredients:
        - [Ingredient 1]: [Quantity]
        - [Ingredient 2]: [Quantity]
        """
        
        logging.info("Sending image analysis request to Gemini...")
        start_time = time.time()
        response = gemini_model.generate_content([prompt, image])
        if response and response.text:
            logging.info(f"Response received from Gemini in {time.time() - start_time:.2f} seconds")
            return response.text
        logging.warning("No valid response received from Gemini for image analysis.")
        return None
    except Exception as e:
        logging.error(f"Error during image analysis: {e}")
        raise

def format_food_details(response_text):
    """Parse Gemini response for food details with robust error handling."""
    if not response_text:
        logging.warning("Empty response text for food details.")
        return "Unknown Food", "100", []
    
    try:
        lines = response_text.split('\n')
        meal_name = "Unknown Food"
        serving_size = "100"
        ingredients = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('Meal Name:'):
                parts = line.replace('Meal Name:', '').strip().split('(')
                if len(parts) > 0:
                    meal_name = parts[0].strip()
                if len(parts) > 1:
                    size = re.search(r'(\d+)\s*g', parts[1])
                    if size:
                        serving_size = size.group(1)
            elif line.startswith('-') and ':' in line:
                ingredients.append(line.strip())
        
        if not ingredients:
            logging.warning("No ingredients parsed from response.")
        return meal_name, serving_size, ingredients
    except Exception as e:
        logging.error(f"Error parsing food details: {e}")
        return "Unknown Food", "100", []

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def get_nutritional_data(food_item, ingredients):
    """Retrieve nutritional data using Gemini with a detailed prompt."""
    prompt = f"""
    You are a certified nutritionist tasked with providing accurate nutritional information for a specific meal. Analyze the following meal and its ingredients to estimate the macronutrient content per serving. Use standard nutritional databases or scientific references to ensure precision. If exact weights or details are not provided, make reasonable assumptions based on typical portion sizes (e.g., assume a standard weight for items like a chicken drumstick or burger bun if not specified). Do not include any disclaimers, explanations, or requests for more information—provide estimates even if assumptions are needed. Strictly adhere to the format below with no additional text.

    Meal: {food_item}
    Ingredients (per serving):
    {', '.join(ingredients) if ingredients else 'Not specified'}

    Provide the nutritional breakdown in the following strict format (no additional text or deviations):
    - Calories: [Estimated Value] kcal
    - Carbohydrates: [Estimated Value] g
    - Protein: [Estimated Value] g
    - Fat: [Estimated Value] g
    - Fiber: [Estimated Value] g
    """
    try:
        logging.info(f"Requesting nutritional data for {food_item}...")
        start_time = time.time()
        response = gemini_model.generate_content(prompt)
        if response and response.text:
            logging.info(f"Nutritional data received in {time.time() - start_time:.2f} seconds")
            logging.info(f"Raw nutritional response: {response.text}")
            return response.text
        logging.warning("No valid nutritional data received from Gemini.")
        return "Error retrieving nutritional data"
    except Exception as e:
        logging.error(f"Error retrieving nutritional data: {str(e)}")
        raise

class UserProfile:
    def __init__(self):
        self.gender = self.date_of_birth = self.height = self.weight = None
        self.height_unit = self.weight_unit = self.age = self.bmi = self.bmr = None
        self.activity_level = self.fitness_goal = self.vegan_preference = None

    def convert_height(self, height, unit):
        if unit == 'ft':
            feet, inches = map(float, height.split('.'))
            return (feet * 12 + inches) * 2.54
        elif unit == 'cm':
            return float(height)
        raise ValueError("Invalid height unit")

    def convert_weight(self, weight, unit):
        if unit == 'lbs':
            return float(weight) * 0.453592
        elif unit == 'kg':
            return float(weight)
        raise ValueError("Invalid weight unit")

    def calculate_age(self, dob):
        born = datetime.strptime(dob, "%Y-%m-%d")
        today = datetime.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

    def calculate_bmi(self):
        if not self.height or not self.weight:
            return None
        self.bmi = round(self.weight / ((self.height/100) ** 2), 2)
        return self.bmi

    def calculate_bmr(self):
        if not all([self.height, self.weight, self.age, self.gender]):
            return None
        bmr = (10 * self.weight + 6.25 * self.height - 5 * self.age + 5) if self.gender.lower() == 'male' else (10 * self.weight + 6.25 * self.height - 5 * self.age - 161)
        self.bmr = round(bmr)
        return self.bmr

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def generate_personalized_meal_plan(self):
        """Generate a personalized meal plan with a detailed and structured prompt."""
        vegan_note = "Ensure all recommendations are strictly vegan with no animal products or by-products." if self.vegan_preference else "Non-vegan options are acceptable, including meat, dairy, and eggs if nutritionally appropriate."
        prompt = f"""
        You are a registered dietitian with expertise in personalized nutrition planning. Your task is to create a 1-day meal plan tailored to the user's physiological data, lifestyle, and dietary preferences. Ensure the plan aligns with the user's fitness goals by calculating appropriate calorie intake and macronutrient distribution. Provide detailed and actionable meal suggestions with precise portion sizes and nutritional benefits.

        User Profile:
        - Gender: {self.gender}
        - Age: {self.age}
        - Height: {self.height} cm
        - Weight: {self.weight} kg
        - BMI: {self.bmi}
        - BMR: {self.bmr} kcal/day
        - Activity Level: {self.activity_level} (adjust calorie needs accordingly)
        - Fitness Goal: {self.fitness_goal} (focus meal composition to support this goal)
        - Dietary Preference: {vegan_note}

        Instructions:
        1. Estimate daily calorie needs based on BMR and activity level, then distribute across meals to support the fitness goal (e.g., calorie deficit for weight loss, surplus for muscle gain).
        2. Structure the meal plan into Breakfast, Lunch, Dinner, and optional Snacks.
        3. For each meal/snack, provide:
           - A descriptive meal name relevant to the user's dietary preference.
           - Key ingredients with specific quantities (e.g., 1 cup, 2 slices, 100g).
           - Estimated calories per meal/snack.
           - Macronutrient breakdown (Carbohydrates, Protein, Fat in grams).
           - A concise health benefit explanation highlighting nutritional value or goal alignment.
        4. Ensure the total daily calories are appropriate for the user's profile and goal.
        5. Format the output cleanly without repetitive text or unnecessary disclaimers.

        Output Format:
        Personalized Meal Plan for a {self.activity_level} {self.age}-Year-Old {self.gender.capitalize()} ({self.fitness_goal})
        Total Estimated Calories: [Total kcal/day] (based on BMR and activity level)

        1. Breakfast ([Estimated Calories] kcal)
        - Meal Name: [Name]
        - Key Ingredients: [List with quantities]
        - Macronutrients: Carbs: [X]g, Protein: [X]g, Fat: [X]g
        - Health Benefit: [Brief explanation]

        2. Lunch ([Estimated Calories] kcal)
        - Meal Name: [Name]
        - Key Ingredients: [List with quantities]
        - Macronutrients: Carbs: [X]g, Protein: [X]g, Fat: [X]g
        - Health Benefit: [Brief explanation]

        3. Dinner ([Estimated Calories] kcal)
        - Meal Name: [Name]
        - Key Ingredients: [List with quantities]
        - Macronutrients: Carbs: [X]g, Protein: [X]g, Fat: [X]g
        - Health Benefit: [Brief explanation]

        4. Snacks (Optional, [Estimated Calories] kcal each)
        - Snack 1: [Name], Ingredients: [List], Macros: Carbs: [X]g, Protein: [X]g, Fat: [X]g, Benefit: [Brief explanation]
        - Snack 2: [Name], Ingredients: [List], Macros: Carbs: [X]g, Protein: [X]g, Fat: [X]g, Benefit: [Brief explanation]

        Important Notes:
        - Hydration is key; aim for 2-3 liters of water daily.
        - Adjust portion sizes based on hunger cues.
        - Consult a dietitian for long-term personalized advice.
        """
        try:
            logging.info("Generating personalized meal plan...")
            start_time = time.time()
            response = gemini_model.generate_content(prompt)
            if response and response.text:
                logging.info(f"Meal plan generated in {time.time() - start_time:.2f} seconds")
                lines = response.text.split('\n')
                unique_lines = []
                [unique_lines.append(line.strip()) for line in lines if line.strip() and line.strip() not in unique_lines]
                return '\n'.join(unique_lines)
            logging.warning("No valid meal plan received from Gemini.")
            return "Error generating meal plan"
        except Exception as e:
            logging.error(f"Error generating meal plan: {e}")
            raise

def parse_nutritional_data(nutritional_data):
    """Parse nutritional data for display."""
    nutrients = {'Calories': '', 'Carbohydrate': '', 'Protein': '', 'Fat': '', 'Fiber': ''}
    found_data = False
    
    for nutrient in nutritional_data.split('\n'):
        nutrient = nutrient.strip()
        if not nutrient:
            continue
        if 'Calories' in nutrient:
            cal_value = re.search(r'(\d+)(?:\s*kcal|kcal)', nutrient)
            if cal_value:
                nutrients['Calories'] = f"{cal_value.group(1)} kcal"
                found_data = True
            else:
                nutrients['Calories'] = f"Unable to parse: {nutrient}"
        elif 'Carbohydrates' in nutrient:
            carb_value = re.search(r'(\d+(?:\.\d+)?)(?:\s*g|g)', nutrient)
            if carb_value:
                nutrients['Carbohydrate'] = f"{carb_value.group(1)} g"
                found_data = True
            else:
                nutrients['Carbohydrate'] = f"Unable to parse: {nutrient}"
        elif 'Protein' in nutrient:
            protein_value = re.search(r'(\d+(?:\.\d+)?)(?:\s*g|g)', nutrient)
            if protein_value:
                nutrients['Protein'] = f"{protein_value.group(1)} g"
                found_data = True
            else:
                nutrients['Protein'] = f"Unable to parse: {nutrient}"
        elif 'Fat' in nutrient:
            fat_value = re.search(r'(\d+(?:\.\d+)?)(?:\s*g|g)', nutrient)
            if fat_value:
                nutrients['Fat'] = f"{fat_value.group(1)} g"
                found_data = True
            else:
                nutrients['Fat'] = f"Unable to parse: {nutrient}"
        elif 'Fiber' in nutrient:
            fiber_value = re.search(r'(\d+(?:\.\d+)?)(?:\s*g|g)', nutrient)
            if fiber_value:
                nutrients['Fiber'] = f"{fiber_value.group(1)} g"
                found_data = True
            else:
                nutrients['Fiber'] = f"Unable to parse: {nutrient}"
    
    return nutrients, found_data

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        choice = request.form.get('choice')
        if choice == 'photo':
            if 'file' not in request.files:
                flash('No file part')
                return redirect(request.url)
            file = request.files['file']
            if file.filename == '':
                flash('No selected file')
                return redirect(request.url)
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                try:
                    with open(file_path, 'rb') as f:
                        image_data = f.read()
                    response = analyze_food_image(image_data)
                    if response:
                        meal_name, serving_size, ingredients = format_food_details(response)
                        if ingredients:
                            nutritional_data = get_nutritional_data(meal_name, ingredients)
                            nutrients, found_data = parse_nutritional_data(nutritional_data)
                            return render_template('result.html', meal_name=meal_name, serving_size=serving_size,
                                                  ingredients=ingredients, nutrients=nutrients, found_data=found_data,
                                                  raw_response=nutritional_data)
                        else:
                            flash('No ingredients found. Try manual entry.')
                    else:
                        flash('Image analysis failed. Try manual entry.')
                except Exception as e:
                    flash(f"Error processing image: {str(e)}")
                finally:
                    if os.path.exists(file_path):
                        os.remove(file_path)
            else:
                flash('Invalid file type. Allowed types: png, jpg, jpeg, gif')
            return redirect(request.url)
        elif choice == 'manual':
            return redirect(url_for('manual_entry'))
    return render_template('index.html')

@app.route('/manual_entry', methods=['GET', 'POST'])
def manual_entry():
    if request.method == 'POST':
        meal_name = request.form.get('meal_name', '').strip()
        serving_size = request.form.get('serving_size', '100').strip()
        ingredients = []
        i = 0
        while True:
            ing_name = request.form.get(f'ingredient_name_{i}', '').strip()
            if not ing_name:
                break
            ing_qty = request.form.get(f'ingredient_qty_{i}', '').strip()
            if ing_qty:
                ingredients.append(f"{ing_name}: {ing_qty}")
            i += 1
        if not meal_name:
            meal_name = "Custom Meal"
            logging.warning("Empty meal name provided, defaulting to 'Custom Meal'.")
        if not ingredients:
            flash('Please add at least one ingredient.')
            return redirect(request.url)
        nutritional_data = get_nutritional_data(meal_name, ingredients)
        nutrients, found_data = parse_nutritional_data(nutritional_data)
        return render_template('result.html', meal_name=meal_name, serving_size=serving_size,
                              ingredients=ingredients, nutrients=nutrients, found_data=found_data,
                              raw_response=nutritional_data)
    return render_template('manual_entry.html')

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if request.method == 'POST':
        try:
            user_profile = UserProfile()
            user_profile.gender = request.form.get('gender', '').lower()
            if user_profile.gender not in ['male', 'female']:
                raise ValueError("Invalid gender. Please select Male or Female.")
            user_profile.date_of_birth = request.form.get('dob', '')
            user_profile.age = user_profile.calculate_age(user_profile.date_of_birth)
            height_input = request.form.get('height', '')
            height_unit = request.form.get('height_unit', '').lower()
            if height_unit not in ['ft', 'cm']:
                raise ValueError("Invalid height unit.")
            user_profile.height = user_profile.convert_height(height_input, height_unit)
            user_profile.height_unit = height_unit
            weight_input = request.form.get('weight', '')
            weight_unit = request.form.get('weight_unit', '').lower()
            if weight_unit not in ['kg', 'lbs']:
                raise ValueError("Invalid weight unit.")
            user_profile.weight = user_profile.convert_weight(weight_input, weight_unit)
            user_profile.weight_unit = weight_unit
            user_profile.activity_level = request.form.get('activity_level', '')
            user_profile.fitness_goal = request.form.get('fitness_goal', '')
            vegan_choice = request.form.get('vegan_preference', '').lower()
            user_profile.vegan_preference = vegan_choice == 'yes'
            user_profile.calculate_bmi()
            user_profile.calculate_bmr()
            meal_plan = user_profile.generate_personalized_meal_plan()
            return render_template('meal_plan.html', meal_plan=meal_plan)
        except Exception as e:
            flash(f"Error generating meal plan: {str(e)}")
            return redirect(request.url)
    return render_template('profile.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)