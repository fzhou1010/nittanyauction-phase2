from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db
from notifications import notify

listings_bp = Blueprint('listings', __name__)

def get_all_subcategories(category, visited=None):
    #Recursively get all subcategories of a given category
    if visited is None:
        visited = set()
    if category in visited:
        return []
    visited.add(category)
    subcats = [category]
    children = query_db('SELECT category_name FROM Categories WHERE parent_category = ?', [category])
    for child in children:
        subcats.extend(get_all_subcategories(child['category_name'], visited))
    return subcats


def _notify_auction_close(seller_email, listing_id, title, outcome, winner=None, amount=None):
    """Notify every bidder and cart-holder of the auction outcome."""
    bidders = query_db(
        'SELECT DISTINCT Bidder_Email FROM Bids WHERE Seller_Email = ? AND Listing_ID = ?',
        [seller_email, listing_id],
    )
    bidder_emails = {row['Bidder_Email'] for row in bidders}

    cart_holders = query_db(
        'SELECT DISTINCT Bidder_Email FROM Shopping_Cart WHERE Seller_Email = ? AND Listing_ID = ?',
        [seller_email, listing_id],
    )
    cart_emails = {row['Bidder_Email'] for row in cart_holders}

    if outcome == 'sold':
        for email in bidder_emails:
            if email == winner:
                notify(email, 'auction_won',
                       f'You won "{title}" for ${amount:.2f}. Complete payment to finalize.',
                       seller_email, listing_id)
            else:
                notify(email, 'auction_lost',
                       f'Auction ended for "{title}". Another bidder won.',
                       seller_email, listing_id)
        for email in cart_emails - bidder_emails:
            notify(email, 'cart_auction_ended',
                   f'An auction in your cart ended: "{title}" was sold.',
                   seller_email, listing_id)
    else:  # failed
        for email in bidder_emails:
            notify(email, 'auction_failed',
                   f'Auction ended for "{title}" — reserve price was not met.',
                   seller_email, listing_id)
        for email in cart_emails - bidder_emails:
            notify(email, 'cart_auction_ended',
                   f'An auction in your cart ended without a sale: "{title}".',
                   seller_email, listing_id)


def check_auction_complete(seller_email, listing_id):
    """Evaluate whether an auction has reached Max_bids and resolve it.

    Returns a dict describing the outcome, or None if the auction is still active.
    Side-effect: updates Auction_Listings.Status (2=sold, 0=failed) and emits notifications.
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
    title = listing['Auction_Title'] or listing['Product_Name'] or 'Listing'
    if highest['Bid_Price'] >= listing['Reserve_Price']:
        db.execute(
            'UPDATE Auction_Listings SET Status = 2 WHERE Seller_Email = ? AND Listing_ID = ?',
            [seller_email, listing_id],
        )
        _notify_auction_close(seller_email, listing_id, title, 'sold',
                              winner=highest['Bidder_Email'], amount=highest['Bid_Price'])
        db.commit()
        return {'status': 'sold', 'winner': highest['Bidder_Email'], 'amount': highest['Bid_Price']}

    db.execute(
        'UPDATE Auction_Listings SET Status = 0 WHERE Seller_Email = ? AND Listing_ID = ?',
        [seller_email, listing_id],
    )
    _notify_auction_close(seller_email, listing_id, title, 'failed')
    db.commit()
    return {'status': 'failed'}

ROOT_PARENT = 'Root'  # sentinel for top-level categories in Categories.parent_category


@listings_bp.route('/browse')
def browse():
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    search = (request.args.get('q') or '').strip()
    category = (request.args.get('category') or '').strip()

    p_min_raw = request.args.get('min_price', '').strip()
    p_max_raw = request.args.get('max_price', '').strip()

    price_min = float(p_min_raw) if p_min_raw else None
    price_max = float(p_max_raw) if p_max_raw else None




    # Flat search bypasses the hierarchy entirely
    if search:
        like = f'%{search}%'
        search_where = '''
            WHERE Status = 1
              AND (Auction_Listings.Auction_Title LIKE ?
                    OR Auction_Listings.Product_Name LIKE ?
                    OR Auction_Listings.Product_Description LIKE ?
                    OR Auction_Listings.Category LIKE ?
                    OR bd.first_name LIKE ?
                    OR bd.last_name LIKE ?)
                AND (
                    (? IS NULL AND ? IS NULL)
                OR
                    (Current_Bid <= COALESCE(?, 99999999) AND Current_Bid >= COALESCE(?, 0)))
        '''
        search_params = [like, like, like, like, like, like, price_max, price_min, price_max, price_min]

        promoted_listings = query_db(
            f'''
            SELECT Auction_Listings.*,
                (SELECT MAX(Bid_Price) FROM Bids b
                 WHERE b.Seller_Email = Auction_Listings.Seller_Email
                   AND b.Listing_ID = Auction_Listings.Listing_ID) AS Current_Bid
            FROM Auction_Listings
            JOIN Bidders bd ON Auction_Listings.Seller_Email = bd.email
            {search_where}
              AND Auction_Listings.is_promoted = 1
            ORDER BY Auction_Listings.promotion_time DESC
            ''',
            search_params,
        )
        promoted_keys = {(r['Seller_Email'], r['Listing_ID']) for r in promoted_listings}

        all_matches = query_db(
            f'''
            SELECT Auction_Listings.*,
                (SELECT MAX(Bid_Price) FROM Bids b
                 WHERE b.Seller_Email = Auction_Listings.Seller_Email
                   AND b.Listing_ID = Auction_Listings.Listing_ID) AS Current_Bid
            FROM Auction_Listings
            JOIN Bidders bd ON Auction_Listings.Seller_Email = bd.email
            {search_where}
            ''',
            search_params,
        )
        listings = [r for r in all_matches if (r['Seller_Email'], r['Listing_ID']) not in promoted_keys]

        return render_template(
            'listings/browse.html',
            mode='search', search=search, listings=listings,
            promoted_listings=promoted_listings,
        )

    # Hierarchy mode: dynamically fetch subcategories of the current node
    parent_key = category if category else ROOT_PARENT
    subcategories = query_db(
        'SELECT category_name FROM Categories WHERE parent_category = ? ORDER BY category_name',
        [parent_key],
    )

    listings = []
    if category:
        listings = query_db(
            '''
            SELECT *,
                (SELECT MAX(Bid_Price) FROM Bids b
                 WHERE b.Seller_Email = Auction_Listings.Seller_Email
                   AND b.Listing_ID = Auction_Listings.Listing_ID) AS Current_Bid
            FROM Auction_Listings
            WHERE Status = 1 AND Category = ? AND (is_promoted IS NULL OR is_promoted = 0)
            ''',
            [category],
        )

    # Walk parents to build breadcrumb (root → current)
    path = []
    cur = category
    while cur:
        path.insert(0, cur)
        parent = query_db(
            'SELECT parent_category FROM Categories WHERE category_name = ?',
            [cur], one=True,
        )
        cur = parent['parent_category'] if parent and parent['parent_category'] != ROOT_PARENT else None

    if not category:
        promoted_listings = query_db('''
            SELECT *,
                (SELECT MAX(Bid_Price) FROM Bids b
                WHERE b.Seller_Email = Auction_Listings.Seller_Email
                AND b.Listing_ID = Auction_Listings.Listing_ID) AS Current_Bid
            FROM Auction_Listings 
            WHERE is_promoted = 1 AND Status = 1
            ORDER BY promotion_time DESC
        ''')
    else:
        all_cats = get_all_subcategories(category)
        placeholders = ','.join('?' * len(all_cats))
        promoted_listings = query_db(f'''
            SELECT *,
                (SELECT MAX(Bid_Price) FROM Bids b
                WHERE b.Seller_Email = Auction_Listings.Seller_Email
                AND b.Listing_ID = Auction_Listings.Listing_ID) AS Current_Bid
            FROM Auction_Listings 
            WHERE is_promoted = 1 AND Status = 1 
            AND Category IN ({placeholders})
            ORDER BY promotion_time DESC
        ''', all_cats)

    return render_template(
        'listings/browse.html',
        mode='hierarchy',
        subcategories=subcategories,
        listings=listings,
        category_path=path,
        current_category=category,
        promoted_listings=promoted_listings
    )

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
        current_cat = parent['parent_category'] if parent and parent['parent_category'] != ROOT_PARENT else None

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

    # Reserve price is a seller's sale threshold, not a bid floor — bidders
    # can open at any positive amount and just need to outbid the current highest.
    if bids:
        min_bid = int(bids[0]['Bid_Price']) + 1
    else:
        min_bid = 1

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

    reviews = query_db(
        "SELECT * FROM Rating WHERE Seller_Email = ?",
        [seller_email]
    )

    avg_rating = query_db(
        "SELECT AVG(Rating) as Avg_Rating From Rating WHERE Seller_Email = ?",
        [seller_email], one=True
    )

    return render_template(
        'listings/detail.html',
        listing=listing, bids=bids, avg_rating = avg_rating, category_path=category_path,
        questions=questions, winner_email=winner_email, has_paid=has_paid,
        remaining_bids=remaining_bids, in_cart=in_cart, reviews = reviews,
        min_bid=min_bid,
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

    # BR-3: a seller cannot bid on their own listing.
    if user_email == seller_email:
        flash('You cannot bid on your own listing.', 'danger')
        return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))

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

    # Turn-taking rule: same bidder cannot place consecutive bids on the same listing
    last_bidder = query_db(
        'SELECT Bidder_Email FROM Bids WHERE Seller_Email = ? AND Listing_ID = ? '
        'ORDER BY Bid_ID DESC LIMIT 1',
        [seller_email, listing_id], one=True,
    )
    if last_bidder and last_bidder['Bidder_Email'] == user_email:
        flash('You cannot place consecutive bids — wait for another bidder first.', 'danger')
        return redirect(url_for('listings.detail', seller_email=seller_email, listing_id=listing_id))

    # Reserve price is the seller's sale threshold (checked at auction close), not
    # a bid floor. Any positive bid is allowed for the first bid; subsequent bids
    # must exceed the current highest by at least $1.
    if current_bids['highest_bid'] is None:
        min_required = 1.00
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

    # Auction may have just reached Max_bids — resolve to Sold (reserve met) or Failed.
    outcome = check_auction_complete(seller_email, listing_id)
    if outcome and outcome['status'] == 'sold':
        if outcome['winner'] == user_email:
            flash('You won the auction! Complete payment to finalize.', 'success')
        else:
            flash('Your bid was placed, but another bidder won the auction.', 'info')
    elif outcome and outcome['status'] == 'failed':
        flash('Auction ended — reserve price was not met.', 'warning')
    # For the open-auction case we let the updated bid card communicate the result.
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
