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

def manual_entry():
    """Allow users to manually input meal details with validation."""
    print("Starting manual entry process...")
    meal_name = input("Enter meal name: ").strip()
    print(f"Meal name entered: {meal_name}")
    if not meal_name:
        logging.warning("Empty meal name provided, defaulting to 'Custom Meal'.")
        meal_name = "Custom Meal"
    
    ingredients = []
    print("Enter ingredients. Type 'done' to finish. For quantities, specify weights (e.g., 100g) if possible.")
    while True:
        ingredient_name = input("Enter ingredient name (or 'done' to finish): ").strip()
        print(f"Ingredient name entered: {ingredient_name}")
        if ingredient_name.lower() == 'done':
            break
        if not ingredient_name:
            print("Ingredient name cannot be empty. Please try again.")
            continue
        quantity = input(f"Enter quantity for {ingredient_name} (e.g., 100g, 1 piece): ").strip()
        print(f"Quantity entered for {ingredient_name}: {quantity}")
        if not quantity:
            print("Quantity cannot be empty. Please enter a quantity.")
            continue
        ingredients.append(f"{ingredient_name}: {quantity}")
    
    serving_size = input("Enter serving size in grams (default is 100): ").strip() or "100"
    print(f"Serving size entered: {serving_size} g")
    return meal_name, serving_size, ingredients

def upload_image_path():
    """Handle image file upload with validation."""
    file_path = input("Enter the full path to your image file: ").strip()
    if not file_path:
        logging.warning("No file path provided.")
        print("No file path provided. Please try again.")
        return None
    try:
        with open(file_path, 'rb') as file:
            image_data = file.read()
        logging.info(f"Successfully read image file: {file_path}")
        return image_data
    except Exception as e:
        logging.error(f"Error reading file {file_path}: {e}")
        print(f"Error reading file: {e}")
        return None

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def analyze_food_image(image_data):
    if not image_data:
        logging.warning("No image data provided for analysis.")
        print("No image data provided.")
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
        print(f"Error during image analysis: {e}")
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

    def get_user_info(self):
        while True:
            self.gender = input("Enter gender (Male/Female): ").strip().lower()
            if self.gender in ['male', 'female']:
                break
            print("Invalid gender. Please enter Male or Female.")
        while True:
            try:
                self.date_of_birth = input("Enter date of birth (YYYY-MM-DD): ").strip()
                datetime.strptime(self.date_of_birth, "%Y-%m-%d")
                self.age = self.calculate_age(self.date_of_birth)
                break
            except ValueError:
                print("Invalid date format. Use YYYY-MM-DD")
        while True:
            height_input = input("Enter height (e.g., 5.7 for 5ft 7in, or 170 for cm): ").strip()
            height_unit = input("Height unit (ft/cm): ").strip().lower()
            if height_unit not in ['ft', 'cm']:
                print("Invalid unit. Choose 'ft' or 'cm'.")
                continue
            try:
                self.height = self.convert_height(height_input, height_unit)
                self.height_unit = height_unit
                break
            except ValueError:
                print("Invalid height input.")
        while True:
            weight_input = input("Enter weight (e.g., in kg or lbs): ").strip()
            weight_unit = input("Weight unit (kg/lbs): ").strip().lower()
            if weight_unit not in ['kg', 'lbs']:
                print("Invalid unit. Choose 'kg' or 'lbs'.")
                continue
            try:
                self.weight = self.convert_weight(weight_input, weight_unit)
                self.weight_unit = weight_unit
                break
            except ValueError:
                print("Invalid weight input.")
        activity_levels = {'1': 'Sedentary', '2': 'Lightly Active', '3': 'Moderately Active', '4': 'Very Active', '5': 'Extra Active'}
        print("\nSelect Activity Level:")
        for key, value in activity_levels.items():
            print(f"{key}. {value}")
        while True:
            activity_choice = input("Choose activity level (1-5): ").strip()
            if activity_choice in activity_levels:
                self.activity_level = activity_levels[activity_choice]
                break
            print("Invalid choice.")
        fitness_goals = {'1': 'Weight Loss', '2': 'Muscle Gain', '3': 'Maintenance', '4': 'General Fitness'}
        print("\nSelect Fitness Goal:")
        for key, value in fitness_goals.items():
            print(f"{key}. {value}")
        while True:
            goal_choice = input("Choose fitness goal (1-4): ").strip()
            if goal_choice in fitness_goals:
                self.fitness_goal = fitness_goals[goal_choice]
                break
            print("Invalid choice.")
        while True:
            vegan_choice = input("\nWould you like vegan meal recommendations? (yes/no): ").strip().lower()
            if vegan_choice in ['yes', 'no']:
                self.vegan_preference = vegan_choice == 'yes'
                break
            print("Please answer with 'yes' or 'no'.")
        self.calculate_bmi()
        self.calculate_bmr()
        return self

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

def display_info(meal_name, serving_size, ingredients, nutritional_data):
    """Display formatted meal and nutritional information with debug output."""
    print("\nFood Details\n------------")
    print(f"Food: {meal_name}")
    print(f"1 serving ({serving_size} g)")
    print("\nIngredients\n-----------")
    print(f"{'Ingredient':<20} {'Quantity':<20}")
    for ingredient in ingredients:
        ing, qty = ingredient.split(':', 1) if ':' in ingredient else (ingredient, "")
        print(f"{ing.strip():<20} {qty.strip():<20}")
    print("\nNutritional Information\n----------------------")
    print(f"Raw response for debugging:\n{nutritional_data}\n")
    
    # Check if the response contains expected format
    found_data = False
    for nutrient in nutritional_data.split('\n'):
        nutrient = nutrient.strip()
        if not nutrient:
            continue
        if 'Calories' in nutrient:
            cal_value = re.search(r'(\d+)(?:\s*kcal|kcal)', nutrient)
            if cal_value:
                print(f"{'Calories':<15} {cal_value.group(1)} kcal")
                found_data = True
            else:
                print(f"{'Calories':<15} Unable to parse: {nutrient}")
        elif 'Carbohydrates' in nutrient:
            carb_value = re.search(r'(\d+(?:\.\d+)?)(?:\s*g|g)', nutrient)
            if carb_value:
                print(f"{'Carbohydrate':<15} {carb_value.group(1)} g")
                found_data = True
            else:
                print(f"{'Carbohydrate':<15} Unable to parse: {nutrient}")
        elif 'Protein' in nutrient:
            protein_value = re.search(r'(\d+(?:\.\d+)?)(?:\s*g|g)', nutrient)
            if protein_value:
                print(f"{'Protein':<15} {protein_value.group(1)} g")
                found_data = True
            else:
                print(f"{'Protein':<15} Unable to parse: {nutrient}")
        elif 'Fat' in nutrient:
            fat_value = re.search(r'(\d+(?:\.\d+)?)(?:\s*g|g)', nutrient)
            if fat_value:
                print(f"{'Fat':<15} {fat_value.group(1)} g")
                found_data = True
            else:
                print(f"{'Fat':<15} Unable to parse: {nutrient}")
        elif 'Fiber' in nutrient:
            fiber_value = re.search(r'(\d+(?:\.\d+)?)(?:\s*g|g)', nutrient)
            if fiber_value:
                print(f"{'Fiber':<15} {fiber_value.group(1)} g")
                found_data = True
            else:
                print(f"{'Fiber':<15} Unable to parse: {nutrient}")
    
    if not found_data:
        print("Note: Nutritional data could not be parsed. The API response did not provide the expected format. Please try providing more specific quantities or weights for ingredients.")

def main():
    while True:
        choice = input("Upload a photo, enter items manually, or exit? (photo/manual/exit): ").lower()
        if choice == 'exit':
            print("Thank you for using Fab & Fit. Goodbye!")
            break
        if choice == 'photo':
            image_data = upload_image_path()
            if image_data:
                response = analyze_food_image(image_data)
                if response:
                    meal_name, serving_size, ingredients = format_food_details(response)
                    if ingredients:
                        nutritional_data = get_nutritional_data(meal_name, ingredients)
                        display_info(meal_name, serving_size, ingredients, nutritional_data)
                    else:
                        print("No ingredients found. Try manual entry.")
                else:
                    print("Image analysis failed. Try manual entry.")
            else:
                print("Failed to load image. Try again.")
            break
        elif choice == 'manual':
            meal_name, serving_size, ingredients = manual_entry()
            nutritional_data = get_nutritional_data(meal_name, ingredients)
            display_info(meal_name, serving_size, ingredients, nutritional_data)
            break
        else:
            print("Invalid choice. Choose 'photo', 'manual', or 'exit'.")
    
    # Asking if user wants a personalized meal plan
    while True:
        plan_choice = input("\nWould you like a personalized meal plan? (yes/no): ").lower()
        if plan_choice in ['yes', 'no']:
            if plan_choice == 'yes':
                user_profile = UserProfile()
                user_profile.get_user_info()
                meal_plan = user_profile.generate_personalized_meal_plan()
                print("\n--- Personalized Meal Plan ---")
                print(meal_plan)
            break
        print("Please answer with 'yes' or 'no'.")

if __name__ == "__main__":
    main()