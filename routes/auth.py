# auth.py — Handles login, logout, registration, and profile routes.

import re
import sqlite3 as sql
import uuid # use uuid for generating an hex id for the address
import hashlib
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db, query_db, format_request_desc, parse_request_desc, HELPDESK_TEAM_EMAIL

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

        if not available_roles:
            # Role-less account - direct to Pending User flow to submit a role request.
            session['available_roles'] = []
            return redirect(url_for('auth.pending_user'))

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

def _build_pending_prefill(email, last_request):
    # Pull whatever we already know about this email from prior state so the user
    # doesn't have to retype on resubmit. Priority: prior PendingRole payload,
    # then any partial Bidders / Address / Credit_Cards / Sellers rows (covers
    # edge cases like a previously-approved account that got re-orphaned).
    prefill = {}
    if last_request is not None:
        for k, v in parse_request_desc(last_request['request_desc']).items():
            if v not in (None, ''):
                prefill[k] = v

    bidder = query_db('SELECT * FROM Bidders WHERE email = ?', [email], one=True)
    if bidder:
        for field in ('first_name', 'last_name', 'age', 'major', 'phone'):
            val = bidder[field]
            if val not in (None, '') and not prefill.get(field):
                prefill[field] = val
        if bidder['home_address_id']:
            addr = query_db(
                'SELECT a.*, z.city, z.state FROM Address a '
                'LEFT JOIN Zipcode_Info z ON a.zipcode = z.zipcode '
                'WHERE a.address_id = ?',
                [bidder['home_address_id']], one=True,
            )
            if addr:
                for field in ('street_num', 'street_name', 'zipcode', 'city', 'state'):
                    val = addr[field]
                    if val not in (None, '') and not prefill.get(field):
                        prefill[field] = val

    cc = query_db(
        'SELECT * FROM Credit_Cards WHERE Owner_email = ? LIMIT 1',
        [email], one=True,
    )
    if cc:
        for field in ('credit_card_num', 'card_type', 'expire_month', 'expire_year', 'security_code'):
            val = cc[field]
            if val not in (None, '') and not prefill.get(field):
                prefill[field] = val

    seller = query_db('SELECT * FROM Sellers WHERE email = ?', [email], one=True)
    if seller:
        if not prefill.get('bank_routing_num') and seller['bank_routing_number']:
            prefill['bank_routing_num'] = seller['bank_routing_number']
        if not prefill.get('bank_account_num') and seller['bank_account_number']:
            prefill['bank_account_num'] = seller['bank_account_number']

    return prefill


@auth_bp.route('/pending_user', methods=['GET', 'POST'])
def pending_user():
    # Guard: require an authenticated session.
    if 'email' not in session:
        return redirect(url_for('auth.login'))

    email = session['email']

    # Role may have been approved since this session was established (e.g. user
    # refreshes the pending page after HelpDesk clicks Complete). Refresh the
    # session's role cache and route them into their new welcome flow instead
    # of sending them back through /login.
    current_roles = get_user_roles(email)
    if current_roles:
        session['roles'] = current_roles
        session['available_roles'] = current_roles
        if len(current_roles) == 1:
            role = current_roles[0]
            session['role'] = role
            flash('Your role has been approved. Welcome!')
            if role == 'seller':
                return redirect(url_for('seller.dashboard'))
            return redirect(url_for(f'{role}.welcome'))
        # Multi-role (e.g. seller approval inserts into both Bidders and Sellers).
        flash('Your role has been approved. Please choose which role to use.')
        return redirect(url_for('auth.choose_role'))

    db = get_db()

    # Find the most recent PendingRole request (if any) for this user.
    last_request = query_db(
        'SELECT * FROM Requests '
        'WHERE sender_email = ? AND request_type = ? '
        'ORDER BY request_id DESC LIMIT 1',
        [email, 'PendingRole'], one=True)

    # Any currently-open pending request (status=0) blocks new submissions.
    open_request = None
    if last_request is not None and last_request['request_status'] == 0:
        open_request = last_request

    if request.method == 'POST':
        # Block if already-open pending request.
        if open_request is not None:
            flash('You already have a pending role request.')
            parsed = parse_request_desc(open_request['request_desc'])
            return render_template(
                'auth/pending_user.html',
                status='pending',
                last_request=open_request,
                requested_role=parsed.get('requested_role'),
                prefill={},
            )

        requested_role = (request.form.get('requested_role') or '').strip().lower()
        if requested_role not in ('bidder', 'seller'):
            flash('Please select a valid role (bidder or seller).')
            # Decide render state based on prior history.
            if last_request is not None and last_request['request_status'] == 2:
                status = 'denied'
            else:
                status = 'new'
            return render_template(
                'auth/pending_user.html',
                status=status,
                last_request=last_request,
                requested_role=None,
                prefill=request.form.to_dict(),
            )

        # Required field set per role - mirrors register_form() for consistency.
        required = [
            'first_name', 'last_name', 'age', 'major', 'phone',
            'street_num', 'street_name', 'zipcode', 'city', 'state',
            'credit_card_num', 'card_type', 'expire_month', 'expire_year',
            'security_code',
        ]
        if requested_role == 'seller':
            required = required + ['bank_routing_num', 'bank_account_num']

        missing = [f for f in required if not (request.form.get(f) or '').strip()]
        if missing:
            flash('Please fill in all required fields: ' + ', '.join(missing))
            if last_request is not None and last_request['request_status'] == 2:
                status = 'denied'
            else:
                status = 'new'
            return render_template(
                'auth/pending_user.html',
                status=status,
                last_request=last_request,
                requested_role=None,
                prefill=request.form.to_dict(),
            )

        # Build payload fields (always personal+address+cc; bank only for seller).
        payload = {'requested_role': requested_role}
        for f in (
            'first_name', 'last_name', 'age', 'major', 'phone',
            'street_num', 'street_name', 'zipcode', 'city', 'state',
            'credit_card_num', 'card_type', 'expire_month', 'expire_year',
            'security_code',
        ):
            payload[f] = request.form.get(f, '').strip()
        if requested_role == 'seller':
            payload['bank_routing_num'] = request.form.get('bank_routing_num', '').strip()
            payload['bank_account_num'] = request.form.get('bank_account_num', '').strip()

        # Compute next request_id via MAX+1 (same pattern as seller.request_category).
        cur_id = query_db('SELECT MAX(request_id) AS cur_id FROM Requests', one=True)
        next_id = (cur_id['cur_id'] or 0) + 1

        db.execute(
            'INSERT INTO Requests '
            '(request_id, sender_email, helpdesk_staff_email, request_type, request_desc, request_status) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            [next_id, email, HELPDESK_TEAM_EMAIL, 'PendingRole',
             format_request_desc(**payload), 0])
        db.commit()

        flash('Role request submitted. A HelpDesk staff member will review it.')
        return redirect(url_for('auth.pending_user'))

    # GET: decide which state to render.
    if open_request is not None:
        parsed = parse_request_desc(open_request['request_desc'])
        return render_template(
            'auth/pending_user.html',
            status='pending',
            last_request=open_request,
            requested_role=parsed.get('requested_role'),
            prefill={},
        )
    if last_request is not None and last_request['request_status'] == 2:
        return render_template(
            'auth/pending_user.html',
            status='denied',
            last_request=last_request,
            requested_role=None,
            prefill=_build_pending_prefill(email, last_request),
        )
    return render_template(
        'auth/pending_user.html',
        status='new',
        last_request=None,
        requested_role=None,
        prefill=_build_pending_prefill(email, None),
    )

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
            required = ['first_name', 'last_name', 'phone', 'street_num', 'street_name', 'zipcode', 'city', 'state',
                        'credit_card_num', 'card_type', 'expire_month', 'expire_year', 'security_code']
            missing = [f for f in required if not request.form.get(f, '').strip()]
            if missing:
                flash('Please fill in all required fields: ' + ', '.join(missing))
                return render_template('auth/register_form.html', role=role)
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
            if query_db('SELECT 1 FROM Credit_Cards WHERE credit_card_num = ?', [credit_card_num], one=True):
                flash('Cards cannot be shared across accounts — this card is already registered to another user.')
                return render_template('auth/register_form.html', role=role)
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
            required = ['first_name', 'last_name', 'phone', 'street_num', 'street_name', 'zipcode', 'city', 'state',
                        'credit_card_num', 'card_type', 'expire_month', 'expire_year', 'security_code',
                        'bank_account_num', 'bank_routing_num']
            missing = [f for f in required if not request.form.get(f, '').strip()]
            if missing:
                flash('Please fill in all required fields: ' + ', '.join(missing))
                return render_template('auth/register_form.html', role=role)
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
            if query_db('SELECT 1 FROM Credit_Cards WHERE credit_card_num = ?', [credit_card_num], one=True):
                flash('Cards cannot be shared across accounts — this card is already registered to another user.')
                return render_template('auth/register_form.html', role=role)
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
                return redirect(url_for('seller.dashboard'))
            except sql.IntegrityError:
                flash('Error saving information into the database.')
                return render_template('auth/register_form.html', role=role)
        else: #means that the role is local_vendor
            required = ['business_name', 'cs_phone_num', 'street_num', 'street_name', 'zipcode', 'city', 'state',
                        'bank_account_num', 'bank_routing_num']
            missing = [f for f in required if not request.form.get(f, '').strip()]
            if missing:
                flash('Please fill in all required fields: ' + ', '.join(missing))
                return render_template('auth/register_form.html', role=role)
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
                db.commit()
                print('commit successful')
                session['email'] = email
                user_roles = get_user_roles(email)
                session['roles'] = user_roles
                session['role'] = 'seller'
                session['available_roles'] = user_roles
                return redirect(url_for('seller.dashboard'))
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
            credit_card_num = (request.form.get('credit_card_num') or '').strip()
            card_type = (request.form.get('card_type') or '').strip()
            expire_month = request.form.get('expire_month')
            expire_year = request.form.get('expire_year')
            security_code = (request.form.get('security_code') or '').strip()

            mine = query_db(
                'SELECT 1 FROM Credit_Cards WHERE credit_card_num = ? AND Owner_email = ?',
                [credit_card_num, user_email], one=True,
            )
            if mine:
                flash('You already have that card on your account.', 'danger')
            else:
                try:
                    db.execute('''
                        INSERT INTO Credit_Cards (credit_card_num, card_type, expire_month, expire_year, security_code, Owner_email)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                        [credit_card_num, card_type, expire_month, expire_year, security_code, user_email])
                    db.commit()
                    flash('Card added successfully!', 'success')
                except sql.IntegrityError:
                    flash('Cards cannot be shared across accounts — this card is already registered to another user.', 'danger')

        elif form_type == 'remove_card':
            # BR-22: scope the DELETE to the session owner so a crafted form
            # cannot remove another bidder's card.
            card_num = request.form.get('credit_card_num', '').strip()
            if not card_num:
                flash('Missing card reference.', 'danger')
            else:
                cur = db.execute(
                    'DELETE FROM Credit_Cards WHERE credit_card_num = ? AND Owner_email = ?',
                    [card_num, user_email],
                )
                db.commit()
                if cur.rowcount:
                    flash('Card removed.', 'success')
                else:
                    flash('Card not found.', 'danger')

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
    
    db = get_db()

    db.execute('''
        INSERT INTO Requests (sender_email, helpdesk_staff_email, request_type, request_desc, request_status)
        VALUES (?, ?, ?, ?, ?)''', [user_email, unassigned_staff, 'BecomeSeller', f"ROUTING:{routing_number} | ACCOUNT:{account_number}" , 0])
    db.commit()

    flash('Your request has been submitted. A HelpDesk staff member will review your request.', 'success')
    return redirect(url_for('auth.profile'))