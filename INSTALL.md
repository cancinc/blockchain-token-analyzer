# Installation Instructions

This document provides detailed instructions for installing and setting up the Blockchain Token Transaction Analyzer.

## Dependencies

The following Python packages are required:

```
flask>=2.0.0
gunicorn>=21.0.0
pandas>=1.3.0
matplotlib>=3.4.0
numpy>=1.20.0
requests>=2.25.0
```

## Installation Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/blockchain-token-analyzer.git
   cd blockchain-token-analyzer
   ```

2. Install the required packages:
   ```bash
   pip install flask gunicorn pandas matplotlib numpy requests
   ```

3. Create necessary directories:
   ```bash
   mkdir -p exports
   mkdir -p presets
   mkdir -p yield_data
   ```

## Running the Application

### Web Interface

To start the web application:

```bash
python main.py
```

This will start a Flask development server on port 5000. For production deployment, use Gunicorn:

```bash
gunicorn --bind 0.0.0.0:5000 main:app
```

### Command Line Tool

The command line tool can be used independently:

```bash
python zero_network_exporter.py --help
```

## Configuration

No additional configuration is required for basic operation. The API endpoints and other parameters can be adjusted in the code if needed.

## Troubleshooting

- If you encounter API connection issues, verify your internet connection and check if the Explorer API is online.
- For empty results in Colony Yield Analysis, try using different date ranges or check if the blockchain explorer has data for the specified period.
- If you get Python module errors, ensure all dependencies are correctly installed.