# 🕷️ Web Scraper App

A full-stack web scraping application with an interactive dashboard. Extract data from any website with ease!

## ✨ Features

✅ **Extract Multiple Data Types**
- Text content (paragraphs, headings)
- Links and URLs
- Images with alt text
- Tables and structured data

✅ **Advanced Scraping Capabilities**
- Handle JavaScript-rendered content using Selenium
- Multi-page crawling (follow links)
- Automatic retry logic with exponential backoff
- Rate limiting and request delays
- Error handling and logging

✅ **Full-Featured Dashboard**
- Beautiful, responsive web interface
- Create and manage scraping jobs
- View scraped data in real-time
- Export data to CSV and JSON
- Job history and statistics
- Real-time statistics tracking

✅ **Backend API**
- RESTful API endpoints
- Background job processing
- SQLite database for job and data storage
- Thread-safe job execution

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Chrome/Chromium browser (for JavaScript rendering)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Raselkhandoker/web-scraper-app.git
   cd web-scraper-app
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\\Scripts\\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Setup environment variables**
   ```bash
   cp .env.example .env
   ```

5. **Run the application**
   ```bash
   python app.py
   ```

6. **Open your browser**
   Navigate to `http://localhost:5000`

## 📖 Usage

### Using the Dashboard

1. **Create a Scraping Job**
   - Enter a job name
   - Provide the website URL
   - Select what to extract (text, links, images)
   - Choose extraction options:
     - **Handle JavaScript**: For dynamic websites
     - **Follow Links**: For multi-page crawling
   - Set request delay for rate limiting
   - Click "Start Scraping"

2. **View Results**
   - Watch real-time status updates
   - View scraped data preview
   - Check statistics dashboard

3. **Export Data**
   - Download as CSV for spreadsheets
   - Export as JSON for APIs
   - Data includes type, content, URL, and timestamp

### API Endpoints

#### Create a Job
```bash
POST /api/jobs
Content-Type: application/json

{
  "job_name": "Tech News",
  "url": "https://example.com",
  "extract_text": true,
  "extract_links": true,
  "extract_images": false,
  "handle_javascript": false,
  "follow_links": false,
  "delay_between_requests": 1.0
}
```

#### Get All Jobs
```bash
GET /api/jobs
```

#### Get Job Data
```bash
GET /api/jobs/<job_id>/data
```

#### Export Data
```bash
GET /api/jobs/<job_id>/export/csv
GET /api/jobs/<job_id>/export/json
```

#### Get Statistics
```bash
GET /api/stats
```

#### Delete a Job
```bash
DELETE /api/jobs/<job_id>
```

## 🔧 Configuration

Edit `.env` file to customize:

```env
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=your-secret-key-change-in-production
DATABASE_URL=sqlite:///scraper.db
PORT=5000
```

## 📁 Project Structure

```
web-scraper-app/
├── app.py              # Flask application setup
├── models.py           # Database models
├── scraper.py          # Core scraping engine
├── routes.py           # API endpoints
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── .gitignore          # Git ignore rules
├── static/
│   └── index.html      # Dashboard UI
├── scraper.db          # SQLite database (auto-created)
└── README.md           # This file
```

## 🏄 Scraper Features

### Text Extraction
- Extracts paragraphs and headings
- Filters out scripts and styles
- Preserves text structure

### Link Extraction
- Converts relative URLs to absolute
- Extracts link text
- Filters duplicates

### Image Extraction
- Gets image URLs
- Preserves alt text descriptions
- Handles relative paths

### Multi-page Crawling
- Follows links on same domain
- Prevents duplicate visits
- Configurable depth limit
- Rate limiting between requests

### Error Handling
- Automatic retry with exponential backoff
- Detailed error logging
- Graceful failure handling
- Job status tracking

### JavaScript Support
- Uses Selenium with Chrome
- Waits for DOM elements
- Handles dynamic content
- Full page rendering

## 📊 Database Schema

### ScrapingJob
- `id`: Primary key
- `job_name`: Name of the scraping job
- `url`: Target URL
- `status`: pending, running, completed, failed, cancelled
- `extract_text`, `extract_links`, `extract_images`: Feature flags
- `handle_javascript`: Use Selenium for JS content
- `follow_links`: Enable multi-page crawling
- `delay_between_requests`: Rate limiting delay
- `created_at`, `started_at`, `completed_at`: Timestamps
- `error_message`: Error details if failed

### ScrapedData
- `id`: Primary key
- `job_id`: Foreign key to ScrapingJob
- `data_type`: text, link, image, table
- `content`: Extracted content
- `url`: Source URL
- `created_at`: Timestamp

## 🔒 Best Practices

1. **Respect robots.txt**: Check website policies
2. **Use delays**: Default 1 second between requests
3. **User-Agent**: Properly identifies the scraper
4. **Error handling**: Automatic retries with backoff
5. **Data limits**: Content capped at 5000 characters
6. **Session management**: Persistent cookies and headers

## ⚠️ Ethical Considerations

- Always check the website's Terms of Service
- Respect robots.txt and rate limits
- Don't overload servers
- Use appropriate delays
- Identify your scraper with User-Agent
- Consider the website's computational costs
- Comply with legal requirements

## 🐛 Troubleshooting

### Chrome not found
```bash
pip install --upgrade webdriver-manager
```

### Port already in use
```bash
export PORT=5001
python app.py
```

### Database locked
```bash
rm scraper.db
python app.py
```

### Selenium timeout
Increase timeout in `scraper.py`:
```python
self.timeout = 20  # seconds
```

## 📦 Dependencies

- **Flask**: Web framework
- **BeautifulSoup4**: HTML parsing
- **Selenium**: JavaScript rendering
- **Requests**: HTTP client
- **SQLAlchemy**: ORM
- **Pandas**: Data processing
- **APScheduler**: Job scheduling

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📄 License

MIT License - feel free to use this project

## 📞 Support

If you encounter issues:
1. Check the troubleshooting section
2. Review logs in the console
3. Create an issue on GitHub
4. Provide error details and steps to reproduce

## 🎉 Happy Scraping!

Enjoy using Web Scraper App! Happy data extraction! 🕷️
