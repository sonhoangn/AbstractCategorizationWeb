import os
import tempfile
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
    llm_selection = request.form.get('llm')
    return jsonify({'message': 'LLM set successfully', 'llm': llm_selection})

@app.route('/set_api_key', methods=['POST'])
def set_api_key():
    global api_key
    api_key = request.form.get('api_key')
    return jsonify({'message': 'API key set successfully', 'api_key': api_key})

@app.route('/process', methods=['POST'])
def process_data():
    global file_path, api_key, llm_selection
    if not file_path:
        return jsonify({'error': 'No file selected'}), 400
    if not llm_selection:
        return jsonify({'error': 'No LLM selected'}), 400
    if not api_key:
        return jsonify({'error': 'No API key provided'}), 400

    try:
        genai.configure(api_key=api_key)  # Configure Gemini API
        model = genai.GenerativeModel(
                model_name=llm_selection,
                system_instruction="""
                You are an expert in sustainable manufacturing that is excellent with analyzing research paper abstracts. Your primary goal is to categorize the abstracts based on predefined topics and provide specific information in a structured format.
            
                Instructions:
            
                1. Analyze the provided abstract and determine the most appropriate "Overall Category."  This category *must* be chosen from one of the following four predefined topics. Do not create new categories.
                2. Identify the specific "Field of Research" that best describes the abstract. This field *must* be chosen from the sub-topics listed under the chosen "Overall Category." Do not create new sub-topics.
                3. Identify the primary "Research Method" used in the research described in the abstract.  Provide a concise answer (no more than three words).
                4. Assess the "Scope" of the research. Assign a score from 1 to 6 (1 = extremely narrow, 6 = extremely broad).
                5. Determine the "Research Purpose."  Is the research primarily "Theoretical" or "Applied"?
                6. Forecast the "Presentation Time" needed for the topic. Choose either "Brief" (less than 10 minutes) or "Long" (up to 15 minutes).
                7. Provide the "Prompt token count" and "Response token count" for billing and troubleshooting.
            
                Predefined Topics and Sub-topics:
            
                1. Sustainable Materials & Products:
                   - Low carbon materials and critical raw materials
                   - Material recycling
                   - Product design, redesign and innovation
                   - Product recovery, reuse and remanufacturing
                   - Product life cycle, information and knowledge management
                   - Life cycle assessment, risk assessment
                   - Sustainable business models
                   
                2. Sustainable Manufacturing Processes:
                   - Manufacturing processes, tools and equipment
                   - Energy and resource efficiency
                   - Resource utilization and waste reduction
                   - Maintenance, repair and overhaul for machines and equipment
                   
                3. Sustainable Manufacturing Systems:
                   - Manufacturing system design
                   - Simulation tools for manufacturing system design/layout testing
                   - Sustainable supply chain
                   - Data usage and sustainable manufacturing/production planning
                   - Metrics for sustainable manufacturing systems
                   
                4. Crosscutting Topics:
                   - Industry 4.0 and sustainable manufacturing
                   - Circular economy
                   - CO2 neutral production
                   - Regional integration for sustainability
                   - Sustainable energy transition / Sustainable energy development
                   - Policy design for sustainability
                   - Engineering education towards sustainable development
                   - Regional integration of sustainability in South East Asia
            
                Response Format:  (Strictly adhere to this format)
            
                - Overall Category: Category name
                - Field of research: Field name
                - Research methods: Methodology
                - Scope: Score Number between 1 to 6
                - Research Purpose: Theoretical or Applied
                - Forecasted Presentation Time: Brief or Long
                - Prompt token count: Number
                - Response token count: Number
                """) # Your system instruction

        df_results = Main_Functions.input_from_spreadsheet(file_path, model, llm_selection)
        df_r = Main_Functions.session_assignment(df_results)
        df_r["Session No."] = df_r["Refined Grouping"].map(lambda g: Main_Functions.merge_groups(df_r).get(g, g))
        df_r["Session No."] = df_r["Session No."].map({name: f"{i+1}" for i, name in enumerate(df_r["Session No."].unique())})
        if df_results is None:
            return jsonify({'error': 'Error during processing'}), 500

        new_df_path = Main_Functions.write_to_excel(df_r, llm_selection)
        new_df = pd.read_excel(new_df_path)
        df1 = Main_Functions.adjust_session_numbers(new_df)
        df1["Session No."] = df1[['Adjusted Session No.']]
        final_df = df1.sort_values('Session No.')

        with tempfile.NamedTemporaryFile(mode='wb', suffix='.xlsx', delete=False,
                                         dir=app.config['UPLOAD_FOLDER']) as tmp_file:  # Binary mode if needed
            temp_file_path = tmp_file.name

            excel_buffer = io.BytesIO()
            final_df.to_excel(excel_buffer, engine='openpyxl', index=False)
            excel_buffer.seek(0)

            tmp_file.write(excel_buffer.getvalue())  # Write the bytes to the temporary file

        return jsonify({'message': 'Processing complete', 'temp_file_path': temp_file_path, 'llm_selection': llm_selection, 'status': 'success'}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download_file():
    try:
        temp_file_path = request.form.get('temp_file_path')
        llm_selection = request.form.get('llm_selection')

        if not temp_file_path or not llm_selection:
            return jsonify({'error': 'Missing file path or LLM selection'}), 400

        df = pd.read_excel(temp_file_path)

        excel_content = Main_Functions.write_to_excel(df, llm_selection)

        headers = {
            'Content-Disposition': f'attachment; filename="processed_data_{llm_selection}.xlsx"',
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }

        response = send_file(
            io.BytesIO(excel_content),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'processed_data_{llm_selection}.xlsx'
        )
        os.remove(temp_file_path) # Clean up temporary file
        return response

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)