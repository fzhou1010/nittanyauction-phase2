from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db

listings_bp = Blueprint('listings', __name__)

@listings_bp.route('/browse')
def browse():
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    # TODO: category browsing, listing display
    return render_template('listings/browse.html')

@listings_bp.route('/search')
def search():
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    # TODO: keyword/category/price search
    return render_template('listings/search.html')

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
