from flask import Flask, render_template, request, jsonify
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from werkzeug.utils import secure_filename
import os
import matplotlib
import shutil
import zipfile
import subprocess
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np   # Add this import
# Use 'Agg' backend to prevent GUI-related errors
matplotlib.use('Agg')
app = Flask(__name__)
app.secret_key = 'your_secret_key'
# SQLite Database Configuration
DATABASE_PATH = "lazarus.db"
CHARTS_FOLDER = "static/charts"
os.makedirs(CHARTS_FOLDER, exist_ok=True)
@app.route('/')
def dashboard():
    return render_template('dashboard.html')
@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        file = request.files['file']
        filename = secure_filename(file.filename)
        if not file:
            return jsonify({"success": False, "message": "No file uploaded."}), 400
        # 🔹 Mapping file names to pre-existing SQLite tables
        table_mapping = {
            "PS1.xlsx": "sheet1",
            "PS2.xlsx": "sheet2",
            "PS3.xlsx": "sheet3"
        }
        table_name = table_mapping.get(filename)
        if not table_name:
            return jsonify({"success": False, "message": "Invalid file name. Use PS1.xlsx, PS2.xlsx, or PS3.xlsx."}), 400
        df = pd.read_excel(file)
        # 🔹 Connect to SQLite database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        # 🔹 Ensure table exists
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cursor.fetchone():
            return jsonify({"success": False, "message": f"Table {table_name} does not exist."}), 400
        # 🔹 Insert only new data (Avoid Duplicates)
        existing_data = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
        new_data = df[~df.apply(tuple, axis=1).isin(existing_data.apply(tuple, axis=1))]
        if new_data.empty:
            return jsonify({"success": False, "message": "No new data to insert."}), 200
        # Append new data
        new_data.to_sql(table_name, conn, if_exists='append', index=False)
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": f"Data uploaded to {table_name} successfully!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
@app.route('/get_tables', methods=['GET'])
def get_tables():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'AND name NOT LIKE 'sqlite_sequence';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return jsonify({"success": True, "tables": tables})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
@app.route('/get_tables', methods=['GET'])
def fetch_tables():
    tables = get_tables()
    return jsonify({"success": True, "tables": tables})
@app.route('/get_columns', methods=['POST'])
def get_columns():
    try:
        table_name = request.json.get('table_name')
        if not table_name:
            return jsonify({"success": False, "message": "Table name is required."}), 400
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        table_check = cursor.fetchone()
        if not table_check:
            return jsonify({"success": False, "message": "Table does not exist."}), 404
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        year_column = next((col for col in columns if "year" in col.lower()), None)
        years = []
        if year_column:
            cursor.execute(f"SELECT DISTINCT {year_column} FROM {table_name} ORDER BY {year_column} ASC")
            years = [row[0] for row in cursor.fetchall() if row[0] is not None]
        conn.close()
        return jsonify({"success": True, "columns": columns, "year_column": year_column, "years": years})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error fetching columns: {str(e)}"}), 500
        
@app.route('/generate_chart', methods=['POST'])
def generate_chart():
    try:
        data = request.json
        table_name = data['table_name']
        year = data.get('year', None)
        chart_type = data['chart_type']
        x_axis = data['x_axis']
        y_axis = data['y_axis']
        show_grid = data.get('show_grid', True)

        conn = sqlite3.connect(DATABASE_PATH)
        query = f"SELECT {x_axis}, {y_axis} FROM {table_name}"
        if year:
            query += f" WHERE year = '{year}'"
        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            return jsonify({"success": False, "message": "No data available for the selected criteria."})

        df.dropna(subset=[x_axis, y_axis], inplace=True)
        df[x_axis] = df[x_axis].astype(str)
        df[y_axis] = df[y_axis].astype(str)

        plt.figure(figsize=(10, 6))

        unique_labels = df[y_axis].unique()
        colors = plt.cm.get_cmap("tab10", len(unique_labels)).colors  # Generate distinct colors
        color_map = {label: colors[i] for i, label in enumerate(unique_labels)}

        if chart_type == "bar":
            df_counts = df.groupby([x_axis, y_axis]).size().reset_index(name='count')
            df_pivot = df_counts.pivot(index=x_axis, columns=y_axis, values='count').fillna(0)
            ax = df_pivot.plot(kind='bar', color=[color_map[col] for col in df_pivot.columns], ax=plt.gca())
            for container in ax.containers:
                ax.bar_label(container, label_type='edge', fontsize=10)

        elif chart_type == "line":
            df_counts = df.groupby([x_axis, y_axis]).size().reset_index(name='count')
            df_pivot = df_counts.pivot(index=x_axis, columns=y_axis, values='count').fillna(0)
            ax = df_pivot.plot(kind='line', marker='o', color=[color_map[col] for col in df_pivot.columns], ax=plt.gca())
            for line in ax.lines:
                for x, y, label in zip(line.get_xdata(), line.get_ydata(), df_pivot.index):
                    ax.annotate(f'{label}: {int(y)}', (x, y), textcoords="offset points", xytext=(0, 5), ha='center', fontsize=10, fontweight='bold')

        elif chart_type == "pie":
            df_pie = df[y_axis].value_counts()
            wedges, texts, autotexts = plt.pie(df_pie, labels=[f'{index}: {value}' for index, value in df_pie.items()], autopct=lambda p: f'{int(p*sum(df_pie)/100)}\n({p:.1f}%)', colors=[color_map[label] for label in df_pie.index])
            for autotext in autotexts:
                autotext.set_fontsize(10)
                autotext.set_weight('bold')

        if show_grid:
            plt.grid(True)
        plt.xlabel(x_axis)
        plt.ylabel(y_axis)

        chart_path = os.path.join(CHARTS_FOLDER, "chart.png")
        plt.savefig(chart_path)
        plt.close()

        return jsonify({"success": True, "chart_url": f"/{chart_path}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/export', methods=['POST'])
def export_chart():
    try:
        export_type = request.form.get('export_type').lower()  # 'png' or 'pdf'
        file_name = request.form.get('file_name')  # Example: 'my_chart'
        file_location = request.form.get('file_location')  # Example: '/path/to/save'
        if not export_type or not file_name or not file_location:
            return jsonify({'success': False, 'message': 'Missing required fields.'})
        source_path = os.path.join(CHARTS_FOLDER, "chart.png")  # The generated chart
        export_path = os.path.join(file_location, f"{file_name}.{export_type}")
        if not os.path.exists(source_path):
            return jsonify({'success': False, 'message': 'No chart found. Generate a chart first.'})
        if export_type == "png":
            shutil.copy(source_path, export_path)  # Copy PNG directly
        elif export_type == "pdf":
            with PdfPages(export_path) as pdf:
                img = plt.imread(source_path)  # Read the PNG image
                plt.figure(figsize=(10, 6))
                plt.imshow(img)
                plt.axis('off')  # Hide axis
                pdf.savefig()  # Save as PDF
                plt.close()
        else:
            return jsonify({'success': False, 'message': 'Unsupported export format. Use PNG or PDF.'})
        return jsonify({'success': True, 'message': f'Exported successfully as {export_type.upper()}', 'location': export_path})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
@app.route('/select_folder', methods=['POST'])
def select_folder():
    try:
        result = subprocess.run(['python', 'select_folder_helper.py'], capture_output=True, text=True)
        folder_path = result.stdout.strip()
        if folder_path and folder_path != "No folder selected.":
            return jsonify({'folder_path': folder_path})
        else:
            error_message = result.stderr.strip() or "No folder selected."
            return jsonify({'folder_path': None, 'error': error_message})
    except Exception as e:
        return jsonify({'folder_path': None, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, threaded=False)  # Disable threading to prevent socket errors