from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class ScrapingJob(db.Model):
    """Model for scraping jobs"""
    __tablename__ = 'scraping_jobs'
    
    id = db.Column(db.Integer, primary_key=True)
    job_name = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(1024), nullable=False)
    status = db.Column(db.String(50), default='pending')  # pending, running, completed, failed, cancelled
    extract_text = db.Column(db.Boolean, default=True)
    extract_links = db.Column(db.Boolean, default=False)
    extract_images = db.Column(db.Boolean, default=False)
    handle_javascript = db.Column(db.Boolean, default=False)
    follow_links = db.Column(db.Boolean, default=False)
    delay_between_requests = db.Column(db.Float, default=1.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    
    # Relationship
    scraped_data = db.relationship('ScrapedData', backref='job', lazy=True, cascade='all, delete-orphan')
    
    @property
    def data_count(self):
        return len(self.scraped_data)
    
    def to_dict(self):
        return {
            'id': self.id,
            'job_name': self.job_name,
            'url': self.url,
            'status': self.status,
            'extract_text': self.extract_text,
            'extract_links': self.extract_links,
            'extract_images': self.extract_images,
            'handle_javascript': self.handle_javascript,
            'follow_links': self.follow_links,
            'delay_between_requests': self.delay_between_requests,
            'data_count': self.data_count,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message
        }


class ScrapedData(db.Model):
    """Model for scraped data"""
    __tablename__ = 'scraped_data'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('scraping_jobs.id'), nullable=False)
    data_type = db.Column(db.String(50), nullable=False)  # text, link, image, table
    content = db.Column(db.Text, nullable=False)
    url = db.Column(db.String(1024))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'job_id': self.job_id,
            'data_type': self.data_type,
            'content': self.content,
            'url': self.url,
            'created_at': self.created_at.isoformat()
        }
