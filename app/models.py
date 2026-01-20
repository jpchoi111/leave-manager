# app/models.py
from .extensions import db
from datetime import date

# ------------------- User -------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100))

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

    # 남은 연차
    @property
    def remaining_leave_by_year(self):
        result = {}
        for balance in self.leave_balances:
            remaining = balance.total_days - (balance.used_days or 0)
            if remaining > 0:
                result[balance.year] = remaining
        return result

    # 총 연차
    @property
    def total_leave_by_year(self):
        result = {}
        for balance in self.leave_balances:
            result[balance.year] = balance.total_days
        return result

    # 신청 가능한 연차 (Pending 반영)
    @property
    def requestable_leave_by_year(self):
        result = {}
        # 1️⃣ 연도 오름차순 정렬
        balances = sorted(self.leave_balances, key=lambda b: b.year)

        # 2️⃣ 연도별 사용 가능 일수 초기화
        available_by_year = {
            b.year: (b.total_days or 0.0) - (b.used_days or 0.0)
            for b in balances
        }

        # 3️⃣ Pending 휴가들을 시작일 기준으로 정렬
        pending_leaves = sorted(
            [l for l in self.leaves if l.status == "Pending"],
            key=lambda l: l.start_date
        )

        # 4️⃣ Pending 휴가를 이전 연도부터 차감 (시뮬레이션)
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

        # 5️⃣ 결과 정리
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
