from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db

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
    return render_template('seller/welcome.html')

@seller_bp.route('/dashboard')
def dashboard():
    email = session['email']
    bal = query_db('SELECT balance from Sellers WHERE email = ?', [email], one=True)

    #we also want to show the active current active listings of the seller along with some details
    active_listings = query_db('''SELECT l.Listing_ID, l.Auction_Title, l.Product_Name, l.Category, l.Reserve_Price, l.Max_bids
        FROM Auction_Listings l 
        WHERE l.Seller_Email = ? AND Status = 1''', [email]) # use triple quotes instead to fix bug of wrapping
        
    

    #query the specific detail of each active listing
    active_listing_details = []
    for listing in active_listings: #for each listing in the active listings, we also want to get the current bidding history
        bidding_information = query_db("""SELECT COUNT (*) AS bid_count, MAX(b.Bid_Price) as highest_bid
                                         FROM bids b
                                         WHERE b.Seller_Email = ? AND Listing_ID = ?""", [email, listing['Listing_ID']], one=True) #we nned this to be true as this returns a single row
        # append an object with key-value pairs with the details to the list 
        active_listing_details.append({
            'Listing_ID': listing["Listing_ID"],
            'Auction_Title': listing['Auction_Title'],     
            'Product_Name': listing['Product_Name'],       
            'Category': listing['Category'],               
            'Reserve_Price': listing['Reserve_Price'],     
            'Max_bids': listing['Max_bids'],               
            'bid_count': bidding_information['bid_count'],            
            'highest_bid': bidding_information['highest_bid']
        })

    #also want to retrieve sold listings for the specific seller, along with transaction status
    # since transactions aren't in the db unless a transaction is made after selling listing, it must be separated
    sold_listings = query_db("""SELECT l.Listing_ID, l.Auction_Title, l.Product_Name, l.Category
                                FROM Auction_Listings l
                                WHERE l.Seller_Email = ? AND l.Status = 2""", [email])
    #try and query for the transaction data per sold listing
    sold_listings_details = []
    for listing in sold_listings:
        transaction_detail = query_db("""SELECT Buyer_Email, Payment, Date
                                        FROM Transactions
                                      WHERE Seller_Email = ? AND Listing_ID = ?""", [email, listing['Listing_ID']], one=True) # we return this as one row
        #append the objects to sold listing details if they exist for the listing
        sold_listings_details.append({
            'Listing_ID': listing['Listing_ID'],
            'Auction_Title': listing['Auction_Title'],                                                        
            'Product_Name': listing['Product_Name'],
            'Category': listing['Category'],
            # add the transaction details if found, otherwise return None for Jinja
            'Buyer_Email': transaction_detail['Buyer_Email'] if transaction_detail else None, 
            'Payment': transaction_detail['Payment'] if transaction_detail else None,
            'Date': transaction_detail['Date'] if transaction_detail else None
        })
    # give the # of unanswered questions
    q_count = query_db('''SELECT COUNT (*) as q_count
                       FROM Questions
                       WHERE Seller_Email = ? AND answered = 0''', [email], one=True)
    # get the average rating of the seller from the rating table
    seller_rating = query_db('''SELECT AVG(Rating) AS avg_rating, COUNT(*) AS count
                             FROM Rating
                             WHERE Seller_Email = ?''', [email], one=True)
    
        
    return render_template('seller/dashboard.html', bal=bal, active_listings=active_listing_details, sold_listings=sold_listings_details,
                           q_count=q_count, seller_rating=seller_rating)

@seller_bp.route('/list_product', methods=['GET', 'POST'])
def list_product():
    # render the category selection for listing a product
    categories = query_db('SELECT category_name FROM Categories ORDER BY category_name')

    if request.method == 'POST':
        category = request.form.get('category')
        if not category:
            flash('Please select a category.')
            return render_template('seller/list_product/category.html', categories=categories)
        #save the current listing information to the session as an object
        session['cur_listing'] = {'category': category}
        return redirect(url_for('seller.list_product_details'))

    return render_template('seller/list_product/category.html', categories=categories)


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


@seller_bp.route('/list_product/review', methods=['GET', 'POST'])
def list_product_review():
    # Step 4: Review and submit
    if 'cur_listing' not in session or 'reserve_price' not in session['cur_listing']:
        return redirect(url_for('seller.list_product'))

    listing = session['cur_listing']

    if request.method == 'POST':
        email = session['email']

        # Get next Listing_ID for this seller (per-seller, not global)
        max_id = query_db(
            'SELECT MAX(Listing_ID) AS max_id FROM Auction_Listings WHERE Seller_Email = ?',
            [email], one=True
        )
        next_id = (max_id['max_id'] or 0) + 1

        db = get_db()
        #fix: need to add the condition of the product
        db.execute('''
            INSERT INTO Auction_Listings
                (Seller_Email, Listing_ID, Category, Auction_Title, Product_Name,
                 Product_Description, Quantity, Reserve_Price, Max_bids, Status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ''', [email, next_id, listing['category'], listing['auction_title'], listing['product_name'],
              listing['product_description'], int(listing['quantity']),
              float(listing['reserve_price']), int(listing['max_bids'])])
        db.commit()

        # after saving all of the data to the database, we can get rid of the listing from the current sessions
        session.pop('cur_listing', None)
        flash('Listing created successfully!')
        return redirect(url_for('seller.dashboard'))

    return render_template('seller/list_product/review.html', listing=listing)

@seller_bp.route('/questions')
def questions():
    email = session['email']
    #TODO: MAKE SURE TO ADD QUESTION TITLE
    #we want to query to get all of the active questiosn associated with the current seller
    active_questions = query_db('''SELECT q.question_id, q.Listing_Id, q.bidder_email, q.question_text, q.answer_text, q.answered, q.question_time, l.Auction_Title, l.Listing_ID
        FROM Questions Q, Auction_Listings l 
        WHERE l.Seller_Email = ? AND q.Listing_ID = l.Listing_ID AND q.answered = 0''', [email])
    
    answered_questions = query_db('''SELECT q.question_id, q.Listing_Id, q.bidder_email, q.question_text, q.answer_text, q.answered, q.question_time, l.Auction_Title, l.Listing_ID
        FROM Questions Q, Auction_Listings l 
        WHERE l.Seller_Email = ? AND q.Listing_ID = l.Listing_ID AND q.answered = 1''', [email])
    
    uq_count = query_db('''SELECT COUNT (*) as q_count
                       FROM Questions
                       WHERE Seller_Email = ? AND answered = 0''', [email], one=True)
    aq_count = query_db('''SELECT COUNT (*) as q_count
                       FROM Questions
                       WHERE Seller_Email = ? AND answered = 1''', [email], one=True)
    

    
    return render_template('seller/questions.html', active_questions=active_questions, answered_questions=answered_questions, uq_count=uq_count, aq_count = aq_count)

@seller_bp.route('/question/<int:qid>') #for specific questions, which would including responding and viewing answers
def question(qid):
        # receiving the question answer from the seller regarding the listing
    email = session['email']
    if request.method == 'POST':
        return
    
    return render_template('seller/question.html', qid=qid)

                 
@seller_bp.route('/questions/<int:qid>/answer', methods=['POST'])
def answer_question(qid):
    # TODO: update question with answer
    return redirect(url_for('seller.questions'))

@seller_bp.route('/request_category', methods=['GET', 'POST'])
def request_category():
    # TODO: new category request -> Requests table
    return render_template('seller/request_category.html')
