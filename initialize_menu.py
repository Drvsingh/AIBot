import firebase_admin
from firebase_admin import credentials, firestore
import os
import json
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import logging

# Initialize Firebase Admin SDK using environment variables
def initialize_firebase():
    try:
        # Check if running in cloud environment
        if os.environ.get('FIREBASE_CREDENTIALS'):
            # Parse credentials from environment variable
            cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
            cred = credentials.Certificate(cred_dict)
        else:
            # Fallback for local development
            cred = credentials.Certificate('serviceaccount.json')
        
        firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        logging.error(f"Failed to initialize Firebase: {e}")
        raise

# Initialize Firestore client
db = initialize_firebase()

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
