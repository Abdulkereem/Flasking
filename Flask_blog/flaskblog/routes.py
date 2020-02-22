import os
import secrets
from PIL import Image
from flask import render_template, url_for, flash, redirect, request, abort
from flaskblog import app, db, bcrypt, mail
from flaskblog.forms import (STUDENT_CODE, TEACHER_CODE, RegistrationForm, LoginForm, UpdateAccountForm,
                             PostForm, RequestResetForm, ResetPasswordForm, InsertGradeForm)
from flask_user import roles_required                             
from flaskblog.models import User, Post, Grade
from flask_login import login_user, current_user, logout_user, login_required
from flask_mail import Message


@app.route("/")
@app.route("/home")
@login_required
def home():
    page = request.args.get('page', 1, type=int)
    if current_user.user_type != 'teacher':
        posts = Post.query.filter_by(access=current_user.access).order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    else:
        posts = Post.query.order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    return render_template('home.html', posts=posts)

@app.route("/grade",  methods=['GET', 'POST'])
@login_required
def grade():
    if current_user.user_type == 'teacher':
        return render_template('grade.html', classes=STUDENT_CODE)
    
    grades = Grade.query.filter_by(user_id=current_user.id).all()
    print(current_user.id)
    print(grades)
    return render_template('myGrades.html', grades=grades)

@app.route("/grade/<string:class_access>", methods=['GET'])
@login_required
def classGrade(class_access):
    if current_user.user_type != 'teacher':
        return redirect(url_for('home'))

    students = User.query.filter_by(access=class_access).all()
    student_ids = [s.id for s in students]
    grades = Grade.query.all()
    names = set([g.title for g in grades if g.user_id in student_ids])
    return render_template('class_grades.html', gradetitles=names, class_value=class_access, class_name=STUDENT_CODE[class_access])

@app.route("/grade/<string:class_access>/<string:gradetitle>", methods=['GET'])
@login_required
def classAllGrades(class_access, gradetitle):
    if current_user.user_type != 'teacher':
        return redirect(url_for('home'))

    students = User.query.filter_by(access=class_access).all()
    student_ids = [s.id for s in students]
    grades = dict([(g.user_id, g.score) for g in Grade.query.filter_by(title=gradetitle).all()])
    newGradesList = [(s.id, s.first_name, s.last_name, 0 if s.id not in grades else grades[s.id]) for s in students]
    return render_template('grades.html', scores=newGradesList, class_value=class_access, class_name=STUDENT_CODE[class_access], gradetitle=gradetitle)

@app.route("/grade/new/<string:class_access>", methods=['GET'])
@login_required
def classNewGrades(class_access):
    if current_user.user_type != 'teacher':
        return redirect(url_for('home'))
    students = User.query.filter_by(access=class_access).all()
    newGradesList = [(s.id, s.first_name, s.last_name, 0) for s in students]
    return render_template('grades.html', scores=newGradesList, class_value=class_access, class_name=STUDENT_CODE[class_access], gradetitle='')

    


@app.route("/grade/update", methods=['POST'])
@login_required
def updateScores():
    # print(list(request.form.keys()))
    # print(request.form['score'])
    gradetitle = request.form['gradetitle']
    class_value = request.form['class_value']
    for k, v in request.form.items():
        if k == 'gradetitle' or k == 'class_value':
            continue
        student_id = int(k)
        try:
            score = int(v)
        except ValueError:
            flash('One of the scores is not a number.', 'danger')
            return redirect(request.url)
        grade = Grade.query.filter_by(user_id=current_user.id, title=gradetitle).first()
        if grade:
            grade.score = score
        else:
            grade = Grade(title=gradetitle, score=score, user_id=student_id)
            print(f'{student_id}, {score}')
            db.session.add(grade)
        db.session.commit()
    return redirect(url_for('classAllGrades', class_access=class_value, gradetitle=gradetitle))


@app.route("/about")
def about():
    return render_template('about.html', title='About')


@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        if form.secretcode.data not in TEACHER_CODE and form.secretcode.data not in STUDENT_CODE.keys():
            flash('Register failed. Wrong register code.', 'danger')
        else:
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
            user = User(username=form.username.data, email=form.email.data, password=hashed_password, first_name=form.first_name.data, last_name=form.last_name.data,
                        access=form.secretcode.data, user_type='student' if form.secretcode.data not in TEACHER_CODE else 'teacher')
            db.session.add(user)
            db.session.commit()
            flash('Your account has been created! You are now able to log in', 'success')
            return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)


@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)



@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('home'))


def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path, 'static/profile_pics', picture_fn)

    output_size = (125, 125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn


@app.route("/account", methods=['GET', 'POST'])
@login_required
def account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('Your account has been updated!', 'success')
        return redirect(url_for('account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
    image_file = url_for('static', filename='profile_pics/' + current_user.image_file)
    return render_template('account.html', title='Account',
                           image_file=image_file, form=form)


@app.route("/post/new", methods=['GET', 'POST'])
@login_required
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(title=form.title.data, content=form.content.data, author=current_user, access=form.target_class.data)
        db.session.add(post)
        db.session.commit()
        flash('Your post has been created!', 'success')
        return redirect(url_for('home'))
    return render_template('create_post.html', title='New Post',
                           form=form, legend='New Post', access=STUDENT_CODE)


@app.route("/post/<int:post_id>")
@login_required
def post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', title=post.title, post=post)


@app.route("/post/<int:post_id>/update", methods=['GET', 'POST'])
@login_required
def update_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        db.session.commit()
        flash('Your post has been updated!', 'success')
        return redirect(url_for('post', post_id=post.id))
    elif request.method == 'GET':
        form.title.data = post.title
        form.content.data = post.content
    return render_template('create_post.html', title='Update Post',
                           form=form, legend='Update Post')


@app.route("/post/<int:post_id>/delete", methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash('Your post has been deleted!', 'success')
    return redirect(url_for('home'))


@app.route("/user/<string:username>")
@login_required
def user_posts(username):
    page = request.args.get('page', 1, type=int)
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(author=user)\
        .order_by(Post.date_posted.desc())\
        .paginate(page=page, per_page=5)
    return render_template('user_posts.html', posts=posts, user=user)


def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request',
                  sender='noreply@demo.com',
                  recipients=[user.email])
    msg.body = f'''To reset your password, visit the following link:
{url_for('reset_token', token=token, _external=True)}
If you did not make this request then simply ignore this email and no changes will be made.
'''
    mail.send(msg)


@app.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        send_reset_email(user)
        flash('An email has been sent with instructions to reset your password.', 'info')
        return redirect(url_for('login'))
    return render_template('reset_request.html', title='Reset Password', form=form)


@app.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        flash('Your password has been updated! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('reset_token.html', title='Reset Password', form=form)