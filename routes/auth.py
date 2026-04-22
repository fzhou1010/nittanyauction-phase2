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

        if not user:
            flash('Invalid email or password.')
            return render_template('auth/login.html')

        session['email'] = email

        available_roles = get_user_roles(email)

        if len(available_roles) == 1:
            role = available_roles[0]
            session['roles'] = available_roles
            session['role'] = role
            session['available_roles'] = available_roles
            if role == 'seller':
                return redirect(url_for('seller.dashboard'))
            else:
                return redirect(url_for(f'{role}.welcome'))
        else:
            session['available_roles'] = available_roles
            return redirect(url_for('auth.choose_role'))

    return render_template('auth/login.html')

@auth_bp.route('/choose_role')
def choose_role():
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    if 'available_roles' not in session:
        return redirect(url_for('auth.login'))
    return render_template('auth/choose_role.html')

@auth_bp.route('/set_role/<role>')
def set_role(role):
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    if role in session.get('available_roles', []):
        session['roles'] = [role]
        session['role'] = role
        if role == 'seller':
            return redirect(url_for('seller.dashboard'))
        else:
            return redirect(url_for(f'{role}.welcome'))
    return redirect(url_for('auth.login'))

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
            phone = request.form['phone']
            street_num = request.form['street_num']
            street_name = request.form['street_name']
            zipcode = request.form['zipcode']
            city = request.form['city']
            state = request.form['state']
            address_id = uuid.uuid4().hex # generate a hex id for the address
            credit_card_num = request.form['credit_card_num']
            card_type = request.form['card_type']
            expire_month = request.form['expire_month']
            expire_year = request.form['expire_year']
            security_code = request.form['security_code']
            try:
                # the order of insert into matters, as we want don;t want an integrity error
                db.execute('INSERT INTO Users (email, password) VALUES (?, ?)', [email, hashed_pswd])
                # the zipcode enter fails when there is already a zipcode entered; use insert or ignore
                db.execute('INSERT OR IGNORE INTO Zipcode_Info (zipcode, city, state) VALUES (?, ?, ?)', [zipcode, city, state])
                db.execute('INSERT INTO Address (address_id, zipcode, street_num, street_name) VALUES (?, ?, ?, ?)',
                            [address_id, zipcode, street_num, street_name])
                db.execute('INSERT INTO Bidders (email, first_name, last_name, age, home_address_id, major, phone) VALUES (?, ?, ?, ?, ?, ?, ?)',
                           [email, first_name, last_name, age, address_id, major, phone])
                # Credit_Cards FK -> Bidders(email), so this must follow the Bidders insert
                db.execute('INSERT INTO Credit_Cards (credit_card_num, card_type, expire_month, expire_year, security_code, Owner_email) VALUES (?, ?, ?, ?, ?, ?)',
                           [credit_card_num, card_type, expire_month, expire_year, security_code, email])
                db.commit()
                session['email'] = email
                user_roles = get_user_roles(email)
                session['roles'] = user_roles
                session['role'] = 'bidder'
                session['available_roles'] = user_roles
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
            phone = request.form['phone']
            street_num = request.form['street_num']
            street_name = request.form['street_name']
            zipcode = request.form['zipcode']
            city = request.form['city']
            state = request.form['state']
            address_id = uuid.uuid4().hex # generate a hex id for the address
            bank_account_num = request.form['bank_account_num']
            bank_routing_num = request.form['bank_routing_num']
            credit_card_num = request.form['credit_card_num']
            card_type = request.form['card_type']
            expire_month = request.form['expire_month']
            expire_year = request.form['expire_year']
            security_code = request.form['security_code']
            try:
                # the order of insert into matters, as we want don;t want an integrity error
                db.execute('INSERT INTO Users (email, password) VALUES (?, ?)', [email, hashed_pswd])
                db.execute('INSERT OR IGNORE INTO Zipcode_Info (zipcode, city, state) VALUES (?, ?, ?)', [zipcode, city, state])
                db.execute('INSERT INTO Address (address_id, zipcode, street_num, street_name) VALUES (?, ?, ?, ?)',
                            [address_id, zipcode, street_num, street_name])
                db.execute('INSERT INTO Bidders (email, first_name, last_name, age, home_address_id, major, phone) VALUES (?, ?, ?, ?, ?, ?, ?)',
                           [email, first_name, last_name, age, address_id, major, phone]) # since student sellers are also bidders by default, they also need to be entered into the bidders relation
                db.execute('INSERT INTO Credit_Cards (credit_card_num, card_type, expire_month, expire_year, security_code, Owner_email) VALUES (?, ?, ?, ?, ?, ?)',
                           [credit_card_num, card_type, expire_month, expire_year, security_code, email])
                db.execute('INSERT INTO Sellers (email, bank_routing_number, bank_account_number) VALUES (?, ?, ?)',
                           [email, bank_routing_num, bank_account_num]) #we want the balance to be set to default in the schema, therefore we don't include a value here
                db.commit()
                session['email'] = email
                user_roles = get_user_roles(email)
                session['roles'] = user_roles
                session['role'] = 'seller'
                session['available_roles'] = user_roles
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
                user_roles = get_user_roles(email)
                session['roles'] = user_roles
                session['role'] = 'seller'
                session['available_roles'] = user_roles
                return redirect(url_for('seller.welcome')) #Todo: Make a local vendor welcome page, or should it be the same as the seller page
            except sql.IntegrityError:
                flash('Error saving information into the database.')
                return render_template('auth/register_form.html', role=role)
            except Exception as e:                                                                                                    
                flash(f'Error saving information: {e}')
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

    user_email = session['email']
    db = get_db()

    user_info = query_db('''
        SELECT first_name, last_name, age, major, home_address_id 
        FROM Bidders 
        WHERE email = ?''', [user_email], one=True)

    address_info = None
    if user_info and user_info['home_address_id']:
        address_info = query_db('''
            SELECT a.*, z.city, z.state
            FROM Address a
            JOIN Zipcode_Info z ON a.zipcode = z.zipcode
            WHERE a.address_id = ?''', [user_info['home_address_id']], one=True)

    cards = query_db('SELECT * FROM Credit_Cards WHERE Owner_email = ?', [user_email])

    if request.method == 'POST':
        form_type = request.form.get('form_type')

        if form_type == 'update_address':
            street_num = request.form.get('street_num')
            street_name = request.form.get('street_name')
            zipcode = request.form.get('zipcode')
            city = request.form.get('city')
            state = request.form.get('state')

            db.execute('INSERT OR IGNORE INTO Zipcode_Info (zipcode, city, state) VALUES (?, ?, ?)', 
                       [zipcode, city, state])

            db.execute('''
                UPDATE Address
                SET street_num = ?, street_name = ?, zipcode = ?
                WHERE address_id = ?''',
                [street_num, street_name, zipcode, user_info['home_address_id']])
            
            db.commit()
            flash('Address updated successfully!', 'success')

        elif form_type == 'change_password':
            old_password = request.form.get('old_password')
            new_password = request.form.get('new_password')

            user_account = query_db('SELECT password FROM Users WHERE email = ?', [user_email], one=True)

            current_hashed = hashlib.sha256(old_password.encode('utf-8')).hexdigest()
            if user_account and user_account['password'] == current_hashed:
                hashed_new = hashlib.sha256(new_password.encode('utf-8')).hexdigest()
                db.execute('UPDATE Users SET password = ? WHERE email = ?', [hashed_new, user_email])
                db.commit()
                flash('Password changed successfully!', 'success')
            else:
                flash('Incorrect current password.', 'danger')

        elif form_type == 'add_card':
            credit_card_num = request.form.get('credit_card_num')
            card_type = request.form.get('card_type')
            expire_month = request.form.get('expire_month')
            expire_year = request.form.get('expire_year')
            security_code = request.form.get('security_code')

            db.execute('''
                INSERT INTO Credit_Cards (credit_card_num, card_type, expire_month, expire_year, security_code, Owner_email) 
                VALUES (?, ?, ?, ?, ?, ?)''',
                [credit_card_num, card_type, expire_month, expire_year, security_code, user_email])
            db.commit()
            flash('Card added successfully!', 'success')

        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html', user=user_info, address=address_info, cards=cards)


@auth_bp.route('/profile/changeID', methods=['POST'])
def changeID():
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    
    new_email = request.form.get('new_email', '').strip()
    sender_email = session['email']

    if not new_email:
        flash('Please provide a new email address.', 'danger')
        return redirect(url_for('auth.profile'))

    unassigned_staff = 'helpdeskteam@lsu.edu'

    db = get_db()
    db.execute('''
        INSERT INTO Requests (sender_email, helpdesk_staff_email, request_type, request_desc, request_status)
        VALUES (?, ?, ?, ?, ?)''', [sender_email, unassigned_staff, 'ChangeID', f"NEW EMAIL: {new_email}", 0])
    db.commit()

    flash('Your request has been submitted. A HelpDesk staff member will review your email change.', 'success')
    return redirect(url_for('auth.profile'))

@auth_bp.route('/profile/promote', methods=['POST'])
def promote():
    if 'email' not in session:
        return redirect(url_for('auth.login'))
    
    user_email = session['email']    

    account_number = request.form.get('account_number','').strip()
    routing_number = request.form.get('routing_number','').strip()

    if not account_number or not routing_number:
        flash('Please provide both bank account number and routing number to apply for seller promotion.', 'danger')
        return redirect(url_for('auth.profile'))
    
    unassigned_staff = 'helpdeskteam@lsu.edu'
    
    request_desc = f"ROUTING:{routing_number} | ACCOUNT:{account_number}"
    db = get_db()

    db.execute('''
        INSERT INTO Requests (sender_email, helpdesk_staff_email, request_type, request_desc, request_status)
        VALUES (?, ?, ?, ?, ?)''', [user_email, unassigned_staff, 'BecomeSeller', request_desc , 0])
    db.commit()

    flash('Your request has been submitted. A HelpDesk staff member will review your request.', 'success')
    return redirect(url_for('auth.profile'))