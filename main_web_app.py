import os
from flask import Flask, request, jsonify, render_template, send_file, render_template_string
import io
import pandas as pd
import Main_Functions
import traceback
import google.generativeai as genai

app = Flask(__name__)

file_path = None
llm_selection = None
api_key = None

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/upload_file', methods=['POST'])
def upload_file():
    global file_path
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)
    return jsonify({'message': 'File uploaded successfully', 'file_path': file_path})

@app.route('/set_llm', methods=['POST'])
def set_llm():
    global llm_selection
    llm_selection = request.form.get('llm') # Get LLM selection from the form
    return jsonify({'message': 'LLM set successfully', 'llm': llm_selection})

@app.route('/set_api_key', methods=['POST'])
def set_api_key():
    global api_key
    api_key = request.form.get('api_key') # Get API key from the form
    return jsonify({'message': 'API key set successfully', 'api_key': api_key})

@app.route('/process', methods=['POST'])
def process_data():
    global file_path
    if not file_path:
        return jsonify({'error': 'No file selected'}), 400
    if not llm_selection:
        return jsonify({'error': 'No LLM selected'}), 400
    if not api_key:
        return jsonify({'error': 'No API key provided'}), 400
    print(f"File path passed to Main_Functions.main: {file_path}")
    try:
        # Initialize the model here, same as in Main_Functions.main
        genai.configure(api_key=api_key)  # Use the global api_key
        model = genai.GenerativeModel(
            model_name=llm_selection,  # Use the global llm_selection
            system_instruction=""" ... """  # Your system instruction
        )
        df_results = Main_Functions.input_from_spreadsheet(file_path, model, llm_selection)
        df_r = Main_Functions.session_assignment(df_results)
        df_r["Session No."] = df_r["Refined Grouping"].map(lambda g: Main_Functions.merge_groups(df_r).get(g, g))
        df_r["Session No."] = df_r["Session No."].map(
            {name: f"{i + 1}" for i, name in enumerate(df_r["Session No."].unique())})
        if df_results is None:
            return jsonify({'error': 'Error during processing'}), 500

        new_df_path = Main_Functions.write_to_excel(df_r, file_path, llm_selection)
        new_df = pd.read_excel(new_df_path)
        df1 = Main_Functions.adjust_session_numbers(new_df)
        df1["Session No."] = df1[['Adjusted Session No.']]
        final_df = df1.sort_values('Session No.')

        html_content = Main_Functions.browser_display(final_df, llm_selection)  # Get HTML string
        return render_template_string(html_content)
    except Exception as e:
        traceback.print_exc() # Print the traceback for debugging
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])  # Use POST for sending file path in body
def download_file():
    try:
        file_path = request.form.get('file_path') # Get file path from POST request body
        if not file_path:
            return jsonify({'error': 'No file path provided'}), 400

        # Load the Excel file
        df = pd.read_excel(file_path)

        # Create in-memory Excel file
        output = io.BytesIO()
        df.to_excel(output, engine='openpyxl', index=False)  # Write to in-memory Excel file, no index
        output.seek(0)

        # Set HTTP headers for download
        headers = {
            'Content-Disposition': 'attachment; filename="processed_data.xlsx"',
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='processed_data.xlsx'  # Or make this dynamic
        )
    except Exception as e:
        print(f"Error in download route: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080) # Port 8080 for Cloud Run