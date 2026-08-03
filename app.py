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
    
    # Create tables
    with app.app_context():
        db.create_all()
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
