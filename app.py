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

# Initialize Firebase Admin SDK using environment variables or local file
def initialize_firebase():
    try:
        if os.environ.get('FIREBASE_CREDENTIALS'):
            cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
            cred = credentials.Certificate(cred_dict)
        else:
            cred = credentials.Certificate('serviceaccount.json')  # Local fallback
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
        req = request.get_json()
        logging.debug(f"Request received: {req}")

        intent = req.get('queryResult', {}).get('intent', {}).get('displayName', "")
        if not intent:
            raise ValueError("Intent not found in the request.")

        if intent == "order_item_place":
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

def handle_place_order(req):
    try:
        # Extract parameters from the request
        data = req.get('queryResult', {}).get('parameters', {})
        menu_items = data.get("menu_item", [])
        quantities = data.get("quantity", [])
        
        if not menu_items or not isinstance(menu_items, list):
            return jsonify({"fulfillmentText": "No valid menu items provided."})

        # Initialize total amount and order details
        total_amount = 0
        order_details = []

        # Fetch menu prices from Firestore
        menu_ref = db.collection("menu_prices").get()
        menu_prices = {item.id: item.to_dict().get("price") for item in menu_ref}

        # Calculate total amount and validate menu items
        for i, item in enumerate(menu_items):
            name = item
            quantity = int(quantities[i]) if i < len(quantities) else 1
            price = menu_prices.get(name)

            if not price:
                return jsonify({"fulfillmentText": f"Item '{name}' is not available in the menu."})

            total_amount += price * quantity
            order_details.append({"item": name, "quantity": quantity})

        # Create a new order in Firestore
        order_id = f"order_{int(datetime.utcnow().timestamp())}"
        new_order = {
            "orderId": order_id,
            "orderItems": order_details,
            "totalAmount": total_amount,
            "timestamp": datetime.now().isoformat()
        }

        db.collection("orders").document(order_id).set(new_order)

        logging.info(f"Order placed successfully: {new_order}")
        return jsonify({"fulfillmentText": f"Your order has been placed! Total amount: ₹{total_amount}"})
    except Exception as e:
        logging.error(f"Error placing order: {e}")
        return jsonify({"fulfillmentText": "Failed to place your order. Please try again later."})

def handle_add_to_order(req):
    try:
        data = req.get('queryResult', {}).get('parameters', {})
        new_items = data.get("menu_item", [])
        quantities = data.get("quantity", [])
        session_id = req.get('session').split('/')[-1]

        # Fetch existing order
        order_ref = db.collection("orders").document(session_id)
        order = order_ref.get()

        if not order.exists:
            return jsonify({"fulfillmentText": "No ongoing order found to add items."})

        current_order = order.to_dict()

        # Fetch menu prices
        menu_ref = db.collection("menu_prices").get()
        menu_prices = {item.id: item.to_dict().get("price") for item in menu_ref}

        total_amount = current_order["totalAmount"]
        updated_items = current_order["orderItems"]

        # Update order with new items
        for i, item in enumerate(new_items):
            name = item
            quantity = int(quantities[i]) if i < len(quantities) else 1
            price = menu_prices.get(name)

            if not price:
                return jsonify({"fulfillmentText": f"Item '{name}' is not available in the menu."})

            total_amount += price * quantity
            updated_items.append({"item": name, "quantity": quantity})

        # Save updated order
        order_ref.set({"orderItems": updated_items, "totalAmount": total_amount}, merge=True)
        return jsonify({"fulfillmentText": f"Added items to your order. Updated total: ₹{total_amount}"})
    except Exception as e:
        logging.error(f"Error adding items to order: {e}")
        return jsonify({"fulfillmentText": "Failed to add items to your order. Please try again later."})

def handle_remove_from_order(req):
    try:
        data = req.get('queryResult', {}).get('parameters', {})
        items_to_remove = data.get("menu_item", [])
        quantities = data.get("quantity", [])
        session_id = req.get('session').split('/')[-1]

        # Fetch existing order
        order_ref = db.collection("orders").document(session_id)
        order = order_ref.get()

        if not order.exists:
            return jsonify({"fulfillmentText": "No ongoing order found to remove items."})

        current_order = order.to_dict()

        # Fetch menu prices
        menu_ref = db.collection("menu_prices").get()
        menu_prices = {item.id: item.to_dict().get("price") for item in menu_ref}

        total_amount = current_order["totalAmount"]
        updated_items = current_order["orderItems"]

        # Remove items from the order
        for i, item in enumerate(items_to_remove):
            name = item
            quantity = int(quantities[i]) if i < len(quantities) else 1

            for order_item in updated_items:
                if order_item["item"] == name and order_item["quantity"] >= quantity:
                    order_item["quantity"] -= quantity
                    if order_item["quantity"] == 0:
                        updated_items.remove(order_item)
                    total_amount -= menu_prices[name] * quantity
                    break

        # Save updated order
        order_ref.set({"orderItems": updated_items, "totalAmount": total_amount}, merge=True)
        return jsonify({"fulfillmentText": f"Removed items from your order. Updated total: ₹{total_amount}"})
    except Exception as e:
        logging.error(f"Error removing items from order: {e}")
        return jsonify({"fulfillmentText": "Failed to remove items from your order. Please try again later."})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
