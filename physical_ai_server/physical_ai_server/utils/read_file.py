import json
import os


def read_json_file(file_path: str) -> dict:
    try:
        if os.path.exists(file_path) and not os.path.isfile(file_path):
            return None
        with open(file_path, 'r') as file:
            data = json.load(file)
        return data
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON from file: {file_path}. The file may be empty or malformed.")
        return None
    except Exception as e:
        print(f"An error occurred while reading the file: {file_path}. Error: {e}")
        return None
