"""Repository for application configuration values."""


class ConfigRepository:
    def __init__(self, db):
        self.db = db

    def save(self, key, value):
        self.db.execute(
            """
            INSERT OR REPLACE INTO app_config(config_key, config_value)
            VALUES (?, ?)
            """,
            (str(key), str(value)),
        )

    def get(self, key, default=""):
        row = self.db.fetchone(
            "SELECT config_value FROM app_config WHERE config_key=?",
            (str(key),),
        )
        return row["config_value"] if row else default

    def load_all(self):
        return self.db.fetchall(
            "SELECT config_key, config_value FROM app_config ORDER BY config_key"
        )

    def get_config(self):
        return {row["config_key"]: row["config_value"] for row in self.load_all()}

    def save_config(self, config):
        for key, value in config.items():
            self.save(key, value)
