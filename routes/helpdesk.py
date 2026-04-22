import uuid

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db, parse_request_desc, HELPDESK_TEAM_EMAIL
from notifications import notify

helpdesk_bp = Blueprint('helpdesk', __name__)


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
        [HELPDESK_TEAM_EMAIL], one=True
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
        [HELPDESK_TEAM_EMAIL],
    )

    my_requests_rows = query_db(
        'SELECT * FROM Requests '
        'WHERE helpdesk_staff_email = ? AND request_status = 0 '
        'ORDER BY request_id',
        [staff_email],
    )

    # Pre-parse the pipe-separated request_desc payload so the template can
    # render a clean field-by-field view instead of raw text.
    my_requests = []
    for row in my_requests_rows:
        entry = dict(row)
        entry['parsed'] = parse_request_desc(row['request_desc'])
        my_requests.append(entry)

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

    if req['helpdesk_staff_email'] != HELPDESK_TEAM_EMAIL:
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
        deny_reason = request.form.get('response_comment', '').strip()
        if not deny_reason:
            flash('A reason is required when denying.')
            return redirect(url_for('helpdesk.queue'))
        db.execute(
            'UPDATE Requests SET request_status = 2, response_comment = ?, response_at = CURRENT_TIMESTAMP WHERE request_id = ?',
            [deny_reason, rid],
        )
        notify(
            req['sender_email'], 'request_denied',
            f'Your request #{rid} ({req["request_type"]}) was denied by HelpDesk staff. Reason: {deny_reason}',
        )
        db.commit()
        flash(f'Request #{rid} denied.')
        return redirect(url_for('helpdesk.queue'))

    approve_comment = request.form.get('response_comment', '').strip()

    handler = _REQUEST_HANDLERS.get(req['request_type'])
    if handler:
        error = handler(db, req)
        if error:
            flash(error)
            return redirect(url_for('helpdesk.queue'))

    db.execute(
        'UPDATE Requests SET request_status = 1, response_comment = ?, response_at = CURRENT_TIMESTAMP WHERE request_id = ?',
        [approve_comment or None, rid],
    )
    msg = f'Your request #{rid} ({req["request_type"]}) was approved by HelpDesk staff.'
    if approve_comment:
        msg += f' Note: {approve_comment}'
    notify(req['sender_email'], 'request_approved', msg)
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

        ancestor = parent_category
        for _ in range(100):
            if ancestor is None or ancestor == 'Root':
                break
            if ancestor == category_name:
                return f'Cannot add "{category_name}" under "{parent_category}": would create a cycle.'
            row = query_db(
                'SELECT parent_category FROM Categories WHERE category_name = ?',
                [ancestor], one=True,
            )
            if not row:
                break
            ancestor = row['parent_category']
        else:
            return f'Cannot add "{category_name}" under "{parent_category}": existing category tree appears to contain a cycle.'

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

    # Defer FK checks until COMMIT so we can rewrite Users.email and every
    # referencing row in one atomic batch. Without this, the Users update
    # fails immediately on any child row (Bidders, Sellers, Helpdesk, ...).
    db.execute('PRAGMA defer_foreign_keys = ON')
    db.execute('UPDATE Users SET email = ? WHERE email = ?', [new_email, old_email])

    for table, col in [
        ('Bidders', 'email'),
        ('Sellers', 'email'),
        ('Helpdesk', 'email'),
        ('Credit_Cards', 'Owner_email'),
        ('Bids', 'Bidder_Email'),
        ('Bids', 'Seller_Email'),
        ('Auction_Listings', 'Seller_Email'),
        ('Transactions', 'Seller_Email'),
        ('Transactions', 'Bidder_Email'),
        ('Rating', 'Bidder_Email'),
        ('Rating', 'Seller_Email'),
        ('Questions', 'Bidder_Email'),
        ('Questions', 'Seller_Email'),
        ('Shopping_Cart', 'Bidder_Email'),
        ('Shopping_Cart', 'Seller_Email'),
        ('Local_Vendors', 'email'),
        ('Notifications', 'recipient_email'),
        ('Notifications', 'seller_email'),
        ('Requests', 'sender_email'),
        ('Requests', 'helpdesk_staff_email'),
    ]:
        db.execute(
            f'UPDATE {table} SET {col} = ? WHERE {col} = ?',
            [new_email, old_email],
        )

    return None


def _handle_market_analysis(db, req):
    return None


def _handle_become_seller(db, req):
    sender = req['sender_email']
    parts = parse_request_desc(req['request_desc'])
    routing = parts.get('ROUTING')
    account = parts.get('ACCOUNT')

    if not routing or not account:
        return 'Banking details missing from this application.'

    if not query_db('SELECT 1 FROM Bidders WHERE email = ?', [sender], one=True):
        return 'Applicant is no longer a registered bidder.'

    if query_db('SELECT 1 FROM Sellers WHERE email = ?', [sender], one=True):
        return 'Applicant is already a seller.'

    db.execute(
        'INSERT INTO Sellers (email, bank_routing_number, bank_account_number) '
        'VALUES (?, ?, ?)',
        [sender, routing, account],
    )
    notify(
        sender, 'seller_approved',
        'Your seller application has been approved. You can now list items for auction.',
    )
    return None


def _handle_pending_role(db, req):
    sender = req['sender_email']
    parts = parse_request_desc(req['request_desc'])
    requested_role = (parts.get('requested_role') or '').strip().lower()

    if requested_role not in ('bidder', 'seller'):
        return 'Invalid requested role on this application.'

    # Guard: applicant might have been given a role in the meantime.
    if query_db('SELECT 1 FROM Bidders WHERE email = ?', [sender], one=True):
        return 'Applicant already has a role.'

    required = ['first_name', 'last_name', 'phone', 'street_num', 'street_name',
                'zipcode', 'city', 'state', 'credit_card_num', 'card_type',
                'expire_month', 'expire_year', 'security_code']
    if requested_role == 'seller':
        required += ['bank_routing_num', 'bank_account_num']
    missing = [f for f in required if not (parts.get(f) or '').strip()]
    if missing:
        return 'Application is missing required fields: ' + ', '.join(missing)

    if query_db('SELECT 1 FROM Credit_Cards WHERE credit_card_num = ?',
                [parts['credit_card_num']], one=True):
        return 'Cards cannot be shared across accounts — this card is already registered to another user.'

    address_id = uuid.uuid4().hex
    db.execute(
        'INSERT OR IGNORE INTO Zipcode_Info (zipcode, city, state) VALUES (?, ?, ?)',
        [parts['zipcode'], parts['city'], parts['state']],
    )
    db.execute(
        'INSERT INTO Address (address_id, zipcode, street_num, street_name) VALUES (?, ?, ?, ?)',
        [address_id, parts['zipcode'], parts['street_num'], parts['street_name']],
    )
    db.execute(
        'INSERT INTO Bidders (email, first_name, last_name, age, home_address_id, major, phone) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        [sender, parts['first_name'], parts['last_name'],
         parts.get('age') or None, address_id, parts.get('major'), parts['phone']],
    )
    db.execute(
        'INSERT INTO Credit_Cards (credit_card_num, card_type, expire_month, expire_year, security_code, Owner_email) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        [parts['credit_card_num'], parts['card_type'], parts['expire_month'],
         parts['expire_year'], parts['security_code'], sender],
    )
    if requested_role == 'seller':
        db.execute(
            'INSERT INTO Sellers (email, bank_routing_number, bank_account_number) VALUES (?, ?, ?)',
            [sender, parts['bank_routing_num'], parts['bank_account_num']],
        )

    notify(
        sender, 'role_approved',
        f'Your role request was approved. You can now log in as {requested_role}.',
    )
    return None


_REQUEST_HANDLERS = {
    'AddCategory': _handle_add_category,
    'ChangeID': _handle_change_id,
    'MarketAnalysis': _handle_market_analysis,
    'BecomeSeller': _handle_become_seller,
    'PendingRole': _handle_pending_role,
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
        parent = row['parent_category'] or 'Root'
        children.setdefault(parent, []).append(row['category_name'])
    return children


@helpdesk_bp.route('/analytics')
def analytics():
    auctions_by_major = query_db(
        'SELECT b.major, COUNT(*) AS cnt '
        'FROM Auction_Listings al '
        'JOIN Bidders b ON b.email = al.Seller_Email '
        'GROUP BY b.major '
        'ORDER BY cnt DESC'
    )

    top_categories = query_db(
        'SELECT Category, COUNT(*) AS cnt '
        'FROM Auction_Listings '
        'GROUP BY Category '
        'ORDER BY cnt DESC '
        'LIMIT 10'
    )

    revenue_by_category = query_db(
        'SELECT al.Category, '
        '       COUNT(t.Transaction_ID) AS sales, '
        '       COALESCE(SUM(t.Payment), 0) AS revenue '
        'FROM Transactions t '
        'JOIN Auction_Listings al ON al.Seller_Email = t.Seller_Email '
        '     AND al.Listing_ID = t.Listing_ID '
        'GROUP BY al.Category '
        'ORDER BY revenue DESC '
        'LIMIT 10'
    )

    auction_outcomes = query_db(
        'SELECT Status, COUNT(*) AS cnt '
        'FROM Auction_Listings '
        'GROUP BY Status '
        'ORDER BY Status'
    )

    top_sellers = query_db(
        'SELECT t.Seller_Email, '
        '       COUNT(t.Transaction_ID) AS sales, '
        '       SUM(t.Payment) AS revenue '
        'FROM Transactions t '
        'GROUP BY t.Seller_Email '
        'ORDER BY revenue DESC '
        'LIMIT 10'
    )

    bidder_age_distribution = query_db(
        'SELECT CASE '
        '         WHEN age < 20 THEN "Under 20" '
        '         WHEN age BETWEEN 20 AND 29 THEN "20-29" '
        '         WHEN age BETWEEN 30 AND 39 THEN "30-39" '
        '         WHEN age BETWEEN 40 AND 49 THEN "40-49" '
        '         ELSE "50+" '
        '       END AS age_group, '
        '       COUNT(*) AS cnt '
        'FROM Bidders '
        'WHERE age IS NOT NULL '
        'GROUP BY age_group '
        'ORDER BY MIN(age)'
    )

    top_bidders = query_db(
        'SELECT b.Bidder_Email, COUNT(*) AS bid_count '
        'FROM Bids b '
        'GROUP BY b.Bidder_Email '
        'ORDER BY bid_count DESC '
        'LIMIT 10'
    )

    sales_under_30 = query_db(
        'SELECT COALESCE(SUM(t.Payment), 0) AS total '
        'FROM Transactions t '
        'JOIN Bidders b ON b.email = t.Bidder_Email '
        'WHERE b.age < 30',
        one=True,
    )

    return render_template(
        'helpdesk/analytics.html',
        auctions_by_major=auctions_by_major,
        top_categories=top_categories,
        revenue_by_category=revenue_by_category,
        auction_outcomes=auction_outcomes,
        top_sellers=top_sellers,
        bidder_age_distribution=bidder_age_distribution,
        top_bidders=top_bidders,
        sales_under_30=sales_under_30,
    )
