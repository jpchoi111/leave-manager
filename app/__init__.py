# app/__init__.py
from flask import Flask
from .config import Config
from .extensions import db, migrate, login_manager

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # extensions 초기화
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # 로그인 사용자 불러오기 함수 등록
    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # 로그인 페이지 지정
    login_manager.login_view = "auth.login"  # auth blueprint 안의 login 함수
    login_manager.login_message = "로그인이 필요합니다."  # 선택사항: 로그인 안내 메시지

    # blueprint import
    from .routes import bp as main_bp
    from .routes import auth_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)

    return app
