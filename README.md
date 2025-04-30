# Smart-Meal-Analyzer 

## Chomp Checker 🍽️

A smart meal analysis web application that helps users track nutritional information through photo uploads or manual entry, powered by AI for accurate food analysis and personalized meal planning.

## Features 🌟

- **Image Analysis**: Upload food photos for automatic nutritional breakdown
- **Manual Entry**: Input meal details manually with ingredient specifications
- **Nutritional Information**: Get detailed macro and micronutrient data
- **Personalized Meal Plans**: Receive customized meal recommendations based on:
  - Personal health goals
  - Dietary preferences
  - Physical characteristics
  - Activity level

## Technologies Used 🛠️

### Frontend
- HTML5
- CSS3
- Bootstrap 5.3
- JavaScript

### Backend
- Python 3.x
- Flask Web Framework
- Google Gemini AI API

### Dependencies
- `google-generative-ai`: For AI-powered food analysis
- `Pillow`: Image processing
- `python-dotenv`: Environment variable management
- `tenacity`: Retry mechanism for API calls
## Output Reference 📊

### 1. Photo/Manual Entry Analysis Output
Results
Nutritional information for your meal

Chicken Burger
Serving size: 100g

Ingredients
Ingredient Quantity
Chicken leg fry 1
Burger buns 2
Lettuce 1

Nutritional Information
Calories 650 kcal
Carbohydrate 60 g
Protein 45 g
Fat 30 g
Fiber 5 g



### 2. Personalized Meal Plan Output
Personalized Meal Plan for a Moderately Active 25-Year-Old Male (Weight Loss)
Total Estimated Calories: 2200 kcal/day

Breakfast (550 kcal)
Meal Name: Greek Yogurt Power Bowl
Key Ingredients:
Greek yogurt (200g)
Mixed berries (100g)
Honey (1 tbsp)
Granola (30g)
Macronutrients: Carbs: 45g, Protein: 25g, Fat: 15g
Health Benefit: High protein breakfast helps maintain satiety and stable blood sugar
Lunch (600 kcal)
Meal Name: Grilled Chicken Quinoa Bowl
Key Ingredients:
Grilled chicken breast (150g)
Quinoa (100g cooked)
Mixed vegetables (150g)
Olive oil (1 tbsp)
Macronutrients: Carbs: 50g, Protein: 40g, Fat: 20g
Health Benefit: Balanced meal with lean protein and complex carbs
Dinner (550 kcal)
Meal Name: Baked Salmon with Sweet Potato
Key Ingredients:
Salmon fillet (150g)
Sweet potato (200g)
Broccoli (100g)
Herbs and seasoning
Macronutrients: Carbs: 40g, Protein: 35g, Fat: 25g
Health Benefit: Rich in omega-3 fatty acids and fiber
Snacks (250 kcal each)
Snack 1: Apple with almond butter
1 medium apple, 2 tbsp almond butter
Macros: Carbs: 25g, Protein: 5g, Fat: 8g
Snack 2: Protein smoothie
Banana, protein powder, almond milk
Macros: Carbs: 20g, Protein: 15g, Fat: 3g
Important Notes:

Hydration: Aim for 2-3 liters of water daily
Adjust portions based on hunger cues
Consult a dietitian for long-term personalized advice


### 3. User Profile Input
Gender: Male
Date of Birth: 1998-05-15
Height: 175 cm
Weight: 75 kg
Activity Level: Moderately Active
Fitness Goal: Weight Loss
Dietary Preference: Regular Diet

Calculated Statistics:

BMI: 24.5
BMR: 1700 kcal/day

Collapse

### 4. API Response Format
```json
{
    "meal_name": "Chicken Burger",
    "serving_size": "100g",
    "ingredients": [
        "Chicken leg fry: 1",
        "Burger buns: 2",
        "Lettuce: 1"
    ],
    "nutrients": {
        "Calories": "650 kcal",
        "Carbohydrate": "60 g",
        "Protein": "45 g",
        "Fat": "30 g",
        "Fiber": "5 g"
    }
}
