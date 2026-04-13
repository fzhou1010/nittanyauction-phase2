# auth.py — Handles login, logout, registration, and profile routes.

import re
import sqlite3 as sql
import uuid # use uuid for generating an hex id for the address
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

        # Clear any existing session so a failed login doesn't mean that a user ahs logged in
        session.clear()

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
    return render_template('auth/register.html')

@auth_bp.route('/register/<role>', methods=['GET', 'POST'])
def register_form(role):
    # we can persist the role the user chose by including it in the URL of the browser
    if role not in ('bidder', 'student_seller', 'local_vendor'): # if somehow the roles are not one of the following, return
        return redirect(url_for('auth.register'))
    if request.method == 'POST':
        email = request.form['email'] # we use request.form for mandatory data
        pswd = request.form['password']
        confirm_pswd = request.form['confirm_password']


        # Some checks to validate the data before sending it to the database
        if role in ('bidder', 'student_seller'):
            #ensure that the email ends in LSU even though it should be enforced client side
            if not email.endswith('@lsu.edu'):
                flash('Bidders/Student sellers must use an @lsu.edu email address')
                return render_template('auth/register_form.html', role=role)
        if pswd != confirm_pswd:
            flash("Passwords don't Match")
            return render_template('auth/register_form.html', role=role)
        
        #hash the passwords based on the requirement by the SHA256 encoding
        hashed_pswd = hashlib.sha256(pswd.encode('utf-8')).hexdigest()
        #check if the email already exists in the database
        user = query_db('SELECT * FROM Users WHERE email = ?',
                        [email], one=True)
        
        if user: # means that this user has already been registered to the database
            flash('Email already registered to an account, please login with correct credentials')
            return render_template('auth/register_form.html', role=role)
        
        #everything passed, meaning ready to send to database
        # we want to get the corresponding data for the specific roles
        db = get_db()
        if role == 'bidder':
            first_name = request.form['first_name']
            last_name = request.form['last_name']
            age = request.form.get('age') # we can use .get from the forms as these fields are not mandatory to the user signing up to use the page
            major = request.form.get('major')
            street_num = request.form['street_num']
            street_name = request.form['street_name']
            zipcode = request.form['zipcode']
            city = request.form['city']
            state = request.form['state']
            address_id = uuid.uuid4().hex # generate a hex id for the address
            try:
                # the order of insert into matters, as we want don;t want an integrity error
                db.execute('INSERT INTO Users (email, password) VALUES (?, ?)', [email, hashed_pswd])
                # the zipcode enter fails when there is already a zipcode entered; use insert or ignore
                db.execute('INSERT OR IGNORE INTO Zipcode_Info (zipcode, city, state) VALUES (?, ?, ?)', [zipcode, city, state])
                db.execute('INSERT INTO Address (address_id, zipcode, street_num, street_name) VALUES (?, ?, ?, ?)',
                            [address_id, zipcode, street_num, street_name])
                db.execute('INSERT INTO Bidders (email, first_name, last_name, age, home_address_id, major) VALUES (?, ?, ?, ?, ?, ?)', 
                           [email, first_name, last_name, age, address_id, major])
                db.commit()
                session['email'] = email
                session['roles'] = get_user_roles(email)
                return redirect(url_for('bidder.welcome'))

            #except Exception as e:
                #flash(f'Error saving information into the database: {e}')
            except sql.IntegrityError:
                flash('Error saving information into the database.')
                return render_template('auth/register_form.html', role=role)
            
        elif role == 'student_seller':
            first_name = request.form['first_name']
            last_name = request.form['last_name']
            age = request.form.get('age') # we can use .get from the forms as these fields are not mandatory to the user signing up to use the page
            major = request.form.get('major')
            street_num = request.form['street_num']
            street_name = request.form['street_name']
            zipcode = request.form['zipcode']
            city = request.form['city']
            state = request.form['state']
            address_id = uuid.uuid4().hex # generate a hex id for the address
            bank_account_num = request.form['bank_account_num']
            bank_routing_num = request.form['bank_routing_num']
            try:
                # the order of insert into matters, as we want don;t want an integrity error
                db.execute('INSERT INTO Users (email, password) VALUES (?, ?)', [email, hashed_pswd])
                db.execute('INSERT OR IGNORE INTO Zipcode_Info (zipcode, city, state) VALUES (?, ?, ?)', [zipcode, city, state])
                db.execute('INSERT INTO Address (address_id, zipcode, street_num, street_name) VALUES (?, ?, ?, ?)',
                            [address_id, zipcode, street_num, street_name])
                db.execute('INSERT INTO Bidders (email, first_name, last_name, age, home_address_id, major) VALUES (?, ?, ?, ?, ?, ?)', 
                           [email, first_name, last_name, age, address_id, major]) # since student sellers are also bidders by default, they also need to be entered into the bidders relation
                db.execute('INSERT INTO Sellers (email, bank_routing_number, bank_account_number) VALUES (?, ?, ?)', 
                           [email, bank_routing_num, bank_account_num]) #we want the balance to be set to default in the schema, therefore we don't include a value here
                db.commit()
                session['email'] = email
                session['roles'] = get_user_roles(email)
                return redirect(url_for('seller.welcome'))
            except sql.IntegrityError:
                flash('Error saving information into the database.')
                return render_template('auth/register_form.html', role=role)
        else: #means that the role is local_vendor
            business_name = request.form['business_name']
            cs_phone_num = request.form['cs_phone_num']
            #business address information, saved to the address table
            street_num = request.form['street_num']
            street_name = request.form['street_name']
            zipcode = request.form['zipcode']
            city = request.form['city']
            state = request.form['state']
            address_id = uuid.uuid4().hex # generate a hex id for the address
            bank_account_num = request.form['bank_account_num']
            bank_routing_num = request.form['bank_routing_num']
            try:
                 # the order of insert into matters, as we want don;t want an integrity error
                db.execute('INSERT INTO Users (email, password) VALUES (?, ?)', [email, hashed_pswd])
                db.execute('INSERT OR IGNORE INTO Zipcode_Info (zipcode, city, state) VALUES (?, ?, ?)', [zipcode, city, state])
                db.execute('INSERT INTO Address (address_id, zipcode, street_num, street_name) VALUES (?, ?, ?, ?)',
                            [address_id, zipcode, street_num, street_name])
                db.execute('INSERT INTO Sellers (email, bank_routing_number, bank_account_number) VALUES (?, ?, ?)', 
                           [email, bank_routing_num, bank_account_num]) #we want the balance to be set to default in the schema, therefore we don't include a value here
                db.execute('INSERT INTO Local_Vendors (email, business_name, business_address_id, customer_service_phone_number) VALUES (?, ?, ?, ?)', 
                           [email, business_name, address_id, cs_phone_num])
                print(f'Commiting the local vendor with email: {email}')
                db.commit()
                print('commit successful')
                session['email'] = email
                session['roles'] = get_user_roles(email)
                return redirect(url_for('seller.welcome')) #Todo: Make a local vendor welcome page, or should it be the same as the seller page
            except Exception as e:                                                                                                    
                flash(f'Error saving information: {e}')
                return render_template('auth/register_form.html', role=role)
            except sql.IntegrityError:
                flash('Error saving information into the database.')
                return render_template('auth/register_form.html', role=role)
            


        
    return render_template('auth/register_form.html', role=role)
    

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
