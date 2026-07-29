import os
import subprocess
import sys

repo = r'C:\Users\Ismail Sajid\Downloads\Inventory-Management-AI-Employee-main\Inventory-Management-AI-Employee'
os.chdir(repo)
cmd = [r'.\.venv\Scripts\python.exe', '-m', 'pytest', 'tests/test_notify_graph.py', '-q']
print('Running:', ' '.join(cmd))
subprocess.check_call(cmd)
