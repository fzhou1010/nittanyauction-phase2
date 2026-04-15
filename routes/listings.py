from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db

listings_bp = Blueprint('listings', __name__)

@listings_bp.route('/browse')
def browse():
    if 'email' not in session:
        return redirect(url_for('auth.login'))

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

    questions = query_db('''
        SELECT question_text, answer_text, Bidder_Email, Question_time
        FROM Questions
        WHERE Seller_Email = ? AND Listing_ID = ?
        ORDER BY Question_time DESC
    ''', [seller_email, listing_id])

    return render_template('listings/detail.html', listing=listing, bids=bids, category_path=category_path, questions=questions)

@listings_bp.route('/listing/<seller_email>/<int:listing_id>/bid', methods=['POST'])
def place_bid(seller_email, listing_id):
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    
    # make sure the input is a valid number
    try:
        bid_amount = float(request.form.get('bid_amount'))
    except (TypeError, ValueError):
        flash('Invalid bid amount.', 'danger')
        return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))
    
    user_email = session.get('email')

    # Fetch auction details and current bids to validate the new bid
    auction = query_db('''
        SELECT Max_bids, Reserve_Price, Status
        FROM Auction_Listings
        WHERE Seller_Email = ? AND Listing_ID = ?
    ''', [seller_email, listing_id], one=True)

    # Fetch current bid stats for this listing
    current_bids = query_db('''
        SELECT COUNT(*) as total, MAX(Bid_Price) as highest_bid
        FROM Bids
        WHERE Seller_Email = ? AND Listing_ID = ?
    ''', [seller_email, listing_id], one=True)

    # if the auction is closed, reject the bid
    if auction['Status'] == 0:
        flash('This listing is closed and cannot accept new bids.', 'danger')
        return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))
    
    # if the max bids limit is reached, reject the bid and close the auction
    if auction['Max_bids'] and current_bids['total'] >= auction['Max_bids']:
        flash('This listing has reached the maximum number of bids and is now closed.', 'danger')
        return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))
    
    # if there are no bids yet, the minimum required bid is the reserve price (or 0 if no reserve). Otherwise, it must be at least $1 higher than the current highest bid.
    if current_bids['highest_bid'] is None:
        min_required = auction['Reserve_Price'] or 0.0
    else:
        min_required = current_bids['highest_bid'] + 1.00

    # validate the new bid against the minimum required
    if bid_amount < min_required:
        flash(f"Your bid must be at least ${min_required:.2f}.", 'danger')
        return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))

    db = get_db()
    db.execute('''
        INSERT INTO Bids (Seller_Email, Listing_ID, Bidder_Email, Bid_Price)
        VALUES (?, ?, ?, ?)
    ''', (seller_email, listing_id, user_email, bid_amount))

    #if the bid reaches max_bids, close the auction
    if auction['Max_bids'] and current_bids['total'] + 1 >= auction['Max_bids']:
        db.execute('''
            UPDATE Auction_Listings
            SET Status = 0
            WHERE Seller_Email = ? AND Listing_ID = ?
        ''', (seller_email, listing_id))
    
    db.commit()

    flash('Your bid has been placed.', 'success')
    
    # TODO: bid validation + insertion, max_bids auto-close
    return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))

@listings_bp.route('/listing/<seller_email>/<int:listing_id>/question', methods=['POST'])
def ask_question(seller_email, listing_id):
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    
    text = request.form.get('question')

    user_email = session.get('email')

    db = get_db()
    db.execute('''
        INSERT INTO Questions (Listing_ID, Seller_Email, question_text, Bidder_Email)
        VALUES (?, ?, ?, ?)
    ''', (listing_id, seller_email, text, user_email))

    db.commit()

    flash('Your question has been posted.', 'success')
    
    return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))
