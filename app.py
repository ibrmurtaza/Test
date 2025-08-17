import os
from io import BytesIO
from datetime import datetime

from flask import (Flask, render_template, redirect, url_for, request, flash,
                   send_file)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, login_required,
                         logout_user, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///datacleanr.db'
app.config['UPLOAD_FOLDER'] = 'uploads'

# database setup
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# in-memory store for processed data
processed_data = {}


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))


class CleaningHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    original_filename = db.Column(db.String(150))
    cleaned_filename = db.Column(db.String(150))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def clean_dataframe(df, remove_duplicates=True, fill_missing=True,
                    standardize=True, normalize=True):
    """Clean dataframe according to options."""
    cleaned = df.copy()
    if remove_duplicates:
        cleaned = cleaned.drop_duplicates()
    if fill_missing:
        for col in cleaned.columns:
            if pd.api.types.is_numeric_dtype(cleaned[col]):
                cleaned[col].fillna(cleaned[col].median(), inplace=True)
                cleaned[col] = pd.to_numeric(cleaned[col], errors='coerce').astype(float)
            else:
                cleaned[col].fillna('N/A', inplace=True)
    if standardize:
        for col in cleaned.columns:
            if 'date' in col.lower() or pd.api.types.is_datetime64_any_dtype(cleaned[col]):
                cleaned[col] = pd.to_datetime(cleaned[col], errors='coerce').dt.strftime('%Y-%m-%d')
            elif pd.api.types.is_numeric_dtype(cleaned[col]):
                cleaned[col] = pd.to_numeric(cleaned[col], errors='coerce').astype(float)
    if normalize:
        for col in cleaned.columns:
            if pd.api.types.is_object_dtype(cleaned[col]):
                cleaned[col] = cleaned[col].astype(str).str.title()
    return cleaned


@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('signup'))
        new_user = User(email=email, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        flash('Account created, please login')
        return redirect(url_for('login'))
    return render_template('signup.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        file = request.files.get('data_file')
        if not file:
            flash('No file selected')
            return redirect(request.url)
        try:
            if file.filename.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
        except Exception:
            flash('Could not read file')
            return redirect(request.url)
        # free tier limit
        if df.shape[0] > 1000:
            flash('Dataset exceeds free tier limit (1000 rows)')
            return redirect(request.url)
        auto = 'auto_clean' in request.form
        options = {
            'remove_duplicates': auto or 'remove_duplicates' in request.form,
            'fill_missing': auto or 'fill_missing' in request.form,
            'standardize': auto or 'standardize' in request.form,
            'normalize': auto or 'normalize' in request.form,
        }
        cleaned = clean_dataframe(df, **options)
        buffer = BytesIO()
        cleaned.to_csv(buffer, index=False)
        buffer.seek(0)
        cleaned_name = f"cleaned_{file.filename}"
        history = CleaningHistory(user_id=current_user.id,
                                  original_filename=file.filename,
                                  cleaned_filename=cleaned_name)
        db.session.add(history)
        db.session.commit()
        processed_data[current_user.id] = {
            'original': df.head(20).to_html(classes='data'),
            'cleaned': cleaned.head(20).to_html(classes='data'),
            'download': buffer.getvalue(),
            'download_name': cleaned_name,
        }
        return redirect(url_for('result'))
    return render_template('upload.html')


@app.route('/result')
@login_required
def result():
    data = processed_data.get(current_user.id)
    if not data:
        return redirect(url_for('dashboard'))
    return render_template('result.html', original=data['original'], cleaned=data['cleaned'])


@app.route('/download')
@login_required
def download():
    data = processed_data.get(current_user.id)
    if not data:
        return redirect(url_for('dashboard'))
    return send_file(BytesIO(data['download']), as_attachment=True,
                     download_name=data['download_name'], mimetype='text/csv')


@app.route('/history')
@login_required
def history():
    records = (CleaningHistory.query
               .filter_by(user_id=current_user.id)
               .order_by(CleaningHistory.timestamp.desc()).all())
    return render_template('history.html', records=records)


@app.route('/account')
@login_required
def account():
    return render_template('account.html', user=current_user)


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0')
