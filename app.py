from flask import Flask
from flask_cors import CORS
import os
import logging
from dotenv import load_dotenv
from models import db
from routes import api_bp
from video_routes import video_bp

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def _auto_migrate():
    """Add any columns that exist on the models but not yet in the database.

    Keeps older SQLite databases working after an update without the user
    having to delete the file. Only additive (ADD COLUMN); never drops data.
    """
    from sqlalchemy import inspect, text

    insp = inspect(db.engine)
    existing_tables = set(insp.get_table_names())

    for table in db.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        existing_cols = {c['name'] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing_cols:
                continue
            col_type = col.type.compile(dialect=db.engine.dialect)
            default_sql = ''
            arg = getattr(col.default, 'arg', None) if col.default is not None else None
            if arg is not None and not callable(arg):
                if isinstance(arg, bool):
                    default_sql = f" DEFAULT {1 if arg else 0}"
                elif isinstance(arg, (int, float)):
                    default_sql = f" DEFAULT {arg}"
                elif isinstance(arg, str):
                    default_sql = f" DEFAULT '{arg}'"
            try:
                with db.engine.begin() as conn:
                    conn.execute(text(
                        f'ALTER TABLE {table.name} '
                        f'ADD COLUMN {col.name} {col_type}{default_sql}'
                    ))
                logger.info("Auto-migrate: added %s.%s", table.name, col.name)
            except Exception as e:  # noqa: BLE001 - best effort
                logger.warning("Auto-migrate skipped %s.%s: %s",
                               table.name, col.name, e)


def create_app():
    """Create and configure Flask app"""
    app = Flask(__name__)
    
    # Configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL',
        'sqlite:///scraper.db'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')

    # Video-to-animation config
    app.config['MEDIA_ROOT'] = os.getenv(
        'MEDIA_ROOT', os.path.join(os.getcwd(), 'media')
    )
    # Max upload size for videos (default 200 MB).
    app.config['MAX_CONTENT_LENGTH'] = int(
        os.getenv('MAX_UPLOAD_MB', '200')
    ) * 1024 * 1024

    # Initialize extensions
    db.init_app(app)
    CORS(app)

    # Register blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(video_bp)
    
    # Create tables + add any newly-introduced columns to existing databases
    # so users never have to delete their database after an update.
    with app.app_context():
        db.create_all()
        _auto_migrate()
        logger.info("Database initialized")
    
    # Static files
    @app.route('/')
    def index():
        with open('static/index.html', 'r', encoding='utf-8') as f:
            return f.read()

    @app.route('/animator')
    def animator():
        with open('static/animator.html', 'r', encoding='utf-8') as f:
            return f.read()

    @app.errorhandler(413)
    def too_large(error):
        return {'error': 'Uploaded file is too large'}, 413

    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Not found'}, 404
    
    @app.errorhandler(500)
    def server_error(error):
        logger.error(f"Server error: {str(error)}")
        return {'error': 'Internal server error'}, 500
    
    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
