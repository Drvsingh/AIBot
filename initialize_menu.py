import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase Admin SDK
def initialize_firebase():
    try:
        cred = credentials.Certificate('serviceaccount.json')  # Replace with your service account file
        firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        raise

# Add menu items to Firestore
def add_menu_items():
    db = initialize_firebase()
    menu_prices = {
        "Pav Bhaji": 150,
        "Chilli Potatoes": 180,
        "Chilli Paneer": 220,
        "Pakoda": 120,
        "Maggi": 100,
        "Fries": 120,
        "Garlic Bread": 160,
        "Wrap": 200,
        "Pizza": 400,
        "Burger": 250,
        "Oreo Shake": 180,
        "Chocolate Shake": 200,
        "Strawberry Shake": 190,
        "Vanilla Shake": 170,
        "Mojito": 150,
        "Fresh Lime Soda": 120,
        "Fresh Juice": 180,
        "Masala Soda": 140,
        "Biryani": 350,
        "Samosa": 80,
        "Lassi": 150,
        "Dosa": 220,
        "Mango Lassi": 180
    }

    try:
        # Reference to the 'menu_prices' collection
        menu_collection = db.collection("menu_prices")

        for item, price in menu_prices.items():
            # Add each item as a document
            menu_collection.document(item).set({"price": price})

        print("Menu items added successfully.")
    except Exception as e:
        print(f"Error adding menu items: {e}")

# Run the script
if __name__ == "__main__":
    add_menu_items()
