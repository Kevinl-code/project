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
from matplotlib.backends.backend_pdf import PdfPages  # Add this import


# Use 'Agg' backend to prevent GUI-related errors
matplotlib.use('Agg')

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# SQLite Database Configuration
DATABASE_PATH = "lazarus.db"
CHARTS_FOLDER = "static/charts"
os.makedirs(CHARTS_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        file = request.files['file']
        table_name = request.form['table_name']

        if not file or not table_name:
            return jsonify({"success": False, "message": "Please provide both file and table name."}), 400

        df = pd.read_excel(file)
        schema = {}
        check_constraints = {}

        for col in df.columns:
            dtype = str(df[col].dtype)
            if dtype.startswith("int"):
                schema[col] = "INT"
            elif dtype.startswith("float"):
                schema[col] = "REAL"
            else:
                schema[col] = "TEXT"

            unique_values = df[col].dropna().unique()
            if len(unique_values) <= 10:
                check_constraints[col] = [str(val) for val in unique_values]

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        column_definitions = []
        for col, dtype in schema.items():
            if col in check_constraints:
                allowed_values = "', '".join(val.replace("'", "''") for val in check_constraints[col])
                column_definition = f'"{col}" {dtype} CHECK("{col}" IN (\'{allowed_values}\'))'
            else:
                column_definition = f'"{col}" {dtype}'
            column_definitions.append(column_definition)

        create_table_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(column_definitions)})'
        cursor.execute(create_table_sql)

        df.to_sql(table_name, conn, if_exists='append', index=False)

        conn.commit()
        conn.close()

        return jsonify({"success": True, "message": "Data imported successfully!"})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/get_tables', methods=['GET'])
def get_tables():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return jsonify({"success": True, "tables": tables})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

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
        color = data['color']
        show_grid = data.get('show_grid', True)

        conn = sqlite3.connect(DATABASE_PATH)
        query = f"SELECT {x_axis}, {y_axis} FROM {table_name}"
        if year:
            query += f" WHERE year = '{year}'"

        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            return jsonify({"success": False, "message": "No data available for the selected criteria."})

        # 🔹 Handle missing values
        df.dropna(subset=[x_axis, y_axis], inplace=True)

        # 🔹 Ensure categorical data is handled correctly
        df[x_axis] = df[x_axis].astype(str)
        df[y_axis] = df[y_axis].astype(str)

        plt.figure(figsize=(10, 6))

        # 🔹 Generate Chart
        if chart_type == "bar":
            df_counts = df.groupby([x_axis, y_axis]).size().reset_index(name='count')
            df_pivot = df_counts.pivot(index=x_axis, columns=y_axis, values='count').fillna(0)
            df_pivot.plot(kind='bar', color=color, ax=plt.gca())

        elif chart_type == "line":
            df_counts = df.groupby([x_axis, y_axis]).size().reset_index(name='count')
            df_pivot = df_counts.pivot(index=x_axis, columns=y_axis, values='count').fillna(0)
            df_pivot.plot(kind='line', marker='o', color=color, ax=plt.gca())

        elif chart_type == "pie":
            df_pie = df[y_axis].value_counts()
            df_pie.plot(kind='pie', autopct='%1.1f%%', colors=[color], ax=plt.gca())

        if show_grid:
            plt.grid(True)

        plt.xlabel(x_axis)
        plt.ylabel(y_axis)
        #plt.title(f"{chart_type.capitalize()} Chart of {y_axis} vs {x_axis}")

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
