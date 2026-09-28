import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'elite_gaming_ultimate_v4'

# DATABASE CONFIG
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'elite_gaming.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# MODELS
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    role = db.Column(db.String(10)) # admin/staff

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    rate_per_hour = db.Column(db.Float)

class Station(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20))
    status = db.Column(db.String(20), default='Available')

class GameSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    station_id = db.Column(db.Integer)
    game_name = db.Column(db.String(50))
    start_time = db.Column(db.DateTime, default=datetime.now)
    end_time = db.Column(db.DateTime, nullable=True)
    total_cost = db.Column(db.Float, default=0.0)
    payment_method = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)

# SYSTEM INITIALIZATION 
with app.app_context(): #allows database operations to happen while Flask knows which application is being used
    db.create_all() #creates database tables if they do not exist
    if not User.query.filter_by(username="admin").first(): #checks if admin is hashed
        pw = generate_password_hash("admin123", method='pbkdf2:sha256')
        db.session.add(User(username="admin", password=pw, role="admin"))
        for i in range(1, 31):
            db.session.add(Station(name=f"ST {i}"))
        db.session.add(Game(name="FIFA 24", rate_per_hour=200.0))#initial game
        db.session.commit()#save everything permanently to db

# AUTH ROUTES
@app.route('/') #route decorator
def index(): return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST': #checks whether the login form has been submitted
        u, p, r = request.form['username'], request.form['password'], request.form['role']# retrieve HTML FORMS
        user = User.query.filter_by(username=u, role=r).first()# SEARCHES FOR USER
        if user and check_password_hash(user.password, p):
            session['user_id'], session['role'] = user.id, user.role
            return redirect(url_for('admin_dashboard' if r == 'admin' else 'user_dashboard'))
        flash("Invalid login credentials") #displays error message
    return render_template('login.html')#shows login page again

@app.route('/logout')
def logout():
    session.clear()#remove stored session info
    return redirect(url_for('login'))#takes back to login

#ADMIN DASHBOARD
@app.route('/admin/dashboard')#admin dashboard route
def admin_dashboard():
    if session.get('role') != 'admin': return redirect(url_for('login'))#authorises
    today_sales = db.session.query(func.sum(GameSession.total_cost)).filter(func.date(GameSession.end_time) == date.today()).scalar() or 0
    return render_template('admin_dashboard.html', stations=Station.query.all(), games=Game.query.all(), total_sales=round(today_sales, 2))

#ANALYTICS & REPORTS
@app.route('/admin/analytics')
def admin_analytics():
    if session.get('role') != 'admin': return redirect(url_for('login'))#only allows admins

    last_7_days, revenues = [], []
    for i in range(6, -1, -1):
        day = date.today() - timedelta(days=i)#calculates all the days
        rev = db.session.query(func.sum(GameSession.total_cost)).filter(func.date(GameSession.end_time) == day).scalar() or 0#sum of all sales during the day
        last_7_days.append(day.strftime('%a'))#changes days to the name weekday
        revenues.append(rev)#revenue is stored here

    reports = GameSession.query.filter_by(is_active=False ) .order_by(GameSession.end_time.desc()).limit(20).all()# get the 20 most recent sessions
    return render_template('analytics.html', labels=last_7_days, values=revenues,reports=reports)

#USER DASHBOARD
@app.route('/user/dashboard')
def user_dashboard():
    if not session.get('user_id'): return redirect(url_for('login'))#if noone is logged in they are sent back to login
    return render_template('user_dashboard.html', stations=Station.query.all(), games=Game.query.all(), active_sessions=GameSession.query.filter_by(is_active=True).all())

#ACTION ROUTES
@app.route('/toggle_service/<int:id>')
def toggle_service(id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    s = Station.query.get(id)#finds station
    s.status = 'Out of Service' if s.status != 'Out of Service' else 'Available'
    db.session.commit()#save changes
    return redirect(url_for('admin_dashboard'))

@app.route('/add_game', methods=['POST'])#only allows posts
def add_game():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    db.session.add(Game(name=request.form['name'], rate_per_hour=float(request.form['rate'])))#gets the name and rate from the form
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/update_game', methods=['POST'])#changing hourly rate
def update_game():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    g = Game.query.get(request.form['game_id'])#finds game
    g.rate_per_hour = float(request.form['rate'])#changess rate
    db.session.commit()#saves update
    return redirect(url_for('admin_dashboard'))

@app.route('/add_user', methods=['POST'])#create staff account
def add_user():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    pw = generate_password_hash(request.form['password'], method='pbkdf2:sha256')#hashes password
    db.session.add(User(username=request.form['username'], password=pw, role='staff'))#creates a staff user
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/start_session', methods=['POST'])#starting a session
def start_session():
    s = Station.query.get(request.form['station_id'])#receive station id
    if s and s.status == 'Available':
        s.status = 'Busy'
        db.session.add(GameSession(station_id=s.id, game_name=request.form['game_name']))#adds a new gaming session
        db.session.commit()
    return redirect(url_for('user_dashboard'))

@app.route('/stop_session/<int:id>', methods=['POST'])#session id received by URL
def stop_session(id):
    gs = GameSession.query.get(id)#finds session
    if gs and gs.is_active:
        game = Game.query.filter_by(name=gs.game_name).first()#find game assosiated with what session
        gs.end_time = datetime.now()#record end time
        duration = (gs.end_time - gs.start_time).total_seconds() / 3600
        gs.total_cost = round(max(duration * game.rate_per_hour, 10.0), 2)
        gs.payment_method, gs.is_active = request.form['payment_method'], False#payment method stored
        Station.query.get(gs.station_id).status = 'Available'#sattion becomes available again
        db.session.commit()
        return redirect(url_for('view_receipt', session_id=gs.id))#redirect to receipt
    return redirect(url_for('user_dashboard'))

@app.route('/receipt/<int:session_id>')#receive session id
def view_receipt(session_id):
    gs = GameSession.query.get(session_id)
    return render_template('receipt.html', session=gs)

if __name__ == '__main__':
    app.run(debug=True)#makes troubleshooting easierc