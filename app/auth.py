# app/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, current_user
from itsdangerous import URLSafeTimedSerializer
from .models import User
from .extensions import db
from flask_mail import Message
from .extensions import mail

auth_bp = Blueprint("auth", __name__)

# 시크릿 키로 토큰 생성
def generate_reset_token(email, secret_key, expiration=3600):
    s = URLSafeTimedSerializer(secret_key)
    return s.dumps(email, salt="password-reset-salt")

def verify_reset_token(token, secret_key, expiration=3600):
    s = URLSafeTimedSerializer(secret_key)
    try:
        email = s.loads(token, salt="password-reset-salt", max_age=expiration)
    except Exception:
        return None
    return User.query.filter_by(email=email).first()


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and user.check_password(request.form["password"]):
            login_user(user)
            flash("로그인 성공!", "success")
            return redirect(url_for("main.index"))

        flash("이메일 또는 비밀번호가 틀렸습니다.", "danger")
        return render_template("login.html")
    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("로그아웃 되었습니다.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/reset_password_request", methods=["GET", "POST"])
def reset_password_request():
    if request.method == "POST":
        email = request.form["email"]
        user = User.query.filter_by(email=email).first()
        if user:
            token = generate_reset_token(email, secret_key=current_app.config["SECRET_KEY"])
            reset_url = url_for("auth.reset_password", token=token, _external=True)

            msg = Message(
                subject="비밀번호 재설정 안내",
                recipients=[email],
                body=f"아래 링크를 클릭해서 비밀번호를 재설정하세요:\n{reset_url}"
            )
            mail.send(msg)
            flash("비밀번호 재설정 링크를 이메일로 보냈습니다.", "info")
        else:
            flash("가입된 이메일이 아닙니다.", "warning")
        return redirect(url_for("auth.login"))
    return render_template("reset_password_request.html")


@auth_bp.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = verify_reset_token(token, secret_key=current_app.config["SECRET_KEY"])
    if not user:
        flash("유효하지 않거나 만료된 토큰입니다.", "danger")
        return redirect(url_for("auth.reset_password_request"))

    if request.method == "POST":
        new_password = request.form["password"]
        user.set_password(new_password)
        db.session.commit()
        flash("비밀번호가 성공적으로 변경되었습니다.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html")