#!/usr/bin/env python3
"""
KPI rollup script - runs hourly to calculate performance metrics
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.memory.db import Database
from app.memory.kpis import KPICalculator
from app.utils import setup_logging, create_alert


class KPIRollup:
    """KPI calculation and rollup service"""

    def __init__(self):
        self.db = None
        self.kpi_calc = None
        self.logger = logging.getLogger(__name__)

    async def initialize(self):
        """Initialize database and KPI calculator"""
        try:
            self.db = Database()
            await self.db.init()

            self.kpi_calc = KPICalculator(self.db)

            self.logger.info("KPI rollup service initialized")

        except Exception as e:
            self.logger.error(f"KPI rollup initialization failed: {e}")
            raise

    async def run_kpi_rollup(self) -> dict:
        """Calculate and store KPI rollups for multiple time periods"""
        rollup_start = datetime.utcnow()

        try:
            self.logger.info("Starting KPI rollup calculations")

            results = {
                "timestamp": rollup_start.isoformat(),
                "rollups": {},
                "alerts": [],
                "success": True,
            }

            # Calculate KPIs for different time periods
            time_periods = [
                ("1hour", 1),
                ("6hour", 6),
                ("24hour", 24),
                ("7day", 168),  # 7 days = 168 hours
            ]

            for period_name, hours in time_periods:
                try:
                    period_kpis = await self.kpi_calc.calculate_period_kpis(hours)

                    if "error" not in period_kpis:
                        # Store in database
                        kpi_id = await self.db.store_kpi_rollup(
                            {**period_kpis, "period": period_name}
                        )

                        results["rollups"][period_name] = {
                            "kpi_id": kpi_id,
                            "data": period_kpis,
                        }

                        # Check for alerts based on KPIs
                        period_alerts = self._check_kpi_alerts(period_kpis, period_name)
                        results["alerts"].extend(period_alerts)

                        self.logger.info(
                            f"KPI rollup completed for {period_name}: ID={kpi_id}"
                        )
                    else:
                        self.logger.warning(
                            f"KPI calculation failed for {period_name}: {period_kpis['error']}"
                        )
                        results["rollups"][period_name] = {
                            "error": period_kpis["error"]
                        }

                except Exception as e:
                    self.logger.error(f"KPI rollup failed for {period_name}: {e}")
                    results["rollups"][period_name] = {"error": str(e)}

            # Calculate trend analysis
            try:
                trends = await self.kpi_calc.calculate_7day_trends()

                if "error" not in trends:
                    results["trends"] = trends

                    # Check for trend-based alerts
                    trend_alerts = self._check_trend_alerts(trends)
                    results["alerts"].extend(trend_alerts)
                else:
                    results["trends"] = {"error": trends["error"]}

            except Exception as e:
                self.logger.error(f"Trend calculation failed: {e}")
                results["trends"] = {"error": str(e)}

            # Store any generated alerts
            for alert in results["alerts"]:
                try:
                    await self.db.store_system_event(alert)
                except Exception as e:
                    self.logger.error(f"Failed to store alert: {e}")

            # Calculate rollup duration
            duration_ms = int((datetime.utcnow() - rollup_start).total_seconds() * 1000)
            results["duration_ms"] = duration_ms

            self.logger.info(
                f"KPI rollup completed in {duration_ms}ms with {len(results['alerts'])} alerts"
            )

            return results

        except Exception as e:
            self.logger.error(f"KPI rollup failed: {e}")

            return {
                "timestamp": rollup_start.isoformat(),
                "success": False,
                "error": str(e),
            }

    def _check_kpi_alerts(self, kpis: dict, period: str) -> list:
        """Check KPIs for alert conditions"""
        alerts = []

        try:
            # Health score alerts
            health_score = kpis.get("health_score", 1.0)
            if health_score < 0.6:
                alerts.append(
                    create_alert(
                        "critical",
                        "system",
                        f"Low health score: {health_score:.2f} in {period}",
                        {"health_score": health_score, "period": period, "kpis": kpis},
                    )
                )
            elif health_score < 0.8:
                alerts.append(
                    create_alert(
                        "warning",
                        "system",
                        f"Declining health score: {health_score:.2f} in {period}",
                        {"health_score": health_score, "period": period},
                    )
                )

            # pH stability alerts
            ph_in_spec_pct = kpis.get("ph_in_spec_pct", 100)
            if ph_in_spec_pct < 80:
                alerts.append(
                    create_alert(
                        "warning",
                        "sensor",
                        f"Poor pH stability: {ph_in_spec_pct}% in-spec in {period}",
                        {"ph_in_spec_pct": ph_in_spec_pct, "period": period},
                    )
                )

            # EC stability alerts
            ec_in_spec_pct = kpis.get("ec_in_spec_pct", 100)
            if ec_in_spec_pct < 80:
                alerts.append(
                    create_alert(
                        "warning",
                        "sensor",
                        f"Poor EC stability: {ec_in_spec_pct}% in-spec in {period}",
                        {"ec_in_spec_pct": ec_in_spec_pct, "period": period},
                    )
                )

            # Excessive dosing alerts
            if period == "24hour":
                ml_total = kpis.get("ml_total", 0)
                if ml_total > 100:  # More than 100ml in 24h
                    alerts.append(
                        create_alert(
                            "warning",
                            "actuator",
                            f"High daily dosing: {ml_total}ml in 24 hours",
                            {"ml_total": ml_total, "period": period},
                        )
                    )

            # Temperature stability alerts
            temp_in_spec_pct = kpis.get("temp_in_spec_pct", 100)
            if temp_in_spec_pct < 90:
                alerts.append(
                    create_alert(
                        "info",
                        "environmental",
                        f"Temperature instability: {temp_in_spec_pct}% in-spec in {period}",
                        {"temp_in_spec_pct": temp_in_spec_pct, "period": period},
                    )
                )

        except Exception as e:
            self.logger.error(f"KPI alert checking failed: {e}")

        return alerts

    def _check_trend_alerts(self, trends: dict) -> list:
        """Check 7-day trends for alert conditions"""
        alerts = []

        try:
            # Health score trend
            health_trend = trends.get("health_trend", "stable")
            health_7day = trends.get("health_7day_avg", 1.0)

            if health_trend == "decreasing" and health_7day < 0.8:
                alerts.append(
                    create_alert(
                        "warning",
                        "system",
                        f"Declining health trend: {health_trend}, 7-day avg: {health_7day:.2f}",
                        {"health_trend": health_trend, "health_7day_avg": health_7day},
                    )
                )

            # pH trend alerts
            ph_trend = trends.get("ph_trend", "stable")
            ph_in_spec_7day = trends.get("ph_in_spec_7day", 100)

            if ph_in_spec_7day < 85:
                alerts.append(
                    create_alert(
                        "warning",
                        "sensor",
                        f"Poor 7-day pH stability: {ph_in_spec_7day}% in-spec, trend: {ph_trend}",
                        {"ph_in_spec_7day": ph_in_spec_7day, "ph_trend": ph_trend},
                    )
                )

            # EC trend alerts
            ec_trend = trends.get("ec_trend", "stable")
            ec_in_spec_7day = trends.get("ec_in_spec_7day", 100)

            if ec_in_spec_7day < 85:
                alerts.append(
                    create_alert(
                        "warning",
                        "sensor",
                        f"Poor 7-day EC stability: {ec_in_spec_7day}% in-spec, trend: {ec_trend}",
                        {"ec_in_spec_7day": ec_in_spec_7day, "ec_trend": ec_trend},
                    )
                )

            # Excessive dosing trend
            ml_total_7day = trends.get("ml_total_7day", 0)
            if ml_total_7day > 200:  # More than 200ml in 7 days
                alerts.append(
                    create_alert(
                        "info",
                        "actuator",
                        f"High weekly dosing trend: {ml_total_7day}ml in 7 days",
                        {"ml_total_7day": ml_total_7day},
                    )
                )

        except Exception as e:
            self.logger.error(f"Trend alert checking failed: {e}")

        return alerts

    async def cleanup_old_data(self):
        """Cleanup old data to maintain database size"""
        try:
            self.logger.info("Starting database cleanup")

            await self.db.cleanup_old_data(days_to_keep=30)

            # Get database statistics after cleanup
            stats = await self.db.get_database_stats()
            self.logger.info(f"Database cleanup complete: {stats}")

            return stats

        except Exception as e:
            self.logger.error(f"Database cleanup failed: {e}")
            return {"error": str(e)}

    async def cleanup(self):
        """Cleanup resources"""
        if self.db:
            await self.db.close()

        self.logger.info("KPI rollup cleanup complete")


async def main():
    """Main execution function"""
    setup_logging()
    logger = logging.getLogger(__name__)

    kpi_rollup = KPIRollup()

    try:
        logger.info("Starting KPI rollup")

        await kpi_rollup.initialize()
        result = await kpi_rollup.run_kpi_rollup()

        # Also run database cleanup (weekly on Sunday)
        if datetime.utcnow().weekday() == 6:  # Sunday
            cleanup_result = await kpi_rollup.cleanup_old_data()
            result["database_cleanup"] = cleanup_result

        if result["success"]:
            logger.info("KPI rollup completed successfully")
            print(json.dumps(result, indent=2, default=str))
            exit_code = 0
        else:
            logger.error(f"KPI rollup failed: {result.get('error')}")
            print(json.dumps(result, indent=2, default=str))
            exit_code = 1

    except Exception as e:
        logger.error(f"KPI rollup script failed: {e}")
        print(
            json.dumps(
                {
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                },
                indent=2,
            )
        )
        exit_code = 2

    finally:
        await kpi_rollup.cleanup()

    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
