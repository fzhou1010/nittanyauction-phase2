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

    all_categories = query_db(
        'SELECT category_name FROM Categories ORDER BY category_name'
    )

    return render_template(
        'helpdesk/queue.html',
        unassigned=unassigned,
        my_requests=my_requests,
        completed=completed,
        all_categories=all_categories,
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
    staff_email = session['email']
    action = request.form.get('action')
    req = query_db('SELECT * FROM Requests WHERE request_id = ?', [rid], one=True)

    if not req:
        flash('Request not found.')
        return redirect(url_for('helpdesk.queue'))

    if req['helpdesk_staff_email'] != staff_email:
        flash('You can only handle requests assigned to you.')
        return redirect(url_for('helpdesk.queue'))

    if req['request_status'] != 0:
        flash('This request has already been resolved.')
        return redirect(url_for('helpdesk.queue'))

    db = get_db()

    if action == 'deny':
        db.execute(
            'UPDATE Requests SET request_status = 2 WHERE request_id = ?', [rid]
        )
        db.commit()
        flash(f'Request #{rid} denied.')
        return redirect(url_for('helpdesk.queue'))

    handler = _REQUEST_HANDLERS.get(req['request_type'])
    if handler:
        error = handler(db, req)
        if error:
            flash(error)
            return redirect(url_for('helpdesk.queue'))

    db.execute(
        'UPDATE Requests SET request_status = 1 WHERE request_id = ?', [rid]
    )
    db.commit()
    flash(f'Request #{rid} completed.')
    return redirect(url_for('helpdesk.queue'))


def _handle_add_category(db, req):
    desc = req['request_desc'] or ''
    category_name = request.form.get('category_name', '').strip()
    parent_category = request.form.get('parent_category', '').strip() or None

    if not category_name:
        return 'Category name is required. Use the form fields to specify it.'

    existing = query_db(
        'SELECT 1 FROM Categories WHERE category_name = ?',
        [category_name], one=True,
    )
    if existing:
        return f'Category "{category_name}" already exists.'

    if parent_category:
        parent_exists = query_db(
            'SELECT 1 FROM Categories WHERE category_name = ?',
            [parent_category], one=True,
        )
        if not parent_exists:
            return f'Parent category "{parent_category}" does not exist.'

    db.execute(
        'INSERT INTO Categories (category_name, parent_category) VALUES (?, ?)',
        [category_name, parent_category],
    )
    return None


def _handle_change_id(db, req):
    old_email = req['sender_email']
    new_email = request.form.get('new_email', '').strip()

    if not new_email:
        return 'New email is required.'

    taken = query_db(
        'SELECT 1 FROM Users WHERE email = ?', [new_email], one=True
    )
    if taken:
        return f'Email "{new_email}" is already in use.'

    db.execute('UPDATE Users SET email = ? WHERE email = ?', [new_email, old_email])

    for table, col in [
        ('Bidders', 'email'),
        ('Sellers', 'email'),
        ('Helpdesk', 'email'),
        ('Credit_Cards', 'Owner_email'),
        ('Bids', 'Bidder_Email'),
        ('Auction_Listings', 'Seller_Email'),
        ('Transactions', 'Seller_Email'),
        ('Transactions', 'Buyer_Email'),
        ('Rating', 'Bidder_Email'),
        ('Rating', 'Seller_Email'),
        ('Questions', 'Bidder_Email'),
        ('Questions', 'Seller_Email'),
        ('Watchlist', 'Bidder_Email'),
        ('Local_Vendors', 'Email'),
        ('Requests', 'sender_email'),
    ]:
        db.execute(
            f'UPDATE {table} SET {col} = ? WHERE {col} = ?',
            [new_email, old_email],
        )

    return None


def _handle_market_analysis(db, req):
    return None


_REQUEST_HANDLERS = {
    'AddCategory': _handle_add_category,
    'ChangeID': _handle_change_id,
    'MarketAnalysis': _handle_market_analysis,
}


@helpdesk_bp.route('/categories', methods=['GET', 'POST'])
def categories():
    db = get_db()

    if request.method == 'POST':
        name = request.form.get('category_name', '').strip()
        parent = request.form.get('parent_category', '').strip() or None

        if not name:
            flash('Category name is required.')
            return redirect(url_for('helpdesk.categories'))

        existing = query_db(
            'SELECT 1 FROM Categories WHERE category_name = ?', [name], one=True
        )
        if existing:
            flash(f'Category "{name}" already exists.')
            return redirect(url_for('helpdesk.categories'))

        if parent:
            parent_exists = query_db(
                'SELECT 1 FROM Categories WHERE category_name = ?', [parent], one=True
            )
            if not parent_exists:
                flash(f'Parent category "{parent}" does not exist.')
                return redirect(url_for('helpdesk.categories'))

        db.execute(
            'INSERT INTO Categories (category_name, parent_category) VALUES (?, ?)',
            [name, parent],
        )
        db.commit()
        flash(f'Category "{name}" created.')
        return redirect(url_for('helpdesk.categories'))

    tree = _build_category_tree()
    all_categories = query_db(
        'SELECT category_name FROM Categories ORDER BY category_name'
    )
    return render_template(
        'helpdesk/categories.html',
        tree=tree,
        all_categories=all_categories,
    )


def _build_category_tree():
    rows = query_db(
        'SELECT category_name, parent_category FROM Categories ORDER BY category_name'
    )
    children = {}
    for row in rows:
        parent = row['parent_category']
        children.setdefault(parent, []).append(row['category_name'])
    return children


@helpdesk_bp.route('/analytics')
def analytics():
    # Step 4: will implement marketing analysis
    return render_template('helpdesk/analytics.html')
