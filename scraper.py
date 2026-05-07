import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time
import logging
from urllib.parse import urljoin, urlparse
from datetime import datetime
import random
import re
import json

logger = logging.getLogger(__name__)

class WebScraper:
    """Web scraper with support for static and JavaScript-rendered content"""
    
    def __init__(self, delay_between_requests=1.0, timeout=10):
        self.delay_between_requests = delay_between_requests
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.visited_urls = set()
        
    def _get_with_retry(self, url, retries=3, backoff_factor=0.5):
        """Get URL with retry logic"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                if attempt < retries - 1:
                    wait_time = backoff_factor * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Retry {attempt + 1}/{retries} for {url} after {wait_time:.2f}s: {str(e)}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to fetch {url} after {retries} attempts: {str(e)}")
                    raise
    
    def scrape_static_content(self, url):
        """Scrape static HTML content using BeautifulSoup"""
        try:
            response = self._get_with_retry(url)
            soup = BeautifulSoup(response.content, 'lxml')
            return soup
        except Exception as e:
            logger.error(f"Error scraping static content from {url}: {str(e)}")
            raise
    
    def scrape_javascript_content(self, url):
        """Scrape JavaScript-rendered content using Selenium"""
        driver = None
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            
            driver.get(url)
            WebDriverWait(driver, self.timeout).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'body'))
            )
            
            soup = BeautifulSoup(driver.page_source, 'lxml')
            return soup
        except Exception as e:
            logger.error(f"Error scraping JavaScript content from {url}: {str(e)}")
            raise
        finally:
            if driver:
                driver.quit()
    
    def extract_text(self, soup, url=None):
        """Extract text from soup"""
        data = []
        try:
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text
            paragraphs = soup.find_all('p')
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text and len(text) > 10:
                    data.append({
                        'type': 'text',
                        'content': text,
                        'url': url
                    })
            
            # Get headings
            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                text = heading.get_text(strip=True)
                if text:
                    data.append({
                        'type': 'text',
                        'content': text,
                        'url': url
                    })
        except Exception as e:
            logger.error(f"Error extracting text: {str(e)}")
        
        return data
    
    def extract_links(self, soup, base_url):
        """Extract links from soup"""
        data = []
        links_set = set()
        try:
            for link in soup.find_all('a', href=True):
                href = link['href']
                # Make absolute URL
                absolute_url = urljoin(base_url, href)
                
                # Filter out anchors and duplicates
                if absolute_url.startswith('http') and absolute_url not in links_set:
                    link_text = link.get_text(strip=True)
                    data.append({
                        'type': 'link',
                        'content': link_text or absolute_url,
                        'url': absolute_url
                    })
                    links_set.add(absolute_url)
        except Exception as e:
            logger.error(f"Error extracting links: {str(e)}")
        
        return data
    
    def extract_images(self, soup, base_url):
        """Extract images from soup"""
        data = []
        images_set = set()
        try:
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if src:
                    absolute_url = urljoin(base_url, src)
                    alt_text = img.get('alt', 'No description')
                    
                    if absolute_url.startswith('http') and absolute_url not in images_set:
                        data.append({
                            'type': 'image',
                            'content': alt_text,
                            'url': absolute_url
                        })
                        images_set.add(absolute_url)
        except Exception as e:
            logger.error(f"Error extracting images: {str(e)}")
        
        return data
    
    def extract_tables(self, soup, url=None):
        """Extract tables from soup"""
        data = []
        try:
            for table in soup.find_all('table'):
                rows = []
                for tr in table.find_all('tr'):
                    cells = []
                    for td in tr.find_all(['td', 'th']):
                        cells.append(td.get_text(strip=True))
                    if cells:
                        rows.append(cells)
                
                if rows:
                    data.append({
                        'type': 'table',
                        'content': str(rows),
                        'url': url
                    })
        except Exception as e:
            logger.error(f"Error extracting tables: {str(e)}")
        
        return data
    
    def extract_price(self, text):
        """Extract price from text"""
        # Match various price formats: $1,234.56, £50.00, €100
        price_pattern = r'[$£€]\s*([0-9,]+\.?[0-9]*)|([0-9,]+\.?[0-9]*)\s*[$£€]'
        match = re.search(price_pattern, text)
        return match.group(0).strip() if match else None
    
    def extract_rating(self, text):
        """Extract rating from text"""
        # Match patterns like "4.5 out of 5" or "4.5 stars"
        rating_pattern = r'(\d+\.?\d*)\s*(?:out of 5|stars?)'
        match = re.search(rating_pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except:
                return None
        return None
    
    def extract_stock_status(self, text):
        """Extract stock status from text"""
        text_lower = text.lower()
        if 'in stock' in text_lower or 'in stock' in text_lower:
            return 'In Stock'
        elif 'out of stock' in text_lower or 'unavailable' in text_lower:
            return 'Out of Stock'
        elif 'limited' in text_lower or 'only' in text_lower and 'left' in text_lower:
            return 'Limited Availability'
        return 'Unknown'
    
    def extract_amazon_products(self, soup, base_url, min_rating=0):
        """Extract Amazon product information"""
        data = []
        try:
            # Amazon product containers
            product_containers = soup.find_all('div', {'data-component-type': 's-search-result'})
            
            if not product_containers:
                # Fallback to alternative selectors
                product_containers = soup.find_all('div', class_=re.compile(r'.*s-result-item.*'))
            
            for product in product_containers:
                try:
                    # Extract title
                    title_elem = product.find('h2', class_='s-size-mini')
                    if not title_elem:
                        title_elem = product.find('span', class_='a-size-base-plus')
                    title = title_elem.get_text(strip=True) if title_elem else 'N/A'
                    
                    # Extract price
                    price_elem = product.find('span', class_=re.compile(r'a-price-whole'))
                    price = price_elem.get_text(strip=True) if price_elem else 'N/A'
                    
                    # Extract rating
                    rating_elem = product.find('span', class_=re.compile(r'a-icon-star-small'))
                    rating_text = rating_elem.get_text(strip=True) if rating_elem else 'N/A'
                    rating = self.extract_rating(rating_text)
                    
                    # Skip if rating doesn't meet minimum
                    if min_rating > 0 and rating and rating < min_rating:
                        continue
                    
                    # Extract seller
                    seller_elem = product.find('span', class_='a-size-base')
                    seller = 'Amazon' if not seller_elem else seller_elem.get_text(strip=True)
                    
                    # Extract product URL
                    link_elem = product.find('a', class_='a-link-normal')
                    product_url = urljoin(base_url, link_elem['href']) if link_elem and 'href' in link_elem.attrs else 'N/A'
                    
                    # Extract stock status
                    availability_text = product.get_text()
                    stock_status = self.extract_stock_status(availability_text)
                    
                    # Create metadata
                    metadata = {
                        'title': title,
                        'price': price,
                        'rating': rating,
                        'seller': seller,
                        'stock_status': stock_status,
                        'product_url': product_url
                    }
                    
                    data.append({
                        'type': 'amazon_product',
                        'content': f"{title} - {price}",
                        'url': product_url,
                        'metadata': json.dumps(metadata)
                    })
                    
                except Exception as e:
                    logger.error(f"Error extracting individual Amazon product: {str(e)}")
                    continue
        except Exception as e:
            logger.error(f"Error extracting Amazon products: {str(e)}")
        
        return data
    
    def scrape(self, url, extract_text=True, extract_links=False, 
               extract_images=False, handle_javascript=False, min_rating=0):
        """Main scrape method"""
        try:
            time.sleep(self.delay_between_requests)
            
            if handle_javascript:
                soup = self.scrape_javascript_content(url)
            else:
                soup = self.scrape_static_content(url)
            
            results = []
            
            # Check if it's Amazon and extract products
            if 'amazon.com' in url.lower():
                amazon_products = self.extract_amazon_products(soup, url, min_rating)
                results.extend(amazon_products)
            
            if extract_text:
                results.extend(self.extract_text(soup, url))
            
            if extract_links:
                results.extend(self.extract_links(soup, url))
            
            if extract_images:
                results.extend(self.extract_images(soup, url))
            
            results.extend(self.extract_tables(soup, url))
            
            return results
        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")
            raise
    
    def crawl(self, start_url, extract_text=True, extract_links=False,
              extract_images=False, handle_javascript=False, max_pages=10, min_rating=0):
        """Crawl multiple pages starting from start_url"""
        all_results = []
        urls_to_visit = [start_url]
        base_domain = urlparse(start_url).netloc
        
        while urls_to_visit and len(self.visited_urls) < max_pages:
            url = urls_to_visit.pop(0)
            
            if url in self.visited_urls:
                continue
            
            # Only visit URLs from the same domain
            if urlparse(url).netloc != base_domain:
                continue
            
            try:
                self.visited_urls.add(url)
                logger.info(f"Crawling {url} ({len(self.visited_urls)}/{max_pages})")
                
                results = self.scrape(url, extract_text, extract_links, 
                                     extract_images, handle_javascript, min_rating)
                all_results.extend(results)
                
                # Get links for crawling
                if extract_links:
                    soup = (self.scrape_javascript_content(url) if handle_javascript 
                           else self.scrape_static_content(url))
                    for link_data in self.extract_links(soup, url):
                        link_url = link_data['url']
                        if link_url not in self.visited_urls and link_url not in urls_to_visit:
                            urls_to_visit.append(link_url)
            except Exception as e:
                logger.error(f"Error crawling {url}: {str(e)}")
                continue
        
        return all_results
