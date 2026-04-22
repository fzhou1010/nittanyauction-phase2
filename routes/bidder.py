from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db, format_request_desc, HELPDESK_TEAM_EMAIL

bidder_bp = Blueprint('bidder', __name__)

STATUS_LABELS = {1: 'Active', 0: 'Inactive', 2: 'Sold'}

@bidder_bp.before_request
def require_login():
    if 'email' not in session:
        return redirect(url_for('auth.login'))

@bidder_bp.route('/welcome')
def welcome():
    return render_template('bidder/welcome.html')

@bidder_bp.route('/credit_cards')
def credit_cards():
    # TODO: list/add/remove credit cards
    return render_template('bidder/credit_cards.html')

@bidder_bp.route('/watchlist')
def watchlist():
    # TODO: list/add/remove watchlist entries
    return render_template('bidder/watchlist.html')

@bidder_bp.route('/cart')
def shopping_cart():
    rows = query_db(
        '''
        SELECT
            c.Seller_Email, c.Listing_ID, c.added_at,
            al.Auction_Title, al.Product_Name, al.Category,
            al.Max_bids, al.Reserve_Price, al.Status,
            (SELECT MAX(Bid_Price) FROM Bids b
                WHERE b.Seller_Email = c.Seller_Email AND b.Listing_ID = c.Listing_ID) AS current_bid,
            (SELECT COUNT(*) FROM Bids b
                WHERE b.Seller_Email = c.Seller_Email AND b.Listing_ID = c.Listing_ID) AS bid_count
        FROM Shopping_Cart c
        JOIN Auction_Listings al
          ON al.Seller_Email = c.Seller_Email AND al.Listing_ID = c.Listing_ID
        WHERE c.Bidder_Email = ?
        ORDER BY c.added_at DESC
        ''',
        [session['email']],
    )

    items = []
    for r in rows:
        bid_count = r['bid_count'] or 0
        items.append({
            'seller_email': r['Seller_Email'],
            'listing_id': r['Listing_ID'],
            'title': r['Auction_Title'],
            'product_name': r['Product_Name'],
            'category': r['Category'],
            'current_bid': r['current_bid'],
            'remaining_bids': max(r['Max_bids'] - bid_count, 0) if r['Max_bids'] else 0,
            'status': r['Status'],
            'status_label': STATUS_LABELS.get(r['Status'], 'Unknown'),
            'reserve_price': r['Reserve_Price'],
        })

    return render_template('bidder/shopping_cart.html', items=items)

@bidder_bp.route('/cart/add', methods=['POST'])
def cart_add():
    seller_email = request.form.get('seller_email', '').strip()
    listing_id = request.form.get('listing_id', '').strip()
    if not seller_email or not listing_id:
        flash('Missing listing reference.')
        return redirect(url_for('listings.browse'))

    if seller_email == session['email']:
        flash('You cannot add your own listing to the cart.')
        return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))

    listing = query_db(
        'SELECT 1 FROM Auction_Listings WHERE Seller_Email = ? AND Listing_ID = ?',
        [seller_email, listing_id], one=True,
    )
    if not listing:
        flash('Listing not found.')
        return redirect(url_for('listings.browse'))

    db = get_db()
    db.execute(
        'INSERT OR IGNORE INTO Shopping_Cart (Bidder_Email, Seller_Email, Listing_ID) VALUES (?, ?, ?)',
        [session['email'], seller_email, listing_id],
    )
    db.commit()
    flash('Added to shopping cart.')
    return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))

@bidder_bp.route('/cart/remove', methods=['POST'])
def cart_remove():
    seller_email = request.form.get('seller_email', '').strip()
    listing_id = request.form.get('listing_id', '').strip()
    if not seller_email or not listing_id:
        flash('Missing listing reference.')
        return redirect(url_for('bidder.shopping_cart'))

    db = get_db()
    db.execute(
        'DELETE FROM Shopping_Cart WHERE Bidder_Email = ? AND Seller_Email = ? AND Listing_ID = ?',
        [session['email'], seller_email, listing_id],
    )
    db.commit()
    flash('Removed from shopping cart.')

    return redirect(request.form.get('next') or url_for('bidder.shopping_cart'))

@bidder_bp.route('/auction_history')
def auction_history():
    email = session['email']

    # Won auctions: closed listings where this bidder had the highest bid and it met reserve.
    won = query_db(
        '''
        SELECT
            al.Seller_Email, al.Listing_ID, al.Auction_Title, al.Product_Name,
            al.Category, al.Reserve_Price, al.Status,
            (SELECT MAX(Bid_Price) FROM Bids b
                WHERE b.Seller_Email = al.Seller_Email AND b.Listing_ID = al.Listing_ID) AS winning_bid,
            t.Date AS sold_date, t.Payment
        FROM Auction_Listings al
        LEFT JOIN Transactions t
            ON t.Seller_Email = al.Seller_Email
           AND t.Listing_ID  = al.Listing_ID
           AND t.Buyer_Email = ?
        WHERE al.Status != 1
          AND ? = (
              SELECT Bidder_Email FROM Bids b
              WHERE b.Seller_Email = al.Seller_Email AND b.Listing_ID = al.Listing_ID
              ORDER BY Bid_Price DESC LIMIT 1
          )
          AND (SELECT MAX(Bid_Price) FROM Bids b
               WHERE b.Seller_Email = al.Seller_Email AND b.Listing_ID = al.Listing_ID)
              >= COALESCE(al.Reserve_Price, 0)
        ORDER BY COALESCE(t.Date, '') DESC, al.Listing_ID DESC
        ''',
        [email, email],
    )

    # Bid history: one row per listing the bidder has touched, with their top bid vs the current leader.
    bids = query_db(
        '''
        SELECT
            al.Seller_Email, al.Listing_ID, al.Auction_Title, al.Category, al.Status,
            MAX(b.Bid_Price) AS my_highest_bid,
            (SELECT MAX(Bid_Price) FROM Bids b2
                WHERE b2.Seller_Email = al.Seller_Email AND b2.Listing_ID = al.Listing_ID) AS current_bid,
            MAX(b.Bid_ID) AS latest_bid_id
        FROM Bids b
        JOIN Auction_Listings al
            ON al.Seller_Email = b.Seller_Email AND al.Listing_ID = b.Listing_ID
        WHERE b.Bidder_Email = ?
        GROUP BY al.Seller_Email, al.Listing_ID
        ORDER BY (al.Status = 1) DESC, latest_bid_id DESC
        ''',
        [email],
    )

    bid_rows = []
    for b in bids:
        bid_rows.append({
            'seller_email': b['Seller_Email'],
            'listing_id': b['Listing_ID'],
            'title': b['Auction_Title'],
            'category': b['Category'],
            'status': b['Status'],
            'status_label': STATUS_LABELS.get(b['Status'], 'Unknown'),
            'my_highest_bid': b['my_highest_bid'],
            'current_bid': b['current_bid'],
            'leading': b['my_highest_bid'] == b['current_bid'],
        })

    return render_template('bidder/auction_history.html', won=won, bids=bid_rows)

@bidder_bp.route('/rate/<seller_email>', methods=['GET', 'POST'])
def rate_seller(seller_email):
    email = session["email"]

    already_rated = query_db(
        "SELECT 1 FROM Rating WHERE Bidder_Email = ? AND Seller_Email = ?", [email, seller_email], one=True
    )
    
    if request.method == "POST":
        if already_rated:
            flash('You have already reated this seller', 'warning')
            return redirect(url_for('bidder/rate/<seller_email>'))
        
        rating = request.form.get('choice', '').strip()
        description = request.form.get('note', '').strip()
        
        desc = format_request_desc(RATING=rating, DESCRIPTION=description)

        db = get_db()
        db.execute(
            'INSERT INTO Rating (Bidder_Email, Seller_Email, '
            '                      Date, Rating, Rating_Desc) '
            'VALUES (?, ?, ?, ?, ?)',
            [email, seller_email, "GETDATE()", rating, description],
        )
        db.commit()
        flash('Your review has been recieved. Thank you.', 'success')
        return redirect(url_for('bidder.welcome'))
        

    return render_template('bidder/rate_seller.html',
                           already_rated = already_rated,
                           form={})

@bidder_bp.route('/apply_seller', methods=['GET', 'POST'])
def apply_seller():
    email = session['email']

    # Defensive: this route is for bidders upgrading to sellers. A non-bidder
    # landing here is most likely a session/role mismatch, not a valid path.
    if not query_db('SELECT 1 FROM Bidders WHERE email = ?', [email], one=True):
        flash('Only bidders may apply to become sellers.')
        return redirect(url_for('listings.browse'))

    already_seller = query_db(
        'SELECT 1 FROM Sellers WHERE email = ?', [email], one=True,
    ) is not None

    pending = query_db(
        "SELECT request_id FROM Requests "
        "WHERE sender_email = ? AND request_type = 'BecomeSeller' "
        "  AND request_status = 0 "
        "ORDER BY request_id DESC LIMIT 1",
        [email], one=True,
    )

    if request.method == 'POST':
        if already_seller:
            flash('You are already a seller.', 'warning')
            return redirect(url_for('bidder.apply_seller'))
        if pending:
            flash('You already have a pending seller application.', 'warning')
            return redirect(url_for('bidder.apply_seller'))

        routing = request.form.get('bank_routing_num', '').strip()
        account = request.form.get('bank_account_num', '').strip()
        note = request.form.get('note', '').strip()

        if not routing or not account:
            flash('Bank routing and account numbers are required.', 'danger')
            return render_template(
                'bidder/apply_seller.html',
                already_seller=already_seller, pending=pending,
                form={'bank_routing_num': routing, 'bank_account_num': account, 'note': note},
            )

        # request_desc encodes the application payload as JSON so values can
        # contain '|' or ':' without being mangled. The helpdesk parser also
        # accepts the legacy pipe format, keeping CSV-seeded rows readable.
        desc = format_request_desc(ROUTING=routing, ACCOUNT=account, NOTE=note)

        db = get_db()
        db.execute(
            'INSERT INTO Requests (sender_email, helpdesk_staff_email, '
            '                      request_type, request_desc, request_status) '
            'VALUES (?, ?, ?, ?, ?)',
            [email, HELPDESK_TEAM_EMAIL, 'BecomeSeller', desc, 0],
        )
        db.commit()
        flash('Your seller application has been submitted for review.', 'success')
        return redirect(url_for('bidder.apply_seller'))

    return render_template(
        'bidder/apply_seller.html',
        already_seller=already_seller,
        pending=pending,
        form={},
    )
