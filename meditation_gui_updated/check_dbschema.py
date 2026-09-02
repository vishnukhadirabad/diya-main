import sqlite3

conn = sqlite3.connect('meditation.db')
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(feedback);")
schema_info = cursor.fetchall()

for column in schema_info:
    print(column)

conn.close()
