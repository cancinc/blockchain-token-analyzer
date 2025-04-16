import os
import json
import csv
import io
import uuid
import time
import pandas as pd
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file

# Import Colony Yield Analyzer
from colony_yield_analyzer import (
    ColonyYieldAnalyzer, get_yield_analysis_status, 
    update_yield_analysis_status, get_recent_yield_reports, DEFAULT_YIELD_DIR
)

# Import our exporter module
from zero_network_exporter import (
    ZeroNetworkExporter, load_presets, save_preset, delete_preset, 
    get_recent_exports, get_export_status, DEFAULT_EXPORT_DIR
)

# Use the new Caldera Explorer API
API_BASE_URL = 'https://zero-network.calderaexplorer.xyz/api'

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", os.urandom(24))

# Ensure the exports directory exists
os.makedirs(DEFAULT_EXPORT_DIR, exist_ok=True)

@app.route('/')
def home():
    """Home page with dashboard."""
    # Get recent export files
    recent_exports = get_recent_exports(max_files=10)
    
    # Format file data for display
    export_files = []
    for file_path in recent_exports:
        file_size = os.path.getsize(file_path) / 1024  # Size in KB
        mod_time = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
        
        # Get the short name (without directory)
        file_name = os.path.basename(file_path)
        
        # Count rows in CSV
        try:
            with open(file_path, 'r') as f:
                row_count = sum(1 for _ in csv.reader(f)) - 1  # Subtract header row
        except Exception:
            row_count = "Unknown"
        
        export_files.append({
            'path': file_path,
            'name': file_name,
            'size': f"{file_size:.1f} KB",
            'modified': mod_time,
            'rows': row_count
        })
    
    # Load presets for quick export
    presets = load_presets()
    
    return render_template('home.html', export_files=export_files, presets=presets)

@app.route('/export', methods=['GET', 'POST'])
def export():
    """Export data page."""
    if request.method == 'POST':
        # Get form data
        addresses = []
        address_label = ""
        
        # Handle different address input types
        single_address = request.form.get('address')
        addresses_list = request.form.get('addresses_list')  # Comma-separated from textarea
        
        # Check for uploaded file
        if 'address_file' in request.files and request.files['address_file'].filename:
            uploaded_file = request.files['address_file']
            
            try:
                # Read file content
                file_content = uploaded_file.read().decode('utf-8')
                
                # Parse addresses (support both CSV and TXT formats)
                if uploaded_file.filename.endswith('.csv'):
                    # For CSV, try to parse as CSV
                    file_io = io.StringIO(file_content)
                    csv_reader = csv.reader(file_io)
                    # Extract addresses from first column
                    addresses = [row[0].strip() for row in csv_reader if row and row[0].strip()]
                else:
                    # For TXT or other formats, split by lines
                    addresses = [line.strip() for line in file_content.splitlines() if line.strip()]
                
                if addresses:
                    address_label = "batch"
                else:
                    flash("No valid addresses found in uploaded file", "danger")
                    return redirect(url_for('export'))
                    
            except Exception as e:
                flash(f"Error processing address file: {str(e)}", "danger")
                return redirect(url_for('export'))
                
        elif single_address:
            # Single address mode
            addresses = [single_address]
            address_label = single_address[:8] if len(single_address) > 8 else single_address
        elif addresses_list:
            # Multiple addresses mode
            addresses = addresses_list.split(',')
            address_label = "batch"
        else:
            # No valid addresses provided
            flash("At least one valid address is required", "danger")
            return redirect(url_for('export'))
        
        # Other form data
        max_pages = request.form.get('max_pages')
        records = request.form.get('records', 100)
        sort = request.form.get('sort', 'asc')
        internal = request.form.get('internal') == 'on'
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        no_date_filter = request.form.get('no_date_filter') == 'on'
        token_contract = request.form.get('token_contract')
        
        # Convert max_pages to integer if provided
        if max_pages:
            try:
                max_pages = int(max_pages)
            except ValueError:
                max_pages = None
        else:
            max_pages = None
            
        # Generate output filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        tx_type = "internal" if internal else "token"
        filename = f"{DEFAULT_EXPORT_DIR}/tx_{tx_type}_{address_label}_{timestamp}.csv"
        
        # Handle date parameters
        if no_date_filter:
            start_date = None
            end_date = None
        
        # Create a unique job ID for tracking progress
        job_id = str(uuid.uuid4())
        
        # Create exporter and process transactions
        try:
            # Start the export and redirect to status page
            exporter = ZeroNetworkExporter(base_url=API_BASE_URL)
            
            # Start the export in a separate thread to avoid blocking
            from threading import Thread
            export_thread = Thread(target=exporter.process_all_pages, kwargs={
                'address': addresses,
                'output_file': filename,
                'max_pages': max_pages,
                'records_per_page': int(records),
                'sort': sort,
                'internal': internal,
                'start_date': start_date,
                'end_date': end_date,
                'token_contract': token_contract,
                'job_id': job_id
            })
            export_thread.daemon = True
            export_thread.start()
            
            # Redirect to the export status page
            return redirect(url_for('export_status', job_id=job_id))
            
        except Exception as e:
            flash(f"Error exporting data: {str(e)}", "danger")
            return redirect(url_for('export'))
    
    # GET request: show export form
    return render_template('export.html')

@app.route('/presets', methods=['GET', 'POST'])
def presets():
    """Manage presets page."""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'save':
            # Save a new preset
            name = request.form.get('preset_name')
            single_address = request.form.get('address')
            addresses_list = request.form.get('addresses_list')  # Handle multiple addresses
            
            # Determine addresses to save
            addresses = None
            if single_address:
                addresses = single_address
            elif addresses_list:
                # Store as list for multiple addresses
                addresses = addresses_list.split(',')
                if len(addresses) == 1:
                    # If only one address, store as string for backwards compatibility
                    addresses = addresses[0]
            else:
                flash("Preset name and at least one address are required", "danger")
                return redirect(url_for('presets'))
                
            # Build preset config
            config = {
                'address': addresses,
                'max_pages': int(request.form.get('max_pages')) if request.form.get('max_pages') else None,
                'records': int(request.form.get('records', 100)),
                'sort': request.form.get('sort', 'asc'),
                'internal': request.form.get('internal') == 'on',
                'fields': None,  # Not implementing field selection in the web UI for now
                'token_contract': request.form.get('token_contract')
            }
            
            # Handle date filters
            if request.form.get('no_date_filter') == 'on':
                config['no_date_filter'] = True
            else:
                if request.form.get('start_date'):
                    config['start_date'] = request.form.get('start_date')
                if request.form.get('end_date'):
                    config['end_date'] = request.form.get('end_date')
            
            # Save the preset
            if save_preset(name, config):
                flash(f"Preset '{name}' saved successfully", "success")
            else:
                flash(f"Error saving preset '{name}'", "danger")
                
        elif action == 'delete':
            # Delete a preset
            name = request.form.get('preset_name')
            
            if delete_preset(name):
                flash(f"Preset '{name}' deleted successfully", "success")
            else:
                flash(f"Error deleting preset '{name}'", "danger")
        
        return redirect(url_for('presets'))
    
    # GET request: show presets management
    presets = load_presets()
    return render_template('presets.html', presets=presets)

@app.route('/view/<path:file_path>')
def view_export(file_path):
    """View an export file."""
    try:
        # Read the CSV file
        rows = []
        
        with open(file_path, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)  # Read headers
            
            # Read rows (limit to 100 for performance)
            count = 0
            for row in reader:
                rows.append(row)
                count += 1
                if count >= 100:
                    break
        
        # Get file metadata
        file_size = os.path.getsize(file_path) / 1024  # Size in KB
        mod_time = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
        
        # Count total rows in CSV
        with open(file_path, 'r') as f:
            total_rows = sum(1 for _ in csv.reader(f)) - 1  # Subtract header row
            
        file_info = {
            'path': file_path,
            'name': os.path.basename(file_path),
            'size': f"{file_size:.1f} KB",
            'modified': mod_time,
            'rows': total_rows,
            'showing_rows': len(rows)
        }
            
        return render_template('view.html', file_info=file_info, headers=headers, rows=rows)
        
    except Exception as e:
        flash(f"Error viewing file: {str(e)}", "danger")
        return redirect(url_for('home'))

@app.route('/download/<path:file_path>')
def download_export(file_path):
    """Download an export file."""
    try:
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        flash(f"Error downloading file: {str(e)}", "danger")
        return redirect(url_for('home'))

@app.route('/run_preset/<name>')
def run_preset(name):
    """Run a saved export preset."""
    presets = load_presets()
    
    if name not in presets:
        flash(f"Preset '{name}' not found", "danger")
        return redirect(url_for('home'))
    
    preset = presets[name]
    
    # Process address(es) - ensure it's always a list
    addresses = []
    address_label = ""
    
    if isinstance(preset['address'], list):
        # Already a list
        addresses = preset['address']
        address_label = "batch"
    else:
        # Convert to list
        addresses = [preset['address']]
        address_label = preset['address'][:8] if len(preset['address']) > 8 else preset['address']
    
    # Generate output filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    tx_type = "internal" if preset.get('internal', False) else "token"
    filename = f"{DEFAULT_EXPORT_DIR}/tx_{tx_type}_{address_label}_{timestamp}.csv"
    
    # Handle date parameters
    start_date = preset.get('start_date')
    end_date = preset.get('end_date')
    no_date_filter = preset.get('no_date_filter', False)
    
    if no_date_filter:
        start_date = None
        end_date = None
    
    # Create a unique job ID for tracking progress
    job_id = str(uuid.uuid4())
    
    # Create exporter and process transactions
    try:
        # Start the export and redirect to status page
        exporter = ZeroNetworkExporter(base_url=API_BASE_URL)
        
        # Start the export in a separate thread to avoid blocking
        from threading import Thread
        export_thread = Thread(target=exporter.process_all_pages, kwargs={
            'address': addresses,
            'output_file': filename,
            'start_page': preset.get('page', 1),
            'max_pages': preset.get('max_pages'),
            'records_per_page': preset.get('records', 100),
            'sort': preset.get('sort', 'asc'),
            'internal': preset.get('internal', False),
            'additional_fields': preset.get('fields'),
            'start_date': start_date,
            'end_date': end_date,
            'token_contract': preset.get('token_contract'),
            'job_id': job_id
        })
        export_thread.daemon = True
        export_thread.start()
        
        # Redirect to the export status page
        return redirect(url_for('export_status', job_id=job_id))
            
    except Exception as e:
        flash(f"Error running preset '{name}': {str(e)}", "danger")
        return redirect(url_for('home'))

@app.route('/export_status/<job_id>')
def export_status(job_id):
    """Show export status page with progress bar."""
    return render_template('export_status.html', job_id=job_id)

@app.route('/api/export_status/<job_id>')
def api_export_status(job_id):
    """API endpoint to get the current export status."""
    status = get_export_status()
    
    # Check if the job ID matches
    if status.get('job_id') != job_id:
        # Check if a file has been created for this job
        recent_files = get_recent_exports(max_files=10)
        for file_path in recent_files:
            # If this is a very recent file (created in the last 5 minutes)
            if time.time() - os.path.getmtime(file_path) < 300:  # 5 minutes in seconds
                # Return completed status with the file
                return jsonify({
                    'job_id': job_id,
                    'status': 'completed',
                    'progress': 100,
                    'output_file': file_path,
                    'total_transactions': 'Unknown',  # We don't know this anymore
                    'processed_addresses': 1,
                    'total_addresses': 1
                })
                
        # If no recent file found, the job might be genuinely not found
        return jsonify({
            'error': 'Job not found or completed',
            'status': 'unknown'
        }), 404
    
    return jsonify(status)

@app.route('/yield', methods=['GET', 'POST'])
def yield_analysis():
    """Colony coin yield analysis page."""
    # Create directories if needed
    os.makedirs(DEFAULT_YIELD_DIR, exist_ok=True)
    
    # Initialize variables
    chart_image = None
    yield_data = []
    report = {}
    stats = {}
    window_days = 7
    
    if request.method == 'POST':
        # Get form data
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        window_days = int(request.form.get('window_days', 7))
        chart_type = request.form.get('chart_type', 'line')
        
        # Create a unique job ID for tracking progress
        job_id = str(uuid.uuid4())
        
        try:
            # Initialize analyzer
            analyzer = ColonyYieldAnalyzer(window_days=window_days)
            
            # Generate the report
            report = analyzer.generate_yield_report(
                start_date=start_date,
                end_date=end_date,
                window_days=window_days,
                job_id=job_id
            )
            
            # Load the data
            if report and report.get('output_file'):
                try:
                    df = pd.read_csv(report['output_file'])
                    yield_data = df.to_dict('records')
                    
                    # Generate chart
                    chart_image = analyzer.generate_yield_chart(df, chart_type=chart_type)
                    
                    # Get statistics
                    stats = report.get('statistics', {})
                    
                    # Check if we actually got data
                    if not df.empty:
                        flash("Yield analysis completed successfully", "success")
                    else:
                        flash("The API returned no data for the selected date range. This may be because the Colony coin contract " +
                              "does not have transactions in the specified period, or the blockchain explorer's API has limited " +
                              "historical data. Try using a different date range or check the contract address.", "warning")
                except Exception as e:
                    flash(f"Error processing yield data: {str(e)}", "danger")
        except Exception as e:
            flash(f"Error analyzing yield data: {str(e)}", "danger")
    
    # Get recent reports for display
    recent_reports = []
    report_files = get_recent_yield_reports(max_files=5)
    
    for file_path in report_files:
        file_size = os.path.getsize(file_path) / 1024  # Size in KB
        mod_time = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
        file_name = os.path.basename(file_path)
        
        recent_reports.append({
            'path': file_path,
            'name': file_name,
            'size': f"{file_size:.1f} KB",
            'modified': mod_time
        })
    
    return render_template('yield.html', 
                         chart_image=chart_image, 
                         yield_data=yield_data,
                         stats=stats,
                         report=report,
                         window_days=window_days,
                         recent_reports=recent_reports)

@app.route('/view_yield/<path:file_path>')
def view_yield_report(file_path):
    """View a yield report file."""
    try:
        # Read the CSV file
        df = pd.read_csv(file_path)
        yield_data = df.to_dict('records')
        
        # Determine window days from filename or set default
        window_days = 7
        filename = os.path.basename(file_path)
        
        # Get file metadata
        file_size = os.path.getsize(file_path) / 1024  # Size in KB
        mod_time = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
        
        # Initialize analyzer
        analyzer = ColonyYieldAnalyzer(window_days=window_days)
        
        # Generate chart
        chart_image = analyzer.generate_yield_chart(df, chart_type='both')
        
        # Calculate statistics
        stats = {}
        if not df.empty:
            stats = {
                "date_range": {
                    "start": df["date"].min(),
                    "end": df["date"].max()
                },
                "yield_stats": {
                    "mean_daily": df["amount"].mean(),
                    "max_daily": df["amount"].max(),
                    "min_daily": df["amount"].min(),
                    "total_amount": df["amount"].sum(),
                    "latest_daily": float(df["amount"].iloc[-1]) if len(df) > 0 else 0,
                    "latest_ma": float(df["moving_avg"].iloc[-1]) if len(df) > 0 else 0
                },
                "total_transfers": len(df)
            }
            
        report = {
            "output_file": file_path
        }
        
        return render_template('yield.html', 
                             chart_image=chart_image, 
                             yield_data=yield_data,
                             stats=stats,
                             report=report,
                             window_days=window_days,
                             recent_reports=[])
                             
    except Exception as e:
        flash(f"Error viewing yield report: {str(e)}", "danger")
        return redirect(url_for('yield_analysis'))

@app.route('/download_yield/<path:file_path>')
def download_yield_report(file_path):
    """Download a yield report file."""
    try:
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        flash(f"Error downloading yield report: {str(e)}", "danger")
        return redirect(url_for('yield_analysis'))

@app.route('/about')
def about():
    """About page."""
    return render_template('about.html')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)