from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db

helpdesk_bp = Blueprint('helpdesk', __name__)

@helpdesk_bp.before_request
def require_helpdesk():
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    if 'helpdesk' not in session.get('roles', []):
        flash('HelpDesk access required.')
        return redirect(url_for('listings.browse'))

@helpdesk_bp.route('/queue')
def queue():
    # TODO: pending/completed requests
    return render_template('helpdesk/queue.html')

@helpdesk_bp.route('/request/<int:rid>/handle', methods=['POST'])
def handle_request(rid):
    # TODO: approve/deny logic per request_type
    return redirect(url_for('helpdesk.queue'))

@helpdesk_bp.route('/categories', methods=['GET', 'POST'])
def categories():
    # TODO: view/add categories
    return render_template('helpdesk/categories.html')

@helpdesk_bp.route('/analytics')
def analytics():
    # TODO: marketing analysis queries
    return render_template('helpdesk/analytics.html')
