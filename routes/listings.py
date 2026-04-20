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

    search = request.args.get("q")
    category_search = request.args.get('category', '')

    categories = query_db('SELECT DISTINCT Category FROM Auction_Listings')

    query = ('SELECT *, (SELECT MAX(Bid_Price) FROM Bids WHERE Bids.Listing_ID = Auction_Listings.Listing_ID) AS Current_Bid FROM Auction_Listings WHERE Status = 1')
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

    in_cart = query_db(
        'SELECT 1 FROM Shopping_Cart WHERE Bidder_Email = ? AND Seller_Email = ? AND Listing_ID = ?',
        [session['email'], seller_email, listing_id], one=True,
    ) is not None

    return render_template(
        'listings/detail.html',
        listing=listing, bids=bids, category_path=category_path,
        questions=questions, winner_email=winner_email, has_paid=has_paid,
        remaining_bids=remaining_bids, in_cart=in_cart
    )

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

    db.commit()

    outcome = check_auction_complete(seller_email, listing_id)

    if outcome:
        if outcome['status'] == 'sold':
            flash(f"Auction closed! Winner: {outcome['winner']} with a bid of ${outcome['amount']:.2f}.", 'success')
        else:
            flash("Auction closed: Reserve price was not met.", 'info')
    else:
        flash('Your bid has been placed.', 'success')

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


@listings_bp.route('/listing/<seller_email>/<int:listing_id>/pay', methods=['GET', 'POST'])
def pay(seller_email, listing_id):
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    email = session['email']

    listing = query_db(
        'SELECT * FROM Auction_Listings WHERE Seller_Email = ? AND Listing_ID = ?',
        [seller_email, listing_id], one=True,
    )
    if not listing or listing['Status'] != 2:
        flash('This listing is not available for payment.')
        return redirect(url_for('listings.browse'))

    highest = query_db(
        'SELECT Bidder_Email, Bid_Price FROM Bids '
        'WHERE Seller_Email = ? AND Listing_ID = ? '
        'ORDER BY Bid_Price DESC LIMIT 1',
        [seller_email, listing_id], one=True,
    )
    if not highest or highest['Bidder_Email'] != email:
        flash('Only the winning bidder can complete payment.')
        return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))

    existing_txn = query_db(
        'SELECT 1 FROM Transactions WHERE Seller_Email = ? AND Listing_ID = ?',
        [seller_email, listing_id], one=True,
    )
    if existing_txn:
        flash('Payment has already been completed for this auction.')
        return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))

    amount = highest['Bid_Price']
    cards = query_db('SELECT * FROM Credit_Cards WHERE Owner_email = ?', [email])

    if request.method == 'GET':
        return render_template(
            'listings/payment.html', listing=listing, amount=amount, cards=cards,
        )

    selected_card = request.form.get('credit_card_num', '').strip()
    valid_card = query_db(
        'SELECT 1 FROM Credit_Cards WHERE credit_card_num = ? AND Owner_email = ?',
        [selected_card, email], one=True,
    )
    if not valid_card:
        flash('Please select a valid credit card.')
        return render_template(
            'listings/payment.html', listing=listing, amount=amount, cards=cards,
        )

    db = get_db()
    from datetime import date
    db.execute(
        'INSERT INTO Transactions (Seller_Email, Listing_ID, Buyer_Email, Date, Payment) '
        'VALUES (?, ?, ?, ?, ?)',
        [seller_email, listing_id, email, date.today().isoformat(), amount],
    )
    db.execute(
        'UPDATE Sellers SET balance = balance + ? WHERE email = ?',
        [amount, seller_email],
    )
    db.commit()

    flash('Payment successful! Transaction recorded.')
    return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))
