# Main entry point for the Flask web application.
# Run this file (python app.py) to start the NittanyAuction server on http://127.0.0.1:5000

from flask import Flask, session, redirect, url_for
from db import close_db

app = Flask(__name__)
app.secret_key = 'nittany-auction-dev-key'       # Used by Flask to sign session cookies
app.teardown_appcontext(close_db)                # Auto-close the DB connection after each request

# Import and register each route blueprint (groups of related pages)
from routes.auth import auth_bp
from routes.listings import listings_bp
from routes.bidder import bidder_bp
from routes.seller import seller_bp
from routes.helpdesk import helpdesk_bp

app.register_blueprint(auth_bp)                              # /login, /logout, /register, /profile
app.register_blueprint(listings_bp)                          # /browse (auction listings)
app.register_blueprint(bidder_bp, url_prefix='/bidder')      # /bidder/welcome, /bidder/credit_cards, etc.
app.register_blueprint(seller_bp, url_prefix='/seller')      # /seller/welcome, /seller/dashboard, etc.
app.register_blueprint(helpdesk_bp, url_prefix='/helpdesk')  # /helpdesk/welcome, /helpdesk/queue, etc.

@app.route('/')
def index():
    # If already logged in, go to listings; otherwise go to login page
    if 'email' in session:
        return redirect(url_for('listings.browse'))
    return redirect(url_for('auth.login'))

if __name__ == '__main__':
    app.run(debug=True)
