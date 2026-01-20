from flask import Flask
from .config import Config
from .extensions import db, migrate  # migrate 추가
from .routes import bp as main_bp
from .models import User, Leave, LeaveBalance  # 필요한 모든 모델 import

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # SQLAlchemy와 Migrate 초기화
    db.init_app(app)
    migrate.init_app(app, db)  # <-- 여기서 Migrate 연결

    # Blueprint 등록
    app.register_blueprint(main_bp)

    return app
