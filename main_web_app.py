import os

from flask import Flask, request, jsonify, render_template
import Main_Functions
import Adjust_Session_Function

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
        Main_Functions.main(file_path, llm_selection, api_key) # Call main processing function
        return jsonify({'message': 'Processing complete'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# @app.route('/refine', methods=['POST'])
# def refine_data():
#     try:
#         Adjust_Session_Function.main()  # Call refine function
#         return jsonify({'message': 'Refinement complete'}), 200
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080) # Port 8080 for Cloud Run