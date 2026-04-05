from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db

listings_bp = Blueprint('listings', __name__)

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
            WHERE al.remaining_bids > 0
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


    # TODO: Q&A
    return render_template('listings/detail.html', listing=listing, bids=bids, category_path=category_path, questions=questions)

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
