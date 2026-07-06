import asyncio
import os

import asyncpg
from dotenv import load_dotenv

from core.audit_log.config import AuditLogConfig
from core.gamification.clickhouse_reader import ClickHouseGamificationReader
from core.gamification.postgres_store import PostgresGamificationStore
from core.gamification.worker import GamificationSweepWorker


async def main() -> None:
    load_dotenv()
    interval_seconds = int(os.getenv("GAMIFICATION_SWEEP_INTERVAL_SECONDS", "600"))
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://legal:legal@127.0.0.1:5432/support_legal",
    )
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    try:
        worker = GamificationSweepWorker(
            event_reader=ClickHouseGamificationReader(AuditLogConfig.from_env()),
            state_store=PostgresGamificationStore(pool),
        )
        print("start run forever")
        await worker.run_forever(interval_seconds=interval_seconds)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
