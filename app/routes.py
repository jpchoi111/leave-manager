# app/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, abort, flash
from datetime import date, datetime, timedelta, time
from .extensions import db
from .models import User, Leave, LeaveBalance, Attendance, PublicHoliday
from flask_login import login_user, logout_user, login_required, current_user
from functools import wraps
from werkzeug.security import check_password_hash
from sqlalchemy.orm import joinedload


auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                    flash("비활성화된 계정입니다. 관리자에게 문의하세요.", "danger")
                    return redirect(url_for('auth.login'))
            login_user(user)
            flash("로그인 성공!", "success")
            return redirect(url_for('main.index'))  # 메인 페이지로 이동
        else:
            flash("이메일 또는 비밀번호가 틀렸습니다.", "danger")

    return render_template('login.html')


bp = Blueprint("main", __name__)

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return f(*args, **kwargs)
    return wrapper

@bp.route("/")
def index():
    return render_template("index.html")


# ------------------- 로그 아웃 -------------------
@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash("로그아웃 되었습니다.", "info")
    return redirect(url_for('auth.login'))



# ------------------- 직원 목록 -------------------
@bp.route("/users")
@login_required
def user_list():
    if current_user.role == "admin":
        users = User.query.options(joinedload(User.leave_balances)).all()
    else:
        users = [current_user]

    return render_template("users.html", users=users, is_admin=(current_user.role == "admin"))


# ------------------- 직원 추가 -------------------
@bp.route("/users/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_user():
    if request.method == "POST":
        # 기존에 같은 이메일이 있는지 체크
        if User.query.filter_by(email=request.form["email"]).first():
            flash("이미 존재하는 이메일입니다.")
            return redirect(url_for("main.add_user"))

        user = User(
            name=request.form["name"],
            email=request.form["email"],
            role=request.form.get("role", "user")
        )

        # 초기 비밀번호 세팅
        user.set_password("12345")

        db.session.add(user)
        db.session.commit()
        flash(f"{user.name} 계정이 생성되었습니다. 초기 비밀번호는 '12345'입니다.")
        return redirect(url_for("main.user_list"))

    return render_template("add_user.html")


# ------------------- 직원 삭제 -------------------
@bp.route("/users/delete/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.role == "admin":
        flash("관리자 계정은 삭제할 수 없습니다.", "danger")
        return redirect(url_for("main.user_list"))

    user.original_email = user.email
    user.email = f"deleted_{user.id}_{user.email}"
    user.is_active = False
    user.deleted_at = datetime.utcnow()

    db.session.commit()
    flash(f"{user.name} 계정이 비활성화되었습니다. 기록은 유지됩니다.", "success")
    return redirect(url_for("main.user_list"))


# ------------------- 비밀번호 변경 -------------------
@bp.route("/auth/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        new_password_confirm = request.form["new_password_confirm"]

        if not check_password_hash(current_user.password_hash, current_password):
            flash("현재 비밀번호가 올바르지 않습니다.", "danger")
            return redirect(url_for("main.change_password"))

        if new_password != new_password_confirm:
            flash("새 비밀번호가 일치하지 않습니다.", "danger")
            return redirect(url_for("main.change_password"))

        current_user.set_password(new_password)
        db.session.commit()

        flash("비밀번호가 변경되었습니다.", "success")
        return redirect(url_for("main.index"))

    return render_template("change_password.html")


# ------------------- 휴가 목록 -------------------
@bp.route("/leaves")
@login_required
def leave_list():
    if current_user.role == "admin":
        leaves = Leave.query
    else:
        leaves = Leave.query.filter_by(user_id=current_user.id)

    today = date.today()

    view = request.args.get("view", "pending")
    if view == "pending":
        leaves = leaves.filter(Leave.status == "Pending")
    elif view == "week":
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


# ------------------- 남은 연차 수정 -------------------
@bp.route("/leave-balance/edit/<int:user_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_leave_balance(user_id):
    user = User.query.get_or_404(user_id)

    # 연도 목록 (연차가 있는 연도 기준)
    years = sorted({b.year for b in user.leave_balances})
    if not years:
        flash("연차 데이터가 없습니다.", "warning")
        return redirect(url_for("main.user_list"))

    # 선택 연도 (GET: 첫 번째 연도, POST: 폼에서 선택)
    year = request.form.get("year", type=int) or years[0]

    # 해당 연도 연차 가져오기, 없으면 새로 생성
    balance = LeaveBalance.query.filter_by(user_id=user.id, year=year).first()
    if not balance:
        balance = LeaveBalance(user_id=user.id, year=year, total_days=15.0, used_days=0.0)
        db.session.add(balance)
        db.session.commit()
        db.session.refresh(user)

    if request.method == "POST":

        if request.form.get("action") != "save":
            return render_template(
                "leave_balance_edit.html",
                user=user,
                balance=balance,
                years=years
            )

        # 총 연차, 사용 연차 입력
        total_days = float(request.form.get("total_days", balance.total_days))
        used_days = float(request.form.get("used_days", balance.used_days))

        # 🔐 안전 체크
        if used_days > total_days:
            flash("사용 연차는 총 연차를 초과할 수 없습니다.", "danger")
            return redirect(request.url)

        balance.total_days = total_days
        balance.used_days = used_days

        # 남은 연차 계산
        remaining = total_days - used_days

        # Pending 휴가 차감
        pending_days = sum(
            l.days for l in Leave.query.filter(
                Leave.user_id == user.id,
                Leave.status == "Pending",
                db.extract("year", Leave.start_date) == year
            )
        )

        balance.available_days = max(remaining - pending_days, 0)

        db.session.commit()
        db.session.refresh(user)

        flash("연차 정보가 수정되었습니다.", "success")
        return redirect(url_for("main.user_list"))

    return render_template(
        "leave_balance_edit.html",
        user=user,
        balance=balance,
        years=years
    )


# ------------------- 휴가 신청 -------------------
@bp.route("/leaves/add", methods=["GET", "POST"])
@login_required
def add_leave():
    users = User.query.all() if current_user.role == "admin" else [current_user]

    if request.method == "POST":
        user = User.query.get_or_404(int(request.form["user_id"]))

        if current_user.role != "admin" and user.id != current_user.id:
            abort(403)

        leave = Leave(
            user_id=user.id,
            start_date=datetime.strptime(request.form["start_date"], "%Y-%m-%d"),
            end_date=datetime.strptime(request.form["end_date"], "%Y-%m-%d"),
            half_day="half_day" in request.form,
            reason=request.form["reason"],
            status="Pending"
        )

        # 날짜 역전 방지
        if leave.end_date < leave.start_date:
            flash("종료일은 시작일보다 빠를 수 없습니다.", "danger")
            return redirect(url_for("main.add_leave"))

        # 날짜 중복 체크
        overlapping_leave = Leave.query.filter(
            Leave.user_id == user.id,
            Leave.status != "Rejected",
            Leave.start_date <= leave.end_date,
            Leave.end_date >= leave.start_date
        ).first()

        if overlapping_leave:
            flash("이미 해당 기간에 신청된 휴가가 있습니다.", "danger")
            return redirect(url_for("main.add_leave"))

        # 주말 제외 후 0일 방지
        used_days = leave.days
        if used_days <= 0:
            flash("선택한 기간에 사용 가능한 평일이 없습니다.", "danger")
            return redirect(url_for("main.add_leave"))


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
@login_required
@admin_required
def approve_leave(leave_id):
    leave = Leave.query.get_or_404(leave_id)
    if leave.status != "Pending":
        return "이미 처리된 휴가입니다.", 400

    user = leave.user
    days_to_use = leave.days

    # 이전 연도 먼저 차감, 사용일수 None 처리
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
@login_required
@admin_required
def reject_leave(leave_id):
    leave = Leave.query.get_or_404(leave_id)
    if leave.status != "Pending":
        return "이미 처리된 휴가입니다.", 400
    leave.status = "Rejected"
    db.session.commit()
    return redirect(url_for("main.leave_list"))

# ------------------- 휴가 삭제 -------------------
@bp.route("/leaves/<int:leave_id>/delete", methods=["POST"])
@login_required
def delete_leave(leave_id):
    leave = Leave.query.get_or_404(leave_id)

    # 본인 휴가가 아니고 admin도 아니면 차단
    if current_user.role != "admin" and leave.user_id != current_user.id:
        abort(403)

    # 일반 유저는 승인된 휴가 삭제 불가
    if current_user.role != "admin" and leave.status == "Approved":
        flash("승인된 휴가는 삭제할 수 없습니다.", "danger")
        return redirect(url_for("main.leave_list"))

    # Approved 상태인 경우만 used_days 복원
    if leave.status == "Approved":
        balances = (
            LeaveBalance.query
            .filter(
                LeaveBalance.user_id == leave.user_id,
                LeaveBalance.year <= leave.start_date.year
            )
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

    flash("휴가가 삭제되었습니다.", "success")

    view_unit = request.form.get("view_unit", "month")
    return redirect(url_for("main.leave_list", view_unit=view_unit))


# ------------------- 휴가 수정 -------------------
@bp.route("/leaves/<int:leave_id>/edit", methods=["GET", "POST"])
@login_required
def edit_leave(leave_id):
    leave = Leave.query.get_or_404(leave_id)
    if current_user.role != "admin" and leave.user_id != current_user.id:
        abort(403)

    users = User.query.all() if current_user.role == "admin" else None

    if request.method == "POST":
        view_unit = request.form.get("view_unit", "week")

        # ===== 기존 값 백업 =====
        old_user_id = leave.user_id
        old_year = leave.start_date.year
        old_days = leave.days

        # 기존 연차 복구
        old_balance = LeaveBalance.query.filter_by(
            user_id=old_user_id,
            year=old_year
        ).first()
        if old_balance:
            old_balance.used_days = (old_balance.used_days or 0.0) - old_days

        # ===== 휴가 수정 =====
        if current_user.role == "admin":
            leave.user_id = int(request.form["user_id"])

        leave.start_date = datetime.strptime(
            request.form["start_date"], "%Y-%m-%d"
        )
        leave.end_date = datetime.strptime(
            request.form["end_date"], "%Y-%m-%d"
        )
        leave.half_day = "half_day" in request.form
        leave.reason = request.form["reason"]

        # ===== 새로운 연차 반영 =====
        new_year = leave.start_date.year
        new_days = leave.days

        new_balance = LeaveBalance.query.filter_by(
            user_id=leave.user_id,
            year=new_year
        ).first()
        if new_balance:
            new_balance.used_days = (new_balance.used_days or 0.0) + new_days

        db.session.commit()
        return redirect(url_for("main.leave_list", view=view_unit))

    view_unit = request.args.get("view_unit", "month")
    return render_template(
        "edit_leave.html",
        leave=leave,
        users=users,
        view_unit=view_unit
    )

@bp.route("/attendance")
@login_required
def attendance_list():

    if current_user.role == "admin":
        attendances = Attendance.query.order_by(Attendance.date.desc()).all()
    else:
        attendances = Attendance.query.filter_by(
            user_id=current_user.id
        ).order_by(Attendance.date.desc()).all()

    return render_template(
        "attendance_list.html",
        attendances=attendances,
        is_admin=(current_user.role == "admin")
    )

# ------------------- 지각 등록 -------------------
@bp.route("/attendance/late/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_late():
    users = User.query.all()
    current_date = date.today().isoformat() 

    if request.method == "POST":
        user_id = int(request.form["user_id"])
        date_value = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        start_time = datetime.strptime(request.form["start_time"], "%H:%M").time()
        end_time = datetime.strptime(request.form["end_time"], "%H:%M").time()

        duration = int(
            (datetime.combine(date_value, end_time) -
             datetime.combine(date_value, start_time)
            ).total_seconds() // 60
        )

        attendance = Attendance(
            user_id=user_id,
            date=date_value,
            type="late",
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration,
            status="Approved"  # 바로 확정
        )

        db.session.add(attendance)
        db.session.commit()

        return redirect(url_for("main.user_list"))

    return render_template("add_late.html", users=users)

# ------------------- 외출 신청 -------------------
@bp.route("/attendance/outing/add", methods=["GET", "POST"])
@login_required
def add_outing():
    if request.method == "POST":
        date_value = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        start_time = datetime.strptime(request.form["start_time"], "%H:%M").time()
        end_time = datetime.strptime(request.form["end_time"], "%H:%M").time()

        if start_time.minute % 15 != 0 or end_time.minute % 15 != 0:
            flash("시간은 15분 단위로 입력해주세요 (00, 15, 30, 45).")
            return redirect(request.url)

        duration = int(
            (datetime.combine(date_value, end_time) -
             datetime.combine(date_value, start_time)
            ).total_seconds() // 60
        )

        attendance = Attendance(
            user_id=current_user.id,
            date=date_value,
            type="outing",
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration,
            reason=request.form.get("reason"),
            status="Pending"
        )

        db.session.add(attendance)
        db.session.commit()

        return redirect(url_for("main.index"))

    return render_template("add_outing.html")

# ------------------- 외출 승인 -------------------
@bp.route("/attendance/<int:att_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_attendance(att_id):
    att = Attendance.query.get_or_404(att_id)

    if att.status != "Pending":
        return "이미 처리되었습니다.", 400

    att.status = "Approved"
    db.session.commit()

    return redirect(url_for("main.index"))


# ------------------- 외출 반려 -------------------
@bp.route("/attendance/<int:att_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_attendance(att_id):
    att = Attendance.query.get_or_404(att_id)

    if att.status != "Pending":
        return "이미 처리되었습니다.", 400

    att.status = "Rejected"
    db.session.commit()

    return redirect(url_for("main.index"))


# ------------------- 외출 수정 -------------------
@bp.route("/attendance/<int:att_id>/edit", methods=["GET", "POST"])
@login_required
def edit_outing(att_id):
    att = Attendance.query.get_or_404(att_id)

    if att.user_id != current_user.id and current_user.role != "admin":
        abort(403)

    # 상태 체크
    if att.status != "Pending" and current_user.role != "admin":
        return "이미 처리된 외출은 수정할 수 없습니다.", 400

    if request.method == "POST":
        date_value = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        start_time = datetime.strptime(request.form["start_time"], "%H:%M").time()
        end_time = datetime.strptime(request.form["end_time"], "%H:%M").time()

        # ✅ 15분 체크
        if start_time.minute % 15 != 0 or end_time.minute % 15 != 0:
            flash("시간은 15분 단위로 입력해주세요.")
            return redirect(request.url)

        duration = int(
            (datetime.combine(date_value, end_time) -
             datetime.combine(date_value, start_time)
            ).total_seconds() // 60
        )

        if duration <= 0:
            flash("종료 시간은 시작 시간보다 이후여야 합니다.")
            return redirect(request.url)

        # 값 업데이트
        att.date = date_value
        att.start_time = start_time
        att.end_time = end_time
        att.duration_minutes = duration
        att.reason = request.form.get("reason")

        db.session.commit()

        return redirect(url_for("main.index"))

    return render_template("edit_outing.html", att=att)

# ------------------- 외출 삭제 -------------------
@bp.route("/attendance/<int:att_id>/delete", methods=["POST"])
@login_required
def delete_outing(att_id):
    att = Attendance.query.get_or_404(att_id)

    if att.user_id != current_user.id and current_user.role != "admin":
        abort(403)

    # 상태 체크
    if att.status != "Pending" and current_user.role != "admin":
        return "이미 처리된 외출은 수정할 수 없습니다.", 400

    db.session.delete(att)
    db.session.commit()

    return redirect(url_for("main.index"))


# ------------------- 공휴일 목록 -------------------
@bp.route("/holidays")
@login_required
@admin_required
def holiday_list():
    year = request.args.get("year", date.today().year, type=int)
    holidays = (
        PublicHoliday.query
        .filter(db.extract("year", PublicHoliday.date) == year)
        .order_by(PublicHoliday.date)
        .all()
    )
    return render_template("holiday_list.html", holidays=holidays, year=year, today=date.today())


# ------------------- 공휴일 추가 -------------------
@bp.route("/holidays/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_holiday():
    if request.method == "POST":
        holiday_date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        name = request.form["name"].strip()

        existing = PublicHoliday.query.filter_by(date=holiday_date).first()
        if existing:
            flash(f"{holiday_date}은 이미 '{existing.name}'으로 등록되어 있습니다.", "warning")
            return redirect(url_for("main.add_holiday"))

        db.session.add(PublicHoliday(
            date=holiday_date,
            name=name,
            created_by_id=current_user.id
        ))
        db.session.commit()
        flash(f"{name} ({holiday_date})이 등록되었습니다.", "success")
        return redirect(url_for("main.holiday_list"))

    return render_template("add_holiday.html")


# ------------------- 공휴일 삭제 -------------------
@bp.route("/holidays/<int:holiday_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_holiday(holiday_id):
    holiday = PublicHoliday.query.get_or_404(holiday_id)
    name = holiday.name
    holiday_date = holiday.date
    db.session.delete(holiday)
    db.session.commit()
    flash(f"{name} ({holiday_date})이 삭제되었습니다.", "success")
    return redirect(url_for("main.holiday_list"))

# ------------------- 캘린더 API -------------------
@bp.route("/api/leaves")
def api_leaves():
    start = request.args.get("start")
    end = request.args.get("end")

    start_date = datetime.fromisoformat(start).date()
    end_date = datetime.fromisoformat(end).date()

    events = []

    # ---------------- 휴가 ----------------
    for leave in Leave.query.filter(
        Leave.end_date >= start_date,
        Leave.start_date <= end_date
    ).all():
        color = "#f1c40f" if leave.status == "Pending" else "#2ecc71" if leave.status == "Approved" else "#e74c3c"

        if leave.half_day:
            label = "반차"
            icon = "🌓"
            days = "반차 0.5"
        else:
            label = "휴가"
            icon = "✈️"
            days = (leave.end_date - leave.start_date).days + 1
            
        events.append({
            "title": f"{icon} {leave.user.name}",
            "start": leave.start_date.isoformat(),
            "end": (leave.end_date + timedelta(days=1)).isoformat(),
            "color": color,
            "allDay": True,
            "extendedProps": {
                "type": "휴가",
                "status": leave.status,
                "days": days,
                "period": f"{leave.start_date} ~ {leave.end_date}",
                "reason": leave.reason
            }
        })

    # ---------------- 근태 ----------------
    attendance_list = Attendance.query.all()  # ✅ status 필터 제거

    for att in attendance_list:
        if att.type == "late":
            # 🔒 지각: Approved만 + 권한 제한
            if att.status != "Approved":
                continue

            if current_user.role != "admin" and att.user_id != current_user.id:
                continue

            color = "#e67e22"
            label = "지각"

        elif att.type == "outing":
            # 👀 외출: Pending 포함 모두 표시
            label = "외출"

            if att.status == "Pending":
                color = "#95a5a6"  # 회색 (대기중)
            elif att.status == "Approved":
                color = "#3498db"  # 파랑
            else:
                color = "#e74c3c"  # 거절 등

        else:
            continue

        icon_map = {
            "지각": "⏰",
            "외출": "🏃",
        }

        events.append({
            "title": f"{icon_map.get(label, '')} {att.user.name} - {label}",
            "start": f"{att.date}",
            "color": color,
            "allDay": True,
            "extendedProps": {
                "type": label,
                "status": att.status,
                "duration": att.duration_minutes,
                "reason": att.reason
            }
        })


    # ---------------- 공휴일 ----------------
    for holiday in PublicHoliday.query.filter(
        PublicHoliday.date >= start_date,
        PublicHoliday.date <= end_date
    ).all():
        events.append({
            "title": f"🎌 {holiday.name}",
            "start": holiday.date.isoformat(),
            "end": (holiday.date + timedelta(days=1)).isoformat(),
            "color": "#c0392b",
            "allDay": True,
            "display": "background",
            "extendedProps": {
                "type": "공휴일",
                "name": holiday.name
            }
        })

    return jsonify(events)


