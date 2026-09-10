from flask import Flask
from flask_login import LoginManager
from .database import init_db
import os

login_manager = LoginManager()

def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'disaster-response-secret-2024')
    app.config['MONGO_URI']  = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/disaster_response')

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        return dict(current_user=current_user)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    init_db()

    from .routes.auth       import auth_bp, _init_oauth
    from .routes.dashboard  import dashboard_bp
    from .routes.reports    import reports_bp
    from .routes.resources  import resources_bp
    from .routes.alerts     import alerts_bp
    from .routes.map_view   import map_bp
    from .routes.api        import api_bp
    from .routes.sos        import sos_bp
    from .routes.weather    import weather_bp
    from .routes.chatbot    import chatbot_bp
    from .routes.analytics  import analytics_bp
    from .routes.volunteer  import volunteer_bp
    from .routes.broadcast  import broadcast_bp
    from .routes.admin      import admin_bp

    app.register_blueprint(auth_bp)
    _init_oauth(app)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(resources_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(map_bp)
    app.register_blueprint(api_bp,       url_prefix='/api')
    app.register_blueprint(sos_bp)
    app.register_blueprint(weather_bp)
    app.register_blueprint(chatbot_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(volunteer_bp)
    app.register_blueprint(broadcast_bp)
    app.register_blueprint(admin_bp)

    return app
