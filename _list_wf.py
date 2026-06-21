import sqlite3

conn = sqlite3.connect('database/concilia.db')
conn.row_factory = sqlite3.Row
workflows = conn.execute('SELECT * FROM workflows').fetchall()
conn.close()

for w in workflows:
    print(f'ID: {w["id"]} | Name: {w["name"]}')
