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

@seller_bp.route('/dashboard')
def dashboard():
    # TODO: seller listings, balance, ratings summary
    return render_template('seller/dashboard.html')

@seller_bp.route('/list_product', methods=['GET', 'POST'])
def list_product():
    # TODO: product listing form + insert
    return render_template('seller/list_product.html')

@seller_bp.route('/questions')
def questions():
    # TODO: unanswered questions on seller's listings
    return render_template('seller/questions.html')

@seller_bp.route('/questions/<int:qid>/answer', methods=['POST'])
def answer_question(qid):
    # TODO: update question with answer
    return redirect(url_for('seller.questions'))

@seller_bp.route('/request_category', methods=['GET', 'POST'])
def request_category():
    # TODO: new category request -> Requests table
    return render_template('seller/request_category.html')
