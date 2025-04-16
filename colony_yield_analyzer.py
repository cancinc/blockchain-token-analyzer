import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
import logging
import json
import io
import base64

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s',
                   datefmt='%Y-%m-%d %H:%M:%S')

# Configuration
CLNY_CONTRACT = "0x23cfb27031FfB204a9161cf6D5994dA6df5c4ae7"
BASE_URL = "https://zero-network.calderaexplorer.xyz/api"
WINDOW_DAYS = 7  # Set the moving average window
LIMIT = 1000  # Max per page (API default)
DEFAULT_YIELD_DIR = "yield_data"

# Ensure the yield data directory exists
os.makedirs(DEFAULT_YIELD_DIR, exist_ok=True)

class ColonyYieldAnalyzer:
    """Class to analyze Colony coin yield rates."""
    
    def __init__(self, base_url=BASE_URL, window_days=WINDOW_DAYS):
        """Initialize the yield analyzer."""
        self.base_url = base_url
        self.window_days = window_days
        self.output_path = f"{DEFAULT_YIELD_DIR}/clny_daily_yield.csv"
        self.status = {
            'job_id': None,
            'status': 'idle',
            'progress': 0,
            'current_page': 0,
            'total_pages': None,
            'error': None,
            'output_file': None
        }

    def fetch_all_transfers(self, start_date=None, end_date=None, job_id=None):
        """Fetch all token transfers for the CLNY token."""
        # The API requires module and action parameters - let's use a compatible endpoint
        url = f"{self.base_url}"
        offset = 0
        all_data = []
        page = 1
        has_more = True
        
        # Update status if job_id is provided
        if job_id:
            self.status = {
                'job_id': job_id,
                'status': 'running',
                'progress': 0,
                'current_page': page,
                'total_pages': None,
                'error': None,
                'output_file': None
            }
            update_yield_analysis_status(self.status)
            
        try:
            while has_more:
                logging.info(f"Fetching page {page} (offset {offset}) of CLNY transfers")
                
                # Update progress for status tracking
                if job_id:
                    self.status['current_page'] = page
                    # Calculate progress (estimate 10 pages total if unknown)
                    self.status['progress'] = min(int(page / (self.status['total_pages'] or 10) * 100), 95)
                    update_yield_analysis_status(self.status)
                
                # Make API request using proper parameters for the explorer API
                # We need to use a different approach - the API isn't returning data for our specific token
                # Let's use a broader search method - just get token transfers for the contract
                params = {
                    "module": "account", 
                    "action": "tokentx",
                    # Try multiple approaches at once to increase chances of getting data
                    "address": CLNY_CONTRACT,
                    # No contractaddress filter to get all token transactions
                    "page": page,
                    "offset": LIMIT,
                    "sort": "asc"
                }
                
                # If we're having trouble with CLNY, try a more common token as a test
                # This is just for debugging to see if the API works at all
                if page == 1:
                    logging.info("Also trying alternate API query to debug connectivity...")
                    alt_params = {
                        "module": "account",
                        "action": "tokentx",
                        # Try a well-known token and address
                        "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",  # vitalik.eth
                        "page": 1,
                        "offset": 1,
                        "sort": "desc"
                    }
                    try:
                        test_url = f"{self.base_url}"
                        test_response = requests.get(test_url, params=alt_params)
                        if test_response.status_code == 200:
                            test_data = test_response.json()
                            if test_data.get("status") == "1":
                                logging.info("API test query succeeded - API is operational")
                            else:
                                logging.warning(f"API test query failed: {test_data.get('message')}")
                        else:
                            logging.warning(f"API test query failed with status: {test_response.status_code}")
                    except Exception as e:
                        logging.warning(f"API test query error: {str(e)}")
                        # Continue with original query regardless of test result
                
                # Add date filters if specified - these APIs usually use block numbers, not timestamps
                # Since we don't have a direct timestamp to block number mapping, we'll fetch all and filter later
                # For some APIs, we can use starttime and endtime parameters if they support it
                if start_date:
                    try:
                        # Add a fallback using timestamp for APIs that support it
                        start_timestamp = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
                        # Use starttime parameter (some APIs support this)
                        params["starttime"] = start_timestamp
                    except Exception as e:
                        logging.warning(f"Error parsing start date: {e}")
                        
                if end_date:
                    try:
                        # Add one day to include the end date fully
                        end_timestamp = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp()) + 86400  # Add one day in seconds
                        # Use endtime parameter (some APIs support this)
                        params["endtime"] = end_timestamp
                    except Exception as e:
                        logging.warning(f"Error parsing end date: {e}")
                
                # Log the full API request URL for debugging
                full_url = f"{url}?" + "&".join([f"{k}={v}" for k, v in params.items()])
                logging.info(f"Making API request to: {full_url}")
                
                # Make API request
                response = requests.get(url, params=params)
                
                # Check for successful response
                if response.status_code != 200:
                    error_msg = f"API error: {response.status_code} - {response.text}"
                    logging.error(error_msg)
                    if job_id:
                        self.status['status'] = 'error'
                        self.status['error'] = error_msg
                        update_yield_analysis_status(self.status)
                    return []
                
                # Log the response for debugging
                logging.info(f"API response status: {response.status_code}")
                try:
                    # Truncate the response text to not overflow logs
                    response_snippet = response.text[:500] + '...' if len(response.text) > 500 else response.text
                    logging.info(f"API response: {response_snippet}")
                except Exception as e:
                    logging.warning(f"Error logging API response: {str(e)}")
                
                # Process data - format differs for this API
                data = response.json()
                
                # Check if the response is successful
                if data.get("status") == "1":
                    items = data.get("result", [])
                    
                    # If no items returned, we've reached the end
                    if not items:
                        has_more = False
                    else:
                        all_data.extend(items)
                        page += 1
                        
                        # Simple estimate - we don't know the total count
                        if not self.status['total_pages']:
                            self.status['total_pages'] = 10  # Arbitrary guess
                        if job_id:
                            update_yield_analysis_status(self.status)
                else:
                    # API returned an error
                    error_msg = f"API returned error: {data.get('message', 'Unknown error')}"
                    logging.error(error_msg)
                    if job_id:
                        self.status['status'] = 'error'
                        self.status['error'] = error_msg
                        update_yield_analysis_status(self.status)
                    # For minor errors, continue with empty result rather than completely fail
                    has_more = False
            
            # Update status if completed successfully
            if job_id:
                self.status['progress'] = 100
                self.status['status'] = 'completed'
                update_yield_analysis_status(self.status)
                
            return all_data
            
        except Exception as e:
            error_msg = f"Error fetching CLNY transfers: {str(e)}"
            logging.error(error_msg)
            if job_id:
                self.status['status'] = 'error'
                self.status['error'] = error_msg
                update_yield_analysis_status(self.status)
            return []

    def process_transfers(self, transfers):
        """Process token transfers to calculate daily yield."""
        if not transfers:
            return pd.DataFrame(columns=["date", "amount", "moving_avg", "daily_change", "weekly_change"])
            
        try:
            # Convert to DataFrame
            df = pd.DataFrame(transfers)
            
            # Check which format we're dealing with based on columns
            if "block_timestamp" in df.columns:
                # Original format
                df["timestamp"] = pd.to_datetime(df["block_timestamp"])
                df["amount"] = pd.to_numeric(df["value"], errors='coerce') / 1e18  # Adjust for token decimals (18 decimals)
            else:
                # API format - different field names
                # Convert timestamp from Unix timestamp to datetime
                if "timeStamp" in df.columns:
                    df["timestamp"] = pd.to_datetime(pd.to_numeric(df["timeStamp"], errors='coerce'), unit='s')
                elif "timestamp" in df.columns:
                    df["timestamp"] = pd.to_datetime(pd.to_numeric(df["timestamp"], errors='coerce'), unit='s')
                    
                # Handle value field with different possible names
                if "value" in df.columns:
                    value_col = "value"
                elif "Value" in df.columns:
                    value_col = "Value"
                elif "tokenValue" in df.columns:
                    value_col = "tokenValue"
                else:
                    # Use first available numeric column as fallback
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    value_col = numeric_cols[0] if len(numeric_cols) > 0 else None
                    
                if value_col:
                    df["amount"] = pd.to_numeric(df[value_col], errors='coerce') / 1e18  # Adjust for token decimals (18 decimals)
                else:
                    # If no suitable value column found, create an empty one
                    df["amount"] = 1.0  # Default to 1.0 for counting transactions
                
            # Extract the date portion 
            df["date"] = df["timestamp"].dt.date
            
            # Group by date and calculate sum
            daily_totals = df.groupby("date")["amount"].sum().reset_index()
            
            # Calculate 7-day moving average
            daily_totals["moving_avg"] = daily_totals["amount"].rolling(window=self.window_days).mean()
            
            # Add day-over-day change
            daily_totals["daily_change"] = daily_totals["amount"].pct_change() * 100
            
            # Fill NaN values for first day
            daily_totals["daily_change"] = daily_totals["daily_change"].fillna(0)
            
            # Add week-over-week change
            daily_totals["weekly_change"] = daily_totals["amount"].pct_change(periods=7) * 100
            
            # Convert date to string to avoid JSON serialization issues
            daily_totals["date"] = daily_totals["date"].astype(str)
            
            return daily_totals
            
        except Exception as e:
            logging.error(f"Error processing transfers: {str(e)}")
            return pd.DataFrame(columns=["date", "amount", "moving_avg", "daily_change", "weekly_change"])

    def save_to_csv(self, df, filename=None):
        """Save yield data to CSV file."""
        output_path = filename or self.output_path
        
        try:
            df.to_csv(output_path, index=False)
            logging.info(f"Yield data saved to {output_path}")
            
            # Update status with output file
            self.status['output_file'] = output_path
            update_yield_analysis_status(self.status)
            
            return output_path
            
        except Exception as e:
            logging.error(f"Error saving to CSV: {str(e)}")
            return None

    def generate_yield_report(self, start_date=None, end_date=None, window_days=None, job_id=None):
        """Generate a complete yield report."""
        # Update window days if provided
        if window_days is not None:
            self.window_days = window_days
            
        # Generate output filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"{DEFAULT_YIELD_DIR}/clny_yield_{timestamp}.csv"
        
        # Fetch and process data
        transfers = self.fetch_all_transfers(start_date, end_date, job_id)
        daily_yield_df = self.process_transfers(transfers)
        
        # Save to CSV
        output_path = self.save_to_csv(daily_yield_df, output_filename)
        
        # Calculate summary statistics
        stats = {}
        if not daily_yield_df.empty:
            stats["total_transfers"] = len(transfers)
            stats["date_range"] = {
                "start": daily_yield_df["date"].min(),
                "end": daily_yield_df["date"].max()
            }
            stats["yield_stats"] = {
                "mean_daily": daily_yield_df["amount"].mean(),
                "max_daily": daily_yield_df["amount"].max(),
                "min_daily": daily_yield_df["amount"].min(),
                "total_amount": daily_yield_df["amount"].sum(),
                "latest_daily": float(daily_yield_df["amount"].iloc[-1]) if len(daily_yield_df) > 0 else 0,
                "latest_ma": float(daily_yield_df["moving_avg"].iloc[-1]) if len(daily_yield_df) > 0 else 0
            }
        
        # Create report
        report = {
            "output_file": output_path,
            "statistics": stats,
            "window_days": self.window_days
        }
        
        return report

    def generate_yield_chart(self, daily_yield_df, chart_type='line'):
        """Generate a chart visualization of yield data."""
        if daily_yield_df.empty:
            return None
            
        try:
            # Convert date strings back to datetime for better x-axis
            daily_yield_df['date'] = pd.to_datetime(daily_yield_df['date'])
            
            # Create figure and axis
            plt.figure(figsize=(12, 6))
            
            if chart_type == 'line' or chart_type == 'both':
                # Plot daily amount
                plt.plot(daily_yield_df['date'], daily_yield_df['amount'], 
                        label='Daily Yield', color='skyblue', alpha=0.7)
                
                # Plot moving average
                plt.plot(daily_yield_df['date'], daily_yield_df['moving_avg'], 
                        label=f'{self.window_days}-Day Moving Avg', 
                        color='darkblue', linewidth=2)
                
            if chart_type == 'bar' or chart_type == 'both':
                # Plot bar chart of daily yield
                plt.bar(daily_yield_df['date'], daily_yield_df['amount'], 
                      alpha=0.5, color='lightblue', width=0.8)
            
            # Add labels and title
            plt.title('CLNY Daily Yield Analysis', fontsize=16)
            plt.xlabel('Date', fontsize=12)
            plt.ylabel('Amount (CLNY)', fontsize=12)
            plt.grid(True, alpha=0.3)
            plt.legend()
            
            # Format y-axis with commas for thousands
            plt.gca().get_yaxis().set_major_formatter(
                plt.matplotlib.ticker.FuncFormatter(lambda x, p: format(int(x), ',')))
            
            # Save to in-memory file
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight')
            buffer.seek(0)
            
            # Encode as base64 string
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # Close the figure to free memory
            plt.close()
            
            return image_base64
            
        except Exception as e:
            logging.error(f"Error generating chart: {str(e)}")
            return None

def get_yield_analysis_status():
    """Get the current yield analysis status."""
    status_file = f"{DEFAULT_YIELD_DIR}/yield_status.json"
    
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                return json.load(f)
        except Exception:
            pass
            
    return {
        'job_id': None,
        'status': 'idle',
        'progress': 0,
        'current_page': 0,
        'total_pages': None,
        'error': None,
        'output_file': None
    }

def update_yield_analysis_status(status):
    """Update the yield analysis status."""
    status_file = f"{DEFAULT_YIELD_DIR}/yield_status.json"
    
    try:
        with open(status_file, 'w') as f:
            json.dump(status, f)
    except Exception as e:
        logging.error(f"Error updating yield analysis status: {str(e)}")

def get_recent_yield_reports(max_files=5):
    """Get a list of recent yield report files."""
    report_files = []
    
    try:
        # Check if directory exists
        if not os.path.exists(DEFAULT_YIELD_DIR):
            os.makedirs(DEFAULT_YIELD_DIR, exist_ok=True)
            return []
            
        # Get all CSV files in the yield_data directory
        for file in os.listdir(DEFAULT_YIELD_DIR):
            if file.endswith('.csv') and file.startswith('clny_yield_'):
                file_path = os.path.join(DEFAULT_YIELD_DIR, file)
                report_files.append({
                    'path': file_path,
                    'mtime': os.path.getmtime(file_path)
                })
        
        # Sort by modification time (newest first)
        report_files.sort(key=lambda x: x['mtime'], reverse=True)
        
        # Return paths only
        return [f['path'] for f in report_files[:max_files]]
    
    except Exception as e:
        logging.error(f"Error getting recent yield reports: {str(e)}")
        return []

# Example usage
if __name__ == "__main__":
    analyzer = ColonyYieldAnalyzer()
    transfers = analyzer.fetch_all_transfers()
    daily_yield_df = analyzer.process_transfers(transfers)
    analyzer.save_to_csv(daily_yield_df)