from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db, format_request_desc, HELPDESK_TEAM_EMAIL

bidder_bp = Blueprint('bidder', __name__)

STATUS_LABELS = {1: 'Active', 0: 'Removed', 2: 'Sold', 3: 'Reserve Price Not Met'}

@bidder_bp.before_request
def require_login():
    if 'email' not in session:
        return redirect(url_for('auth.login'))

@bidder_bp.route('/welcome')
def welcome():
    return render_template('bidder/welcome.html')

@bidder_bp.route('/cart')
def shopping_cart():
    rows = query_db(
        '''
        SELECT
            c.Seller_Email, c.Listing_ID, c.added_at,
            al.Auction_Title, al.Product_Name, al.Category,
            al.Max_bids, al.Status,
            s.Current_Bid AS current_bid,
            COALESCE(s.Bid_Count, 0) AS bid_count,
            sar.Avg_Rating, sar.Rating_Count
        FROM Shopping_Cart c
        JOIN Auction_Listings al
          ON al.Seller_Email = c.Seller_Email AND al.Listing_ID = c.Listing_ID
        LEFT JOIN Listing_Bid_Stats s
          ON s.Seller_Email = c.Seller_Email AND s.Listing_ID = c.Listing_ID
        LEFT JOIN Seller_Avg_Rating sar
          ON sar.Seller_Email = c.Seller_Email
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
            'avg_rating': r['Avg_Rating'],
            'rating_count': r['Rating_Count'],
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
        'SELECT Status FROM Auction_Listings WHERE Seller_Email = ? AND Listing_ID = ?',
        [seller_email, listing_id], one=True,
    )
    if not listing:
        flash('Listing not found.')
        return redirect(url_for('listings.browse'))
    if listing['Status'] != 1:
        flash('This auction has ended and can no longer be added to your cart.')
        return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))

    db = get_db()
    db.execute(
        'INSERT OR IGNORE INTO Shopping_Cart (Bidder_Email, Seller_Email, Listing_ID) VALUES (?, ?, ?)',
        [session['email'], seller_email, listing_id],
    )
    db.commit()
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

    return redirect(request.form.get('next') or url_for('bidder.shopping_cart'))

@bidder_bp.route('/auction_history')
def auction_history():
    email = session['email']

    # won auctions + whether they already rated the seller
    won_rows = query_db(
        '''
        SELECT
            al.Seller_Email, al.Listing_ID, al.Auction_Title, al.Product_Name,
            al.Category, al.Reserve_Price, al.Status,
            (SELECT MAX(Bid_Price) FROM Bids b
                WHERE b.Seller_Email = al.Seller_Email AND b.Listing_ID = al.Listing_ID) AS winning_bid,
            t.Date AS sold_date, t.Payment,
            EXISTS(
                SELECT 1 FROM Rating r
                WHERE r.Bidder_Email = ?
                  AND r.Seller_Email = al.Seller_Email
                  AND r.Listing_ID  = al.Listing_ID
            ) AS already_rated
        FROM Auction_Listings al
        LEFT JOIN Transactions t
            ON t.Seller_Email = al.Seller_Email
           AND t.Listing_ID  = al.Listing_ID
           AND t.Bidder_Email = ?
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
        [email, email, email],
    )
    won = [dict(r) for r in won_rows]
    for w in won:
        w['can_rate'] = bool(w['Payment']) and not w['already_rated']

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

@bidder_bp.route('/rate/<seller_email>/<int:listing_id>', methods=['GET', 'POST'])
def rate_seller(seller_email, listing_id):
    email = session['email']

    # only bidders can rate
    if not query_db('SELECT 1 FROM Bidders WHERE email = ?', [email], one=True):
        flash('Only bidders can rate sellers.', 'danger')
        return redirect(url_for('listings.browse'))

    listing = query_db(
        'SELECT Auction_Title, Status FROM Auction_Listings '
        'WHERE Seller_Email = ? AND Listing_ID = ?',
        [seller_email, listing_id], one=True,
    )
    if not listing:
        flash('Listing not found.', 'danger')
        return redirect(url_for('bidder.auction_history'))

    # need to have actually won + paid for this auction
    transaction = query_db(
        'SELECT 1 FROM Transactions '
        'WHERE Seller_Email = ? AND Listing_ID = ? AND Bidder_Email = ?',
        [seller_email, listing_id, email], one=True,
    )
    if not transaction:
        flash('You can only rate a seller after winning and paying for one of their auctions.', 'warning')
        return redirect(url_for('bidder.auction_history'))

    # one rating per auction; schema enforces it too but this gives a nicer msg
    existing_rating = query_db(
        'SELECT Rating, Rating_Desc, Date FROM Rating '
        'WHERE Bidder_Email = ? AND Seller_Email = ? AND Listing_ID = ?',
        [email, seller_email, listing_id], one=True,
    )
    already_rated = existing_rating is not None

    if request.method == 'POST':
        if already_rated:
            flash('You have already rated this seller for this auction.', 'warning')
            return redirect(url_for('bidder.auction_history'))

        try:
            rating_value = int(request.form.get('choice', '').strip())
        except ValueError:
            rating_value = 0
        if rating_value < 1 or rating_value > 5:
            flash('Please choose a rating between 1 and 5.', 'danger')
            return redirect(url_for('bidder.rate_seller',
                                    seller_email=seller_email, listing_id=listing_id))

        description = request.form.get('note', '').strip() or None

        db = get_db()
        db.execute(
            'INSERT INTO Rating (Bidder_Email, Seller_Email, Listing_ID, Date, Rating, Rating_Desc) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            [email, seller_email, listing_id, date.today().isoformat(), rating_value, description],
        )
        db.commit()
        flash('Your review has been received. Thank you.', 'success')
        return redirect(url_for('bidder.auction_history'))

    return render_template(
        'bidder/rate_seller.html',
        seller_email=seller_email,
        listing=listing,
        listing_id=listing_id,
        already_rated=already_rated,
        existing_rating=existing_rating,
        form={},
    )

@bidder_bp.route('/apply_seller', methods=['GET', 'POST'])
def apply_seller():
    email = session['email']

    # only bidders can apply; anyone else here is a session mixup
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

        # json payload so special chars don't break parsing
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
