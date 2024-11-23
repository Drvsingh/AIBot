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
        if intent == "order_item_place_yes":
            return handle_place_order(req)
        elif intent == "order.add - context: ongoing-order":
            return handle_add_to_order(req)
        elif intent == "order.remove - context: ongoing-order":
            return handle_remove_from_order(req)
        else:
            return jsonify({"fulfillmentText": "I couldn't process that request."})

    except Exception as e:
        logging.error(f"Error handling request: {e}")
        return jsonify({"fulfillmentText": "An error occurred while processing your request."})

# Handle placing an order
def handle_place_order(req):
    try:
        # Extract order details from Dialogflow request
        data = req.get('queryResult', {}).get('parameters', {})
        menu_items = data.get("orderItems", [])  # [{"item": "Pizza", "quantity": 2}]
        total_amount = 0
        order_details = []

        # Fetch menu prices from Firestore
        menu_ref = db.collection("menu_prices").get()
        menu_prices = {item.id: item.to_dict().get("price") for item in menu_ref}

        # Calculate the total amount and format order details
        for item in menu_items:
            name = item.get("item")
            quantity = int(item.get("quantity", 1))
            price = menu_prices.get(name)

            if not price:
                return jsonify({"fulfillmentText": f"Item '{name}' is not available in the menu."})

            total_amount += price * quantity
            order_details.append({"item": name, "quantity": quantity})

        # Create a new order object
        new_order = {
            "orderId": f"order_{int(datetime.utcnow().timestamp())}",  # Unique ID
            "orderItems": order_details,
            "totalAmount": total_amount,
            "timestamp": datetime.now().isoformat()  # ISO format timestamp
        }

        # Save the order to Firestore
        db.collection("orders").add(new_order)

        logging.info(f"Order placed successfully: {new_order}")
        return jsonify({"fulfillmentText": f"Your order has been placed! Total amount: ₹{total_amount}"})
    except Exception as e:
        logging.error(f"Error placing order: {e}")
        return jsonify({"fulfillmentText": "Failed to place your order. Please try again later."})

# Handle adding to an order
def handle_add_to_order(req):
    try:
        # Extract ongoing order and additional items
        data = req.get('queryResult', {}).get('parameters', {})
        new_items = data.get("orderItems", [])  # New items to be added
        session_id = req.get('session').split('/')[-1]  # Extract unique session ID
        order_ref = db.collection("orders").document(session_id)
        order = order_ref.get()

        if not order.exists:
            return jsonify({"fulfillmentText": "No ongoing order found to add items."})

        # Fetch the current order and menu prices
        current_order = order.to_dict()
        menu_ref = db.collection("menu_prices").get()
        menu_prices = {item.id: item.to_dict().get("price") for item in menu_ref}

        # Add new items to the order
        total_amount = current_order["totalAmount"]
        updated_items = current_order["orderItems"]

        for item in new_items:
            name = item.get("item")
            quantity = int(item.get("quantity", 1))
            price = menu_prices.get(name)

            if not price:
                return jsonify({"fulfillmentText": f"Item '{name}' is not available in the menu."})

            total_amount += price * quantity
            updated_items.append({"item": name, "quantity": quantity})

        # Update the order in Firestore
        order_ref.update({"orderItems": updated_items, "totalAmount": total_amount})
        return jsonify({"fulfillmentText": f"Added items to your order. Updated total: ₹{total_amount}"})
    except Exception as e:
        logging.error(f"Error adding items to order: {e}")
        return jsonify({"fulfillmentText": "Failed to add items to your order. Please try again later."})

# Handle removing items from an order
def handle_remove_from_order(req):
    try:
        # Extract ongoing order and items to remove
        data = req.get('queryResult', {}).get('parameters', {})
        items_to_remove = data.get("orderItems", [])  # Items to be removed
        session_id = req.get('session').split('/')[-1]  # Extract unique session ID
        order_ref = db.collection("orders").document(session_id)
        order = order_ref.get()

        if not order.exists:
            return jsonify({"fulfillmentText": "No ongoing order found to remove items."})

        # Fetch the current order and menu prices
        current_order = order.to_dict()
        menu_ref = db.collection("menu_prices").get()
        menu_prices = {item.id: item.to_dict().get("price") for item in menu_ref}

        # Remove specified items from the order
        total_amount = current_order["totalAmount"]
        updated_items = current_order["orderItems"]

        for item in items_to_remove:
            name = item.get("item")
            quantity = int(item.get("quantity", 1))

            # Check if the item exists in the current order
            for i, order_item in enumerate(updated_items):
                if order_item["item"] == name and order_item["quantity"] >= quantity:
                    updated_items[i]["quantity"] -= quantity
                    if updated_items[i]["quantity"] == 0:
                        updated_items.pop(i)
                    total_amount -= menu_prices[name] * quantity
                    break

        # Update the order in Firestore
        order_ref.update({"orderItems": updated_items, "totalAmount": total_amount})
        return jsonify({"fulfillmentText": f"Removed items from your order. Updated total: ₹{total_amount}"})
    except Exception as e:
        logging.error(f"Error removing items from order: {e}")
        return jsonify({"fulfillmentText": "Failed to remove items from your order. Please try again later."})

# Run Flask app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
