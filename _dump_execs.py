import sqlite3
conn = sqlite3.connect('database/concilia.db')
conn.row_factory = sqlite3.Row
execs = conn.execute('SELECT * FROM executions ORDER BY id DESC LIMIT 5').fetchall()
for e in execs:
    print("ID:", e['id'], "| Status:", e['status'], "| Error:", e['error_message'])
