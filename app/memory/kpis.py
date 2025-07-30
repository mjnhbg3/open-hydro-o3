"""
KPI calculation system for hydroponic monitoring
"""

import logging
import statistics
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from .db import Database

class KPICalculator:
    """Calculates Key Performance Indicators for hydroponic system"""
    
    def __init__(self, db: Database = None):
        self.db = db or Database()
        self.logger = logging.getLogger(__name__)
    
    async def calculate_current_kpis(self, sensor_data: Dict[str, Any],
                                   target_ranges: Dict[str, Any] = None) -> Dict[str, Any]:
        """Calculate current KPIs based on sensor data and targets"""
        
        if target_ranges is None:
            target_ranges = {
                'ph_min': 5.5, 'ph_max': 6.5,
                'ec_min': 1.2, 'ec_max': 2.0,
                'temp_min': 18, 'temp_max': 26,
                'humidity_min': 50, 'humidity_max': 70,
                'co2_min': 400, 'co2_max': 1200
            }
        
        try:
            water = sensor_data.get('water', {})
            air = sensor_data.get('air', {})
            
            # Individual parameter compliance
            ph_in_spec = self._is_in_range(water.get('ph'), 
                                         target_ranges['ph_min'], target_ranges['ph_max'])
            
            ec_in_spec = self._is_in_range(water.get('ec'),
                                         target_ranges['ec_min'], target_ranges['ec_max'])
            
            temp_in_spec = self._is_in_range(air.get('temperature'),
                                           target_ranges['temp_min'], target_ranges['temp_max'])
            
            humidity_in_spec = self._is_in_range(air.get('humidity'),
                                               target_ranges['humidity_min'], target_ranges['humidity_max'])
            
            co2_in_spec = self._is_in_range(air.get('co2'),
                                          target_ranges['co2_min'], target_ranges['co2_max'])
            
            # Overall health score (weighted average)
            health_components = [
                (ph_in_spec, 0.3),      # pH most critical
                (ec_in_spec, 0.25),     # EC very important
                (temp_in_spec, 0.2),    # Temperature important
                (humidity_in_spec, 0.15), # Humidity moderately important
                (co2_in_spec, 0.1)      # CO2 least critical for basic growth
            ]
            
            health_score = sum(score * weight for score, weight in health_components)
            
            # Get recent dosing totals
            recent_dosing = await self._get_recent_dosing_totals()
            
            # Days since last reservoir change (placeholder - would track from config changes)
            days_since_change = await self._get_days_since_reservoir_change()
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "ph_in_spec": ph_in_spec,
                "ec_in_spec": ec_in_spec,
                "temp_in_spec": temp_in_spec,
                "humidity_in_spec": humidity_in_spec,
                "co2_in_spec": co2_in_spec,
                "health_score": round(health_score, 3),
                "ph_value": water.get('ph'),
                "ec_value": water.get('ec'),
                "temp_value": air.get('temperature'),
                "humidity_value": air.get('humidity'),
                "co2_value": air.get('co2'),
                "ml_total_24h": recent_dosing.get('total_24h', 0),
                "pump_a_ml_24h": recent_dosing.get('pump_a_24h', 0),
                "pump_b_ml_24h": recent_dosing.get('pump_b_24h', 0),
                "ph_pump_ml_24h": recent_dosing.get('ph_pump_24h', 0),
                "days_since_reservoir_change": days_since_change
            }
            
        except Exception as e:
            self.logger.error(f"KPI calculation failed: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def calculate_period_kpis(self, period_hours: int = 24) -> Dict[str, Any]:
        """Calculate KPIs for a specific time period"""
        try:
            # Get sensor data for the period
            sensor_data = await self.db.get_recent_sensor_data(hours=period_hours)
            
            if not sensor_data:
                return {
                    "error": "No sensor data available for period",
                    "period_hours": period_hours,
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            # Extract values for statistical analysis
            ph_values = [r['ph'] for r in sensor_data if r['ph'] is not None]
            ec_values = [r['ec'] for r in sensor_data if r['ec'] is not None]
            temp_values = [r['air_temp'] for r in sensor_data if r['air_temp'] is not None]
            humidity_values = [r['humidity'] for r in sensor_data if r['humidity'] is not None]
            co2_values = [r['co2'] for r in sensor_data if r['co2'] is not None]
            
            # Calculate averages
            kpis = {
                "timestamp": datetime.utcnow().isoformat(),
                "period_hours": period_hours,
                "reading_count": len(sensor_data)
            }
            
            if ph_values:
                kpis.update({
                    "ph_avg": round(statistics.mean(ph_values), 2),
                    "ph_min": round(min(ph_values), 2),
                    "ph_max": round(max(ph_values), 2),
                    "ph_std": round(statistics.stdev(ph_values) if len(ph_values) > 1 else 0, 3),
                    "ph_in_spec_pct": round(self._calculate_in_spec_percentage(ph_values, 5.5, 6.5), 1)
                })
            
            if ec_values:
                kpis.update({
                    "ec_avg": round(statistics.mean(ec_values), 2),
                    "ec_min": round(min(ec_values), 2),
                    "ec_max": round(max(ec_values), 2),
                    "ec_std": round(statistics.stdev(ec_values) if len(ec_values) > 1 else 0, 3),
                    "ec_in_spec_pct": round(self._calculate_in_spec_percentage(ec_values, 1.2, 2.0), 1)
                })
            
            if temp_values:
                kpis.update({
                    "temp_avg": round(statistics.mean(temp_values), 1),
                    "temp_min": round(min(temp_values), 1),
                    "temp_max": round(max(temp_values), 1),
                    "temp_std": round(statistics.stdev(temp_values) if len(temp_values) > 1 else 0, 2),
                    "temp_in_spec_pct": round(self._calculate_in_spec_percentage(temp_values, 18, 26), 1)
                })
            
            if humidity_values:
                kpis.update({
                    "humidity_avg": round(statistics.mean(humidity_values), 1),
                    "humidity_min": round(min(humidity_values), 1),
                    "humidity_max": round(max(humidity_values), 1),
                    "humidity_in_spec_pct": round(self._calculate_in_spec_percentage(humidity_values, 50, 70), 1)
                })
            
            if co2_values:
                kpis.update({
                    "co2_avg": round(statistics.mean(co2_values), 0),
                    "co2_min": min(co2_values),
                    "co2_max": max(co2_values),
                    "co2_in_spec_pct": round(self._calculate_in_spec_percentage(co2_values, 400, 1200), 1)
                })
            
            # Calculate overall health score for period
            health_scores = []
            for reading in sensor_data:
                if all(reading[key] is not None for key in ['ph', 'ec', 'air_temp', 'humidity', 'co2']):
                    ph_score = 1.0 if 5.5 <= reading['ph'] <= 6.5 else 0.0
                    ec_score = 1.0 if 1.2 <= reading['ec'] <= 2.0 else 0.0
                    temp_score = 1.0 if 18 <= reading['air_temp'] <= 26 else 0.0
                    humid_score = 1.0 if 50 <= reading['humidity'] <= 70 else 0.0
                    co2_score = 1.0 if 400 <= reading['co2'] <= 1200 else 0.0
                    
                    health_score = (ph_score * 0.3 + ec_score * 0.25 + temp_score * 0.2 + 
                                  humid_score * 0.15 + co2_score * 0.1)
                    health_scores.append(health_score)
            
            if health_scores:
                kpis["health_score"] = round(statistics.mean(health_scores), 3)
            
            # Get dosing totals for period
            actions = await self.db.get_recent_actions(hours=period_hours)
            dosing_totals = self._calculate_dosing_totals(actions)
            kpis.update(dosing_totals)
            
            return kpis
            
        except Exception as e:
            self.logger.error(f"Period KPI calculation failed: {e}")
            return {
                "error": str(e),
                "period_hours": period_hours,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def calculate_7day_trends(self) -> Dict[str, Any]:
        """Calculate 7-day moving averages and trends"""
        try:
            # Get 7 days of KPI rollups
            kpi_history = await self.db.get_kpi_history(days=7)
            
            if len(kpi_history) < 2:
                return {
                    "error": "Insufficient data for trend analysis",
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            # Calculate moving averages for key metrics
            ph_values = [k['ph_avg'] for k in kpi_history if k.get('ph_avg') is not None]
            ec_values = [k['ec_avg'] for k in kpi_history if k.get('ec_avg') is not None]
            health_values = [k['health_score'] for k in kpi_history if k.get('health_score') is not None]
            
            trends = {
                "timestamp": datetime.utcnow().isoformat(),
                "data_points": len(kpi_history)
            }
            
            if ph_values:
                trends.update({
                    "ph_7day_avg": round(statistics.mean(ph_values), 2),
                    "ph_trend": self._calculate_trend(ph_values),
                    "ph_in_spec_7day": round(statistics.mean([k.get('ph_in_spec_pct', 0) for k in kpi_history]), 1)
                })
            
            if ec_values:
                trends.update({
                    "ec_7day_avg": round(statistics.mean(ec_values), 2),
                    "ec_trend": self._calculate_trend(ec_values),
                    "ec_in_spec_7day": round(statistics.mean([k.get('ec_in_spec_pct', 0) for k in kpi_history]), 1)
                })
            
            if health_values:
                trends.update({
                    "health_7day_avg": round(statistics.mean(health_values), 3),
                    "health_trend": self._calculate_trend(health_values)
                })
            
            # Calculate total dosing for week
            total_ml = sum(k.get('ml_total', 0) for k in kpi_history)
            trends["ml_total_7day"] = round(total_ml, 1)
            
            return trends
            
        except Exception as e:
            self.logger.error(f"7-day trend calculation failed: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def _is_in_range(self, value: Optional[float], min_val: float, max_val: float) -> float:
        """Check if value is in range, return compliance score 0-1"""
        if value is None:
            return 0.0
        
        if min_val <= value <= max_val:
            return 1.0
        
        # Gradual degradation outside range
        if value < min_val:
            deviation = (min_val - value) / min_val
        else:
            deviation = (value - max_val) / max_val
        
        # Return degraded score based on deviation
        return max(0.0, 1.0 - (deviation * 2))  # 50% penalty per 100% deviation
    
    def _calculate_in_spec_percentage(self, values: List[float], min_val: float, max_val: float) -> float:
        """Calculate percentage of values within specification"""
        if not values:
            return 0.0
        
        in_spec_count = sum(1 for v in values if min_val <= v <= max_val)
        return (in_spec_count / len(values)) * 100
    
    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend direction from time series data"""
        if len(values) < 2:
            return "stable"
        
        # Simple linear trend calculation
        n = len(values)
        x_sum = sum(range(n))
        y_sum = sum(values)
        xy_sum = sum(i * values[i] for i in range(n))
        x2_sum = sum(i * i for i in range(n))
        
        slope = (n * xy_sum - x_sum * y_sum) / (n * x2_sum - x_sum * x_sum)
        
        # Classify trend
        if abs(slope) < 0.01:  # Threshold for "stable"
            return "stable"
        elif slope > 0:
            return "increasing"
        else:
            return "decreasing"
    
    def _calculate_dosing_totals(self, actions: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate total dosing amounts from action history"""
        totals = {
            "ml_total": 0.0,
            "pump_a_ml": 0.0,
            "pump_b_ml": 0.0,
            "ph_pump_ml": 0.0
        }
        
        for action in actions:
            if action.get('success', True):  # Only count successful actions
                totals["pump_a_ml"] += action.get('pump_a_ml', 0) or 0
                totals["pump_b_ml"] += action.get('pump_b_ml', 0) or 0
                totals["ph_pump_ml"] += action.get('ph_pump_ml', 0) or 0
        
        totals["ml_total"] = totals["pump_a_ml"] + totals["pump_b_ml"] + totals["ph_pump_ml"]
        
        return totals
    
    async def _get_recent_dosing_totals(self) -> Dict[str, float]:
        """Get dosing totals for last 24 hours"""
        try:
            actions = await self.db.get_recent_actions(hours=24)
            return self._calculate_dosing_totals(actions)
        except Exception as e:
            self.logger.error(f"Failed to get recent dosing totals: {e}")
            return {"total_24h": 0, "pump_a_24h": 0, "pump_b_24h": 0, "ph_pump_24h": 0}
    
    async def _get_days_since_reservoir_change(self) -> int:
        """Get days since last reservoir change"""
        try:
            # This would check config_changes table for reservoir change events
            # For now, return a placeholder
            return 5  # Mock value
        except Exception:
            return 0