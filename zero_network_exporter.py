#!/usr/bin/env python3
"""
Zero Network Token Transaction Exporter

This script fetches token transactions from Zero Network Explorer API
and exports them to a CSV file.
"""

import argparse
import csv
import json
import logging
import os
import sys
import glob
import threading
import time
import requests
from datetime import datetime
from pathlib import Path

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Directories for storing exports and presets
DEFAULT_EXPORT_DIR = "exports"
DEFAULT_PRESETS_DIR = "presets"
DEFAULT_PRESETS_FILE = "presets/export_presets.json"

# Global variables for tracking export progress
export_status = {
    'job_id': None,
    'status': 'idle',  # 'idle', 'running', 'completed', 'error'
    'progress': 0,  # 0-100 percentage
    'total_addresses': 0,
    'processed_addresses': 0,
    'current_address': None,
    'total_transactions': 0,
    'current_page': 0,
    'max_pages': 0,
    'error': None,
    'output_file': None,
    'start_time': None,
    'end_time': None
}

# Lock for thread-safe access to the status variable
status_lock = threading.RLock()


class ZeroNetworkExporter:
    """Class to handle fetching and exporting Zero Network token transactions."""

    def __init__(self, base_url='https://zero-network.calderaexplorer.xyz/api'):
        """
        Initialize the exporter with API base URL.

        Args:
            base_url (str): Base URL for the Zero Network API (or compatible explorer API)
        """
        self.base_url = base_url
        self.session = requests.Session()

    def fetch_transactions(self, address, page=1, offset=100, sort='asc', internal=False, 
                          start_date=None, end_date=None, token_contract=None):
        """
        Fetch token transactions for the given address.

        Args:
            address (str): Blockchain address to fetch transactions for
            page (int): Page number for pagination
            offset (int): Number of records per page
            sort (str): Sort order ('asc' or 'desc')
            internal (bool): Whether to fetch internal transactions
            start_date (str): Start date in format 'YYYY-MM-DD' to filter transactions
            end_date (str): End date in format 'YYYY-MM-DD' to filter transactions
            token_contract (str): Token contract address to filter transactions

        Returns:
            dict: API response data
        """
        # Check if token is NFT (ERC-721) if token_contract is provided
        is_nft = False
        if token_contract:
            try:
                token_info_params = {
                    'module': 'token',
                    'action': 'getToken',
                    'contractaddress': token_contract
                }
                token_info_response = requests.get(f"{self.base_url}", params=token_info_params)
                token_info = token_info_response.json()
                
                if token_info.get('status') == '1' and token_info.get('result', {}).get('type') == 'ERC-721':
                    is_nft = True
                    logger.info(f"Token {token_contract} detected as ERC-721 NFT")
            except Exception as e:
                logger.warning(f"Error checking token type: {e}")
        
        # Select the appropriate action based on token type
        if is_nft:
            action = 'tokennfttx'  # For NFT transactions
            logger.info(f"Using NFT transactions endpoint for ERC-721 token")
        elif internal:
            action = 'tokentxlistinternal'
        else:
            action = 'tokentx'  # Default for ERC-20 tokens

        params = {
            'module': 'account',
            'action': action,
            'address': address,
            'page': page,
            'offset': offset,
            'sort': sort
        }
        
        # Add token contract address if specified
        if token_contract:
            params['contractaddress'] = token_contract
            logger.info(f"Filtering for token contract: {token_contract}")
        
        # Convert dates to Unix timestamps if provided
        if start_date:
            try:
                start_timestamp = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
                params['startblock'] = 1  # Use a very early block as fallback
                params['starttime'] = start_timestamp
                logger.debug(f"Using start timestamp: {start_timestamp} ({start_date})")
            except ValueError:
                logger.warning(f"Invalid start date format: {start_date}, expected YYYY-MM-DD")
        
        if end_date:
            try:
                # Set to end of day (23:59:59)
                end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
                end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
                end_timestamp = int(end_datetime.timestamp())
                params['endblock'] = 999999999  # Use a very high block as fallback
                params['endtime'] = end_timestamp
                logger.debug(f"Using end timestamp: {end_timestamp} ({end_date})")
            except ValueError:
                logger.warning(f"Invalid end date format: {end_date}, expected YYYY-MM-DD")

        logger.info(f"Fetching transactions for address: {address} (page {page}, {offset} per page)")
        
        try:
            response = self.session.get(self.base_url, params=params)
            response.raise_for_status()  # Raise an exception for HTTP errors
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise

    def export_to_csv(self, data, output_file, additional_fields=None):
        """
        Export transaction data to CSV.

        Args:
            data (dict): Transaction data to export
            output_file (str): Path to output CSV file
            additional_fields (list): Optional additional fields to include in CSV

        Returns:
            int: Number of transactions exported
        """
        if 'result' not in data:
            logger.error("Error: 'result' key not found in the response")
            logger.debug(f"Response data: {json.dumps(data, indent=2)}")
            raise KeyError("'result' key not found in the API response")

        # Default fields to extract
        fields = [
            'timeStamp', 'hash', 'from', 'to', 'value', 'tokenName', 
            'tokenSymbol', 'tokenDecimal', 'contractAddress', 'tokenID'
        ]
        
        # Add additional fields if specified
        if additional_fields:
            fields.extend([field for field in additional_fields if field not in fields])

        # Human-readable field names for CSV header
        field_display_names = {
            'timeStamp': 'Timestamp',
            'hash': 'Transaction Hash',
            'from': 'From Address',
            'to': 'To Address',
            'value': 'Value',
            'tokenName': 'Token Name',
            'tokenSymbol': 'Token Symbol',
            'tokenDecimal': 'Token Decimal',
            'contractAddress': 'Contract Address',
            'tokenID': 'Token ID',
            'gasUsed': 'Gas Used',
            'gasPrice': 'Gas Price',
            'cumulativeGasUsed': 'Cumulative Gas Used',
            'confirmations': 'Confirmations',
            'blockNumber': 'Block Number',
            'blockHash': 'Block Hash',
            'transactionIndex': 'Transaction Index',
            'nonce': 'Nonce'
        }

        # Get human-readable headers for selected fields
        headers = [field_display_names.get(field, field) for field in fields]
        
        transactions = data['result']
        if not transactions:
            logger.warning("No transactions found in the API response")
            return 0

        # Ensure output directory exists
        output_path = Path(output_file)
        output_dir = output_path.parent
        if output_dir != Path('.') and not output_dir.exists():
            logger.info(f"Creating output directory: {output_dir}")
            output_dir.mkdir(parents=True, exist_ok=True)

        with open(output_file, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(headers)
            
            for tx in transactions:
                # Process timestamp to human-readable format if available
                if 'timeStamp' in tx and tx['timeStamp']:
                    try:
                        timestamp = int(tx['timeStamp'])
                        tx['timeStamp'] = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                    except (ValueError, TypeError):
                        pass  # Keep original if conversion fails
                
                # Process token value with decimal places if available
                if 'value' in tx and 'tokenDecimal' in tx:
                    try:
                        value = int(tx['value'])
                        decimals = int(tx['tokenDecimal'])
                        tx['value'] = value / (10 ** decimals)
                    except (ValueError, TypeError):
                        pass  # Keep original if conversion fails
                
                # Extract values for each field
                row = [tx.get(field, '') for field in fields]
                writer.writerow(row)
        
        logger.info(f"Successfully exported {len(transactions)} transactions to {output_file}")
        return len(transactions)

    def process_all_pages(self, address, output_file, start_page=1, max_pages=None, 
                         records_per_page=100, sort='asc', internal=False, additional_fields=None,
                         start_date=None, end_date=None, token_contract=None, job_id=None):
        """
        Process all pages of transactions and export to a single CSV file.

        Args:
            address (str or list): Blockchain address(es) to fetch transactions for.
                                   Can be a single address string or a list of addresses.
            output_file (str): Path to output CSV file
            start_page (int): Page to start from
            max_pages (int): Maximum number of pages to process (None for all)
            records_per_page (int): Number of records per page
            sort (str): Sort order ('asc' or 'desc')
            internal (bool): Whether to fetch internal transactions
            additional_fields (list): Optional additional fields to include in CSV
            start_date (str): Start date in format 'YYYY-MM-DD' to filter transactions
            end_date (str): End date in format 'YYYY-MM-DD' to filter transactions
            token_contract (str): Token contract address to filter transactions
            job_id (str): Optional job ID for tracking progress

        Returns:
            int: Total number of transactions exported
        """
        total_transactions = 0
        all_data = {'result': []}

        # Log date range if provided
        if start_date or end_date:
            date_range = f"from {start_date}" if start_date else "until"
            if end_date:
                date_range = f"{date_range} to {end_date}" if start_date else f"until {end_date}"
            logger.info(f"Filtering transactions {date_range}")
        
        # Handle multiple addresses
        address_list = address if isinstance(address, list) else [address]
        
        # Initialize progress tracking if job_id is provided
        if job_id:
            start_export_job(job_id, address_list, max_pages)
            update_export_progress(output_file=output_file)
        
        try:
            for addr_index, addr in enumerate(address_list):
                logger.info(f"Processing address: {addr}")
                
                # Update progress status with current address
                if job_id:
                    update_export_progress(current_address=addr)
                
                current_page = start_page
                addr_transactions = 0
                
                while True:
                    try:
                        # Update progress status with current page
                        if job_id:
                            update_export_progress(current_page=current_page)
                        
                        data = self.fetch_transactions(
                            address=addr,
                            page=current_page,
                            offset=records_per_page,
                            sort=sort,
                            internal=internal,
                            start_date=start_date,
                            end_date=end_date,
                            token_contract=token_contract
                        )
                        
                        # Check if we have results
                        if 'result' not in data or not data['result']:
                            logger.info(f"No more transactions found for address {addr} at page {current_page}")
                            break
                        
                        # Filter results by date if needed
                        filtered_results = data['result']
                        if start_date or end_date:
                            start_ts = None
                            end_ts = None
                            
                            if start_date:
                                try:
                                    start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
                                except ValueError:
                                    pass
                            
                            if end_date:
                                try:
                                    end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
                                    end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
                                    end_ts = int(end_datetime.timestamp())
                                except ValueError:
                                    pass
                            
                            if start_ts or end_ts:
                                logger.debug(f"Post-filtering transactions by timestamp")
                                filtered_results = []
                                for tx in data['result']:
                                    tx_ts = int(tx.get('timeStamp', 0))
                                    if (not start_ts or tx_ts >= start_ts) and (not end_ts or tx_ts <= end_ts):
                                        filtered_results.append(tx)
                                
                                logger.debug(f"Filtered {len(data['result']) - len(filtered_results)} transactions outside date range")
                        
                        # Add filtered results to our collection
                        all_data['result'].extend(filtered_results)
                        current_page_count = len(filtered_results)
                        addr_transactions += current_page_count
                        total_transactions += current_page_count
                        
                        # Update progress with transaction count
                        if job_id:
                            update_export_progress(transactions=current_page_count)
                        
                        logger.info(f"Retrieved {current_page_count} transactions for address {addr} from page {current_page}")
                        
                        # Check if we've reached the max pages or if there are no more results
                        if max_pages and current_page >= start_page + max_pages - 1:
                            logger.info(f"Reached maximum pages limit ({max_pages}) for address {addr}")
                            break
                        
                        # If we got fewer records than requested, we've reached the end
                        if current_page_count < records_per_page:
                            logger.info(f"Reached last page of results for address {addr}")
                            break
                        
                        current_page += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing page {current_page} for address {addr}: {e}")
                        if job_id:
                            update_export_progress(error=str(e))
                        break
                
                logger.info(f"Completed processing address {addr}: {addr_transactions} transactions found")
            
            # Export all collected data
            if all_data['result']:
                self.export_to_csv(all_data, output_file, additional_fields)
                logger.info(f"Exported a total of {total_transactions} transactions from {len(address_list)} addresses")
                
                # Update progress to completed
                if job_id:
                    update_export_progress(status='completed')
            else:
                if len(address_list) == 1:
                    msg = f"No transactions found for address {address_list[0]}"
                    logger.warning(msg)
                    if job_id:
                        update_export_progress(status='error', error=msg)
                else:
                    msg = f"No transactions found for any of the {len(address_list)} addresses"
                    logger.warning(msg)
                    if job_id:
                        update_export_progress(status='error', error=msg)
                
            return total_transactions
            
        except Exception as e:
            logger.error(f"Error during export process: {e}")
            if job_id:
                update_export_progress(status='error', error=str(e))
            raise


def start_export_job(job_id, addresses, max_pages=None):
    """
    Initialize or reset the export status for a new job.
    
    Args:
        job_id (str): Unique identifier for the export job
        addresses (list): List of addresses to process
        max_pages (int): Maximum pages to process per address
        
    Returns:
        dict: Current export status
    """
    with status_lock:
        global export_status
        export_status = {
            'job_id': job_id,
            'status': 'running',
            'progress': 0,
            'total_addresses': len(addresses) if isinstance(addresses, list) else 1,
            'processed_addresses': 0,
            'current_address': addresses[0] if isinstance(addresses, list) and addresses else addresses,
            'total_transactions': 0,
            'current_page': 1,
            'max_pages': max_pages,
            'error': None,
            'output_file': None,
            'start_time': datetime.now().isoformat(),
            'end_time': None
        }
        return export_status.copy()

def update_export_progress(current_address=None, current_page=None, transactions=None, status=None, error=None, output_file=None):
    """
    Update the export progress status.
    
    Args:
        current_address (str): Current address being processed
        current_page (int): Current page being processed
        transactions (int): Number of transactions processed
        status (str): Current status ('running', 'completed', 'error')
        error (str): Error message if status is 'error'
        output_file (str): Path to the output file
        
    Returns:
        dict: Updated export status
    """
    with status_lock:
        global export_status
        
        if current_address and current_address != export_status['current_address']:
            export_status['current_address'] = current_address
            export_status['processed_addresses'] += 1
            export_status['current_page'] = 1
        
        if current_page:
            export_status['current_page'] = current_page
        
        if transactions:
            export_status['total_transactions'] += transactions
        
        if status:
            export_status['status'] = status
            if status in ['completed', 'error']:
                export_status['end_time'] = datetime.now().isoformat()
        
        if error:
            export_status['error'] = error
            
        if output_file:
            export_status['output_file'] = output_file
        
        # Calculate progress percentage
        total_work = export_status['total_addresses'] * (export_status['max_pages'] if export_status['max_pages'] else 10)
        current_work = (export_status['processed_addresses'] * (export_status['max_pages'] if export_status['max_pages'] else 10)) + export_status['current_page']
        export_status['progress'] = min(int((current_work / total_work) * 100), 99)
        
        # If status is completed, set progress to 100%
        if export_status['status'] == 'completed':
            export_status['progress'] = 100
            
        return export_status.copy()

def get_export_status():
    """
    Get the current export status.
    
    Returns:
        dict: Current export status
    """
    with status_lock:
        return export_status.copy()

def get_recent_exports(max_files=5):
    """
    Get a list of the most recent export files.
    
    Args:
        max_files (int): Maximum number of files to retrieve
        
    Returns:
        list: List of recent export files, sorted by modification time (newest first)
    """
    # Search for CSV files in the export directory and root
    export_files = []
    
    # Check the export directory first
    if os.path.exists(DEFAULT_EXPORT_DIR):
        export_files.extend(glob.glob(f"{DEFAULT_EXPORT_DIR}/*.csv"))
    
    # Also check the root directory
    export_files.extend(glob.glob("*.csv"))
    
    # Sort by modification time (newest first)
    export_files.sort(key=os.path.getmtime, reverse=True)
    
    # Return the most recent files
    return export_files[:max_files]


def show_recent_exports():
    """Display information about recent export files."""
    recent_files = get_recent_exports()
    
    if not recent_files:
        logger.info("No recent export files found.")
        return
    
    logger.info("Recent export files:")
    for idx, file_path in enumerate(recent_files, 1):
        file_size = os.path.getsize(file_path) / 1024  # Size in KB
        mod_time = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"{idx}. {file_path} ({file_size:.1f} KB, modified: {mod_time})")


def generate_output_filename(address, internal=False):
    """
    Generate a timestamped output filename.
    
    Args:
        address (str): The blockchain address
        internal (bool): Whether this is for internal transactions
        
    Returns:
        str: The generated output filename
    """
    # Create short address for filename (first 8 chars)
    short_addr = address[:8] if len(address) > 8 else address
    
    # Get current timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Create the filename
    tx_type = "internal" if internal else "token"
    filename = f"{DEFAULT_EXPORT_DIR}/tx_{tx_type}_{short_addr}_{timestamp}.csv"
    
    return filename


def load_presets():
    """
    Load export presets from the presets file.
    
    Returns:
        dict: Dictionary of preset configurations
    """
    # Ensure presets directory exists
    os.makedirs(DEFAULT_PRESETS_DIR, exist_ok=True)
    
    # Check if presets file exists
    if not os.path.exists(DEFAULT_PRESETS_FILE):
        # Create empty presets file
        with open(DEFAULT_PRESETS_FILE, 'w') as f:
            json.dump({}, f, indent=2)
        return {}
    
    # Load presets from file
    try:
        with open(DEFAULT_PRESETS_FILE, 'r') as f:
            presets = json.load(f)
        return presets
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading presets: {e}")
        return {}


def save_preset(name, config):
    """
    Save an export configuration preset.
    
    Args:
        name (str): Name of the preset
        config (dict): Export configuration dictionary
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Load existing presets
    presets = load_presets()
    
    # Add or update the preset
    presets[name] = config
    
    # Save presets back to file
    try:
        # Ensure presets directory exists
        os.makedirs(DEFAULT_PRESETS_DIR, exist_ok=True)
        
        with open(DEFAULT_PRESETS_FILE, 'w') as f:
            json.dump(presets, f, indent=2)
        logger.info(f"Preset '{name}' saved successfully")
        return True
    except IOError as e:
        logger.error(f"Error saving preset: {e}")
        return False


def delete_preset(name):
    """
    Delete an export configuration preset.
    
    Args:
        name (str): Name of the preset to delete
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Load existing presets
    presets = load_presets()
    
    # Check if preset exists
    if name not in presets:
        logger.error(f"Preset '{name}' not found")
        return False
    
    # Delete the preset
    del presets[name]
    
    # Save presets back to file
    try:
        with open(DEFAULT_PRESETS_FILE, 'w') as f:
            json.dump(presets, f, indent=2)
        logger.info(f"Preset '{name}' deleted successfully")
        return True
    except IOError as e:
        logger.error(f"Error deleting preset: {e}")
        return False


def list_presets():
    """
    List all available export presets.
    
    Returns:
        dict: Dictionary of presets
    """
    presets = load_presets()
    
    if not presets:
        logger.info("No export presets found")
    else:
        logger.info(f"Found {len(presets)} export presets:")
        for idx, (name, config) in enumerate(presets.items(), 1):
            # Extract key information for display
            address = config.get('address', 'N/A')
            internal = config.get('internal', False)
            date_range = ""
            
            if config.get('start_date') and config.get('end_date'):
                date_range = f"{config['start_date']} to {config['end_date']}"
            elif config.get('start_date'):
                date_range = f"from {config['start_date']}"
            elif config.get('end_date'):
                date_range = f"until {config['end_date']}"
            elif config.get('no_date_filter', False):
                date_range = "no date filtering"
                
            tx_type = "internal" if internal else "token"
            max_pages = config.get('max_pages', 'all')
            
            logger.info(f"{idx}. {name}: {address} ({tx_type}, {date_range}, pages: {max_pages})")
    
    return presets


def main():
    """Main entry point for the script."""
    # Create the base parser
    parser = argparse.ArgumentParser(
        description='Fetch and export Zero Network token transactions to CSV',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Check for legacy mode first (direct address input)
    if len(sys.argv) > 1 and sys.argv[1].startswith('0x'):
        # Legacy mode detected, handle differently
        address = sys.argv[1]
        logger.info(f"Legacy mode detected. Processing address: {address}")
        
        # Create args for legacy mode
        args = argparse.Namespace()
        args.command = 'export'
        args.address = address
        args.output = 'transactions.csv'
        args.page = 1
        args.max_pages = None
        args.records = 100
        args.sort = 'asc'
        args.internal = False
        args.api_url = 'https://explorer.zero.network/api'
        args.fields = None
        args.verbose = False
        args.num_files = 5
        args.start_date = None
        args.end_date = None
        args.no_date_filter = False
        
        # Process remaining arguments from command line
        i = 2
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg == '-v' or arg == '--verbose':
                args.verbose = True
                i += 1
            elif arg == '-i' or arg == '--internal':
                args.internal = True
                i += 1
            elif arg == '--no-date-filter':
                args.no_date_filter = True
                i += 1
            elif i + 1 < len(sys.argv):
                val = sys.argv[i + 1]
                if arg == '-o' or arg == '--output':
                    args.output = val
                    i += 2
                elif arg == '-p' or arg == '--page':
                    args.page = int(val)
                    i += 2
                elif arg == '-m' or arg == '--max-pages':
                    args.max_pages = int(val)
                    i += 2
                elif arg == '-r' or arg == '--records':
                    args.records = int(val)
                    i += 2
                elif arg == '-s' or arg == '--sort':
                    args.sort = val
                    i += 2
                elif arg == '-u' or arg == '--api-url':
                    args.api_url = val
                    i += 2
                elif arg == '--start-date':
                    args.start_date = val
                    i += 2
                elif arg == '--end-date':
                    args.end_date = val
                    i += 2
                else:
                    i += 1
            else:
                i += 1
    else:
        # Add verbose flag to main parser (applies to all commands)
        parser.add_argument('-v', '--verbose', action='store_true',
                            help='Enable verbose logging')
                            
        # Command subparsers
        subparsers = parser.add_subparsers(dest='command', help='Command to execute')
        
        # Export command
        export_parser = subparsers.add_parser('export', help='Export transactions')
        address_group = export_parser.add_mutually_exclusive_group(required=True)
        address_group.add_argument('--address', '-a', help='Blockchain address to fetch transactions for')
        address_group.add_argument('--address-file', '-af', help='File containing one blockchain address per line')
        address_group.add_argument('--addresses', '-as', nargs='+', help='Multiple blockchain addresses to fetch transactions for')
        export_parser.add_argument('-o', '--output', 
                            help='Output CSV file path (default: auto-generated timestamped file)')
        export_parser.add_argument('-p', '--page', type=int, default=1,
                            help='Page number to start from')
        export_parser.add_argument('-m', '--max-pages', type=int, default=None,
                            help='Maximum number of pages to process (default: all)')
        export_parser.add_argument('-r', '--records', type=int, default=100,
                            help='Number of records per page')
        export_parser.add_argument('-s', '--sort', choices=['asc', 'desc'], default='asc',
                            help='Sort order for transactions')
        export_parser.add_argument('-i', '--internal', action='store_true',
                            help='Fetch internal token transactions')
        export_parser.add_argument('-u', '--api-url', default='https://zero-network.calderaexplorer.xyz/api',
                            help='Blockchain explorer API base URL')
        export_parser.add_argument('-f', '--fields', nargs='+',
                            help='Additional fields to include in the CSV output')
        export_parser.add_argument('--start-date', 
                            help='Start date for filtering transactions (format: YYYY-MM-DD)')
        export_parser.add_argument('--end-date', 
                            help='End date for filtering transactions (format: YYYY-MM-DD)')
        export_parser.add_argument('--no-date-filter', action='store_true',
                            help='Disable date filtering completely')
        export_parser.add_argument('--token-contract',
                            help='Token contract address to filter transactions')
        export_parser.add_argument('-v', '--verbose', action='store_true',
                            help='Enable verbose logging for export command')
        
        # Recent command
        recent_parser = subparsers.add_parser('recent', help='List recent export files')
        recent_parser.add_argument('-n', '--num-files', type=int, default=5,
                             help='Number of recent files to display')
        recent_parser.add_argument('-v', '--verbose', action='store_true',
                             help='Enable verbose logging for recent command')
                             
        # Preset commands
        preset_parser = subparsers.add_parser('preset', help='Manage export configuration presets')
        preset_subparsers = preset_parser.add_subparsers(dest='preset_command', help='Preset command to execute')
        
        # List presets command
        list_parser = preset_subparsers.add_parser('list', help='List available presets')
        list_parser.add_argument('-v', '--verbose', action='store_true',
                           help='Enable verbose logging for preset list command')
        
        # Save preset command
        save_parser = preset_subparsers.add_parser('save', help='Save current or specified export configuration as a preset')
        save_parser.add_argument('name', help='Name of the preset to save')
        save_parser.add_argument('-a', '--address', required=True,
                           help='Blockchain address to fetch transactions for')
        save_parser.add_argument('-m', '--max-pages', type=int, default=None,
                           help='Maximum number of pages to process (default: all)')
        save_parser.add_argument('-r', '--records', type=int, default=100,
                           help='Number of records per page')
        save_parser.add_argument('-s', '--sort', choices=['asc', 'desc'], default='asc',
                           help='Sort order for transactions')
        save_parser.add_argument('-i', '--internal', action='store_true',
                           help='Fetch internal token transactions')
        save_parser.add_argument('--start-date', 
                           help='Start date for filtering transactions (format: YYYY-MM-DD)')
        save_parser.add_argument('--end-date', 
                           help='End date for filtering transactions (format: YYYY-MM-DD)')
        save_parser.add_argument('--no-date-filter', action='store_true',
                           help='Disable date filtering completely')
        save_parser.add_argument('--token-contract',
                           help='Token contract address to filter transactions')
        save_parser.add_argument('-f', '--fields', nargs='+',
                           help='Additional fields to include in the CSV output')
        save_parser.add_argument('-v', '--verbose', action='store_true',
                           help='Enable verbose logging for preset save command')
        
        # Delete preset command
        delete_parser = preset_subparsers.add_parser('delete', help='Delete a preset')
        delete_parser.add_argument('name', help='Name of the preset to delete')
        delete_parser.add_argument('-v', '--verbose', action='store_true',
                              help='Enable verbose logging for preset delete command')
        
        # Use preset command
        use_parser = preset_subparsers.add_parser('use', help='Use a preset for export')
        use_parser.add_argument('name', help='Name of the preset to use')
        use_parser.add_argument('-o', '--output', 
                          help='Output CSV file path (default: auto-generated timestamped file)')
        use_parser.add_argument('-v', '--verbose', action='store_true',
                          help='Enable verbose logging for preset use command')
        
        # Parse arguments
        args = parser.parse_args()
    
    # Set logging level based on verbosity
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Handle the 'recent' command
    if args.command == 'recent':
        show_recent_exports()
        return 0
        
    # Handle the 'preset' commands
    if args.command == 'preset':
        # If no preset subcommand was specified
        if not hasattr(args, 'preset_command') or not args.preset_command:
            logger.error("No preset command specified")
            parser.print_help()
            return 1
            
        # Handle preset list command
        if args.preset_command == 'list':
            list_presets()
            return 0
            
        # Handle preset save command
        elif args.preset_command == 'save':
            preset_config = {
                'address': args.address,
                'max_pages': args.max_pages,
                'records': args.records,
                'sort': args.sort,
                'internal': args.internal,
                'fields': args.fields,
                'token_contract': args.token_contract if hasattr(args, 'token_contract') else None
            }
            
            # Handle date filtering options
            if args.no_date_filter:
                preset_config['no_date_filter'] = True
            else:
                if args.start_date:
                    preset_config['start_date'] = args.start_date
                if args.end_date:
                    preset_config['end_date'] = args.end_date
            
            success = save_preset(args.name, preset_config)
            if success:
                logger.info(f"Preset '{args.name}' saved successfully with address: {args.address}")
                list_presets()  # Show all presets
                return 0
            else:
                logger.error(f"Failed to save preset '{args.name}'")
                return 1
                
        # Handle preset delete command
        elif args.preset_command == 'delete':
            success = delete_preset(args.name)
            if success:
                logger.info(f"Preset '{args.name}' deleted successfully")
                list_presets()  # Show remaining presets
                return 0
            else:
                logger.error(f"Failed to delete preset '{args.name}'")
                return 1
                
        # Handle preset use command
        elif args.preset_command == 'use':
            presets = load_presets()
            
            if args.name not in presets:
                logger.error(f"Preset '{args.name}' not found")
                return 1
                
            preset = presets[args.name]
            logger.info(f"Using preset '{args.name}' with configuration:")
            for key, value in preset.items():
                logger.info(f"  {key}: {value}")
                
            # Prepare for export
            # Create the exports directory if it doesn't exist
            if not os.path.exists(DEFAULT_EXPORT_DIR):
                os.makedirs(DEFAULT_EXPORT_DIR, exist_ok=True)
                logger.info(f"Created export directory: {DEFAULT_EXPORT_DIR}")
            
            # Generate output filename if not provided
            output_file = args.output
            if not output_file:
                output_file = generate_output_filename(preset['address'], preset.get('internal', False))
                logger.info(f"Auto-generated output filename: {output_file}")
                
            # Create exporter and process transactions
            exporter = ZeroNetworkExporter(base_url=preset.get('api_url', 'https://zero-network.calderaexplorer.xyz/api'))
            
            # Handle date parameters
            start_date = preset.get('start_date')
            end_date = preset.get('end_date')
            no_date_filter = preset.get('no_date_filter', False)
            
            if no_date_filter:
                start_date = None
                end_date = None
                logger.info("Date filtering disabled in preset configuration")
            elif not start_date and not end_date:
                # Use default date range if not specified in preset
                start_date = "2025-02-01"
                end_date = "2025-04-05"
                logger.info(f"Using default date range: {start_date} to {end_date}")
                
            try:
                total_txs = exporter.process_all_pages(
                    address=preset['address'],
                    output_file=output_file,
                    start_page=preset.get('page', 1),
                    max_pages=preset.get('max_pages'),
                    records_per_page=preset.get('records', 100),
                    sort=preset.get('sort', 'asc'),
                    internal=preset.get('internal', False),
                    additional_fields=preset.get('fields'),
                    start_date=start_date,
                    end_date=end_date,
                    token_contract=preset.get('token_contract')
                )
                
                if total_txs > 0:
                    logger.info(f"Successfully exported {total_txs} transactions to {output_file}")
                    # Show recent exports after a successful export
                    show_recent_exports()
                else:
                    logger.warning(f"No transactions found for address {preset['address']}")
                
                return 0
            except Exception as e:
                logger.error(f"Error: {e}")
                if args.verbose:
                    import traceback
                    logger.debug(traceback.format_exc())
                return 1
        
        else:
            logger.error(f"Unknown preset command: {args.preset_command}")
            parser.print_help()
            return 1
    
    # Legacy mode handling already done at the start of the function
        
    # Default to 'export' if no command specified
    if not args.command or args.command == 'export':
        try:
            # Create the exports directory if it doesn't exist
            if not os.path.exists(DEFAULT_EXPORT_DIR):
                os.makedirs(DEFAULT_EXPORT_DIR, exist_ok=True)
                logger.info(f"Created export directory: {DEFAULT_EXPORT_DIR}")
            
            # Process address(es) - either single, multiple, or from file
            addresses = None
            address_label = ""  # For filename and logging
            
            if hasattr(args, 'address') and args.address:
                # Single address mode
                addresses = [args.address]
                address_label = args.address
                logger.info(f"Processing single address: {args.address}")
            
            elif hasattr(args, 'addresses') and args.addresses:
                # Multiple addresses mode
                addresses = args.addresses
                address_label = "batch"
                logger.info(f"Processing {len(addresses)} addresses in batch mode")
                for idx, addr in enumerate(addresses, 1):
                    logger.info(f"  {idx}. {addr}")
            
            elif hasattr(args, 'address_file') and args.address_file:
                # Address file mode
                try:
                    with open(args.address_file, 'r') as f:
                        addresses = [line.strip() for line in f if line.strip() and line.strip().startswith('0x')]
                    address_label = "file"
                    logger.info(f"Loaded {len(addresses)} addresses from file {args.address_file}")
                except Exception as e:
                    logger.error(f"Error loading addresses from file: {e}")
                    return 1
            
            if not addresses:
                logger.error("No valid addresses provided")
                return 1
            
            # Generate output filename if not provided
            output_file = args.output
            if not output_file:
                output_file = generate_output_filename(address_label, args.internal)
                logger.info(f"Auto-generated output filename: {output_file}")
            
            # Create exporter and process transactions
            exporter = ZeroNetworkExporter(base_url=args.api_url)
            # Handle date parameters
            if args.start_date == "":
                args.start_date = None
            if args.end_date == "":
                args.end_date = None
                
            # Special case: "none" means no date filtering
            if args.start_date and args.start_date.lower() == "none":
                args.start_date = None
            if args.end_date and args.end_date.lower() == "none":
                args.end_date = None
                
            # Check if date filtering should be disabled
            if hasattr(args, 'no_date_filter') and args.no_date_filter:
                args.start_date = None
                args.end_date = None
                logger.info("Date filtering disabled with --no-date-filter parameter")
            # Set default date range only if both are None and no explicit override
            elif args.start_date is None and args.end_date is None:
                args.start_date = "2025-02-01"
                args.end_date = "2025-04-05"
                logger.info(f"Using default date range: {args.start_date} to {args.end_date}")
                
            # Process all addresses
            total_txs = exporter.process_all_pages(
                address=addresses,  # Now passing a list of addresses
                output_file=output_file,
                start_page=args.page,
                max_pages=args.max_pages,
                records_per_page=args.records,
                sort=args.sort,
                internal=args.internal,
                additional_fields=args.fields,
                start_date=args.start_date,
                end_date=args.end_date,
                token_contract=args.token_contract if hasattr(args, 'token_contract') else None
            )
            
            if total_txs > 0:
                logger.info(f"Successfully exported {total_txs} transactions to {output_file}")
                # Show recent exports after a successful export
                show_recent_exports()
            else:
                if len(addresses) == 1:
                    logger.warning(f"No transactions found for address {addresses[0]}")
                else:
                    logger.warning(f"No transactions found for any of the {len(addresses)} addresses")
            
        except Exception as e:
            logger.error(f"Error: {e}")
            if args.verbose:
                import traceback
                logger.debug(traceback.format_exc())
            return 1
    else:
        parser.print_help()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
