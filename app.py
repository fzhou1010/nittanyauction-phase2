from flask import Flask, session, redirect, url_for
from db import close_db

app = Flask(__name__)
app.secret_key = 'nittany-auction-dev-key'
app.teardown_appcontext(close_db)

from routes.auth import auth_bp
from routes.listings import listings_bp
from routes.bidder import bidder_bp
from routes.seller import seller_bp
from routes.helpdesk import helpdesk_bp

app.register_blueprint(auth_bp)
app.register_blueprint(listings_bp)
app.register_blueprint(bidder_bp, url_prefix='/bidder')
app.register_blueprint(seller_bp, url_prefix='/seller')
app.register_blueprint(helpdesk_bp, url_prefix='/helpdesk')

@app.route('/')
def index():
    if 'email' in session:
        return redirect(url_for('listings.browse'))
    return redirect(url_for('auth.login'))

if __name__ == '__main__':
    app.run(debug=True)
