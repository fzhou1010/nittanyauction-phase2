from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from db import get_db, query_db
from notifications import notify

seller_bp = Blueprint('seller', __name__)

@seller_bp.before_request
def require_seller():
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    if 'seller' not in session.get('roles', []):
        flash('Seller access required.')
        return redirect(url_for('listings.browse'))

@seller_bp.route('/welcome')
def welcome():
    return redirect(url_for('seller.dashboard'))

@seller_bp.route('/dashboard')
def dashboard():
    email = session['email']
    bal = query_db('SELECT balance from Sellers WHERE email = ?', [email], one=True)
    bal = bal or {'balance': 0.00} # if bal is none, default to 0 balance
    balance_num = float(bal['balance'] or 0)

    has_card = query_db('SELECT 1 FROM Credit_Cards WHERE Owner_email = ?', [email], one=True) is not None
    # Seller subtype drives which payment methods the promotion dialog exposes:
    # local vendors can't own CCs (schema 3.5) so they must use balance; student
    # sellers (also in Bidders) may choose either.
    is_vendor = query_db('SELECT 1 FROM Local_Vendors WHERE email = ?', [email], one=True) is not None
    is_bidder = query_db('SELECT 1 FROM Bidders WHERE email = ?', [email], one=True) is not None
    
    # Active listings + per-listing bid stats in a single query via the Listing_Bid_Stats view.
    # LEFT JOIN so listings with zero bids still appear.
    active_listings = query_db('''SELECT l.Listing_ID, l.Auction_Title, l.Product_Name, l.Category, l.Reserve_Price, l.Max_bids, l.is_promoted,
               COALESCE(s.Bid_Count, 0) AS bid_count,
               s.Current_Bid AS highest_bid
        FROM Auction_Listings l
        LEFT JOIN Listing_Bid_Stats s
          ON s.Seller_Email = l.Seller_Email AND s.Listing_ID = l.Listing_ID
        WHERE l.Seller_Email = ? AND l.Status = 1''', [email])

    active_listing_details = []
    for listing in active_listings:
        active_listing_details.append({
            'Listing_ID': listing["Listing_ID"],
            'Auction_Title': listing['Auction_Title'],
            'Product_Name': listing['Product_Name'],
            'Category': listing['Category'],
            'Reserve_Price': listing['Reserve_Price'],
            'Max_bids': listing['Max_bids'],
            'bid_count': listing['bid_count'],
            'highest_bid': listing['highest_bid'],
            'is_promoted': listing['is_promoted'] or 0
        })

    #also want to retrieve sold listings for the specific seller, along with transaction status
    # since transactions aren't in the db unless a transaction is made after selling listing, it must be separated
    sold_listings = query_db("""SELECT l.Listing_ID, l.Auction_Title, l.Product_Name, l.Category
                                FROM Auction_Listings l
                                WHERE l.Seller_Email = ? AND l.Status = 2""", [email])
    #try and query for the transaction data per sold listing
    sold_listings_details = []
    for listing in sold_listings:
        transaction_detail = query_db("""SELECT Bidder_Email, Payment, Date
                                        FROM Transactions
                                      WHERE Seller_Email = ? AND Listing_ID = ?""", [email, listing['Listing_ID']], one=True) # we return this as one row
        #append the objects to sold listing details if they exist for the listing
        sold_listings_details.append({
            'Listing_ID': listing['Listing_ID'],
            'Auction_Title': listing['Auction_Title'],                                                        
            'Product_Name': listing['Product_Name'],
            'Category': listing['Category'],
            # add the transaction details if found, otherwise return None for Jinja
            'Bidder_Email': transaction_detail['Bidder_Email'] if transaction_detail else None, 
            'Payment': transaction_detail['Payment'] if transaction_detail else None,
            'Date': transaction_detail['Date'] if transaction_detail else None
        })
    #also need to query inactive or removed listings
    inactive_listings = query_db("""SELECT Listing_ID, Auction_Title, Product_Name, Category, remaining_bids, reason_of_removal
                                FROM Auction_Listings
                                WHERE Seller_Email = ? AND Status = 0""", [email])
    # give the # of unanswered questions
    q_count = query_db('''SELECT COUNT (*) as q_count
                       FROM Questions
                       WHERE Seller_Email = ? AND answered = 0''', [email], one=True)
    # get the average rating of the seller via the Seller_Avg_Rating view
    seller_rating = query_db('''SELECT Avg_Rating AS avg_rating, Rating_Count AS count
                             FROM Seller_Avg_Rating
                             WHERE Seller_Email = ?''', [email], one=True)
    # view returns no row when the seller has zero ratings; preserve the {avg_rating, count} shape
    if not seller_rating:
        seller_rating = {'avg_rating': None, 'count': 0}
    
    return render_template('seller/dashboard.html', bal=bal, active_listings=active_listing_details, sold_listings=sold_listings_details,
                           q_count=q_count, seller_rating=seller_rating, inactive_listings=inactive_listings,
                           has_card=has_card, is_vendor=is_vendor, is_bidder=is_bidder, balance_num=balance_num)

# Initial Step of Creating a Listing, Selecting a Category
@seller_bp.route('/list_product', methods=['GET', 'POST'])
def list_product():
    # BR-18: only leaf categories hold products — exclude any category that is someone's parent.
    categories = query_db('''
        SELECT category_name FROM Categories
        WHERE category_name NOT IN (SELECT DISTINCT parent_category FROM Categories WHERE parent_category IS NOT NULL)
        ORDER BY category_name
    ''')

    if request.method == 'POST':
        category = request.form.get('category')
        if not category:
            flash('Please select a category.')
            return render_template('seller/list_product/category.html', categories=categories)
        #save the current listing information to the session as an object
        session['cur_listing'] = {'category': category}
        return redirect(url_for('seller.list_product_details'))

    return render_template('seller/list_product/category.html', categories=categories)

# Details on the Listing
@seller_bp.route('/list_product/details', methods=['GET', 'POST'])
def list_product_details(): 
    #for the user to input product listing details
    #if the listing is not in the session, rediret to the same template to choose category
    if 'cur_listing' not in session: 
        return redirect(url_for('seller.list_product'))
    
    # the current listing exists, continue
    if request.method == 'POST':
        listing = session['cur_listing'] #get the object from the session
        # record details for the listing, saved to listing object
        listing['auction_title'] = request.form.get('auction_title', '').strip()
        listing['product_name'] = request.form.get('product_name', '').strip()
        listing['product_description'] = request.form.get('product_description', '').strip()
        listing['quantity'] = request.form.get('quantity', '1')
        listing['condition'] = request.form.get('condition', '')

        # check if all of the details are filled out correctly
        if not listing['auction_title'] or not listing['product_name'] or not listing['product_description'] or not listing['quantity'] :
            flash('Please fill out all of the details for the product')
            return render_template('seller/list_product/product_details.html', listing=listing)
        
        
        
        #if passes, update the listing in the session and go to next step
        session['cur_listing'] = listing
        return redirect(url_for('seller.list_product_pricing'))

    return render_template('seller/list_product/product_details.html', listing=session['cur_listing'])

# Update Product Listing Price
@seller_bp.route('/list_product/pricing', methods=['GET', 'POST'])
def list_product_pricing(): # for the product reserve price and auction termination parameters
    #check if the listing is in the session
    if 'cur_listing' not in session:
        return redirect(url_for('seller.list_product'))

    if request.method == 'POST':
        listing = session['cur_listing']
        listing['reserve_price'] = request.form.get('reserve_price')
        listing['max_bids'] = request.form.get('max_bids')

        try:
            reserve = float(listing['reserve_price'])
            max_bids = int(listing['max_bids'])
            if reserve <= 0 or max_bids <= 0:
                raise ValueError
        except (ValueError, TypeError):
            flash('Reserve price and max bids must be positive numbers.')
            return render_template('seller/list_product/pricing.html', listing=listing)

        session['cur_listing'] = listing
        return redirect(url_for('seller.list_product_review'))

    return render_template('seller/list_product/pricing.html', listing=session['cur_listing'])

# Review the listing before posting in case anything is wrong
@seller_bp.route('/list_product/review', methods=['GET', 'POST'])
def list_product_review():
    #if the listing is not in the session or if the previous reserve price was not saved
    if 'cur_listing' not in session or 'reserve_price' not in session['cur_listing']:
        return redirect(url_for('seller.list_product'))

    listing = session['cur_listing']
    if request.method == 'POST': 
        email = session['email']

        #we want to get the maximum auction id for this user, so we can increment it for this upcoming listing
        max_id = query_db(
            'SELECT MAX(Listing_ID) AS max_id FROM Auction_Listings WHERE Seller_Email = ?',
            [email], one=True
        )
        next_id = (max_id['max_id'] or 0) + 1

        db = get_db()
        db.execute('''
            INSERT INTO Auction_Listings
                (Seller_Email, Listing_ID, Category, Auction_Title, Product_Name, Product_Description, Condition, Quantity, Reserve_Price, Max_bids, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ''', [email, next_id, listing['category'], listing['auction_title'], listing['product_name'],
              listing['product_description'], listing['condition'], int(listing['quantity']), float(listing['reserve_price']), int(listing['max_bids'])])
        db.commit()

        # after saving all of the data to the database, we can get rid of the listing from the current sessions
        session.pop('cur_listing', None)
        flash('Listing created successfully!')
        return redirect(url_for('seller.dashboard'))

    return render_template('seller/list_product/review.html', listing=listing)

# Editing Listings
@seller_bp.route('/edit_listing/<int:lid>', methods=['GET', 'POST'])
def edit_listing(lid): #should pass in the listing id
    email = session['email']
    #get the current listing, should be seller email and listing id
    cur_listing = query_db('''SELECT Listing_ID, Auction_Title, Product_Name, Product_Description, Category, Reserve_Price, Max_bids, Condition, Quantity, Status
        FROM Auction_Listings
        WHERE Seller_Email = ? AND Listing_ID = ?''', [email, lid], one=True) #should be one row

    #if the current listing is not found
    if not cur_listing:
        flash('There has been an error, listing not found')
        return redirect(url_for('seller.dashboard'))

    # BR-18: only leaf categories hold products. Include the listing's current category
    # as an OR branch so legacy listings filed under a now-non-leaf category still render.
    categories = query_db('''
        SELECT category_name FROM Categories
        WHERE category_name NOT IN (SELECT DISTINCT parent_category FROM Categories WHERE parent_category IS NOT NULL)
           OR category_name = ?
        ORDER BY category_name
    ''', [cur_listing['Category']])

    # sold or inactive listings cannot be edited
    if cur_listing['Status'] != 1:
        flash('Only active listings can be edited')
        return redirect(url_for('seller.dashboard'))

    #we still want to check whether or listing being edited is allowed to be edited
    bid_count = query_db('''SELECT COUNT(*) AS cnt FROM Bids                                                                       
                          WHERE Seller_Email = ? AND Listing_ID = ?''', [email, lid], one=True)                              
    if bid_count['cnt'] > 0:                                                                                                       
        flash('This listing cannot be edited because bidding has started')                                                
        return redirect(url_for('seller.dashboard'))
    
    if request.method == 'POST':

        # get the updated values from the form
        category = request.form.get('category', '').strip()
        auction_title = request.form.get('auction_title', '').strip()
        product_name = request.form.get('product_name', '').strip()
        product_description = request.form.get('product_description', '').strip()
        condition = request.form.get('condition', '')
        quantity = request.form.get('quantity', '1')
        reserve_price = request.form.get('reserve_price')
        max_bids = request.form.get('max_bids')

        # validate required fields
        if not auction_title or not product_name or not product_description or not condition or not quantity or not reserve_price or not max_bids:
            flash('Please fill out all of the fields')
            return render_template('seller/edit_listing.html', listing=cur_listing, categories=categories)

        # validate numeric fields
        try:
            reserve = float(reserve_price)
            max_b = int(max_bids)
            if reserve <= 0 or max_b <= 0: #ensure that the reserve price is more than 0 and that the truncated maximum bids is greater than as well
                raise ValueError
        except (ValueError, TypeError):
            flash('Reserve price and max bids must be positive numbers')
            return render_template('seller/edit_listing.html', listing=cur_listing, categories=categories)

        # update the listing in the database with the values in form field
        db = get_db()
        db.execute('''UPDATE Auction_Listings
                    SET Auction_Title = ?, Product_Name = ?, Product_Description = ?, Condition = ?, Category = ?, Quantity = ?, Reserve_Price = ?, Max_bids = ?
                    WHERE Seller_Email = ? AND Listing_ID = ?''',
                   [auction_title, product_name, product_description, condition, category, int(quantity), reserve, max_b, email, lid])
        db.commit()
        flash('Listing updated successfully!')
        return redirect(url_for('seller.dashboard'))

    return render_template('seller/edit_listing.html', listing=cur_listing, categories=categories)

# Remove Listings of the Seller, and record Reason
@seller_bp.route('/remove_listing/<int:lid>', methods=['POST'])
def remove_listing(lid):
    email = session['email']

    #get the max_bids and status of the listing to make sure it's active
    cur_listing= query_db('''SELECT Auction_Title, Max_bids, Status
                        FROM Auction_Listings
                        WHERE Seller_Email = ? AND Listing_ID = ?''', [email, lid], one=True) #need to return as a row
    
    if not cur_listing:
        flash('Listing not found')
        return redirect(url_for('seller.dashboard'))

    #if the listing is already sold or inactive
    if cur_listing['Status'] != 1:
        flash('Only active listings can be deleted')
        return redirect(url_for('seller.dashboard'))
    
    if request.method == 'POST':
        removal_reason = request.form.get('removal_reason', '').strip()
        if not removal_reason: # if not reason is provided, then we can direct back to editing page
            flash(f"Please provide a reason for the removal of the listing, {cur_listing['Auction_Title']}")
            return redirect(url_for('seller.edit_listing', lid=lid))
        
        bid_count = query_db('''SELECT COUNT(*) AS cnt FROM Bids                                                           
                            WHERE Seller_Email = ? AND Listing_ID = ?''', [email, lid], one=True)
        remaining_bid_count = cur_listing['Max_bids'] - bid_count['cnt']
        
        #update the listing
        db = get_db()
        db.execute('''UPDATE Auction_Listings                                                                              
                    SET Status = 0, remaining_bids = ?, reason_of_removal = ?                                            
                    WHERE Seller_Email = ? AND Listing_ID = ?''',[remaining_bid_count, removal_reason, email, lid])
        db.commit()
        flash('The listing has been successfully removed from the Auction')
        return redirect(url_for('seller.dashboard'))

# Seller Questions
@seller_bp.route('/questions')
def questions():
    email = session['email']
    #we want to query to get all of the active questiosn associated with the current seller
    active_questions = query_db('''SELECT q.question_id, q.Listing_Id, q.bidder_email, q.question_text, q.answer_text, q.answered, q.question_time, l.Auction_Title, l.Listing_ID
        FROM Questions Q, Auction_Listings l
        WHERE l.Seller_Email = ? AND q.Seller_Email = l.Seller_Email AND q.Listing_ID = l.Listing_ID AND q.answered = 0''', [email])

    answered_questions = query_db('''SELECT q.question_id, q.Listing_Id, q.bidder_email, q.question_text, q.answer_text, q.answered, q.question_time, q.answer_time, l.Auction_Title, l.Listing_ID
        FROM Questions Q, Auction_Listings l
        WHERE l.Seller_Email = ? AND q.Seller_Email = l.Seller_Email AND q.Listing_ID = l.Listing_ID AND q.answered = 1''', [email])
    
    uq_count = query_db('''SELECT COUNT (*) as q_count
                       FROM Questions
                       WHERE Seller_Email = ? AND answered = 0''', [email], one=True)
    aq_count = query_db('''SELECT COUNT (*) as q_count
                       FROM Questions
                       WHERE Seller_Email = ? AND answered = 1''', [email], one=True)
    

    
    return render_template('seller/questions.html', active_questions=active_questions, answered_questions=answered_questions, uq_count=uq_count, aq_count = aq_count)

@seller_bp.route('/question/<int:qid>', methods=['GET','POST']) #for specific questions, which would including responding and viewing answers
def question(qid):
    # receiving the question answer from the seller regarding the listing
    email = session['email']
    question = query_db('''SELECT q.question_id, q.Listing_ID, q.Bidder_Email, q.question_text, q.answer_text, q.answered, q.question_time, q.answer_time, l.Auction_Title
                            FROM Questions q, Auction_Listings l
                            WHERE q.Seller_Email = l.Seller_Email AND q.Listing_ID = l.Listing_ID AND q.question_id = ? AND q.Seller_Email = ?''',
                          [qid, email], one=True) # returns one row of data per question
    #get the answer response from the form and save
    if request.method == 'POST':
        answer_text = request.form.get('answer_text', '').strip()
        if not answer_text:
            flash('Please provide an answer for the question')
            return redirect(url_for('seller.question', qid=qid))
        #update the answer text for the question
        db = get_db()
        db.execute('''UPDATE Questions SET answer_text = ?, answered = 1, answer_time = CURRENT_TIMESTAMP
                    WHERE question_id = ? AND Seller_Email = ?
                    ''', [answer_text, qid, email])
        notify(
            question['Bidder_Email'], 'question_answered',
            f'Your question on "{question["Auction_Title"]}" has been answered.',
            seller_email=email, listing_id=question['Listing_ID'],
        )
        db.commit()
        flash('Answer has been recorded')
        #return to the same question page for the seller to view the entire log
        return redirect(url_for('seller.question', qid=qid))
        
    return render_template('seller/question.html', question=question)

# Seller Category Request
@seller_bp.route('/request_category', methods=['GET', 'POST'])
def request_category():
    email = session['email']

    # since we want to maintain a hierarichal structure for the categories, we want a parent and a child category
    if request.method == 'POST':
        parent_category = request.form.get('parent_category', '').strip()
        new_category = request.form.get('new_category', '').strip()
        sub_category = request.form.get('sub_category', '').strip()


        #if neither are there, then error
        if not parent_category or not new_category:
            flash('Please select a parent category and enter a new category name.')
            return redirect(url_for('seller.request_category'))

        # check if the category already exists in db
        is_existing = query_db('SELECT * FROM Categories WHERE category_name = ?', [new_category], one=True)
        if is_existing:
            flash('A category with that name already exists')
            return redirect(url_for('seller.request_category'))
        
        #if the user selected a sub-category as the parent
        if sub_category != '':
            # get the current request id to increment by one
            cur_id = query_db('SELECT MAX(request_id) AS cur_id FROM Requests', one=True)
            next_id = (cur_id['cur_id'] or 0) + 1
             #create request ticket for helpdesk to process
            req_desc = f"Please add a new category '{new_category}' under '{sub_category}'"
            db = get_db()
            db.execute('''INSERT INTO Requests (request_id, sender_email, helpdesk_staff_email, request_type, request_desc, request_status)
                      VALUES (?, ?, ?, ?, ?, 0)''',
                   [next_id, email, 'helpdeskteam@lsu.edu', 'AddCategory', req_desc])
            db.commit()
            flash('Category request submitted successfully!')
            return redirect(url_for('seller.request_category'))

        # get the current request id to increment by one
        cur_id = query_db('SELECT MAX(request_id) AS cur_id FROM Requests', one=True)
        next_id = (cur_id['cur_id'] or 0) + 1

        #create request ticket for helpdesk to process
        req_desc = f"Please add a new category '{new_category}' under '{parent_category}'"
        db = get_db()
        db.execute('''INSERT INTO Requests (request_id, sender_email, helpdesk_staff_email, request_type, request_desc, request_status)
                      VALUES (?, ?, ?, ?, ?, 0)''',
                   [next_id, email, 'helpdeskteam@lsu.edu', 'AddCategory', req_desc])
        db.commit()
        flash('Category request submitted successfully!')
        return redirect(url_for('seller.request_category'))

    #we want to first get all of the root categories, where parent category attribute = 'Root'
    root_categories = query_db("SELECT category_name FROM Categories WHERE parent_category = 'Root' ORDER BY category_name")
    #then we can query all of the categories as row items
    all_categories = query_db("SELECT category_name, parent_category FROM Categories ORDER BY category_name")

    category_hierarchy = {}
    # for each row item in all of the categories
    for cat in all_categories:
        parent = cat['parent_category']
        if parent not in category_hierarchy: # if the parent category is not already in the dictonary as a key, make a key
            category_hierarchy[parent] = []
        #if the parent is already in the dictionary, add the category to the parent category key
        category_hierarchy[parent].append(cat['category_name'])

    

    # get this seller's past category requests to display the current status
    my_requests = query_db('''SELECT request_id, request_desc, request_status
                              FROM Requests
                              WHERE sender_email = ? AND request_type = 'AddCategory'
                              ORDER BY request_id DESC''', [email])

    return render_template('seller/request_category.html', root_categories=root_categories, category_hierarchy=category_hierarchy, my_requests=my_requests)

@seller_bp.route('/promote/<int:listing_id>', methods=['POST'])
def promote_listing(listing_id):
    email = session['email']
    # payment_method: 'balance' (all sellers) or 'card' (student sellers / dual-role only).
    # Local vendors are forced to 'balance' regardless of what the form sends.
    payment_method = (request.form.get('payment_method') or '').strip().lower()

    listing = query_db('''SELECT * FROM Auction_Listings
                         WHERE Seller_Email = ? AND Listing_ID = ?''',
                         [email, listing_id], one=True)
    if not listing:
        flash('Listing not found.', 'danger')
        return redirect(url_for('seller.dashboard'))
    if listing['is_promoted']:
        flash('This listing is already promoted.', 'warning')
        return redirect(url_for('seller.dashboard'))
    if listing['Status'] != 1:
        flash('Only active listings can be promoted.', 'danger')
        return redirect(url_for('seller.dashboard'))

    is_vendor = query_db('SELECT 1 FROM Local_Vendors WHERE email = ?', [email], one=True) is not None
    is_bidder = query_db('SELECT 1 FROM Bidders WHERE email = ?', [email], one=True) is not None

    # Vendors can't own CCs per schema 3.5, so force balance even if the form was tampered with.
    if is_vendor and not is_bidder:
        payment_method = 'balance'
    if payment_method not in ('balance', 'card'):
        flash('Please choose a payment method to promote this listing.', 'danger')
        return redirect(url_for('seller.dashboard'))

    promotion_fee = round(listing['Reserve_Price'] * 0.05, 2)
    db = get_db()

    if payment_method == 'balance':
        bal_row = query_db('SELECT balance FROM Sellers WHERE email = ?', [email], one=True)
        current_balance = float(bal_row['balance'] or 0) if bal_row else 0.0
        if current_balance < promotion_fee:
            flash(
                f'Insufficient balance to promote. Fee is ${promotion_fee:.2f} but your balance is ${current_balance:.2f}.',
                'danger',
            )
            return redirect(url_for('seller.dashboard'))
        db.execute('UPDATE Sellers SET balance = balance - ? WHERE email = ?',
                   [promotion_fee, email])
    else:  # payment_method == 'card'
        if not is_bidder:
            flash('Credit card payment is only available to sellers who are also bidders.', 'danger')
            return redirect(url_for('seller.dashboard'))
        has_card = query_db('SELECT 1 FROM Credit_Cards WHERE Owner_email = ?', [email], one=True)
        if not has_card:
            flash('You must have a credit card on file to pay by card. Add one in your profile.', 'danger')
            return redirect(url_for('seller.dashboard'))

    db.execute('''UPDATE Auction_Listings
                  SET is_promoted = 1, promotion_fee = ?, promotion_time = CURRENT_TIMESTAMP
                  WHERE Seller_Email = ? AND Listing_ID = ?''',
                  [promotion_fee, email, listing_id])
    db.commit()

    method_label = 'balance' if payment_method == 'balance' else 'credit card'
    flash(f'Listing promoted! A fee of ${promotion_fee:.2f} was charged to your {method_label}.', 'success')
    return redirect(url_for('seller.dashboard'))
