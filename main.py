"""
Simplified Market Data API with Form Submission
Top 5 Gainers/Losers from Global and Indian Markets + News + Form Submission
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import yfscreen as yfs
import yfinance as yf
from datetime import datetime
from typing import Dict, List
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import gspread
import os
# Removed mangum - not needed for Vercel


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="Market Overview API")

# Allow CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Email and Google Sheets Configuration
EMAIL_CONFIG = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "email": os.getenv("EMAIL_ADDRESS", "akash.yadavv181198@gmail.com"),
    "password": os.getenv("EMAIL_PASSWORD", "tmnsodotbingfaqo"),
}

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "1tGgnMQWpX19Us7H0c_Sx8s9SkmeTZCs8fekQIl3qJL4")


def fetch_top_stocks(region_filter=None, gainers=True):
    """Fetch top 5 gainers or losers"""
    try:
        filters = []
        if gainers:
            filters.append(["gt", ["percentchange", 3]])
        else:
            filters.append(["lt", ["percentchange", -2.5]])
        
        market_cap_threshold = 2e9 if region_filter is None else 1e9
        price_threshold = 5 if region_filter is None else 10

        filters.append(["gt", ["intradaymarketcap", market_cap_threshold]])
        filters.append(["gt", ["intradayprice", price_threshold]])
        filters.append(["gt", ["dayvolume", 1000]])

        if region_filter:
            filters.append(["eq", ["region", region_filter]])

        query = yfs.create_query(filters)
        payload = yfs.create_payload("equity", query)
        data = yfs.get_data(payload)
        data_sorted = data.sort_values("regularMarketChangePercent.raw", ascending=not gainers)
        
        return data_sorted.head(5)[["symbol", "regularMarketPrice.raw", "regularMarketChangePercent.raw", "regularMarketVolume.raw"]].to_dict(orient="records")
    
    except Exception as e:
        logger.error(f"Error fetching stocks: {e}")
        return []


def fetch_global_news():
    try:
        ticker = yf.Ticker("^GSPC")  # Use a global market index ticker
        news = ticker.news

        logger.info(f"Global news API returned {len(news) if news else 0} articles")

        global_news = []
        for article in news:
            content = article.get("content", {})
            region = content.get("canonicalUrl", {}).get("region", "")
            title = content.get("title", "Title not found")
            publisher = content.get("provider", {}).get("displayName", "Unknown")
            link = content.get("canonicalUrl", {}).get("url", "No link")
            global_news.append({"title": title, "publisher": publisher, "link": link})

        logger.info(f"Processed {len(global_news)} global news articles")
        return global_news[:5]  # Return top 5
    except Exception as e:
        logger.error(f"Error fetching global news: {e}")
        return []  # Return empty if nothing


# Indian market indices with alternative symbols
INDIAN_INDICES = {
    "nifty": "^NSEI",
    "sensex": "^BSESN",
    "banknifty": "^NSEBANK",
    "midcap_nifty": "NIFTYMIDCAP50.NS"  # Alternative symbol
}

indian_symbols = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "LT.NS",
    "SBIN.NS",
    "AXISBANK.NS",
    "KOTAKBANK.NS",
    "HINDUNILVR.NS",
    "ITC.NS",
    "BAJFINANCE.NS",
    "BHARTIARTL.NS",
    "ASIANPAINT.NS",
    "ULTRACEMCO.NS",
    "MARUTI.NS",
    "NESTLEIND.NS",
    "COALINDIA.NS",
    "POWERGRID.NS",
    "ONGC.NS",
]


def fetch_indian_indices():
    """Fetch current data for Indian market indices - show blank when unavailable"""
    try:
        indices_data = {}

        for index_name, symbol in INDIAN_INDICES.items():
            try:
                # Try to get real data
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="2d")

                if not hist.empty and len(hist) >= 1:
                    current_price = hist['Close'].iloc[-1]

                    # Calculate change if we have previous day data
                    if len(hist) >= 2:
                        prev_close = hist['Close'].iloc[-2]
                        change = current_price - prev_close
                        change_percent = (change / prev_close) * 100 if prev_close != 0 else 0
                    else:
                        prev_close = current_price
                        change = 0
                        change_percent = 0

                    indices_data[index_name] = {
                        "symbol": symbol,
                        "name": index_name.replace("_", " ").title(),
                        "current_price": round(float(current_price), 2),
                        "previous_close": round(float(prev_close), 2),
                        "change": round(float(change), 2),
                        "change_percent": round(float(change_percent), 2),
                        "volume": int(hist['Volume'].iloc[-1]) if 'Volume' in hist.columns and not hist['Volume'].empty else 0,
                        "status": "live_data"
                    }
                    logger.info(f"Successfully fetched live data for {index_name}")
                else:
                    # Return blank/empty structure when no data available
                    indices_data[index_name] = {
                        "symbol": symbol,
                        "name": index_name.replace("_", " ").title(),
                        "current_price": None,
                        "previous_close": None,
                        "change": None,
                        "change_percent": None,
                        "volume": None,
                        "status": "no_data"
                    }
                    logger.warning(f"No historical data available for {index_name}")

            except Exception as e:
                # Return blank/empty structure when error occurs
                indices_data[index_name] = {
                    "symbol": symbol,
                    "name": index_name.replace("_", " ").title(),
                    "current_price": None,
                    "previous_close": None,
                    "change": None,
                    "change_percent": None,
                    "volume": None,
                    "status": "error"
                }
                logger.warning(f"Error fetching data for {index_name}: {e}")

        logger.info(f"Successfully processed data for {len(indices_data)} indices")
        return indices_data

    except Exception as e:
        logger.error(f"Error fetching Indian indices: {e}")
        return {}


def fetch_indian_news(symbols):
    try:
        news_results = []
        seen_links = set()
        successful_symbols = 0

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                news_articles = ticker.news[:1]  # top 1 news per symbol

                if news_articles:
                    successful_symbols += 1

                for article in news_articles:
                    content = article.get("content", {})
                    title = content.get("title", "Title not found")
                    publisher = content.get("provider", {}).get("displayName", "Unknown")
                    link = content.get("canonicalUrl", {}).get("url", "No link")

                    if link not in seen_links:
                        news_results.append({
                            "symbol": symbol,
                            "title": title,
                            "publisher": publisher,
                            "link": link
                        })
                        seen_links.add(link)
            except Exception as e:
                logger.debug(f"Failed to get news for {symbol}: {e}")
                continue  # Skip this symbol if it fails

        logger.info(f"Indian news: {successful_symbols} symbols had news, {len(news_results)} unique articles")
        return news_results
    except Exception as e:
        logger.error(f"Error fetching Indian news: {e}")
        return []  # Return empty if nothing


async def send_email(subject: str, form_data: dict):
    """Send email with form data"""
    try:
        msg = MIMEMultipart()
        msg['From'] = "akash.yadavv181198@gmail.com"
        msg['To'] = "support@aadhaarcapital.com"  # Same sender and receiver
        msg['Subject'] = subject
        
        # Create HTML table for form data
        table_rows = ""
        for key, value in form_data.items():
            # Format key to be more readable (capitalize and replace underscores)
            formatted_key = key.replace("_", " ").title()
            table_rows += f"""
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd; background-color: #f9f9f9; font-weight: bold;">{formatted_key}</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{value}</td>
            </tr>"""

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2c3e50;">Hello Aadhar Capital Team,</h2>

            <p>You have received a new enquiry from your website.</p>

            <h3 style="color: #34495e;">Form Details:</h3>

            <table style="border-collapse: collapse; width: 100%; max-width: 600px; margin: 20px 0;">
                <thead>
                    <tr style="background-color: #3498db; color: white;">
                        <th style="padding: 12px; border: 1px solid #ddd; text-align: left;">Field</th>
                        <th style="padding: 12px; border: 1px solid #ddd; text-align: left;">Value</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>

            <p style="margin-top: 30px; padding: 15px; background-color: #ecf0f1; border-left: 4px solid #3498db;">
                <strong>Submitted at:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            </p>

            <hr style="margin: 30px 0; border: none; border-top: 1px solid #bdc3c7;">

            <p style="font-size: 12px; color: #7f8c8d;">
                This email was automatically generated from your website contact form.
            </p>
        </body>
        </html>
        """

        msg.attach(MIMEText(html_body, 'html'))
        
        server = smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"])
        server.starttls()
        
        if EMAIL_CONFIG["password"]:
            server.login(EMAIL_CONFIG["email"], EMAIL_CONFIG["password"])
            server.send_message(msg)
            server.quit()
            return True
        else:
            logger.warning("Email password not configured")
            return False
            
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return False


async def add_to_google_sheet(form_data: dict):
    """Add dynamic form data to Google Sheet"""
    try:
        service_account_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

        if not service_account_path or not os.path.exists(service_account_path):
            logger.info("Google Sheets credentials not configured - logging form data instead")
            logger.info(f"Form data to add to sheet: {form_data}")
            return False

        gc = gspread.service_account(filename=service_account_path)
        sheet = gc.open_by_key(GOOGLE_SHEET_ID).sheet1

        # Get all existing records to check if headers exist
        existing_records = sheet.get_all_records()

        # Get current headers or create new ones
        if len(existing_records) == 0:
            # No data exists, create headers from form_data keys
            headers = list(form_data.keys())
            sheet.insert_row(headers, 1)
        else:
            # Get existing headers
            headers = sheet.row_values(1)

            # Check if we need to add new columns
            new_fields = [key for key in form_data.keys() if key not in headers]
            if new_fields:
                # Add new headers
                headers.extend(new_fields)
                sheet.insert_row(headers, 1)
                sheet.delete_rows(2)  # Remove old header row

        # Create row data based on current headers
        row_data = []
        for header in headers:
            row_data.append(form_data.get(header, ""))

        sheet.append_row(row_data)
        logger.info(f"Successfully added form data to Google Sheet with {len(headers)} fields")
        return True

    except Exception as e:
        logger.error(f"Error adding to Google Sheet: {e}")
        logger.info(f"Form data (Google Sheets failed): {form_data}")
        return False


@app.get("/")
def root():
    return {
        "message": "Market Overview API with Indian Indices",
        "version": "2.0.0",
        "features": [
            "Indian Market Indices (Nifty, Sensex, Bank Nifty, Midcap Nifty)",
            "Top 5 Gainers/Losers (Global & India)",
            "Financial News (Global & India)",
            "Dynamic Form Submissions with HTML Email"
        ],
        "endpoints": {
            "market_summary": "/market-summary",
            "submit_form": "/submit-form (POST)",
            "health": "/health",
            "docs": "/docs"
        }
    }


@app.get("/market-summary")
def market_summary():
    """Get market summary with Indian indices, top gainers/losers and news"""
    try:
        # Fetch Indian market indices
        indian_indices = fetch_indian_indices()

        # Fetch top gainers/losers
        top5_gainers_global = fetch_top_stocks(region_filter=None, gainers=True)
        top5_losers_global = fetch_top_stocks(region_filter=None, gainers=False)
        top5_gainers_india = fetch_top_stocks(region_filter="in", gainers=True)
        top5_losers_india = fetch_top_stocks(region_filter="in", gainers=False)

        # Fetch news
        global_news = fetch_global_news()
        indian_news = fetch_indian_news(indian_symbols)

        return {
            "success": True,
            "data": {
                "indian_indices": {
                    "nifty": indian_indices.get("nifty", {}),
                    "sensex": indian_indices.get("sensex", {}),
                    "banknifty": indian_indices.get("banknifty", {}),
                    "midcap_nifty": indian_indices.get("midcap_nifty", {})
                },
                "top5_gainers_global": top5_gainers_global,
                "top5_losers_global": top5_losers_global,
                "top5_gainers_india": top5_gainers_india,
                "top5_losers_india": top5_losers_india,
                "global_news": global_news,
                "india_news": indian_news,
            },
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in market summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch market data: {str(e)}")


@app.post("/submit-form")
async def submit_form(request: Request):
    """Submit dynamic form data - accepts any fields, sends email and adds to Google Sheet"""
    try:
        # Get form data from request
        form = await request.form()

        # Convert form data to dictionary
        form_data = {}
        for key, value in form.items():
            form_data[key] = value if value else "Not provided"

        # Add timestamp
        form_data["timestamp"] = datetime.now().isoformat()

        # Get subject for email (default if not provided)
        subject = form_data.get("subject", "Aadhar Capital Website Enquiry")

        email_sent = await send_email(
            subject=f"{subject}",
            form_data=form_data
        )

        # sheet_added = await add_to_google_sheet(form_data)

        return {
            "success": True,
            "message": "Form submitted successfully",
            "email_sent": email_sent,
            # "sheet_updated": sheet_added,
            "timestamp": datetime.now().isoformat(),
            "data": form_data
        }

    except Exception as e:
        logger.error(f"Error submitting form: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit form: {str(e)}")


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "email_configured": bool(EMAIL_CONFIG["password"]),
        "google_sheets_id": GOOGLE_SHEET_ID,
        "timestamp": datetime.now().isoformat()
    }


# Vercel serverless function handler
app = app

# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
