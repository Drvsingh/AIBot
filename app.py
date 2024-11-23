import os
import json
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import logging
from datetime import datetime

# Initialize logging
logging.basicConfig(level=logging.DEBUG)

# Initialize Flask app
app = Flask(__name__)

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

@app.route('/', methods=['POST'])
def webhook():
    try:
        # Parse the request from Dialogflow
        req = request.get_json()
        logging.debug(f"Request received: {req}")

        # Extract intent from request
        intent = req.get('queryResult', {}).get('intent', {}).get('displayName', "")
        if not intent:
            raise ValueError("Intent not found in the request.")

        # Route based on intent name
        if intent == "get.menu":
            return handle_get_menu()
        elif intent == "order.new":
            return handle_new_order(req)
        elif intent == "order_item_place":
            return handle_place_order(req)
        elif intent == "order.add":
            return handle_add_to_order(req)
        elif intent == "order.remove":
            return handle_remove_from_order(req)
        else:
            return jsonify({"fulfillmentText": "I couldn't process that request."})

    except Exception as e:
        logging.error(f"Error handling request: {e}")
        return jsonify({"fulfillmentText": "An error occurred while processing your request."})

# Handlers for each intent
def handle_get_menu():
    try:
        # Fetch menu from Firestore
        menu_ref = db.collection("menu_prices").get()
        menu = {item.id: item.to_dict() for item in menu_ref}

        logging.info("Menu fetched successfully.")
        return jsonify({"fulfillmentText": f"Here's our menu: {json.dumps(menu)}"})
    except Exception as e:
        logging.error(f"Error fetching menu: {e}")
        return jsonify({"fulfillmentText": "Failed to fetch the menu."})

def handle_new_order(req):
    try:
        data = req.get('queryResult', {}).get('parameters', {})
        new_order = {
            "userId": data.get("userId"),
            "orderItems": data.get("orderItems", []),
            "timestamp": firestore.SERVER_TIMESTAMP,
            "status": "pending"
        }
        # Save the new order in Firestore
        db.collection("orders").add(new_order)
        logging.info("New order created successfully.")
        return jsonify({"fulfillmentText": "Your order has been created successfully!"})
    except Exception as e:
        logging.error(f"Error creating new order: {e}")
        return jsonify({"fulfillmentText": "Failed to create your order."})

def handle_place_order(req):
    try:
        data = req.get('queryResult', {}).get('parameters', {})
        menu_items = data.get("orderItems", [])  # [{"item": "Pizza", "quantity": 2}]
        total_amount = 0
        order_details = []

        # Fetch menu prices from Firestore
        menu_ref = db.collection("menu_prices").get()
        menu_prices = {item.id: item.to_dict().get("price") for item in menu_ref}

        # Calculate total amount and prepare order details
        for item in menu_items:
            name = item.get("item")
            quantity = int(item.get("quantity", 1))
            price = menu_prices.get(name)

            if not price:
                return jsonify({"fulfillmentText": f"Item '{name}' is not available in the menu."})

            total_amount += price * quantity
            order_details.append({"item": name, "quantity": quantity, "price": price})

        # Save order to Firestore
        user_id = data.get("userId")
        timestamp = datetime.now().isoformat()

        new_order = {
            "userId": user_id,
            "orderItems": order_details,
            "totalAmount": total_amount,
            "status": "pending",
            "timestamp": timestamp,
        }
        db.collection("orders").add(new_order)

        logging.info(f"Order placed successfully: {new_order}")
        return jsonify({"fulfillmentText": f"Your order has been placed! Total amount: ₹{total_amount}"})
    except Exception as e:
        logging.error(f"Error placing order: {e}")
        return jsonify({"fulfillmentText": "Failed to place your order."})

# Add items to an ongoing order
def handle_add_to_order(req):
    try:
        parameters = req.get('queryResult', {}).get('parameters', {})
        new_items = parameters.get('orderItems', [])
        user_id = parameters.get('userId')

        # Fetch ongoing order
        orders_ref = db.collection("orders")
        ongoing_order_query = orders_ref.where("userId", "==", user_id).where("status", "==", "pending").get()

        if not ongoing_order_query:
            return jsonify({"fulfillmentText": "You don't have any pending orders."})

        ongoing_order = ongoing_order_query[0]
        ongoing_order_data = ongoing_order.to_dict()
        ongoing_items = ongoing_order_data.get("orderItems", [])

        # Update order items
        for item in new_items:
            existing_item = next((i for i in ongoing_items if i['item'] == item['item']), None)
            if existing_item:
                existing_item['quantity'] += item['quantity']
            else:
                ongoing_items.append(item)

        orders_ref.document(ongoing_order.id).update({"orderItems": ongoing_items})
        return jsonify({"fulfillmentText": "Items have been added to your order."})
    except Exception as e:
        logging.error(f"Error adding items to order: {e}")
        return jsonify({"fulfillmentText": "Failed to add items to your order."})

# Remove items from an ongoing order
def handle_remove_from_order(req):
    try:
        parameters = req.get('queryResult', {}).get('parameters', {})
        items_to_remove = parameters.get('orderItems', [])
        user_id = parameters.get('userId')

        # Fetch ongoing order
        orders_ref = db.collection("orders")
        ongoing_order_query = orders_ref.where("userId", "==", user_id).where("status", "==", "pending").get()

        if not ongoing_order_query:
            return jsonify({"fulfillmentText": "You don't have any pending orders."})

        ongoing_order = ongoing_order_query[0]
        ongoing_order_data = ongoing_order.to_dict()
        ongoing_items = ongoing_order_data.get("orderItems", [])

        # Update order items
        for item in items_to_remove:
            ongoing_items = [i for i in ongoing_items if i['item'] != item['item']]

        orders_ref.document(ongoing_order.id).update({"orderItems": ongoing_items})
        return jsonify({"fulfillmentText": "Items have been removed from your order."})
    except Exception as e:
        logging.error(f"Error removing items from order: {e}")
        return jsonify({"fulfillmentText": "Failed to remove items from your order."})

# Run Flask app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
