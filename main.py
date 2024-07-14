from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from flask_sqlalchemy import SQLAlchemy
import pyqrcode
import io
import base64
from datetime import datetime, timedelta
import logging

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Sample desk list
desks = [
    {"id": 1, "name": "Desk 1", "available": True},
    {"id": 2, "name": "Desk 2", "available": True},
    {"id": 3, "name": "Desk 3", "available": True},
]

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)

    def __repr__(self):
        return '<User %r>' % self.username

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    desk_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            session['user_email'] = user.email
            return redirect(url_for('booking'))
        else:
            username = request.form['username']
            new_user = User(username=username, email=email)
            db.session.add(new_user)
            db.session.commit()
            session['user_email'] = new_user.email
            return redirect(url_for('booking'))
    else:
        users = User.query.all()
        return render_template('index.html', users=users)

@app.route('/booking')
def booking():
    if 'user_email' not in session:
        return redirect(url_for('index'))
    return render_template('booking.html')

@app.route('/logoff')
def logoff():
    session.pop('user_email', None)
    return redirect(url_for('index'))

# Fetch the list of desks
@app.route('/desks', methods=['GET'])
def get_desks():
    return jsonify(desks)

# Fetch reservation data for a specific desk
@app.route('/reservations/<int:desk_id>', methods=['GET'])
def get_reservations(desk_id):
    reservations = Reservation.query.filter_by(desk_id=desk_id).all()
    reservation_data = []
    for reservation in reservations:
        reservation_data.append({
            "start_time": reservation.start_time.strftime('%Y-%m-%dT%H:%M'),
            "end_time": reservation.end_time.strftime('%Y-%m-%dT%H:%M')
        })
    return jsonify(reservation_data)

# Fetch reservation data for a specific desk and month
@app.route('/reservations/<int:desk_id>/month/<int:year>/<int:month>', methods=['GET'])
def get_month_reservations(desk_id, year, month):
    reservations = Reservation.query.filter(
        Reservation.desk_id == desk_id,
        Reservation.start_time >= datetime(year, month, 1),
        Reservation.start_time < datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1)
    ).all()

    days_status = {}
    for day in range(1, 32):
        try:
            date = datetime(year, month, day)
        except ValueError:
            break

        reserved_hours = 0
        for reservation in reservations:
            if reservation.start_time.date() <= date.date() <= reservation.end_time.date():
                start = max(reservation.start_time, datetime(year, month, day, 8))
                end = min(reservation.end_time, datetime(year, month, day, 22))
                reserved_hours += (end - start).total_seconds() / 3600

        if reserved_hours >= 14:
            days_status[day] = 'reserved'
        elif reserved_hours > 0:
            days_status[day] = 'partial'
        else:
            days_status[day] = 'available'

    return jsonify(days_status)

@app.route('/reserve_desk', methods=['POST'])
def reserve_desk():
    try:
        if 'user_email' not in session:
            return jsonify({"message": "User not logged in."}), 401

        data = request.form
        desk_id = int(data.get('desk_id'))
        user_email = session['user_email']
        start_time_str = data.get('start_datetime')
        end_time_str = data.get('end_datetime')

        user = User.query.filter_by(email=user_email).first()
        if not user:
            return jsonify({"message": "User not found."}), 404

        start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')

        if start_time >= end_time:
            return jsonify({"message": "End time must be after start time."}), 400

        # Check for overlapping reservations
        overlapping_reservations = Reservation.query.filter(
            Reservation.desk_id == desk_id,
            Reservation.start_time < end_time,
            Reservation.end_time > start_time
        ).all()

        if overlapping_reservations:
            return jsonify({"message": "This desk is already reserved for the selected time period."}), 400

        new_reservation = Reservation(
            desk_id=desk_id,
            user_id=user.id,
            start_time=start_time,
            end_time=end_time
        )
        db.session.add(new_reservation)
        db.session.commit()

        qr = pyqrcode.create(f"Desk reservation: {desk_id}, User: {user.username}, Start: {start_time}, End: {end_time}")
        buffer = io.BytesIO()
        qr.png(buffer, scale=2)  # Smaller QR code
        qr_code_data = buffer.getvalue()

        # Convert QR code binary data to Base64
        qr_code_base64 = base64.b64encode(qr_code_data).decode('utf-8')

        reservation_info = {
            "message": f"Desk {desk_id} has been reserved from {start_time} to {end_time}.",
            "qr_code": qr_code_base64
        }

        session['reservation_info'] = reservation_info
        return redirect(url_for('reservation_info'))
    except Exception as e:
        app.logger.error(f"Error while reserving desk: {e}")
        return jsonify({"message": f"An error occurred while processing your request: {e}"}), 500

@app.route('/reservation_info')
def reservation_info():
    reservation_info = session.get('reservation_info', None)
    if not reservation_info:
        reservation_info = {"message": "No reservation info available.", "qr_code": ""}
    return render_template('reservation_info.html', reservation_info=reservation_info)

@app.route('/user_reservations', methods=['GET'])
def user_reservations():
    if 'user_email' not in session:
        return redirect(url_for('index'))
    user_email = session['user_email']
    user = User.query.filter_by(email=user_email).first()
    if not user:
        return jsonify({"message": "User not found."}), 404

    reservations = Reservation.query.filter_by(user_id=user.id).all()
    reserved_desks = []
    for reservation in reservations:
        desk = next((d for d in desks if d['id'] == reservation.desk_id), None)
        if desk:
            reserved_desks.append({
                "id": desk['id'],
                "name": desk['name'],
                "start_time": reservation.start_time.strftime('%Y-%m-%d %H:%M'),
                "end_time": reservation.end_time.strftime('%Y-%m-%d %H:%M')
            })
    return render_template('user_reservations.html', reserved_desks=reserved_desks, email=user_email)

# Unreserve a desk
@app.route('/unreserve_desk', methods=['POST'])
def unreserve_desk():
    try:
        if 'user_email' not in session:
            return jsonify({"message": "User not logged in."}), 401

        desk_id = int(request.form['desk_id'])
        user_email = session['user_email']
        user = User.query.filter_by(email=user_email).first()
        if not user:
            return jsonify({"message": "User not found."}), 404

        reservation = Reservation.query.filter_by(desk_id=desk_id, user_id=user.id).first()
        if reservation:
            db.session.delete(reservation)
            db.session.commit()
            return redirect(url_for('user_reservations'))
        else:
            return jsonify({"message": f"No reservation found for desk {desk_id} by this user."}), 404
    except Exception as e:
        app.logger.error(f"Error while unreserving desk: {e}")
        return jsonify({"message": f"An error occurred while processing your request: {e}"}), 500

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='127.0.0.1', port=5000)
