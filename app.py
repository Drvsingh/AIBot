import os
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
import logging

# Initialize logging
logging.basicConfig(level=logging.DEBUG)

# Initialize Flask app
app = Flask(__name__)

# Initialize Firebase Admin SDK
cred = credentials.Certificate(r"C:\Aibot\serviceaccount.json")  # Use raw string for Windows path
firebase_admin.initialize_app(cred)

# Firestore client
db = firestore.client()

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
        if intent == "new.order":
            return handle_new_order(req)
        elif intent == "order.add":
            return handle_add_items(req)
        elif intent == "order.remove":
            return handle_remove_items(req)
        elif intent == "order_item_place":
            return handle_update_order_status(req)
        elif intent == "order_item_place - yes":
            return handle_confirm_order(req)
        elif intent == "order_item_place - no":
            return handle_cancel_order(req)
        else:
            return jsonify({"fulfillmentText": "I couldn't process that request."})

    except Exception as e:
        logging.error(f"Error handling request: {e}")
        return jsonify({"fulfillmentText": "An error occurred while processing your request."})

# Handlers for each intent

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

def handle_add_items(req):
    try:
        data = req.get('queryResult', {}).get('parameters', {})
        order_id = data.get("orderId")
        items = data.get("items", [])
        db.collection("orders").document(order_id).update({
            "orderItems": firestore.ArrayUnion(items)
        })
        logging.info(f"Items added to order {order_id}.")
        return jsonify({"fulfillmentText": "Items have been added to your order."})
    except Exception as e:
        logging.error(f"Error adding items: {e}")
        return jsonify({"fulfillmentText": "Failed to add items to your order."})

def handle_remove_items(req):
    try:
        data = req.get('queryResult', {}).get('parameters', {})
        order_id = data.get("orderId")
        items = data.get("items", [])
        db.collection("orders").document(order_id).update({
            "orderItems": firestore.ArrayRemove(items)
        })
        logging.info(f"Items removed from order {order_id}.")
        return jsonify({"fulfillmentText": "Items have been removed from your order."})
    except Exception as e:
        logging.error(f"Error removing items: {e}")
        return jsonify({"fulfillmentText": "Failed to remove items from your order."})

def handle_update_order_status(req):
    try:
        data = req.get('queryResult', {}).get('parameters', {})
        order_id = data.get("orderId")
        new_status = data.get("status")
        db.collection("orders").document(order_id).update({"status": new_status})
        logging.info(f"Order {order_id} status updated to {new_status}.")
        return jsonify({"fulfillmentText": f"Order status has been updated to {new_status}."})
    except Exception as e:
        logging.error(f"Error updating order status: {e}")
        return jsonify({"fulfillmentText": "Failed to update order status."})

def handle_confirm_order(req):
    try:
        data = req.get('queryResult', {}).get('parameters', {})
        order_id = data.get("orderId")
        db.collection("orders").document(order_id).update({"status": "confirmed"})
        logging.info(f"Order {order_id} has been confirmed.")
        return jsonify({"fulfillmentText": "Your order has been confirmed!"})
    except Exception as e:
        logging.error(f"Error confirming order: {e}")
        return jsonify({"fulfillmentText": "Failed to confirm your order."})

def handle_cancel_order(req):
    try:
        data = req.get('queryResult', {}).get('parameters', {})
        order_id = data.get("orderId")
        db.collection("orders").document(order_id).update({"status": "canceled"})
        logging.info(f"Order {order_id} has been canceled.")
        return jsonify({"fulfillmentText": "Your order has been canceled."})
    except Exception as e:
        logging.error(f"Error canceling order: {e}")
        return jsonify({"fulfillmentText": "Failed to cancel your order."})

# Run Flask app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
