from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from threading import Thread
import requests
import time
import uuid

# Инициализация приложения Flask и конфигурация базы данных и веб-сокетов
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

socketio = SocketIO(app)
db = SQLAlchemy(app)
current_rates = {}

# Модель пользователя для базы данных
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Создание базы данных
with app.app_context():
    db.create_all()

# Функция для получения курсов валют с API Центробанка
def fetch_currency_rates():
    try:
        response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js")
        data = response.json()
        rates = {currency: {'Name': info['Name'], 'Value': info['Value']}
                 for currency, info in data['Valute'].items()}
        return rates
    except Exception as e:
        print(f"Error fetching rates: {e}")
        return None

# Наблюдатель за изменением курсов валют
def currency_observer():
    global current_rates
    while True:
        new_rates = fetch_currency_rates()
        if new_rates and new_rates != current_rates:
            current_rates = new_rates
            socketio.emit('currency_update', {'rates': current_rates})
        time.sleep(60)  # Интервал обновления курсов в секундах

# Маршрут для регистрации
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует!')
            return redirect(url_for('register'))
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Регистрация прошла успешно! Теперь войдите в систему.')
        return redirect(url_for('login'))
    return render_template('register.html')

# Маршрут для входа
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            flash('Вход выполнен успешно!')
            return redirect(url_for('index'))
        else:
            flash('Неправильное имя пользователя или пароль!')
    return render_template('login.html')

# Главная страница с отображением курсов
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

# Обработчик подключения веб-сокета
@socketio.on('connect')
def handle_connect():
    if 'user_id' not in session:
        return False  # отклонить подключение, если пользователь не авторизован
    client_id = str(uuid.uuid4())
    print(f'Клиент подключен с ID: {client_id}')
    emit('currency_update', {'rates': current_rates, 'client_id': client_id})

# Маршрут для выхода из системы
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы вышли из системы.')
    return redirect(url_for('login'))

# Запуск наблюдателя в отдельном потоке
if __name__ == '__main__':
    observer_thread = Thread(target=currency_observer)
    observer_thread.daemon = True
    observer_thread.start()
    socketio.run(app, port=5000)
