# Main entry point for the Flask web application.
# Run this file (python app.py) to start the NittanyAuction server on http://127.0.0.1:5000

from flask import Flask, session, redirect, url_for
from db import close_db, query_db

app = Flask(__name__)
app.secret_key = 'nittany-auction-dev-key'       # Used by Flask to sign session cookies
app.teardown_appcontext(close_db)                # Auto-close the DB connection after each request


@app.template_filter('displaydate')
def displaydate(value):
    """Normalize a Rating.Date value (either ISO 'YYYY-MM-DD' written by our code,
    or legacy 'M/D/YY' from the seed CSV) to a consistent 'M/D/YY' for display."""
    if value is None or value == '':
        return ''
    s = str(value).strip()
    from datetime import datetime
    for fmt in ('%Y-%m-%d', '%m/%d/%y', '%m/%d/%Y'):
        try:
            dt = datetime.strptime(s, fmt)
            return f'{dt.month}/{dt.day}/{dt.year % 100:02d}'
        except ValueError:
            continue
    return s  # unknown format: render as-is


@app.context_processor
def inject_notifications():
    """Expose unread notification count and a short preview list to every template."""
    if 'email' not in session:
        return {}
    unread_count = query_db(
        'SELECT COUNT(*) AS n FROM Notifications WHERE recipient_email = ? AND is_read = 0',
        [session['email']], one=True,
    )['n']
    recent = query_db(
        'SELECT notification_id, notif_type, message, seller_email, listing_id, is_read, created_at '
        'FROM Notifications WHERE recipient_email = ? ORDER BY created_at DESC LIMIT 5',
        [session['email']],
    )
    return {'nav_unread_count': unread_count, 'nav_recent_notifications': recent}

# Import and register each route blueprint (groups of related pages)
from routes.auth import auth_bp
from routes.listings import listings_bp
from routes.bidder import bidder_bp
from routes.seller import seller_bp
from routes.helpdesk import helpdesk_bp
from routes.notifications import notifications_bp

app.register_blueprint(auth_bp)                              # /login, /logout, /register, /profile
app.register_blueprint(listings_bp)                          # /browse (auction listings)
app.register_blueprint(bidder_bp, url_prefix='/bidder')      # /bidder/welcome, /bidder/cart, etc.
app.register_blueprint(seller_bp, url_prefix='/seller')      # /seller/welcome, /seller/dashboard, etc.
app.register_blueprint(helpdesk_bp, url_prefix='/helpdesk')  # /helpdesk/welcome, /helpdesk/queue, etc.
app.register_blueprint(notifications_bp, url_prefix='/notifications')  # shared notifications UI for all roles

@app.route('/')
def index():
    # If already logged in, go to listings; otherwise go to login page

    if 'roles' not in session:
        if 'email' in session and session.get('available_roles'):
            return redirect(url_for('auth.choose_role'))
        return redirect(url_for('auth.login'))
    if 'helpdesk' in session['roles']:                                                                                                                       
        return redirect(url_for('helpdesk.welcome'))
    elif 'seller' in session['roles']:
        return redirect(url_for('seller.dashboard'))
    else:                                                                                                                                                    
        return redirect(url_for('bidder.welcome'))
    
    return redirect(url_for('auth.login'))

if __name__ == '__main__':
    app.run(debug=True)
