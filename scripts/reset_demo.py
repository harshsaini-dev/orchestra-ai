"""Explicit local reset with automatic database backup."""
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
from app.main import ROOT, load_environment
from app.database import Database
import os


def main():
    parser=argparse.ArgumentParser(description="Reset all local demonstration data. Stop the server first.")
    parser.add_argument("--confirm",action="store_true",help="Confirm reset after stopping the server")
    args=parser.parse_args()
    if not args.confirm:
        parser.error("Stop the server, then pass --confirm. A timestamped backup is created first.")
    load_environment()
    path=Path(os.getenv("AGENTFLOW_DB",str(ROOT/"data/agentflow.db")))
    if path.exists():
        backup=path.with_name(path.stem+"_backup_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".db")
        with sqlite3.connect(path) as src,sqlite3.connect(backup) as dst:src.backup(dst)
        path.unlink()
        for suffix in ("-wal","-shm"):
            sidecar=Path(str(path)+suffix)
            if sidecar.exists():sidecar.unlink()
        print("Backup:",backup)
    Database(path).initialize()
    print("Sample orders restored. Start the server again.")


if __name__=="__main__":main()
