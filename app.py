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

# Initialize Firebase Admin SDK
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
        menu_prices = {item.id.strip().lower(): item.to_dict().get("price") for item in menu_ref}

        # Process each menu item
        for i, item in enumerate(menu_items):
            name = item.strip().lower()
            quantity = int(quantities[i]) if i < len(quantities) else 1

            price = menu_prices.get(name)
            if not price:
                return jsonify({"fulfillmentText": f"Item '{item}' is not available in the menu."})

            total_amount += price * quantity
            order_details.append({"item": item, "quantity": quantity})

        order_id = f"order_{int(datetime.utcnow().timestamp())}"
        new_order = {
            "orderId": order_id,
            "orderItems": order_details,
            "totalAmount": total_amount,
            "timestamp": datetime.now().isoformat()
        }

        db.collection("orders").document(order_id).set(new_order)
        logging.info(f"Order placed successfully: {new_order}")

        return jsonify({
            "fulfillmentText": f"Your order has been placed successfully! Order ID: {order_id}. Total amount: ₹{total_amount}. If you wish to modify your order, please provide this Order ID."
        })
    except Exception as e:
        logging.error(f"Error placing order: {e}")
        return jsonify({"fulfillmentText": "Failed to place your order. Please try again later."})

def handle_add_to_order(req):
    try:
        data = req.get('queryResult', {}).get('parameters', {})
        new_items = data.get("menu_item", [])
        quantities = data.get("quantity", [])
        order_id = data.get("order_id")

        if not order_id:
            return jsonify({"fulfillmentText": "Please provide a valid Order ID to add items."})

        # Validate order_id from Firestore
        order_ref = db.collection("orders").document(order_id)
        order = order_ref.get()

        if not order.exists:
            return jsonify({"fulfillmentText": "No order found with the provided Order ID."})

        current_order = order.to_dict()

        # Fetch menu prices
        menu_ref = db.collection("menu_prices").get()
        menu_prices = {item.id.strip().lower(): item.to_dict().get("price") for item in menu_ref}

        total_amount = current_order.get("totalAmount", 0)
        updated_items = current_order.get("orderItems", [])

        for i, item in enumerate(new_items):
            name = item.strip().lower()
            quantity = int(quantities[i]) if i < len(quantities) and quantities[i].isdigit() else 1
            price = menu_prices.get(name)

            if not price:
                return jsonify({"fulfillmentText": f"Item '{item}' is not available in the menu."})

            # Check if the item already exists in the current order
            existing_item = next((order_item for order_item in updated_items if order_item["item"].strip().lower() == name), None)

            if existing_item:
                # If item exists, update the quantity
                existing_item["quantity"] += quantity
            else:
                # If item is new, add to the list
                updated_items.append({"item": item, "quantity": quantity})

            total_amount += price * quantity

        order_ref.set({"orderItems": updated_items, "totalAmount": total_amount}, merge=True)
        return jsonify({"fulfillmentText": f"Added items to your order. Updated total: ₹{total_amount}."})

    except ValueError as ve:
        logging.error(f"Value error while adding items to order: {ve}")
        return jsonify({"fulfillmentText": "Invalid quantity provided. Please check your input and try again."})
    except Exception as e:
        logging.error(f"Error adding items to order: {e}")
        return jsonify({"fulfillmentText": "Failed to add items to your order. Please try again later."})

def handle_remove_from_order(req):
    try:
        logging.info("Request received: %s", req)

        # Extract parameters
        data = req.get('queryResult', {}).get('parameters', {})
        items_to_remove = data.get("menu_item", [])
        quantities = data.get("quantity", [])
        order_id = data.get("order_id", "")

        logging.info("Parsed parameters: items_to_remove=%s, quantities=%s, order_id=%s", items_to_remove, quantities, order_id)

        # Flatten nested lists if necessary
        if isinstance(items_to_remove, list) and any(isinstance(i, list) for i in items_to_remove):
            items_to_remove = [item for sublist in items_to_remove for item in sublist]
        if isinstance(quantities, list) and any(isinstance(q, list) for q in quantities):
            quantities = [q for sublist in quantities for q in sublist]

        logging.info("Validated parameters: items_to_remove=%s, quantities=%s", items_to_remove, quantities)

        if not order_id:
            return jsonify({"fulfillmentText": "Order ID is missing. Please provide a valid order ID."})

        # Fetch existing order
        order_ref = db.collection("orders").document(order_id)
        order = order_ref.get()

        if not order.exists:
            logging.error("Order not found for ID: %s", order_id)
            return jsonify({"fulfillmentText": f"No order found with ID {order_id}."})

        current_order = order.to_dict()
        updated_items = current_order.get("orderItems", [])
        total_amount = current_order.get("totalAmount", 0)

        logging.info("Fetched order: %s", current_order)

        # Fetch menu prices for reference
        menu_ref = db.collection("menu_prices").get()
        menu_prices = {item.id.strip().lower(): item.to_dict().get("price") for item in menu_ref}

        logging.info("Fetched menu prices: %s", menu_prices)

        # Remove items from the order
        for i, item in enumerate(items_to_remove):
            name = str(item).strip().lower()  # Ensure the item is a string
            quantity_to_remove = int(quantities[i]) if i < len(quantities) else 1

            logging.info("Attempting to remove item: %s, quantity: %d", name, quantity_to_remove)

            item_found = False
            for order_item in updated_items:
                if order_item["item"].strip().lower() == name:
                    item_found = True
                    if order_item["quantity"] >= quantity_to_remove:
                        order_item["quantity"] -= quantity_to_remove
                        total_amount -= menu_prices.get(name, 0) * quantity_to_remove
                        if order_item["quantity"] == 0:
                            updated_items.remove(order_item)
                        break
                    else:
                        logging.warning("Not enough quantity for item: %s", name)
                        return jsonify({
                            "fulfillmentText": f"Cannot remove {quantity_to_remove} {item}(s). You only have {order_item['quantity']} in the order."
                        })

            if not item_found:
                logging.warning("Item not found in order: %s", name)
                return jsonify({"fulfillmentText": f"Item '{item}' is not in your order."})

        logging.info("Updated items: %s, total_amount: %s", updated_items, total_amount)

        # Update the Firestore document
        order_ref.set({"orderItems": updated_items, "totalAmount": total_amount}, merge=True)

        # Respond with success
        return jsonify({
            "fulfillmentText": f"Items removed successfully! Updated total amount: ₹{total_amount}."
        })

    except Exception as e:
        logging.error("Error removing items from order: %s", e)
        return jsonify({"fulfillmentText": "Failed to remove items from your order. Please try again later."})



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


"""import os
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
        menu_prices = {item.id.strip().lower(): item.to_dict().get("price") for item in menu_ref}

        # Process each menu item
        for i, item in enumerate(menu_items):
            # Normalize item name for matching
            name = item.strip().lower()
            quantity = int(quantities[i]) if i < len(quantities) else 1

            # Check if item exists in menu
            price = menu_prices.get(name)
            if not price:
                return jsonify({"fulfillmentText": f"Item '{item}' is not available in the menu."})

            # Calculate total amount
            total_amount += price * quantity
            order_details.append({"item": item, "quantity": quantity})  # Store original item name

        # Create a unique order ID
        order_id = f"order_{int(datetime.utcnow().timestamp())}"

        # Create the new order
        new_order = {
            "orderId": order_id,
            "orderItems": order_details,
            "totalAmount": total_amount,
            "timestamp": datetime.now().isoformat()
        }

        # Save the order to Firestore
        db.collection("orders").document(order_id).set(new_order)

        # Log the successful order
        logging.info(f"Order placed successfully: {new_order}")

        # Respond with Order ID and Total Amount
        return jsonify({
            "fulfillmentText": f"Your order has been placed successfully! Order ID: {order_id}. Total amount: ₹{total_amount}."
        })
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
"""
