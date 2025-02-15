import tkinter as tk
from tkinter import filedialog
import sys

# Suppress tkinter root window
root = tk.Tk()
root.withdraw()

try:
    # Open folder selection dialog
    folder_path = filedialog.askdirectory(title="Select Folder")
    if folder_path:
        print(folder_path)  # Output the selected folder path for Flask
    else:
        print("No folder selected.")  # Output this if no folder was selected
except Exception as e:
    print(f"Error: {str(e)}", file=sys.stderr)
