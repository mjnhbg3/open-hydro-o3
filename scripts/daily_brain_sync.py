#!/usr/bin/env python3
"""
Daily brain sync script - synchronizes with LLM memory and performs daily analysis
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.llm_agent import LLMAgent
from app.memory.db import Database
from app.memory.vector import VectorMemory
from app.memory.kpis import KPICalculator
from app.utils import setup_logging, create_alert
from app.utils import load_config


class DailyBrainSync:
    """Daily LLM brain synchronization and analysis"""

    def __init__(self):
        self.config = load_config()
        self.db = None
        self.vector_memory = None
        self.llm_agent = None
        self.kpi_calc = None
        self.logger = logging.getLogger(__name__)

    async def initialize(self):
        """Initialize all components"""
        try:
            self.db = Database()
            await self.db.init()

            self.vector_memory = VectorMemory()
            self.kpi_calc = KPICalculator(self.db)

            try:
                self.llm_agent = LLMAgent()
                self.logger.info("LLM agent initialized for brain sync")
            except Exception as e:
                self.logger.error(f"LLM agent initialization failed: {e}")
                raise

            self.logger.info("Daily brain sync initialized")

        except Exception as e:
            self.logger.error(f"Brain sync initialization failed: {e}")
            raise

    async def run_daily_sync(self) -> dict:
        """Execute daily brain synchronization"""
        sync_start = datetime.utcnow()

        try:
            self.logger.info("Starting daily brain sync")

            results = {
                "timestamp": sync_start.isoformat(),
                "components": {},
                "analysis": {},
                "recommendations": {},
                "success": True,
            }

            # 1. Synchronize vector memory
            memory_sync = await self._sync_vector_memory()
            results["components"]["memory_sync"] = memory_sync

            # 2. Generate daily summary
            daily_summary = await self._generate_daily_summary()
            results["analysis"]["daily_summary"] = daily_summary

            # 3. Performance analysis
            performance_analysis = await self._analyze_performance()
            results["analysis"]["performance"] = performance_analysis

            # 4. Generate recommendations
            recommendations = await self._generate_recommendations(
                daily_summary, performance_analysis
            )
            results["recommendations"] = recommendations

            # 5. Store brain sync results
            await self._store_sync_results(results)

            # 6. Cleanup old memories
            cleanup_result = await self._cleanup_memories()
            results["components"]["memory_cleanup"] = cleanup_result

            duration_ms = int((datetime.utcnow() - sync_start).total_seconds() * 1000)
            results["duration_ms"] = duration_ms

            self.logger.info(f"Daily brain sync completed in {duration_ms}ms")

            return results

        except Exception as e:
            self.logger.error(f"Daily brain sync failed: {e}")

            return {
                "timestamp": sync_start.isoformat(),
                "success": False,
                "error": str(e),
            }

    async def _sync_vector_memory(self) -> dict:
        """Synchronize vector memory with recent decisions"""
        try:
            # Get recent LLM decisions from database
            recent_decisions = await self.db.get_recent_actions(hours=24)

            stored_memories = 0
            for decision in recent_decisions:
                try:
                    # Extract relevant data for memory storage
                    if decision.get("raw_data"):
                        raw_data = json.loads(decision["raw_data"])

                        # Create memory entry
                        memory_entry = {
                            "timestamp": decision["timestamp"],
                            "type": "daily_decision",
                            "decision_summary": self._create_decision_summary(decision),
                            "raw_decision": raw_data,
                            "outcome": (
                                "executed" if decision.get("success") else "failed"
                            ),
                        }

                        # Store in vector memory
                        await self.vector_memory.store(memory_entry)
                        stored_memories += 1

                except Exception as e:
                    self.logger.warning(
                        f"Failed to store memory for decision {decision.get('id')}: {e}"
                    )

            return {
                "success": True,
                "memories_stored": stored_memories,
                "decisions_processed": len(recent_decisions),
            }

        except Exception as e:
            self.logger.error(f"Vector memory sync failed: {e}")
            return {"success": False, "error": str(e)}

    async def _generate_daily_summary(self) -> dict:
        """Generate comprehensive daily summary"""
        try:
            yesterday = datetime.utcnow() - timedelta(days=1)

            # Get 24-hour KPIs
            daily_kpis = await self.kpi_calc.calculate_period_kpis(24)

            # Get sensor readings count
            sensor_data = await self.db.get_recent_sensor_data(hours=24)

            # Get actions taken
            actions = await self.db.get_recent_actions(hours=24)

            # Calculate summary statistics
            summary = {
                "date": yesterday.strftime("%Y-%m-%d"),
                "sensor_readings": len(sensor_data),
                "actions_taken": len(actions),
                "kpis": daily_kpis,
                "key_metrics": {
                    "health_score": daily_kpis.get("health_score", 0),
                    "ph_stability": daily_kpis.get("ph_in_spec_pct", 0),
                    "ec_stability": daily_kpis.get("ec_in_spec_pct", 0),
                    "total_dosing_ml": sum(
                        action.get("pump_a_ml", 0)
                        + action.get("pump_b_ml", 0)
                        + action.get("ph_pump_ml", 0)
                        for action in actions
                        if action.get("success", True)
                    ),
                },
                "notable_events": self._extract_notable_events(sensor_data, actions),
            }

            return summary

        except Exception as e:
            self.logger.error(f"Daily summary generation failed: {e}")
            return {"error": str(e)}

    async def _analyze_performance(self) -> dict:
        """Analyze system performance trends"""
        try:
            # Get 7-day trends
            trends = await self.kpi_calc.calculate_7day_trends()

            # Compare with previous week
            previous_week_kpis = await self.kpi_calc.calculate_period_kpis(
                168
            )  # 7 days in hours

            analysis = {
                "trends": trends,
                "week_comparison": previous_week_kpis,
                "performance_grade": self._calculate_performance_grade(trends),
                "improvement_areas": self._identify_improvement_areas(trends),
                "stability_assessment": self._assess_stability(trends),
            }

            return analysis

        except Exception as e:
            self.logger.error(f"Performance analysis failed: {e}")
            return {"error": str(e)}

    async def _generate_recommendations(
        self, daily_summary: dict, performance_analysis: dict
    ) -> dict:
        """Generate LLM-powered recommendations"""
        try:
            # Prepare context for LLM
            context_prompt = f"""
            Analyze the following hydroponic system performance data and provide recommendations:
            
            DAILY SUMMARY:
            {json.dumps(daily_summary, indent=2)}
            
            PERFORMANCE ANALYSIS:
            {json.dumps(performance_analysis, indent=2)}
            
            Please provide:
            1. Overall system assessment
            2. Specific improvement recommendations
            3. Potential issues to monitor
            4. Optimization opportunities
            
            Focus on actionable insights based on the stable-unless-better philosophy.
            """

            # Get LLM recommendations
            llm_response = await self.llm_agent._call_llm(
                "You are an expert hydroponic system analyst. Provide concise, actionable recommendations based on the data provided.",
                context_prompt,
            )

            recommendations = {
                "llm_analysis": llm_response,
                "automated_recommendations": self._generate_automated_recommendations(
                    daily_summary, performance_analysis
                ),
                "priority_actions": self._identify_priority_actions(
                    daily_summary, performance_analysis
                ),
            }

            return recommendations

        except Exception as e:
            self.logger.error(f"Recommendation generation failed: {e}")
            return {"error": str(e)}

    def _create_decision_summary(self, decision: dict) -> str:
        """Create text summary of decision for vector storage"""
        summary_parts = []

        if decision.get("pump_a_ml", 0) > 0:
            summary_parts.append(f"Pump A: {decision['pump_a_ml']}ml")
        if decision.get("pump_b_ml", 0) > 0:
            summary_parts.append(f"Pump B: {decision['pump_b_ml']}ml")
        if decision.get("ph_pump_ml", 0) > 0:
            summary_parts.append(f"pH: {decision['ph_pump_ml']}ml")
        if decision.get("fan_speed", 0) > 0:
            summary_parts.append(f"Fan: {decision['fan_speed']}%")

        reason = decision.get("reason", "No reason provided")

        if summary_parts:
            return f"Actions: {', '.join(summary_parts)} | Reason: {reason}"
        else:
            return f"No actions | Reason: {reason}"

    def _extract_notable_events(self, sensor_data: list, actions: list) -> list:
        """Extract notable events from sensor and action data"""
        events = []

        try:
            # Check for significant parameter deviations
            for reading in sensor_data:
                if reading.get("ph") and reading["ph"] < 5.0 or reading["ph"] > 7.0:
                    events.append(
                        f"pH deviation: {reading['ph']} at {reading['timestamp']}"
                    )

                if reading.get("ec") and reading["ec"] > 2.5:
                    events.append(f"High EC: {reading['ec']} at {reading['timestamp']}")

                if not reading.get("level_high"):
                    events.append(f"Low water level at {reading['timestamp']}")

            # Check for significant actions
            for action in actions:
                total_ml = (
                    action.get("pump_a_ml", 0)
                    + action.get("pump_b_ml", 0)
                    + action.get("ph_pump_ml", 0)
                )
                if total_ml > 20:  # Significant dosing
                    events.append(f"Large dose: {total_ml}ml at {action['timestamp']}")

        except Exception as e:
            self.logger.warning(f"Event extraction failed: {e}")

        return events[:10]  # Limit to 10 most recent events

    def _calculate_performance_grade(self, trends: dict) -> str:
        """Calculate overall performance grade"""
        try:
            health_avg = trends.get("health_7day_avg", 0)
            ph_in_spec = trends.get("ph_in_spec_7day", 0) / 100
            ec_in_spec = trends.get("ec_in_spec_7day", 0) / 100

            overall_score = (
                (health_avg * 0.5) + (ph_in_spec * 0.25) + (ec_in_spec * 0.25)
            )

            if overall_score >= 0.95:
                return "A+"
            elif overall_score >= 0.9:
                return "A"
            elif overall_score >= 0.85:
                return "B+"
            elif overall_score >= 0.8:
                return "B"
            elif overall_score >= 0.7:
                return "C"
            else:
                return "D"

        except Exception:
            return "Unknown"

    def _identify_improvement_areas(self, trends: dict) -> list:
        """Identify areas needing improvement"""
        areas = []

        try:
            if trends.get("ph_in_spec_7day", 100) < 90:
                areas.append("pH stability")

            if trends.get("ec_in_spec_7day", 100) < 90:
                areas.append("EC stability")

            if trends.get("health_7day_avg", 1.0) < 0.8:
                areas.append("Overall plant health")

            if trends.get("ml_total_7day", 0) > 150:
                areas.append("Nutrient efficiency")

        except Exception as e:
            self.logger.warning(f"Improvement area identification failed: {e}")

        return areas

    def _assess_stability(self, trends: dict) -> dict:
        """Assess system stability"""
        try:
            stability = {
                "ph_stable": trends.get("ph_trend", "stable") == "stable",
                "ec_stable": trends.get("ec_trend", "stable") == "stable",
                "health_stable": trends.get("health_trend", "stable")
                in ["stable", "increasing"],
                "overall": "stable",
            }

            unstable_count = sum(1 for stable in stability.values() if stable is False)

            if unstable_count == 0:
                stability["overall"] = "very_stable"
            elif unstable_count <= 1:
                stability["overall"] = "stable"
            elif unstable_count <= 2:
                stability["overall"] = "somewhat_unstable"
            else:
                stability["overall"] = "unstable"

            return stability

        except Exception:
            return {"overall": "unknown"}

    def _generate_automated_recommendations(
        self, daily_summary: dict, performance_analysis: dict
    ) -> list:
        """Generate automated recommendations based on data"""
        recommendations = []

        try:
            kpis = daily_summary.get("kpis", {})

            # Health score recommendations
            health_score = kpis.get("health_score", 1.0)
            if health_score < 0.7:
                recommendations.append(
                    {
                        "priority": "high",
                        "area": "health",
                        "recommendation": "Investigate root cause of low health score",
                        "details": f"Current health score: {health_score:.2f}",
                    }
                )

            # pH stability recommendations
            ph_in_spec = kpis.get("ph_in_spec_pct", 100)
            if ph_in_spec < 85:
                recommendations.append(
                    {
                        "priority": "medium",
                        "area": "pH",
                        "recommendation": "Improve pH control system",
                        "details": f"pH in-spec: {ph_in_spec}%",
                    }
                )

            # Dosing efficiency recommendations
            total_dosing = daily_summary.get("key_metrics", {}).get(
                "total_dosing_ml", 0
            )
            if total_dosing > 80:
                recommendations.append(
                    {
                        "priority": "medium",
                        "area": "efficiency",
                        "recommendation": "Review nutrient dosing efficiency",
                        "details": f"Daily dosing: {total_dosing}ml",
                    }
                )

        except Exception as e:
            self.logger.warning(f"Automated recommendation generation failed: {e}")

        return recommendations

    def _identify_priority_actions(
        self, daily_summary: dict, performance_analysis: dict
    ) -> list:
        """Identify priority actions for today"""
        actions = []

        try:
            # Based on performance grade
            grade = performance_analysis.get("performance_grade", "C")

            if grade in ["D", "C"]:
                actions.append(
                    "Investigate system issues - performance below acceptable level"
                )

            # Based on improvement areas
            improvement_areas = performance_analysis.get("improvement_areas", [])
            for area in improvement_areas[:3]:  # Top 3 areas
                actions.append(f"Focus on improving {area}")

            # Based on stability
            stability = performance_analysis.get("stability_assessment", {})
            if stability.get("overall") == "unstable":
                actions.append(
                    "Prioritize system stability - multiple parameters unstable"
                )

        except Exception as e:
            self.logger.warning(f"Priority action identification failed: {e}")

        return actions

    async def _store_sync_results(self, results: dict):
        """Store brain sync results in database"""
        try:
            # Store as system event
            sync_event = create_alert(
                "info",
                "system",
                "Daily brain sync completed",
                {
                    "sync_results": results,
                    "performance_grade": results.get("analysis", {})
                    .get("performance", {})
                    .get("performance_grade"),
                    "recommendations_count": len(
                        results.get("recommendations", {}).get(
                            "automated_recommendations", []
                        )
                    ),
                },
            )

            await self.db.store_system_event(sync_event)

        except Exception as e:
            self.logger.error(f"Failed to store sync results: {e}")

    async def _cleanup_memories(self) -> dict:
        """Cleanup old vector memories"""
        try:
            await self.vector_memory.delete_old_memories(days_to_keep=30)

            status = await self.vector_memory.get_status()

            return {"success": True, "memory_status": status}

        except Exception as e:
            self.logger.error(f"Memory cleanup failed: {e}")
            return {"success": False, "error": str(e)}

    async def cleanup(self):
        """Cleanup resources"""
        if self.db:
            await self.db.close()

        self.logger.info("Daily brain sync cleanup complete")


async def main():
    """Main execution function"""
    setup_logging()
    logger = logging.getLogger(__name__)

    brain_sync = DailyBrainSync()

    try:
        logger.info("Starting daily brain sync")

        await brain_sync.initialize()
        result = await brain_sync.run_daily_sync()

        if result["success"]:
            logger.info("Daily brain sync completed successfully")
            print(json.dumps(result, indent=2, default=str))
            exit_code = 0
        else:
            logger.error(f"Daily brain sync failed: {result.get('error')}")
            print(json.dumps(result, indent=2, default=str))
            exit_code = 1

    except Exception as e:
        logger.error(f"Daily brain sync script failed: {e}")
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
        await brain_sync.cleanup()

    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
