# Main entry point for the Flask web application.
# Run this file (python app.py) to start the NittanyAuction server on http://127.0.0.1:5000

from flask import Flask, session, redirect, url_for, request, flash
from db import close_db, query_db

app = Flask(__name__)
app.secret_key = 'nittany-auction-dev-key'       # Used by Flask to sign session cookies
app.teardown_appcontext(close_db)                # Auto-close the DB connection after each request


@app.template_filter('displaydate')
def displaydate(value):
    """Format a Rating.Date as 'M/D/YY'."""
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


@app.before_request
def invalidate_stale_session():
    # if helpdesk renamed the session's email, drop the session and send them to login
    if request.endpoint in (None, 'static', 'auth.login', 'auth.logout'):
        return
    email = session.get('email')
    if not email:
        return
    if not query_db('SELECT 1 FROM Users WHERE email = ?', [email], one=True):
        session.clear()
        flash('Your email was changed by HelpDesk. Please sign in with your new email.', 'warning')
        return redirect(url_for('auth.login'))


# keep session['available_roles'] in sync with the DB so HelpDesk approvals apply without a relog
@app.before_request
def sync_available_roles():
    if request.endpoint in (None, 'static', 'auth.login', 'auth.logout'):
        return
    email = session.get('email')
    if not email:
        return

    current = []
    if query_db('SELECT 1 FROM Bidders WHERE email = ?', [email], one=True):
        current.append('bidder')
    if query_db('SELECT 1 FROM Sellers WHERE email = ?', [email], one=True):
        current.append('seller')
    if query_db('SELECT 1 FROM Helpdesk WHERE email = ?', [email], one=True):
        current.append('helpdesk')

    prior = session.get('available_roles')
    if prior is None or set(current) != set(prior):
        newly_granted = [r for r in current if r not in (prior or [])]
        session['available_roles'] = current

        # drop active role if it was revoked
        active = session.get('role')
        if active and active not in current:
            session.pop('role', None)
            session['roles'] = [r for r in session.get('roles', []) if r in current]

        # flash only for mid-session upgrades, not fresh logins or pending-user flow
        if newly_granted and session.get('role'):
            labels = ', '.join(r.capitalize() for r in newly_granted)
            flash(
                f'{labels} access has been approved. Switch via your profile to start using it.',
                'success',
            )


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
