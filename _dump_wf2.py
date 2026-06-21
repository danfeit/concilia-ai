import sqlite3

conn = sqlite3.connect('database/concilia.db')
conn.row_factory = sqlite3.Row
w = conn.execute('SELECT code FROM workflows WHERE id=2').fetchone()
conn.close()

if w:
    with open('_code_wf2.py', 'w', encoding='utf-8') as f:
        f.write(w['code'])
    print("Código do workflow 2 salvo em _code_wf2.py")
else:
    print("Workflow 2 não encontrado")
