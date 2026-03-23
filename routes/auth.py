import hashlib
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db

auth_bp = Blueprint('auth', __name__)

def get_user_roles(email):
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
        hashed = hashlib.sha256(password.encode('utf-8')).hexdigest()
        user = query_db('SELECT * FROM Users WHERE email = ? AND password = ?',
                        [email, hashed], one=True)
        if user:
            session['email'] = email
            roles = get_user_roles(email)
            session['roles'] = roles
            # Redirect to role-specific welcome page
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
    session.clear()
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    # TODO: profile view/edit
    return render_template('auth/profile.html')
