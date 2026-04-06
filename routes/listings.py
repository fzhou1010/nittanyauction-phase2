from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db

listings_bp = Blueprint('listings', __name__)


def check_auction_complete(seller_email, listing_id):
    """Evaluate whether an auction has reached Max_bids and resolve it.

    Returns a dict describing the outcome, or None if the auction is still active.
    Side-effect: updates Auction_Listings.Status (2=sold, 0=failed).
    """
    listing = query_db(
        'SELECT * FROM Auction_Listings WHERE Seller_Email = ? AND Listing_ID = ?',
        [seller_email, listing_id], one=True,
    )
    if not listing or listing['Status'] != 1:
        return None

    bid_count = query_db(
        'SELECT COUNT(*) AS cnt FROM Bids WHERE Seller_Email = ? AND Listing_ID = ?',
        [seller_email, listing_id], one=True,
    )['cnt']

    if bid_count < listing['Max_bids']:
        return None

    highest = query_db(
        'SELECT Bidder_Email, Bid_Price FROM Bids '
        'WHERE Seller_Email = ? AND Listing_ID = ? '
        'ORDER BY Bid_Price DESC LIMIT 1',
        [seller_email, listing_id], one=True,
    )

    db = get_db()
    if highest['Bid_Price'] >= listing['Reserve_Price']:
        db.execute(
            'UPDATE Auction_Listings SET Status = 2 WHERE Seller_Email = ? AND Listing_ID = ?',
            [seller_email, listing_id],
        )
        db.commit()
        return {'status': 'sold', 'winner': highest['Bidder_Email'], 'amount': highest['Bid_Price']}

    db.execute(
        'UPDATE Auction_Listings SET Status = 0 WHERE Seller_Email = ? AND Listing_ID = ?',
        [seller_email, listing_id],
    )
    db.commit()
    return {'status': 'failed'}

@listings_bp.route('/browse')
def browse():
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    
    category = request.args.get('category')
    listings = []
    if category:
        listings = query_db('''
            WITH RECURSIVE cat_tree AS (
                SELECT category_name FROM Categories WHERE category_name = ?
                UNION ALL
                SELECT c.category_name FROM Categories c
                    JOIN cat_tree ct ON c.parent_category = ct.category_name
            )
            SELECT al.Seller_Email, al.Listing_ID, al.Auction_Title, al.Product_Name, al.Category
            FROM Auction_Listings al
            JOIN cat_tree ct ON al.Category = ct.category_name
            WHERE al.Status = 1
        ''', [category])

    current_cat = category
    category_path = []
    while current_cat:
        category_path.insert(0, current_cat)
        parent = query_db(
            'SELECT parent_category FROM Categories WHERE category_name = ?',
            [current_cat],
            one=True
        )
        current_cat = parent['parent_category'] if parent else None

    categories = query_db('SELECT category_name FROM Categories ORDER BY category_name')
    
    return render_template('listings/browse.html', listings=listings, categories=categories, selected_category=category, category_path=category_path)

    search = request.args.get("q")
    category_search = request.args.get('category', '')

    categories = query_db('SELECT DISTINCT Category FROM Auction_Listings')

    query = ('SELECT * FROM Auction_Listings WHERE 1=1')
    args = []

    if search:
        query += (' AND (Auction_Title LIKE ? OR Product_Name LIKE ?)')
        args.extend([f'%{search}%', f'%{search}%'])

    if category_search:
        query += (' AND Category = ?')
        args.append(category_search)

    listings = query_db(query, tuple(args))

    return render_template('listings/browse.html', listings=listings, categories=categories)

@listings_bp.route('/listing/<seller_email>/<int:listing_id>')
def detail(seller_email, listing_id):
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    
    listing = query_db('''
        SELECT * 
        FROM Auction_Listings
        WHERE Seller_Email = ? AND Listing_ID = ?
        ''', [seller_email, listing_id], one=True)
    
    if not listing:
        flash('Listing not found.', 'danger')
        return redirect(url_for('listings.browse'))
    
    bids = query_db('''
        SELECT *
        FROM Bids
        WHERE Seller_Email = ? AND Listing_ID = ?
        ORDER BY Bid_Price DESC
    ''', [seller_email, listing_id])

    current_cat = listing['Category']
    category_path = []
    while current_cat:
        category_path.insert(0, current_cat)
        parent = query_db(
            'SELECT parent_category FROM Categories WHERE category_name = ?',
            [current_cat],
            one=True
        )
        current_cat = parent['parent_category'] if parent else None

    questions = []

    # Determine auction-end state for the template
    winner_email = None
    has_paid = False
    bid_count = len(bids)
    remaining_bids = listing['Max_bids'] - bid_count if listing['Max_bids'] else 0

    if listing['Status'] == 2 and bids:
        winner_email = bids[0]['Bidder_Email']  # bids ordered DESC by price
        txn = query_db(
            'SELECT 1 FROM Transactions WHERE Seller_Email = ? AND Listing_ID = ?',
            [seller_email, listing_id], one=True,
        )
        has_paid = txn is not None

    return render_template(
        'listings/detail.html',
        listing=listing, bids=bids, category_path=category_path,
        questions=questions, winner_email=winner_email, has_paid=has_paid,
        remaining_bids=remaining_bids,
    )

@listings_bp.route('/listing/<seller_email>/<int:listing_id>/bid', methods=['POST'])
def place_bid(seller_email, listing_id):
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    # TODO: bid validation + insertion, max_bids auto-close
    return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))

@listings_bp.route('/listing/<seller_email>/<int:listing_id>/question', methods=['POST'])
def ask_question(seller_email, listing_id):
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    # TODO: insert question
    return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))
