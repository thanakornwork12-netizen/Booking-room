from apscheduler.schedulers.background import BackgroundScheduler
import subprocess
import sys

def retrain_model():
    print("🔁 Retraining AI model...")
    subprocess.run([sys.executable, "ml/train.py"])

def start():
    scheduler = BackgroundScheduler()

    
    scheduler.add_job(retrain_model, 'cron', hour=3)

    scheduler.start()