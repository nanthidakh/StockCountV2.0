"""
=========================================================
Project : HWK_StockV1
File : repository/config_repository.py
=========================================================
"""
from models.app_config import AppConfig
class ConfigRepository:
    def __init__(self, db):
        self.db = db
    def create_table(self):
        sql = """
        CREATE TABLE IF NOT EXISTS app_config(
            config_key TEXT PRIMARY KEY,
            config_value TEXT
        )
        """
        self.db.execute(sql)
    def save(self, key, value):
        sql = """
        INSERT OR REPLACE INTO app_config
        (
            config_key,
            config_value
        )
        VALUES (?,?)
        """
        self.db.execute(
            sql,
            (key, value)
        )
    #    self.db.commit()
    def get(self, key, default=""):
        sql = """
        SELECT config_value
        FROM app_config
        WHERE config_key=?
        """
        row = self.db.fetchone(
            sql,
            (key,)
        )
        if row:
            return row["config_value"]
        return default
    def load_all(self):
        sql = """
        SELECT
            config_key,
            config_value
        FROM app_config
        """
        return self.db.fetchall(sql)
    def get_config(self):
        rows = self.load_all()
        config = {}
        for row in rows:
            config[row["config_key"]] = row["config_value"]
        return config
    
    def save_config(
        self,
            config
        ):

            for key, value in config.items():

                self.save(
                    key,
                    str(value)
                )