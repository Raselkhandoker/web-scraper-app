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

## 🎬 Video → Animation

Turn a normal video into a cartoon/animated version, and trim out the parts
you don't want. Open **`/animator`** in your browser (there's a link at the
top of the main dashboard).

**How it works**

1. Upload a video (mp4, mov, avi, mkv, webm…).
2. Optionally list **cut segments** in seconds to remove, e.g. `0-3, 10-12.5`.
   Use the built-in preview player to find timestamps.
3. Optionally **remove logos / text**: tick "Draw boxes", drag rectangles on
   the preview over any logo or burned-in text, and pick how to cover them
   (blur / pixelate / black box / inpaint). The boxes are applied to every
   frame before styling. This *hides* the marked areas rather than perfectly
   reconstructing what was behind them (true erasure needs AI video
   inpainting). Region removal runs on the `local` engine.
4. Pick a **style** and an **engine**, then create the animation and download
   the result.

**Styles** (local engine = stylised *approximations* of these techniques):
`cartoon`, `anime`, `2d`, `traditional`, `flipbook`, `stop_motion`,
`cutout`, `sand`, `paint_glass`, `clay`, `rotoscope`, `whiteboard`,
`experimental`, `sketch`. `flipbook`/`stop_motion`/`clay`/`sand` also add the
choppy "frame-hold" timing of real stop-motion. For a faithful (not
filter-approximated) result, use the `ai` engine, which passes the style name
to the model as a prompt.

> Note: "Audio-Animatronics / Autonomatronics" is a physical robotics
> technique (animated puppets), not a video look, so it is not offered.

**Audio options** (choose one per job):

| Mode | What it does | Needs |
|------|--------------|-------|
| `keep` | keep the original audio, trimmed to match | – |
| `mute` | no audio | – |
| `replace` | swap in an audio file you upload | an audio upload |
| `ai_music` | generate style-matched music with AI (MusicGen) | `REPLICATE_API_TOKEN` |

With `ai_music` the server generates a short backing track whose mood matches
the chosen style (you can also type your own music description); it is muxed
onto the animation in place of the original audio.

**Two engines**

| Engine  | Cost | Needs | Quality |
|---------|------|-------|---------|
| `local` | Free, offline (OpenCV) | nothing | stylised cartoon filter |
| `ai`    | Paid | `REPLICATE_API_TOKEN` | high-quality AI animation |

The `local` engine is the default and works out of the box — no API key. The
`ai` engine sends the video to [Replicate](https://replicate.com); set
`REPLICATE_API_TOKEN` (and optionally `REPLICATE_MODEL`) in your `.env`.

No system `ffmpeg` install is required — the bundled `imageio-ffmpeg` binary
is used for encoding and audio muxing.

**Video API endpoints**

```bash
GET    /api/video/styles              # list styles + engines
POST   /api/video/jobs                # multipart: video, job_name, engine, style, cut_segments, keep_audio
GET    /api/video/jobs                # list jobs
GET    /api/video/jobs/<id>           # poll status/progress
GET    /api/video/jobs/<id>/source    # original video (for preview)
GET    /api/video/jobs/<id>/download  # download the animation
DELETE /api/video/jobs/<id>           # delete job + files
```

### Windows one-click launch

After the first setup (below), you can just **double-click `start.bat`** to
launch the app and open the tool in your browser — no typing needed.

### Verify it works

Run the offline self-test (no internet / API token required):

```bash
py -3.11 smoke_test.py      # Windows
python3 smoke_test.py       # Mac / Linux
```

It renders every style, trims, keeps audio, and removes a region. A final
`ALL CHECKS PASSED` means the engine is healthy.

> **Updating:** the database upgrades itself on startup (new columns are
> added automatically), so you never need to delete your database after
> pulling an update.

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
├── models.py           # Database models (scraping + video jobs)
├── scraper.py          # Core scraping engine
├── routes.py           # Scraper API endpoints
├── video_animator.py   # Video → animation engine (OpenCV, trimming, audio)
├── ai_backends.py      # Optional AI engine (Replicate)
├── video_routes.py     # Video API endpoints
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── .gitignore          # Git ignore rules
├── static/
│   ├── index.html      # Scraper dashboard UI
│   └── animator.html   # Video → animation UI
├── media/              # Uploaded videos + rendered animations (auto-created)
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
- **OpenCV** (`opencv-python-headless`): Frame-by-frame video stylisation
- **imageio / imageio-ffmpeg**: Video encoding + audio muxing (bundled ffmpeg)
- **Pillow / NumPy**: Image processing

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
