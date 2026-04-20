from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db

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
    # TODO: won auctions + bid history
    return render_template('bidder/auction_history.html')

@bidder_bp.route('/rate/<seller_email>', methods=['GET', 'POST'])
def rate_seller(seller_email):
    # TODO: rating form + insert
    return render_template('bidder/rate_seller.html')

@bidder_bp.route('/apply_seller', methods=['GET', 'POST'])
def apply_seller():
    # TODO: seller application form -> Requests table
    return render_template('bidder/apply_seller.html')
