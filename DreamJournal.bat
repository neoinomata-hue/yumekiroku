@echo off
cd /d C:\Users\neo\Downloads\dream_journal
call venv\Scripts\activate
start "" http://127.0.0.1:5000
python app.py
