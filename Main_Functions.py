import datetime
import os
import time
import io
import webbrowser
from collections import defaultdict
from pathlib import Path
import traceback
import google.generativeai as genai
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

# Define output path and check whether output path already existed in the target directory
RESULTS_PATH = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "results")))
print(f"RESULTS_PATH: {RESULTS_PATH}")
os.makedirs(RESULTS_PATH, exist_ok=True)

# Define current running time
def ct():
    crtm = datetime.datetime.now()
    return crtm.strftime("%Y-%m-%d %H:%M:%S")

# Define method to categorize abstract
def categorize_abstract(index, abstract, model):
    # Setting up prompt
    prompt = f"""
    Paper index:
    {index}
    Abstract:
    {abstract}
    """
    # Configure generative ai response
    response = model.generate_content(prompt)
    print(f"{ct()} - Response for Abstract No. {index} provided. Analyzing...\n")
    # Find the best fit overall category name from the response
    line1 = [line for line in response.text.split("\n") if line.startswith("- Overall Category: ")]
    if line1:
        overall_category = line1[0].split(": ")[1].strip()
    else:
        overall_category = "N/A"
    # Find the best fit topic name from the response
    line2 = [line for line in response.text.split("\n") if line.startswith("- Field of research: ")]
    if line2:
        research_field = line2[0].split(": ")[1].strip()
    else:
        research_field = "N/A"
    # Find the best fit research method name from the response
    line3 = [line for line in response.text.split("\n") if line.startswith("- Research methods: ")]
    if line3:
        research_method = line3[0].split(": ")[1].strip()
    else:
        research_method = "N/A"
    # Define Scope level
    line4 = [line for line in response.text.split("\n") if line.startswith("- Scope: ")]
    if line4:
        scope = line4[0].split(": ")[1].strip()
    else:
        scope = "N/A"
    # Distinguish whether the target paper is a theoretical or applied one
    line5 = [line for line in response.text.split("\n") if line.startswith("- Research Purpose: ")]
    if line5:
        purpose = line5[0].split(": ")[1].strip()
    else:
        purpose = "N/A"
    # Forecast presentation duration needed for the abstract
    line6 = [line for line in response.text.split("\n") if line.startswith("- Forecasted Presentation Time: ")]
    if line6:
        forecasted_time = line6[0].split(": ")[1].strip()
    else:
        forecasted_time = "N/A"
    # Get token count
    prompt_tokens = str(model.count_tokens(prompt)).split(": ")[1].strip()
    response_tokens = str(model.count_tokens(response.text)).split(": ")[1].strip()
    # Return values from method
    print(f"{ct()} - Abstract No. {index} finishes preliminary categorization...\n")
    return overall_category, research_field, research_method, scope, purpose, forecasted_time, prompt_tokens, response_tokens

# Session Assignment
def session_assignment(df):
    # Initial Grouping based on identical Topics
    df['Grouping'] = df.groupby('Topic').ngroup() + 1
    # Count items per Grouping, "Topic" column is selected as reference
    df["Count"] = df.groupby("Grouping")["Topic"].transform("count")
    # Initialize a new column for refined grouping, this temp. column will not show up in the result
    df["Refined Grouping"] = ""
    refined_groups = []
    for group, subset in df.groupby("Grouping"):
        if len(subset) <= 6:
            refined_groups.extend([group] * len(subset))
        else:
            # Create smaller groups, using an index-based suffix
            for i, (_, row) in enumerate(subset.iterrows()):
                refined_groups.append(f"{group}_{i // 6 + 1}")
    # Assigned refined group naming to the temp. column
    df["Refined Grouping"] = refined_groups
    # Return the data frame containing the temp. refined grouping column
    return df

# Merge smaller groups into groups of 6 based on their identical Overall Category
def merge_groups(df):
    # Count items per refined group
    group_counts = df.groupby("Refined Grouping").size()
    # Identify small groups of less than 6 row items
    small_groups = {g: df[df["Grouping"] == g] for g, size in group_counts.items() if size < 6}
    # Mapping "Overall Category" to small groups
    category_to_groups = defaultdict(set)
    for group, rows in small_groups.items():
        unique_categories = rows["Overall Category"].unique()
        for category in unique_categories:
            category_to_groups[category].add(group)
    # Merge small groups into exactly 6-row groups
    merged_groups = {}
    # Track assigned group
    assigned = set()
    # New Group assignment counter
    new_group_id = 1
    for group, rows in small_groups.items():
        if group is assigned:
            continue
        # Start a new merged group
        current_merge = [group]
        assigned.add(group)
        # Find potential merge partners
        for category in rows["Overall Category"].unique():
            possible_partners = category_to_groups[category] - set(current_merge) - assigned
            for partner in possible_partners:
                if len(df[df["Grouping"].isin(current_merge)]) + len(df[df["Grouping"] == partner]) <= 6:
                    current_merge.append(partner)
                    assigned.add(partner)
                # Stop merging if exactly 6 rows are reached
                if len(df[df["Grouping"].isin(current_merge)]) == 6:
                    break
            if len(df[df["Grouping"].isin(current_merge)]) == 6:
                break
        # Assigned new ID for merged group
        for g in current_merge:
            merged_groups[g] = f"Merged_{new_group_id}"
        new_group_id += 1
    return merged_groups

# Adjust Session No.
def adjust_session_numbers(df):
    df["Adjusted Session No."] = df["Session No."]  # Start by copying original values

    # Step 1: Identify groups with exactly 6 items
    session_counts = df["Session No."].value_counts()
    exact_6_sessions = session_counts[session_counts == 6].index
    less_than_6_sessions = session_counts[session_counts < 6].index

    # Step 2: Mark groups as Type A (same "Overall Category") or Type B (different "Overall Category")
    session_types = {}
    for session in less_than_6_sessions:
        categories = df[df["Session No."] == session]["Overall Category"].unique()
        session_types[session] = "A" if len(categories) == 1 else "B"

        # Step 3: Merge Type A groups within the same "Overall Category"
        merged_session_map = {}  # Stores new session numbers
        new_session_no = int(df["Session No."].max()) + 1  # Start numbering after the highest existing Session No.

        type_a_sessions = [s for s, t in session_types.items() if t == "A"]
        grouped_a = df[df["Session No."].isin(type_a_sessions)].groupby("Overall Category")

        for _, group in grouped_a:
            session_list = group["Session No."].unique()
            items = group.copy()

            # Split into smaller groups of 6 if needed
            for i in range(0, len(items), 6):
                batch = items.iloc[i:i + 6]
                merged_session_no = int(new_session_no)
                new_session_no += 1  # Increment for the next batch

                for session in batch["Session No."].unique():
                    merged_session_map[int(session)] = merged_session_no

    # Step 4: Merge Type B sessions (without considering "Overall Category")
    type_b_sessions = [s for s, t in session_types.items() if t == "B"]
    leftover_df = df[df["Session No."].isin(type_b_sessions)].copy()

    for i in range(0, len(leftover_df), 6):
        leftover_df.loc[leftover_df.index[i:i+6], "Adjusted Session No."] = new_session_no
        new_session_no += 1  # Increment for the next batch

    # Step 5: Apply merged session mapping
    df["Adjusted Session No."] = df["Session No."].replace(merged_session_map)

    # Step 6: Ensure exact 6-item groups remain unchanged
    df.loc[df["Session No."].isin(exact_6_sessions), "Adjusted Session No."] = df["Session No."]

    # Step 7: Assign new session numbers to any remaining unmerged groups
    remaining_unmerged = df[df["Adjusted Session No."].isna()]
    for i in range(0, len(remaining_unmerged), 6):
        df.loc[remaining_unmerged.index[i:i+6], "Adjusted Session No."] = new_session_no
        new_session_no += 1

    # Step 8: Renaming "Adjusted Session No." values sequentially
    unique_sessions = df["Adjusted Session No."].dropna().unique()
    session_rename_map = {old: new for new, old in enumerate(sorted(unique_sessions), start=1)}
    df["Adjusted Session No."] = df["Adjusted Session No."].map(session_rename_map)

    return df
def input_from_spreadsheet(file_path, model, llm_selection):
    # Create data frame from the provided spreadsheet
    df = pd.read_excel(file_path)
    # Record start time
    start_time = time.time()
    # Define response from genai as an array
    results = []
    print(f"{ct()} - Extracting abstracts from raw data...\n")
    # Check if abstract column present in the spreadsheet
    if "Abstract" not in df.columns:
        print(f"{ct()} - Unable to locate abstracts list.\n")
        return None
    # Start prompting for each abstract
    with ThreadPoolExecutor(max_workers=4) as executor:  # Adjust max_workers as needed
        futures = [executor.submit(categorize_abstract, index, abstract, model) for index, abstract in df.iterrows()]

        for future, (index, abstract) in zip(futures, df.iterrows()):
            try:
                overall_category, research_field, research_method, scope, purpose, forecasted_time, prompt_tokens, response_tokens = future.result()
                results.append((index, abstract, overall_category, research_field, research_method, scope, purpose,
                                forecasted_time, prompt_tokens, response_tokens))
                if (index + 1) % 10 == 0:
                    print(f"{ct()} - No. of abstracts processed: {index + 1}\n")
            except Exception as e:
                print(f"{ct()} - Error processing abstract {index + 1}: {e}\n")
                results.append((index, abstract, "Error", "Error", "Error", "Error", "Error", "Error", 0, 0))

    print(f"{ct()} - All {index + 1} abstracts processed in {(time.time() - start_time):.2f} seconds.\n")
    # Create a Data frame with results
    df_results = pd.DataFrame(results, columns=["No.", "Abstract", "Overall Category", "Topic", "Research methods", "Scope", "Research Purpose", "Forecasted Presentation Duration", "Prompt token count", "Response token count"])
    df_results["Paper Title"] = df[['Paper Title']]
    df_results["Paper ID"] = df[['Paper ID']]
    df_results["Authors"] = df[['Authors']]
    df_results["Country"] = df[['Country']]
    df_results_reorg = df_results[['No.', 'Paper ID', 'Paper Title', 'Authors', 'Country', 'Overall Category', 'Topic']]
    # Sort data frame based on "Topic" column
    df_results = df_results_reorg.sort_values('Topic')
    return df_results


# Write results to spreadsheet
def write_to_excel(df_results, file_path, llm):
    columns_to_save = ['Paper ID', 'Session No.', 'Paper Title', 'Overall Category', 'Topic', 'Authors', 'Country']
    df_final = df_results[columns_to_save]

    output = io.BytesIO()  # Create in-memory file
    df_final.to_excel(output, engine='openpyxl', index=False)
    output.seek(0)

    return output.getvalue()  # Return the byte content of the Excel file

# Write results to spreadsheet and display
def write_to_excel_display(df_results, file_path, llm):
    columns_to_save = ['Paper ID', 'Session No.', 'Paper Title', 'Overall Category', 'Topic', 'Authors', 'Country']
    df_final = df_results[columns_to_save]

    output = io.BytesIO()  # Create in-memory file
    df_final.to_excel(output, engine='openpyxl', index=False)
    output.seek(0)

    return output.getvalue()  # Return the byte content of the Excel file

def unexpected_characters(text):
    return text.replace('\u01b0', 'L')

# Display results via browser
def browser_display(df_final, llm):
    print(f"{ct()} - Converting result spreadsheet to readable html format.\n")
    html_table = unexpected_characters(df_final).to_html(index=False)
    return html_table
    # output_path = RESULTS_PATH / f"Sessions_schedule_{llm}.html"
    #
    # with open(output_path, "w", encoding="utf-8") as f:
    #     f.write(html_table)
    #
    # try:
    #     webbrowser.open(output_path)
    #     print(f"{ct()} - DataFrame displayed in browser: {output_path}\n")
    # except Exception as e:
    #     print(f"{ct()} - Error opening HTML file in browser: {e}\n")

def main(file_path, llm_selection, API_KEY):
    print(f"{ct()} - Working Directory (Main_Functions): {os.getcwd()}!\n")
    print(f"{ct()} - Start analyzing!\n")
    # Check if a spreadsheet containing data has been selected
    model = None
    if not file_path:
        print(f"{ct()} - No file selected.\n")
        return

    if file_path:
        # Setting up Generative AI model
        pak = API_KEY
        gam = llm_selection
        print(f"{ct()} - File path received: {file_path}")
        try:
            genai.configure(api_key=pak)
            model = genai.GenerativeModel(
                model_name=gam,
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
                """)

            # Transforming original spreadsheet into machine-readable data frame
            print(f"{ct()} - Analyzing...\n")
            df = pd.read_excel(file_path)
            print(f"{ct()} - Excel file read successfully. Shape: {df.shape}\n")
            # Preliminary data processing using original spreadsheet data
            df_results = input_from_spreadsheet(file_path, model, llm_selection)
            df_r = session_assignment(df_results)
            df_r["Session No."] = df_r["Refined Grouping"].map(lambda g: merge_groups(df_r).get(g, g))
            df_r["Session No."] = df_r["Session No."].map({name: f"{i+1}" for i, name in enumerate(df_r["Session No."].unique())})
            if df_results is None:
                return

            # Write temporary results to spreadsheet
            new_df_path = write_to_excel(df_r, file_path, llm_selection)
            print(f"{ct()} - new_df_path: {new_df_path}.\n")
            new_df = pd.read_excel(new_df_path)
            print(f"{ct()} - new_df_path read successfully. Shape: {new_df.shape}.\n")
            # Refine the results and write the final results to spreadsheet
            df1 = adjust_session_numbers(new_df)
            df1["Session No."] = df1[['Adjusted Session No.']]
            final_df = df1.sort_values('Session No.')
            final_df_path = write_to_excel_display(final_df, file_path, llm_selection)
            print(f"{ct()} - Final results save to {final_df_path}\n")
            return

        except Exception as e:
            print(f"{ct()} - Error in Main_Functions.main: {e}")
            traceback.print_exc()
            return