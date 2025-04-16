# Blockchain Token Transaction Analyzer

A robust tool for comprehensive blockchain token transaction analysis, featuring advanced ERC-721 NFT token export capabilities and yield analysis functionality. This project includes both a command-line interface and a web application for easy interaction with blockchain data.

## Features

- Fetch token transactions from Zero Network Explorer API
- Process and format transaction data 
- Export transactions to CSV with customizable fields
- Automatic pagination for retrieving large transaction sets
- Automatic ERC-721 NFT detection and specialized handling
- Multiple address batch processing for comprehensive analysis
- Colony Yield Analysis for calculating CLNY token yield rates
- Data visualization with charts and statistical analysis
- Proper error handling and user feedback
- Command-line interface with subcommands
- Web interface for easy export management and data visualization
- Auto-generated timestamped filenames
- Directory management for exports
- Recent files tracking
- Date range filtering for transactions
- Export configuration presets management
- Real-time progress tracking for long-running operations

## Requirements

- Python 3.6+
- Required Python Packages:
  - Flask: Web application framework
  - Requests: For API communication
  - Pandas: Data processing and analysis
  - Matplotlib: Visualization and charting
  - NumPy: Numerical computation
  - Gunicorn: Production web server (optional for deployment)

This project uses a requirements.txt file to manage dependencies.

## Usage

### Export Transactions

```bash
# Basic usage with auto-generated filename
python zero_network_exporter.py export 0xYourAddressHere

# Specify output file
python zero_network_exporter.py export 0xYourAddressHere -o custom_filename.csv

# Limit to 3 pages
python zero_network_exporter.py export 0xYourAddressHere -m 3

# Enable verbose logging
python zero_network_exporter.py export 0xYourAddressHere -v

# Fetch internal transactions
python zero_network_exporter.py export 0xYourAddressHere -i

# Filter by date range (format: YYYY-MM-DD)
python zero_network_exporter.py export 0xYourAddressHere --start-date 2025-02-01 --end-date 2025-04-05

# Disable date filtering completely
python zero_network_exporter.py export 0xYourAddressHere --no-date-filter
```

### List Recent Export Files

```bash
# List the 5 most recent export files
python zero_network_exporter.py recent

# List more recent files
python zero_network_exporter.py recent -n 10

# Enable verbose logging
python zero_network_exporter.py recent -v
```

### Legacy Mode

The script also supports the original command-line interface for backward compatibility:

```bash
# Legacy mode examples
python zero_network_exporter.py 0xYourAddressHere

# With legacy mode options
python zero_network_exporter.py 0xYourAddressHere -m 2 -v
python zero_network_exporter.py 0xYourAddressHere -o my_transactions.csv -i

# With date filtering in legacy mode
python zero_network_exporter.py 0xYourAddressHere --start-date 2025-02-01 --end-date 2025-04-05

# Disable date filtering in legacy mode
python zero_network_exporter.py 0xYourAddressHere --no-date-filter
python zero_network_exporter.py 0xYourAddressHere --start-date 2025-02-01 --end-date 2025-04-05
```

## Date Filtering

By default, when no date range is specified, the script will filter transactions between February 1, 2025 and April 5, 2025. You can override this behavior by specifying your own date range:

```bash
# Custom date range
python zero_network_exporter.py export 0xYourAddressHere --start-date 2025-01-01 --end-date 2025-03-15
```

## Output

By default, exports are saved to the `exports/` directory with auto-generated filenames that include:
- Transaction type (token or internal)
- Short address identifier
- Timestamp

Example: `exports/tx_token_0x1234567_20250406_152030.csv`

### Preset Management

Save common export configurations as presets for easy reuse:

```bash
# Save a preset for a specific address (required)
python zero_network_exporter.py preset save default_contract -a 0x00b1cA2C150920F4cA57701452c63B1bA2b4b758

# Save a preset with date filtering
python zero_network_exporter.py preset save march_data -a 0x00b1cA2C150920F4cA57701452c63B1bA2b4b758 --start-date 2025-03-01 --end-date 2025-03-31

# Save a preset with no date filtering
python zero_network_exporter.py preset save all_data -a 0x00b1cA2C150920F4cA57701452c63B1bA2b4b758 --no-date-filter

# List all available presets
python zero_network_exporter.py preset list

# Use a saved preset for export
python zero_network_exporter.py preset use default_contract

# Use a preset with a custom output filename
python zero_network_exporter.py preset use march_data -o march_transactions.csv

# Delete a preset
python zero_network_exporter.py preset delete preset_name
```

## Web Interface

The application includes a web interface for easier interaction, especially on mobile devices:

```bash
# Run the web interface
python main.py
```

This starts a Flask web server on port 5000. Access the interface at http://localhost:5000 or through your Replit domain.

### Web Interface Features

- **Dashboard**: View recent exports and quick access to presets
- **New Export**: Create a new export with a user-friendly form
- **Presets Management**: Create, view, run, and delete export presets
- **Export Viewer**: View and analyze exported transaction data directly in the browser
- **Colony Yield Analysis**: Calculate and visualize CLNY token yield rates
- **Download**: Download CSV files for offline analysis

## Colony Yield Analysis

The tool includes a specialized module for analyzing the daily yield rate of the Colony (CLNY) token. This helps in understanding token distribution patterns and predicting future yield rates.

### Using the Web Interface

1. Navigate to the "Colony Yield" tab in the web interface
2. Select a date range for analysis
3. Choose a window size for the moving average (default: 7 days)
4. Run the analysis to generate a report
5. View the generated chart and statistical data
6. Download the CSV file for further analysis

### Using the Command Line

You can also run the yield analysis directly from the command line:

```bash
# Run a basic yield analysis
python colony_yield_analyzer.py

# Specify a date range
python colony_yield_analyzer.py --start-date 2025-01-01 --end-date 2025-04-01

# Customize the moving average window
python colony_yield_analyzer.py --window-days 14
```

### Output

The yield analysis generates:
- CSV files with daily yield data
- Statistical analysis of yield patterns
- Visualization charts with daily yields and moving averages
- Calculation of day-over-day and week-over-week changes

Files are saved to the `yield_data/` directory with timestamped filenames.

## Notes for Replit Users

- When running on Replit, you can access the script directly from the Replit console or mobile app
- For the best experience on mobile, use the web interface by running `python main.py`
- The command-line `recent` command is particularly useful when accessing from the mobile app to quickly view and access your exported files
- All exports are stored persistently in the Replit storage, allowing you to access them between sessions
- Presets are stored in the `presets/export_presets.json` file and are accessible between Replit sessions
