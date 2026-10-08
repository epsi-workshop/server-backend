"""Historique des mesures du boîtier (SQLite) : température, humidité et déclenchements PIR.

Sert à l'entraînement de l'Isolation Forest (plusieurs jours de fonctionnement normal) et au calcul
des variables qui dépendent du passé (variations sur 5 min, PIR sur 1 h, régression sur 30 min).
"""
import sqlite3
from collections.abc import Iterable
from pathlib import Path

import numpy as np


class History:
    def __init__(self, path: Path | str) -> None:
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS samples (ts REAL NOT NULL, temp REAL NOT NULL, hum REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS samples_ts ON samples (ts);
            CREATE TABLE IF NOT EXISTS pir (ts REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS pir_ts ON pir (ts);
        """)

    def add_sample(self, ts: float, temp: float, hum: float) -> None:
        self.add_samples([(ts, temp, hum)])

    def add_samples(self, rows: Iterable[tuple[float, float, float]]) -> None:
        with self.db:
            self.db.executemany("INSERT INTO samples (ts, temp, hum) VALUES (?, ?, ?)", rows)

    def add_pir(self, ts: float) -> None:
        with self.db:
            self.db.execute("INSERT INTO pir (ts) VALUES (?)", (ts,))

    def samples(self, since: float = 0.0) -> np.ndarray:
        """Mesures depuis `since` (secondes epoch), triées : tableau (n, 3) ts, température, humidité."""
        rows = self.db.execute("SELECT ts, temp, hum FROM samples WHERE ts >= ? ORDER BY ts", (since,)).fetchall()
        return np.array(rows, dtype=np.float64).reshape(-1, 3)

    def pir_times(self, since: float = 0.0) -> np.ndarray:
        rows = self.db.execute("SELECT ts FROM pir WHERE ts >= ? ORDER BY ts", (since,)).fetchall()
        return np.array([r[0] for r in rows], dtype=np.float64)

    def prune(self, before: float) -> None:
        with self.db:
            self.db.execute("DELETE FROM samples WHERE ts < ?", (before,))
            self.db.execute("DELETE FROM pir WHERE ts < ?", (before,))

    def close(self) -> None:
        self.db.close()
