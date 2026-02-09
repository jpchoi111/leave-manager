# app/models.py
from .extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date

# ------------------- User -------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="user")

    # 관계 정의
    leaves = db.relationship(
        "Leave",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan"
    )
    leave_balances = db.relationship(
        "LeaveBalance",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # 비밀번호 헬퍼
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # ------------------- 연차 계산 -------------------

    # 총 연차
    @property
    def total_leave_by_year(self):
        return {b.year: b.total_days for b in self.leave_balances}

    # 사용 연차 (used_days)
    @property
    def used_leave_by_year(self):
        return {b.year: b.used_days or 0.0 for b in self.leave_balances}

    # 남은 연차 (total - used)
    @property
    def remaining_leave_by_year(self):
        result = {}
        for b in self.leave_balances:
            remaining = (b.total_days or 0.0) - (b.used_days or 0.0)
            result[b.year] = remaining
        return result

    # 신청 가능한 연차 (Pending 휴가 반영)
    @property
    def requestable_leave_by_year(self):
        result = {}
        balances = sorted(self.leave_balances, key=lambda b: b.year)
        available_by_year = {b.year: (b.total_days or 0.0) - (b.used_days or 0.0) for b in balances}

        pending_leaves = sorted(
            [l for l in self.leaves if l.status == "Pending"],
            key=lambda l: l.start_date
        )

        for leave in pending_leaves:
            remaining = leave.days
            for year in available_by_year:
                if year > leave.start_date.year:
                    continue
                if remaining <= 0:
                    break
                deduct = min(available_by_year[year], remaining)
                available_by_year[year] -= deduct
                remaining -= deduct

        for year, days in available_by_year.items():
            if days > 0:
                result[year] = round(days, 1)

        return result


# ------------------- Leave -------------------
class Leave(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    half_day = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default="Pending")
    reason = db.Column(db.String(200))

    @property
    def days(self):
        return 0.5 if self.half_day else (self.end_date - self.start_date).days + 1

    @property
    def pending_days_by_year(self):
        """Pending 상태일 때 이전 연도부터 차감 예상일 계산"""
        if self.status != "Pending":
            return {}

        remaining_to_use = self.days
        result = {}

        # 이전 연도 먼저, 올해 순으로 차감
        start_year = self.start_date.year
        years = [start_year - 1, start_year]
        for year in years:
            balance = LeaveBalance.query.filter_by(user_id=self.user_id, year=year).first()
            if balance:
                used = balance.used_days or 0.0
                available = balance.total_days - used
                deduct = min(available, remaining_to_use)
                if deduct > 0:
                    result[year] = deduct
                    remaining_to_use -= deduct
            if remaining_to_use <= 0:
                break

        return result


# ------------------- LeaveBalance -------------------
class LeaveBalance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    total_days = db.Column(db.Float, default=15.0)
    used_days = db.Column(db.Float, default=0.0)
    pending_days = db.Column(db.Float, default=0.0)

    user = db.relationship("User", back_populates="leave_balances")
