import json
from core.config import load_config
from agents.debug_agent import analyze_and_fix

config = load_config()

dummy_code = """import pandas as pd
def main():
    df = pd.read_csv("test.csv")
    print(df['valor_a'])
if __name__ == "__main__": main()"""

dummy_error = "KeyError: 'valor_a'"
dummy_stderr = ""
dummy_log = {"status": "error"}
dummy_info = [{"path": "test.csv", "columns": ["valor_b", "data"], "sample_rows": []}]

result = analyze_and_fix(dummy_code, dummy_error, dummy_stderr, dummy_log, dummy_info, config)

with open("test_debug_agent_output.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
