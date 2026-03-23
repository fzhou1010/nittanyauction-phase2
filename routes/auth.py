# auth.py — Handles login, logout, registration, and profile routes.

import hashlib
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db

auth_bp = Blueprint('auth', __name__)

def get_user_roles(email):
    """Check which roles (bidder, seller, helpdesk) a user has by looking them up
    in the corresponding tables. A user can have multiple roles."""
    roles = []
    if query_db('SELECT 1 FROM Bidders WHERE email = ?', [email], one=True):
        roles.append('bidder')
    if query_db('SELECT 1 FROM Sellers WHERE email = ?', [email], one=True):
        roles.append('seller')
    if query_db('SELECT 1 FROM Helpdesk WHERE email = ?', [email], one=True):
        roles.append('helpdesk')
    return roles

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Hash the entered password with SHA256 to compare against the stored hash
        hashed = hashlib.sha256(password.encode('utf-8')).hexdigest()
        user = query_db('SELECT * FROM Users WHERE email = ? AND password = ?',
                        [email, hashed], one=True)

        if user:
            # Store user info in the session so other pages know who is logged in
            session['email'] = email
            roles = get_user_roles(email)
            session['roles'] = roles

            # Redirect to the appropriate welcome page based on the user's role
            if 'helpdesk' in roles:
                return redirect(url_for('helpdesk.welcome'))
            elif 'seller' in roles:
                return redirect(url_for('seller.welcome'))
            else:
                return redirect(url_for('bidder.welcome'))

        flash('Invalid email or password.')
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # TODO: registration form + insert into Users/Bidders
    return render_template('auth/register.html')

@auth_bp.route('/logout')
def logout():
    session.clear()  # Remove all session data (logs the user out)
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    # TODO: profile view/edit
    return render_template('auth/profile.html')
