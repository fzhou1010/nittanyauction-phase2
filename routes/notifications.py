from flask import Blueprint, render_template, request, redirect, url_for, session
from db import get_db, query_db

# notifications blueprint, shared across all roles
# Registered with url_prefix='/notifications' in app.py.
notifications_bp = Blueprint('notifications', __name__)


@notifications_bp.before_request
def require_login():
    if 'email' not in session:
        return redirect(url_for('auth.login'))


@notifications_bp.route('/')
def list():
    rows = query_db(
        'SELECT notification_id, notif_type, message, seller_email, listing_id, is_read, created_at '
        'FROM Notifications WHERE recipient_email = ? ORDER BY created_at DESC',
        [session['email']],
    )
    return render_template('bidder/notifications.html', notifications=rows)


@notifications_bp.route('/mark_read', methods=['POST'])
def mark_read():
    notification_id = request.form.get('notification_id', '').strip()
    db = get_db()
    if notification_id:
        db.execute(
            'UPDATE Notifications SET is_read = 1 WHERE notification_id = ? AND recipient_email = ?',
            [notification_id, session['email']],
        )
    else:
        db.execute(
            'UPDATE Notifications SET is_read = 1 WHERE recipient_email = ? AND is_read = 0',
            [session['email']],
        )
    db.commit()
    return redirect(request.form.get('next') or url_for('notifications.list'))
