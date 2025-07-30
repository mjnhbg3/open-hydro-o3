"""
Database interface for storing hydroponic system data
"""

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

import aiosqlite
import json

class Database:
    """SQLite database interface for hydroponic data"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path("~/hydro/db/hydro.db").expanduser()
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
        self._connection = None
    
    async def init(self):
        """Initialize database and create tables"""
        try:
            self._connection = await aiosqlite.connect(str(self.db_path))
            await self._connection.execute("PRAGMA foreign_keys = ON")
            await self._create_tables()
            self.logger.info(f"Database initialized: {self.db_path}")
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            raise
    
    async def _create_tables(self):
        """Create all required database tables"""
        
        # Sensor readings table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                ph REAL,
                ec REAL,
                water_temp REAL,
                air_temp REAL,
                humidity REAL,
                co2 INTEGER,
                root_temp REAL,
                lux REAL,
                turbidity REAL,
                level_high BOOLEAN,
                level_low BOOLEAN,
                pressure REAL,
                led_power INTEGER,
                raw_data TEXT
            )
        """)
        
        # Actuator actions table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS actuator_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                action_type TEXT NOT NULL,
                pump_a_ml REAL DEFAULT 0,
                pump_b_ml REAL DEFAULT 0,
                ph_pump_ml REAL DEFAULT 0,
                refill_ml REAL DEFAULT 0,
                fan_speed INTEGER DEFAULT 0,
                led_power INTEGER DEFAULT 0,
                duration_minutes INTEGER,
                reason TEXT,
                success BOOLEAN DEFAULT 1,
                raw_data TEXT
            )
        """)
        
        # System events and alerts table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT,
                acknowledged BOOLEAN DEFAULT 0,
                resolved BOOLEAN DEFAULT 0
            )
        """)
        
        # Configuration changes table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS config_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                config_version TEXT NOT NULL,
                changes TEXT NOT NULL,
                reason TEXT,
                user_initiated BOOLEAN DEFAULT 0
            )
        """)
        
        # KPI rollups table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS kpi_rollups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                period TEXT NOT NULL,
                ph_avg REAL,
                ph_in_spec_pct REAL,
                ec_avg REAL,
                ec_in_spec_pct REAL,
                temp_avg REAL,
                temp_in_spec_pct REAL,
                humidity_avg REAL,
                co2_avg REAL,
                health_score REAL,
                ml_total REAL,
                pump_a_ml REAL,
                pump_b_ml REAL,
                ph_pump_ml REAL,
                days_since_change INTEGER,
                raw_data TEXT
            )
        """)
        
        # LLM decisions table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS llm_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                sensor_context TEXT NOT NULL,
                decision_data TEXT NOT NULL,
                reasoning TEXT,
                confidence REAL,
                executed BOOLEAN DEFAULT 0,
                outcome TEXT
            )
        """)
        
        # Create indexes for performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_sensor_timestamp ON sensor_readings(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_actions_timestamp ON actuator_actions(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON system_events(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_kpi_timestamp ON kpi_rollups(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_llm_timestamp ON llm_decisions(timestamp)"
        ]
        
        for index_sql in indexes:
            await self._connection.execute(index_sql)
        
        await self._connection.commit()
    
    async def store_sensor_reading(self, sensor_data: Dict[str, Any]) -> int:
        """Store sensor reading in database"""
        try:
            water = sensor_data.get('water', {})
            air = sensor_data.get('air', {})
            root = sensor_data.get('root', {})
            light = sensor_data.get('light', {})
            
            cursor = await self._connection.execute("""
                INSERT INTO sensor_readings (
                    timestamp, ph, ec, water_temp, air_temp, humidity, co2,
                    root_temp, lux, turbidity, level_high, level_low, 
                    pressure, led_power, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sensor_data.get('timestamp'),
                water.get('ph'),
                water.get('ec'), 
                water.get('temperature'),
                air.get('temperature'),
                air.get('humidity'),
                air.get('co2'),
                root.get('temperature'),
                light.get('lux'),
                water.get('turbidity'),
                water.get('level_high'),
                water.get('level_low'),
                air.get('pressure'),
                light.get('led_power'),
                json.dumps(sensor_data)
            ))
            
            await self._connection.commit()
            return cursor.lastrowid
            
        except Exception as e:
            self.logger.error(f"Failed to store sensor reading: {e}")
            raise
    
    async def store_actuator_action(self, action_data: Dict[str, Any]) -> int:
        """Store actuator action in database"""
        try:
            executed = action_data.get('executed', {})
            
            cursor = await self._connection.execute("""
                INSERT INTO actuator_actions (
                    timestamp, action_type, pump_a_ml, pump_b_ml, ph_pump_ml,
                    refill_ml, fan_speed, led_power, duration_minutes, 
                    reason, success, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                action_data.get('timestamp'),
                action_data.get('action_type', 'multiple'),
                executed.get('pump_a', {}).get('ml', 0),
                executed.get('pump_b', {}).get('ml', 0),
                executed.get('ph_pump', {}).get('ml', 0),
                executed.get('refill', {}).get('ml', 0),
                action_data.get('fan_speed', 0),
                action_data.get('led_power', 0),
                action_data.get('duration_minutes'),
                action_data.get('reason', ''),
                len(action_data.get('errors', [])) == 0,
                json.dumps(action_data)
            ))
            
            await self._connection.commit()
            return cursor.lastrowid
            
        except Exception as e:
            self.logger.error(f"Failed to store actuator action: {e}")
            raise
    
    async def store_system_event(self, event_data: Dict[str, Any]) -> int:
        """Store system event/alert in database"""
        try:
            cursor = await self._connection.execute("""
                INSERT INTO system_events (
                    timestamp, event_type, severity, category, message,
                    details, acknowledged, resolved
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_data.get('timestamp'),
                event_data.get('event_type', 'alert'),
                event_data.get('severity'),
                event_data.get('category'),
                event_data.get('message'),
                json.dumps(event_data.get('details', {})),
                event_data.get('acknowledged', False),
                event_data.get('resolved', False)
            ))
            
            await self._connection.commit()
            return cursor.lastrowid
            
        except Exception as e:
            self.logger.error(f"Failed to store system event: {e}")
            raise
    
    async def store_kpi_rollup(self, kpi_data: Dict[str, Any]) -> int:
        """Store KPI rollup data"""
        try:
            cursor = await self._connection.execute("""
                INSERT INTO kpi_rollups (
                    timestamp, period, ph_avg, ph_in_spec_pct, ec_avg, ec_in_spec_pct,
                    temp_avg, temp_in_spec_pct, humidity_avg, co2_avg, health_score,
                    ml_total, pump_a_ml, pump_b_ml, ph_pump_ml, days_since_change, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                kpi_data.get('timestamp'),
                kpi_data.get('period'),
                kpi_data.get('ph_avg'),
                kpi_data.get('ph_in_spec_pct'),
                kpi_data.get('ec_avg'),
                kpi_data.get('ec_in_spec_pct'),
                kpi_data.get('temp_avg'),
                kpi_data.get('temp_in_spec_pct'),
                kpi_data.get('humidity_avg'),
                kpi_data.get('co2_avg'),
                kpi_data.get('health_score'),
                kpi_data.get('ml_total'),
                kpi_data.get('pump_a_ml'),
                kpi_data.get('pump_b_ml'),
                kpi_data.get('ph_pump_ml'),
                kpi_data.get('days_since_change'),
                json.dumps(kpi_data)
            ))
            
            await self._connection.commit()
            return cursor.lastrowid
            
        except Exception as e:
            self.logger.error(f"Failed to store KPI rollup: {e}")
            raise
    
    async def get_recent_sensor_data(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent sensor readings"""
        try:
            since = datetime.utcnow() - timedelta(hours=hours)
            
            cursor = await self._connection.execute("""
                SELECT * FROM sensor_readings 
                WHERE timestamp > ? 
                ORDER BY timestamp DESC
            """, (since.isoformat(),))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in rows]
            
        except Exception as e:
            self.logger.error(f"Failed to get recent sensor data: {e}")
            return []
    
    async def get_recent_actions(self, hours: int = 6) -> List[Dict[str, Any]]:
        """Get recent actuator actions"""
        try:
            since = datetime.utcnow() - timedelta(hours=hours)
            
            cursor = await self._connection.execute("""
                SELECT * FROM actuator_actions 
                WHERE timestamp > ? 
                ORDER BY timestamp DESC
            """, (since.isoformat(),))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in rows]
            
        except Exception as e:
            self.logger.error(f"Failed to get recent actions: {e}")
            return []
    
    async def get_kpi_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get KPI history"""
        try:
            since = datetime.utcnow() - timedelta(days=days)
            
            cursor = await self._connection.execute("""
                SELECT * FROM kpi_rollups 
                WHERE timestamp > ? 
                ORDER BY timestamp DESC
            """, (since.isoformat(),))
            
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in rows]
            
        except Exception as e:
            self.logger.error(f"Failed to get KPI history: {e}")
            return []
    
    async def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old data to manage database size"""
        try:
            cutoff = datetime.utcnow() - timedelta(days=days_to_keep)
            
            # Keep sensor readings for specified days
            await self._connection.execute("""
                DELETE FROM sensor_readings WHERE timestamp < ?
            """, (cutoff.isoformat(),))
            
            # Keep actions for longer (90 days)
            action_cutoff = datetime.utcnow() - timedelta(days=90)
            await self._connection.execute("""
                DELETE FROM actuator_actions WHERE timestamp < ?
            """, (action_cutoff.isoformat(),))
            
            # Keep resolved events for 30 days
            await self._connection.execute("""
                DELETE FROM system_events 
                WHERE timestamp < ? AND resolved = 1
            """, (cutoff.isoformat(),))
            
            await self._connection.commit()
            self.logger.info(f"Cleaned up data older than {days_to_keep} days")
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup old data: {e}")
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            stats = {}
            
            tables = ['sensor_readings', 'actuator_actions', 'system_events', 
                     'kpi_rollups', 'llm_decisions']
            
            for table in tables:
                cursor = await self._connection.execute(f"SELECT COUNT(*) FROM {table}")
                count = await cursor.fetchone()
                stats[f"{table}_count"] = count[0]
            
            # Database file size
            stats['db_size_mb'] = round(self.db_path.stat().st_size / (1024 * 1024), 2)
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Failed to get database stats: {e}")
            return {}
    
    async def close(self):
        """Close database connection"""
        if self._connection:
            await self._connection.close()
            self.logger.info("Database connection closed")