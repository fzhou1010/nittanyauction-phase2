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
    # TODO: listing detail, bid history, Q&A
    return render_template('listings/detail.html')

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
