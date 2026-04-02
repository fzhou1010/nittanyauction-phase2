from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db

helpdesk_bp = Blueprint('helpdesk', __name__)

UNASSIGNED_EMAIL = 'helpdeskteam@lsu.edu'


@helpdesk_bp.before_request
def require_helpdesk():
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    if 'helpdesk' not in session.get('roles', []):
        flash('HelpDesk access required.')
        return redirect(url_for('listings.browse'))


@helpdesk_bp.route('/welcome')
def welcome():
    staff_email = session['email']
    my_pending = query_db(
        'SELECT COUNT(*) AS cnt FROM Requests '
        'WHERE helpdesk_staff_email = ? AND request_status = 0',
        [staff_email], one=True
    )['cnt']
    unassigned = query_db(
        'SELECT COUNT(*) AS cnt FROM Requests '
        'WHERE helpdesk_staff_email = ? AND request_status = 0',
        [UNASSIGNED_EMAIL], one=True
    )['cnt']
    return render_template(
        'helpdesk/welcome.html',
        my_pending=my_pending,
        unassigned=unassigned,
    )


@helpdesk_bp.route('/queue')
def queue():
    staff_email = session['email']

    unassigned = query_db(
        'SELECT * FROM Requests '
        'WHERE helpdesk_staff_email = ? AND request_status = 0 '
        'ORDER BY request_id',
        [UNASSIGNED_EMAIL],
    )

    my_requests = query_db(
        'SELECT * FROM Requests '
        'WHERE helpdesk_staff_email = ? AND request_status = 0 '
        'ORDER BY request_id',
        [staff_email],
    )

    completed = query_db(
        'SELECT * FROM Requests '
        'WHERE helpdesk_staff_email = ? AND request_status != 0 '
        'ORDER BY request_id DESC',
        [staff_email],
    )

    return render_template(
        'helpdesk/queue.html',
        unassigned=unassigned,
        my_requests=my_requests,
        completed=completed,
    )


@helpdesk_bp.route('/request/<int:rid>/claim', methods=['POST'])
def claim_request(rid):
    staff_email = session['email']
    req = query_db('SELECT * FROM Requests WHERE request_id = ?', [rid], one=True)

    if not req:
        flash('Request not found.')
        return redirect(url_for('helpdesk.queue'))

    if req['helpdesk_staff_email'] != UNASSIGNED_EMAIL:
        flash('This request has already been claimed.')
        return redirect(url_for('helpdesk.queue'))

    db = get_db()
    db.execute(
        'UPDATE Requests SET helpdesk_staff_email = ? WHERE request_id = ?',
        [staff_email, rid],
    )
    db.commit()
    flash(f'Claimed request #{rid}.')
    return redirect(url_for('helpdesk.queue'))


@helpdesk_bp.route('/request/<int:rid>/handle', methods=['POST'])
def handle_request(rid):
    # Step 3: will implement approve/deny/complete logic
    flash('Request handling not yet implemented.')
    return redirect(url_for('helpdesk.queue'))


@helpdesk_bp.route('/categories', methods=['GET', 'POST'])
def categories():
    # Step 2: will implement category tree + add
    return render_template('helpdesk/categories.html')


@helpdesk_bp.route('/analytics')
def analytics():
    # Step 4: will implement marketing analysis
    return render_template('helpdesk/analytics.html')
