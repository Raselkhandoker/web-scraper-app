from flask import Blueprint, request, jsonify, send_file
from datetime import datetime
import csv
import json
import io
import logging
from models import db, ScrapingJob, ScrapedData
from scraper import WebScraper
import threading

logger = logging.getLogger(__name__)
api_bp = Blueprint('api', __name__, url_prefix='/api')

def run_scraping_job(job_id):
    """Run scraping job in background"""
    try:
        job = ScrapingJob.query.get(job_id)
        if not job:
            return
        
        job.status = 'running'
        job.started_at = datetime.utcnow()
        db.session.commit()
        
        scraper = WebScraper(delay_between_requests=job.delay_between_requests)
        
        try:
            if job.follow_links:
                results = scraper.crawl(
                    job.url,
                    extract_text=job.extract_text,
                    extract_links=job.extract_links,
                    extract_images=job.extract_images,
                    handle_javascript=job.handle_javascript,
                    max_pages=20
                )
            else:
                results = scraper.scrape(
                    job.url,
                    extract_text=job.extract_text,
                    extract_links=job.extract_links,
                    extract_images=job.extract_images,
                    handle_javascript=job.handle_javascript
                )
            
            # Save scraped data
            for result in results:
                scraped_data = ScrapedData(
                    job_id=job_id,
                    data_type=result['type'],
                    content=result['content'][:5000],  # Limit content length
                    url=result.get('url')
                )
                db.session.add(scraped_data)
            
            job.status = 'completed'
            job.completed_at = datetime.utcnow()
            db.session.commit()
            logger.info(f"Job {job_id} completed successfully with {len(results)} items")
            
        except Exception as e:
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.session.commit()
            logger.error(f"Job {job_id} failed: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error in run_scraping_job: {str(e)}")


# Routes

@api_bp.route('/jobs', methods=['POST'])
def create_job():
    """Create a new scraping job"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('job_name') or not data.get('url'):
            return jsonify({'error': 'job_name and url are required'}), 400
        
        job = ScrapingJob(
            job_name=data['job_name'],
            url=data['url'],
            extract_text=data.get('extract_text', True),
            extract_links=data.get('extract_links', False),
            extract_images=data.get('extract_images', False),
            handle_javascript=data.get('handle_javascript', False),
            follow_links=data.get('follow_links', False),
            delay_between_requests=float(data.get('delay_between_requests', 1.0))
        )
        
        db.session.add(job)
        db.session.commit()
        
        # Run scraping in background thread
        thread = threading.Thread(target=run_scraping_job, args=(job.id,))
        thread.daemon = True
        thread.start()
        
        return jsonify(job.to_dict()), 201
    
    except Exception as e:
        logger.error(f"Error creating job: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/jobs', methods=['GET'])
def get_jobs():
    """Get all scraping jobs"""
    try:
        jobs = ScrapingJob.query.order_by(ScrapingJob.created_at.desc()).all()
        return jsonify([job.to_dict() for job in jobs]), 200
    except Exception as e:
        logger.error(f"Error getting jobs: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/jobs/<int:job_id>', methods=['GET'])
def get_job(job_id):
    """Get a specific job"""
    try:
        job = ScrapingJob.query.get(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        return jsonify(job.to_dict()), 200
    except Exception as e:
        logger.error(f"Error getting job: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/jobs/<int:job_id>', methods=['DELETE'])
def delete_job(job_id):
    """Delete a job"""
    try:
        job = ScrapingJob.query.get(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        db.session.delete(job)
        db.session.commit()
        return jsonify({'message': 'Job deleted successfully'}), 200
    except Exception as e:
        logger.error(f"Error deleting job: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/jobs/<int:job_id>/data', methods=['GET'])
def get_job_data(job_id):
    """Get scraped data for a job"""
    try:
        job = ScrapingJob.query.get(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        data = ScrapedData.query.filter_by(job_id=job_id).all()
        return jsonify([item.to_dict() for item in data]), 200
    except Exception as e:
        logger.error(f"Error getting job data: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/jobs/<int:job_id>/export/csv', methods=['GET'])
def export_csv(job_id):
    """Export job data as CSV"""
    try:
        job = ScrapingJob.query.get(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        data = ScrapedData.query.filter_by(job_id=job_id).all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Type', 'Content', 'URL', 'Created At'])
        
        for item in data:
            writer.writerow([item.data_type, item.content, item.url, item.created_at])
        
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'scraped_data_{job_id}.csv'
        )
    except Exception as e:
        logger.error(f"Error exporting CSV: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/jobs/<int:job_id>/export/json', methods=['GET'])
def export_json(job_id):
    """Export job data as JSON"""
    try:
        job = ScrapingJob.query.get(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        data = ScrapedData.query.filter_by(job_id=job_id).all()
        
        export_data = {
            'job': job.to_dict(),
            'data': [item.to_dict() for item in data]
        }
        
        output = io.BytesIO(json.dumps(export_data, indent=2).encode('utf-8'))
        output.seek(0)
        return send_file(
            output,
            mimetype='application/json',
            as_attachment=True,
            download_name=f'scraped_data_{job_id}.json'
        )
    except Exception as e:
        logger.error(f"Error exporting JSON: {str(e)}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get statistics"""
    try:
        total_jobs = ScrapingJob.query.count()
        completed_jobs = ScrapingJob.query.filter_by(status='completed').count()
        failed_jobs = ScrapingJob.query.filter_by(status='failed').count()
        total_data_items = ScrapedData.query.count()
        
        return jsonify({
            'total_jobs': total_jobs,
            'completed_jobs': completed_jobs,
            'failed_jobs': failed_jobs,
            'total_data_items': total_data_items
        }), 200
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return jsonify({'error': str(e)}), 500
