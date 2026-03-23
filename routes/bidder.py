from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db

bidder_bp = Blueprint('bidder', __name__)

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
