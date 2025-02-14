from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
import pandas as pd
from collections import defaultdict
import Main_Functions

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
            batch = items.iloc[i:i+6]
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

    # Step 8: **Renaming "Adjusted Session No." values sequentially**
    unique_sessions = df["Adjusted Session No."].dropna().unique()
    session_rename_map = {old: new for new, old in enumerate(sorted(unique_sessions), start=1)}
    df["Adjusted Session No."] = df["Adjusted Session No."].map(session_rename_map)

    return df

def main():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(
        title="Select Abstracts List",
        filetypes=[("Excel files", "*.xlsx;*.xls;*.csv")]
    )
    root.destroy()
    if file_path:
        df = pd.read_excel(file_path)
        df1 = adjust_session_numbers(df)
        df["Session No."] = df1[['Adjusted Session No.']]
        refined_df = df[['Paper ID', 'Session No.', 'Paper Title', 'Overall Category', 'Topic', 'Authors', 'Country']]
        # Sort data frame based on "Session No." column
        final_df = refined_df.sort_values('Session No.')
        output_file = Path(__file__).parent / "results" / file_path.replace(".xlsx", "_refined.xlsx")
        with pd.ExcelWriter(output_file, mode='w') as writer:
            final_df.to_excel(writer, sheet_name='Processed')
        print(f"- Results are saved to {output_file}")
        Main_Functions.browser_display(final_df)
    else:
        print("No file selected.")
        return

if __name__ == "__main__":
    main()
