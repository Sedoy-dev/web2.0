from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy import case
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# Модели базы данных
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)


class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))


class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(20), nullable=False, unique=True)
    lessons = db.Column(db.String(1000))


class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    upload_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.context_processor
def inject_now():
    return {'now': datetime.now(timezone.utc)}


# Главная страница
@app.route('/')
def home():
    news = News.query.order_by(News.date_posted.desc()).limit(3).all()
    photos = Photo.query.order_by(Photo.upload_date.desc()).limit(6).all()

    # Получаем все дни расписания
    schedule_days = Schedule.query.order_by(
        case(
            {"Понедельник": 1, "Вторник": 2, "Среда": 3, "Четверг": 4, "Пятница": 5},
            value=Schedule.day
        )
    ).all()

    # Формируем данные для шаблона
    schedule_data = []
    for day in schedule_days:
        lessons = json.loads(day.lessons)
        if lessons:  # Добавляем только дни с уроками
            schedule_data.append({
                'day': day.day,
                'lessons': lessons
            })

    return render_template('index.html',
                           news=news,
                           photos=photos,
                           schedule=schedule_data)


# Авторизация
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = db.session.query(User).filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('admin' if user.is_admin else 'home'))
        flash('Неверные учетные данные', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


# Админ-панель
@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('home'))
    return render_template('admin.html')


# Управление новостями
@app.route('/admin/news', methods=['GET', 'POST'])
@login_required
def manage_news():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        news = News(title=title, content=content, author_id=current_user.id)
        db.session.add(news)
        db.session.commit()
        flash('Новость успешно добавлена', 'success')
        return redirect(url_for('manage_news'))

    news_list = News.query.order_by(News.date_posted.desc()).all()
    return render_template('manage_news.html', news=news_list)


@app.route('/admin/delete_news/<int:id>')
@login_required
def delete_news(id):
    if not current_user.is_admin:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('home'))

    news = db.session.get(News, id)
    if news:
        db.session.delete(news)
        db.session.commit()
        flash('Новость успешно удалена', 'success')
    else:
        flash('Новость не найдена', 'warning')
    return redirect(url_for('manage_news'))


# Управление расписанием
@app.route('/admin/schedule', methods=['GET', 'POST'])
@login_required
def manage_schedule():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('home'))

    days_of_week = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница']

    if request.method == 'POST':
        # Обрабатываем все дни недели
        for day in days_of_week:
            lessons = []
            # Собираем уроки для текущего дня
            for i in range(10):  # 10 уроков максимум
                lesson_key = f"{day}-lesson{i}"
                lesson = request.form.get(lesson_key, '').strip()
                if lesson:  # Добавляем только непустые уроки
                    lessons.append(lesson)

            lessons_json = json.dumps(lessons)

            # Ищем или создаем запись для дня
            schedule = Schedule.query.filter_by(day=day).first()
            if schedule:
                schedule.lessons = lessons_json
            else:
                schedule = Schedule(day=day, lessons=lessons_json)
                db.session.add(schedule)

        db.session.commit()
        flash('Расписание успешно обновлено для всех дней', 'success')
        return redirect(url_for('manage_schedule'))

    # Подготавливаем данные для формы
    schedule_data = {}
    for day in days_of_week:
        db_day = Schedule.query.filter_by(day=day).first()
        schedule_data[day] = json.loads(db_day.lessons) if db_day else []

    return render_template('manage_schedule.html',
                           schedule=schedule_data,
                           days=days_of_week)

# Управление фотогалереей
@app.route('/admin/photos', methods=['GET', 'POST'])
@login_required
def manage_photos():
    if not current_user.is_admin:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        if 'photo' not in request.files:
            flash('Файл не выбран', 'danger')
            return redirect(url_for('manage_photos'))

        file = request.files['photo']
        if file.filename == '':
            flash('Файл не выбран', 'danger')
            return redirect(url_for('manage_photos'))

        if file:
            filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{file.filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            photo = Photo(
                filename=filename,
                description=request.form.get('description', '')
            )
            db.session.add(photo)
            db.session.commit()
            flash('Фото успешно загружено', 'success')
            return redirect(url_for('manage_photos'))

    photos = Photo.query.order_by(Photo.upload_date.desc()).all()
    return render_template('manage_photos.html', photos=photos)


@app.route('/admin/delete_photo/<int:id>')
@login_required
def delete_photo(id):
    if not current_user.is_admin:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('home'))

    photo = db.session.get(Photo, id)
    if photo:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], photo.filename))
        except OSError:
            pass
        db.session.delete(photo)
        db.session.commit()
        flash('Фото успешно удалено', 'success')
    else:
        flash('Фото не найдено', 'warning')
    return redirect(url_for('manage_photos'))


def init_db():
    with app.app_context():
        db.create_all()
        if not db.session.query(User).filter_by(username='admin').first():
            admin = User(
                username='admin',
                password=generate_password_hash('admin123'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()


if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    init_db()
    app.run(debug=True)