# app/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from datetime import datetime, timedelta
from .extensions import db
from .models import User, Leave, LeaveBalance

bp = Blueprint("main", __name__)

@bp.route("/")
def index():
    return render_template("index.html")

# ------------------- 직원 목록 -------------------
@bp.route("/users")
def user_list():
    users = User.query.all()
    return render_template("users.html", users=users)

# ------------------- 직원 추가 -------------------
@bp.route("/users/add", methods=["GET", "POST"])
def add_user():
    if request.method == "POST":
        user = User(
            name=request.form["name"],
            email=request.form["email"]
        )
        db.session.add(user)
        db.session.commit()
        return redirect(url_for("main.user_list"))
    return render_template("add_user.html")

# ------------------- 직원 삭제 -------------------
@bp.route("/users/delete/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    Leave.query.filter_by(user_id=user.id).delete()
    LeaveBalance.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for("main.user_list"))

# ------------------- 휴가 목록 -------------------
@bp.route("/leaves")
def leave_list():
    leaves = Leave.query
    view = request.args.get("view", "month")
    today = datetime.today().date()

    if view == "week":
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        leaves = leaves.filter(Leave.start_date <= end_of_week, Leave.end_date >= start_of_week)
    elif view == "month":
        start_of_month = today.replace(day=1)
        if start_of_month.month == 12:
            next_month = start_of_month.replace(year=start_of_month.year+1, month=1, day=1)
        else:
            next_month = start_of_month.replace(month=start_of_month.month+1, day=1)
        end_of_month = next_month - timedelta(days=1)
        leaves = leaves.filter(Leave.start_date <= end_of_month, Leave.end_date >= start_of_month)
    elif view == "year":
        start_of_year = today.replace(month=1, day=1)
        end_of_year = today.replace(month=12, day=31)
        leaves = leaves.filter(Leave.start_date <= end_of_year, Leave.end_date >= start_of_year)

    leaves = leaves.order_by(Leave.start_date).all()
    return render_template("leave_list.html", leaves=leaves, view=view)

# ------------------- 연차 추가 -------------------
@bp.route("/leave-balance/add", methods=["GET", "POST"])
def add_leave_balance():
    user_id = request.args.get("user_id", type=int)
    if request.method == "POST":
        user_id = int(request.form["user_id"])
        year = int(request.form["year"])
        total_days = float(request.form["total_days"])
        balance = LeaveBalance.query.filter_by(user_id=user_id, year=year).first()
        if balance:
            balance.total_days = total_days
        else:
            balance = LeaveBalance(user_id=user_id, year=year, total_days=total_days)
            db.session.add(balance)
        db.session.commit()
        return redirect(url_for("main.user_list"))

    if user_id:
        users = User.query.filter_by(id=user_id).all()
    else:
        users = User.query.all()
    return render_template("leave_balance_form.html", users=users)

# ------------------- 휴가 신청 -------------------
@bp.route("/leaves/add", methods=["GET", "POST"])
def add_leave():
    users = User.query.all()
    if request.method == "POST":
        user = User.query.get_or_404(int(request.form["user_id"]))
        leave = Leave(
            user_id=user.id,
            start_date=datetime.strptime(request.form["start_date"], "%Y-%m-%d"),
            end_date=datetime.strptime(request.form["end_date"], "%Y-%m-%d"),
            half_day="half_day" in request.form,
            reason=request.form["reason"],
            status="Pending"
        )
        used_days = leave.days
        year = leave.start_date.year
        requestable = user.requestable_leave_by_year.get(year, 0)
        if used_days > requestable:
            return "신청 가능한 연차를 초과했습니다.", 400

        db.session.add(leave)
        db.session.commit()
        return redirect(url_for("main.leave_list"))

    return render_template("add_leave.html", users=users)

# ------------------- 휴가 승인 -------------------
@bp.route("/leaves/<int:leave_id>/approve", methods=["POST"])
def approve_leave(leave_id):
    leave = Leave.query.get_or_404(leave_id)
    if leave.status != "Pending":
        return "이미 처리된 휴가입니다.", 400

    user = leave.user
    days_to_use = leave.days

    # 🔥 이전 연도 먼저 차감, 사용일수 None 처리
    balances = (
        LeaveBalance.query
        .filter(LeaveBalance.user_id == user.id, LeaveBalance.year <= leave.start_date.year)
        .order_by(LeaveBalance.year.asc())
        .all()
    )

    remaining = days_to_use
    for balance in balances:
        balance.used_days = balance.used_days or 0.0
        available = balance.total_days - balance.used_days
        if available <= 0:
            continue
        deduct = min(available, remaining)
        balance.used_days += deduct
        remaining -= deduct
        if remaining <= 0:
            break

    if remaining > 0:
        return "연차가 부족하여 승인할 수 없습니다.", 400

    leave.status = "Approved"
    db.session.commit()
    return redirect(url_for("main.leave_list"))

# ------------------- 휴가 반려 -------------------
@bp.route("/leaves/<int:leave_id>/reject", methods=["POST"])
def reject_leave(leave_id):
    leave = Leave.query.get_or_404(leave_id)
    if leave.status != "Pending":
        return "이미 처리된 휴가입니다.", 400
    leave.status = "Rejected"
    db.session.commit()
    return redirect(url_for("main.leave_list"))

# ------------------- 휴가 삭제 -------------------
@bp.route("/leaves/<int:leave_id>/delete", methods=["POST"])
def delete_leave(leave_id):
    leave = Leave.query.get_or_404(leave_id)
    
    # ✅ Approved 상태인 경우만 used_days 조정
    if leave.status == "Approved":
        # 이전 연도부터 차감되었으므로 해당 연도 Balance 찾아서 복원
        balances = (
            LeaveBalance.query
            .filter(LeaveBalance.user_id == leave.user_id, LeaveBalance.year <= leave.start_date.year)
            .order_by(LeaveBalance.year.asc())
            .all()
        )
        remaining = leave.days
        for balance in balances:
            balance.used_days = balance.used_days or 0.0
            deduct = min(balance.used_days, remaining)
            balance.used_days -= deduct
            remaining -= deduct
            if remaining <= 0:
                break

    db.session.delete(leave)
    db.session.commit()
    
    view_unit = request.form.get("view_unit", "week")
    return redirect(url_for("main.leave_list", view_unit=view_unit))

# ------------------- 휴가 수정 -------------------
@bp.route("/leaves/<int:leave_id>/edit", methods=["GET", "POST"])
def edit_leave(leave_id):
    leave = Leave.query.get_or_404(leave_id)
    users = User.query.all()
    if request.method == "POST":
        view_unit = request.form.get("view_unit", "week")
        old_days = leave.days
        balance = LeaveBalance.query.filter_by(user_id=leave.user_id, year=leave.start_date.year).first()
        if balance:
            balance.used_days = (balance.used_days or 0.0) - old_days

        leave.user_id = int(request.form["user_id"])
        leave.start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d")
        leave.end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d")
        leave.half_day = "half_day" in request.form
        leave.reason = request.form["reason"]

        new_days = leave.days
        balance = LeaveBalance.query.filter_by(user_id=leave.user_id, year=leave.start_date.year).first()
        if balance:
            balance.used_days = (balance.used_days or 0.0) + new_days

        db.session.commit()
        return redirect(url_for("main.leave_list", view_unit=view_unit))

    view_unit = request.args.get("view_unit", "week")
    return render_template("add_leave.html", leave=leave, users=users, view_unit=view_unit)

# ------------------- 캘린더 API -------------------
@bp.route("/api/leaves")
def api_leaves():
    events = []
    for leave in Leave.query.all():
        color = "#f1c40f" if leave.status == "Pending" else "#2ecc71" if leave.status == "Approved" else "#e74c3c"
        events.append({
            "title": f"{leave.user.name} ({leave.status})",
            "start": leave.start_date.isoformat(),
            "end": (leave.end_date + timedelta(days=1)).isoformat(),
            "color": color,
        })
    return jsonify(events)
