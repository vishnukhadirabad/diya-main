import sqlite3
import pandas as pd

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect('./database.db')
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    return conn

def get_all_data_from_table(table_name):
    """Fetches all data from the specified table."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Query to select all data from the given table
    cursor.execute(f'SELECT * FROM {table_name}')

    # Fetch all rows
    rows = cursor.fetchall()

    conn.close()

    return rows

def write_table_data_to_file(table_name, file):
    """Writes all the data from a specific table into a file in tabular format."""
    data = get_all_data_from_table(table_name)

    if data:
        # Create a pandas DataFrame from the data
        df = pd.DataFrame(data, columns=data[0].keys())

        # Write the table name and a divider
        file.write(f"\nDisplaying data from table: {table_name}\n")
        file.write(f"{'-' * 80}\n")

        # Write the DataFrame to the file in a markdown-style table
        file.write(df.to_markdown(index=False))
        file.write("\n\n")
    else:
        file.write(f"No data found in {table_name}\n")

def list_tables():
    """Lists all the tables in the SQLite database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Query to get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    conn.close()

    return [table['name'] for table in tables]

if __name__ == "__main__":
    # Open a file to write the output
    with open("database_content.txt", "w") as file:
        # Get a list of all tables in the database
        tables = list_tables()

        if tables:
            for table in tables:
                write_table_data_to_file(table, file)
        else:
            file.write("No tables found in the database.\n")

    print("Data has been written to 'database_content.txt' in a tabular format.")