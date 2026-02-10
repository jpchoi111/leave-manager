# app/auth.py
from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_user, logout_user
from .models import User

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and user.check_password(request.form["password"]):
            login_user(user)

            session.permanent = True
            flash("로그인 성공!", "success")
            return redirect(url_for("main.index"))
        
        flash("이메일 또는 비밀번호가 틀렸습니다.", "danger")
        return "로그인 실패", 401
    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
