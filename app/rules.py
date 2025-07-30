"""
Rules engine implementing "Stable-Unless-Better" logic for hydroponic control
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .memory.db import Database
from .memory.kpis import KPICalculator

class RulesEngine:
    """Implements intelligent rule-based control with stable-unless-better philosophy"""
    
    def __init__(self, config: Dict[str, Any], db: Database = None):
        self.config = config
        self.db = db or Database()
        self.kpi_calc = KPICalculator(self.db)
        self.logger = logging.getLogger(__name__)
        
        # Load safety limits
        self.safety_limits = self._load_safety_limits()
        
        # Rule thresholds
        self.thresholds = {
            'ph_in_spec_threshold': 0.9,          # 90% readings in spec
            'ec_in_spec_threshold': 0.9,          # 90% readings in spec
            'health_score_threshold': 0.8,        # 80% health score
            'stability_threshold': 0.95,          # 95% in-spec for freeze
            'dosing_variance_threshold': 0.2,     # 20% increase over baseline
            'ph_adjustment_limit': 0.1,           # Max pH change per adjustment
            'ec_adjustment_limit': 0.1,           # Max EC change per adjustment
            'reservoir_change_days': {'GREENS': 14, 'FRUITS': 7},
            'freeze_period_days': 14,             # Freeze successful config for 14 days
            'rollback_check_hours': 48            # Check for degradation within 48h
        }
    
    def _load_safety_limits(self) -> Dict[str, Any]:
        """Load safety limits from configuration"""
        try:
            safety_path = Path("app/config/safety_limits.json")
            if safety_path.exists():
                with open(safety_path) as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"Could not load safety limits: {e}")
        
        # Default safety limits
        return {
            "ph_min_absolute": 4.0,
            "ph_max_absolute": 8.0,
            "ec_min_absolute": 0.5,
            "ec_max_absolute": 3.0,
            "temp_min_absolute": 10,
            "temp_max_absolute": 35,
            "max_daily_dose_ml": 200,
            "max_single_dose_ml": 50,
            "fan_max_speed": 100,
            "led_max_power": 100
        }
    
    async def evaluate_rules(self, sensor_data: Dict[str, Any], 
                           current_kpis: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate all rules and return recommended actions"""
        try:
            # Get 7-day trends for decision making
            trends = await self.kpi_calc.calculate_7day_trends()
            
            recommendations = {
                "timestamp": datetime.utcnow().isoformat(),
                "rule_evaluations": [],
                "actions": {},
                "freeze_status": await self._check_freeze_status(trends),
                "rollback_required": await self._check_rollback_required(current_kpis)
            }
            
            # Skip adjustments if system is frozen or rollback required
            if recommendations["freeze_status"]["frozen"]:
                recommendations["rule_evaluations"].append({
                    "rule": "freeze_check",
                    "result": "System frozen - excellent performance maintained",
                    "action": "none"
                })
                return recommendations
            
            if recommendations["rollback_required"]["required"]:
                recommendations["actions"]["rollback"] = recommendations["rollback_required"]
                return recommendations
            
            # Evaluate pH adjustment rules
            ph_action = await self._evaluate_ph_rules(sensor_data, trends)
            if ph_action:
                recommendations["rule_evaluations"].append(ph_action)
                if "action" in ph_action:
                    recommendations["actions"]["ph_adjustment"] = ph_action["action"]
            
            # Evaluate EC adjustment rules
            ec_action = await self._evaluate_ec_rules(sensor_data, trends, current_kpis)
            if ec_action:
                recommendations["rule_evaluations"].append(ec_action)
                if "action" in ec_action:
                    recommendations["actions"]["ec_adjustment"] = ec_action["action"]
            
            # Evaluate environmental control rules
            env_actions = await self._evaluate_environmental_rules(sensor_data, current_kpis)
            if env_actions:
                recommendations["rule_evaluations"].extend(env_actions)
                for action in env_actions:
                    if "action" in action:
                        action_type = action.get("type", "environmental")
                        recommendations["actions"][action_type] = action["action"]
            
            # Evaluate reservoir change rules
            reservoir_action = await self._evaluate_reservoir_rules(current_kpis)
            if reservoir_action:
                recommendations["rule_evaluations"].append(reservoir_action)
                if "action" in reservoir_action:
                    recommendations["actions"]["reservoir"] = reservoir_action["action"]
            
            return recommendations
            
        except Exception as e:
            self.logger.error(f"Rules evaluation failed: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _evaluate_ph_rules(self, sensor_data: Dict[str, Any], 
                               trends: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Evaluate pH adjustment rules"""
        try:
            current_ph = sensor_data.get('water', {}).get('ph')
            ph_target = self.config.get('targets', {}).get('ph_target', 6.0)
            ph_in_spec_7day = trends.get('ph_in_spec_7day', 100)
            
            if current_ph is None:
                return None
            
            # Rule: Adjust pH if 7-day in-spec < 90%
            if ph_in_spec_7day < (self.thresholds['ph_in_spec_threshold'] * 100):
                
                # Calculate adjustment direction and amount
                ph_deviation = current_ph - ph_target
                
                # Only adjust if deviation is significant (> 0.2 pH units)
                if abs(ph_deviation) > 0.2:
                    
                    # Limit adjustment to maximum safe amount
                    adjustment = min(abs(ph_deviation) * 0.5, self.thresholds['ph_adjustment_limit'])
                    
                    if ph_deviation > 0:  # pH too high, need to lower
                        dosage_ml = self._calculate_ph_down_dosage(adjustment)
                        reason = f"pH {current_ph} > target {ph_target}, 7-day in-spec: {ph_in_spec_7day}%"
                    else:  # pH too low, need to raise
                        dosage_ml = self._calculate_ph_up_dosage(adjustment)
                        reason = f"pH {current_ph} < target {ph_target}, 7-day in-spec: {ph_in_spec_7day}%"
                    
                    # Safety check
                    if self._is_dosage_safe('ph_pump', dosage_ml):
                        return {
                            "rule": "ph_adjustment",
                            "result": f"pH adjustment needed: {reason}",
                            "action": {
                                "type": "dose",
                                "ph_pump": {
                                    "ml": round(dosage_ml, 1),
                                    "reason": reason
                                }
                            }
                        }
            
            return {
                "rule": "ph_check",
                "result": f"pH stable: current {current_ph}, 7-day in-spec: {ph_in_spec_7day}%",
                "action": None
            }
            
        except Exception as e:
            self.logger.error(f"pH rule evaluation failed: {e}")
            return None
    
    async def _evaluate_ec_rules(self, sensor_data: Dict[str, Any], 
                               trends: Dict[str, Any], 
                               current_kpis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Evaluate EC adjustment rules"""
        try:
            current_ec = sensor_data.get('water', {}).get('ec')
            ec_target = self.config.get('targets', {}).get('ec_target', 1.6)
            ec_in_spec_7day = trends.get('ec_in_spec_7day', 100)
            health_score = current_kpis.get('health_score', 1.0)
            ml_total_7day = trends.get('ml_total_7day', 0)
            
            if current_ec is None:
                return None
            
            # Rule 1: Raise EC if low in-spec and low health score
            if (ec_in_spec_7day < (self.thresholds['ec_in_spec_threshold'] * 100) and 
                health_score < self.thresholds['health_score_threshold']):
                
                if current_ec < ec_target:
                    adjustment = min(ec_target - current_ec, self.thresholds['ec_adjustment_limit'])
                    dosage_ml = self._calculate_nutrient_dosage(adjustment, increase=True)
                    
                    if self._is_dosage_safe('pump_a', dosage_ml):
                        return {
                            "rule": "ec_increase",
                            "result": f"EC increase needed: health {health_score}, in-spec {ec_in_spec_7day}%",
                            "action": {
                                "type": "dose",
                                "pump_a": {
                                    "ml": round(dosage_ml * 0.6, 1),  # Part A
                                    "reason": f"Raise EC from {current_ec} toward {ec_target}"
                                },
                                "pump_b": {
                                    "ml": round(dosage_ml * 0.4, 1),  # Part B
                                    "reason": f"Raise EC from {current_ec} toward {ec_target}"
                                }
                            }
                        }
            
            # Rule 2: Lower EC if excessive dosing detected
            baseline_ml = self.config.get('baseline_dosing_ml_per_week', 50)
            if ml_total_7day > baseline_ml * (1 + self.thresholds['dosing_variance_threshold']):
                if current_ec > ec_target and ec_in_spec_7day > 95:
                    adjustment = min(current_ec - ec_target, self.thresholds['ec_adjustment_limit'])
                    
                    return {
                        "rule": "ec_decrease",
                        "result": f"Excessive dosing detected: {ml_total_7day}ml > {baseline_ml}ml baseline",
                        "action": {
                            "type": "config_change",
                            "ec_target": round(ec_target - adjustment, 2),
                            "reason": f"Reduce EC target due to excessive dosing"
                        }
                    }
            
            return {
                "rule": "ec_check", 
                "result": f"EC stable: current {current_ec}, target {ec_target}, 7-day in-spec: {ec_in_spec_7day}%"
            }
            
        except Exception as e:
            self.logger.error(f"EC rule evaluation failed: {e}")
            return None
    
    async def _evaluate_environmental_rules(self, sensor_data: Dict[str, Any],
                                          current_kpis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluate environmental control rules"""
        actions = []
        
        try:
            air = sensor_data.get('air', {})
            light = sensor_data.get('light', {})
            current_temp = air.get('temperature')
            current_humidity = air.get('humidity')
            current_lux = light.get('lux', 0)
            
            # Temperature control
            if current_temp is not None:
                temp_target = self.config.get('targets', {}).get('temp_target', 22)
                temp_range = 2.0  # ±2°C tolerance
                
                if current_temp > temp_target + temp_range:
                    # Too hot - increase fan speed
                    fan_speed = min(80, int((current_temp - temp_target) * 20))
                    actions.append({
                        "rule": "temperature_cooling",
                        "result": f"Temperature {current_temp}°C > {temp_target + temp_range}°C",
                        "type": "fan",
                        "action": {
                            "fan_speed": fan_speed,
                            "duration_minutes": 30,
                            "reason": f"Cooling: temperature {current_temp}°C too high"
                        }
                    })
                
                elif current_temp < temp_target - temp_range:
                    # Too cold - reduce fan, maybe increase LED heat
                    actions.append({
                        "rule": "temperature_heating",
                        "result": f"Temperature {current_temp}°C < {temp_target - temp_range}°C",
                        "type": "environmental",
                        "action": {
                            "fan_speed": 10,  # Minimal fan
                            "reason": f"Reduce cooling: temperature {current_temp}°C too low"
                        }
                    })
            
            # Humidity control
            if current_humidity is not None:
                humidity_target = self.config.get('targets', {}).get('humidity_target', 60)
                
                if current_humidity > 80:  # High humidity risk
                    actions.append({
                        "rule": "humidity_control",
                        "result": f"High humidity {current_humidity}% > 80%",
                        "type": "fan",
                        "action": {
                            "fan_speed": 60,
                            "duration_minutes": 20,
                            "reason": f"Humidity control: {current_humidity}% too high"
                        }
                    })
            
            # Light control (basic DLI management)
            if current_lux > 30000:  # Very bright conditions
                current_ec = sensor_data.get('water', {}).get('ec', 0)
                if current_ec > 2.0:  # High light + high EC = potential stress
                    actions.append({
                        "rule": "light_stress_prevention",
                        "result": f"High light {current_lux} lux + high EC {current_ec} = stress risk",
                        "type": "led",
                        "action": {
                            "led_power": 70,  # Reduce LED power
                            "reason": "Prevent light stress with high EC"
                        }
                    })
            
            return actions
            
        except Exception as e:
            self.logger.error(f"Environmental rules evaluation failed: {e}")
            return []
    
    async def _evaluate_reservoir_rules(self, current_kpis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Evaluate reservoir change rules"""
        try:
            days_since_change = current_kpis.get('days_since_reservoir_change', 0)
            grow_phase = self.config.get('grow_phase', 'GREENS')
            max_days = self.thresholds['reservoir_change_days'].get(grow_phase, 14)
            
            if days_since_change >= max_days:
                return {
                    "rule": "reservoir_change_cadence",
                    "result": f"Reservoir change due: {days_since_change} days >= {max_days} days for {grow_phase}",
                    "action": {
                        "type": "reservoir_change",
                        "reason": f"Scheduled change for {grow_phase} phase after {days_since_change} days"
                    }
                }
            
            return {
                "rule": "reservoir_check",
                "result": f"Reservoir OK: {days_since_change}/{max_days} days for {grow_phase}"
            }
            
        except Exception as e:
            self.logger.error(f"Reservoir rules evaluation failed: {e}")
            return None
    
    async def _check_freeze_status(self, trends: Dict[str, Any]) -> Dict[str, Any]:
        """Check if system should be frozen due to excellent performance"""
        try:
            health_7day = trends.get('health_7day_avg', 0)
            ph_in_spec = trends.get('ph_in_spec_7day', 0)
            ec_in_spec = trends.get('ec_in_spec_7day', 0)
            
            # Check if all metrics are excellent
            freeze_threshold = self.thresholds['stability_threshold'] * 100  # 95%
            
            should_freeze = (
                health_7day >= 0.95 and
                ph_in_spec >= freeze_threshold and
                ec_in_spec >= freeze_threshold
            )
            
            return {
                "frozen": should_freeze,
                "reason": f"Health: {health_7day:.2f}, pH in-spec: {ph_in_spec}%, EC in-spec: {ec_in_spec}%",
                "freeze_until": (datetime.utcnow() + timedelta(days=self.thresholds['freeze_period_days'])).isoformat() if should_freeze else None
            }
            
        except Exception as e:
            self.logger.error(f"Freeze status check failed: {e}")
            return {"frozen": False, "error": str(e)}
    
    async def _check_rollback_required(self, current_kpis: Dict[str, Any]) -> Dict[str, Any]:
        """Check if recent config changes caused degradation"""
        try:
            # Get recent config changes and KPI history
            rollback_hours = self.thresholds['rollback_check_hours']
            
            # This would check if KPIs degraded significantly after config change
            # For now, implement basic health score check
            health_score = current_kpis.get('health_score', 1.0)
            
            if health_score < 0.6:  # Significant degradation
                return {
                    "required": True,
                    "reason": f"Health score {health_score} indicates significant degradation",
                    "rollback_to": "previous_stable_config"
                }
            
            return {"required": False}
            
        except Exception as e:
            self.logger.error(f"Rollback check failed: {e}")
            return {"required": False, "error": str(e)}
    
    def _calculate_ph_down_dosage(self, ph_adjustment: float) -> float:
        """Calculate pH down dosage in ml"""
        # Empirical formula: 1ml per 0.1 pH reduction per 10L
        reservoir_volume = self.config.get('reservoir_volume_l', 20)
        return (ph_adjustment / 0.1) * (reservoir_volume / 10)
    
    def _calculate_ph_up_dosage(self, ph_adjustment: float) -> float:
        """Calculate pH up dosage in ml"""
        # pH up typically more concentrated than pH down
        reservoir_volume = self.config.get('reservoir_volume_l', 20)
        return (ph_adjustment / 0.1) * (reservoir_volume / 10) * 0.7
    
    def _calculate_nutrient_dosage(self, ec_adjustment: float, increase: bool = True) -> float:
        """Calculate nutrient dosage to achieve EC adjustment"""
        # Empirical formula: ~5ml per 0.1 EC increase per 10L
        reservoir_volume = self.config.get('reservoir_volume_l', 20)
        base_dosage = (ec_adjustment / 0.1) * 5 * (reservoir_volume / 10)
        
        return base_dosage if increase else base_dosage * 0.5  # Dilution is harder
    
    def _is_dosage_safe(self, pump_type: str, dosage_ml: float) -> bool:
        """Check if dosage is within safety limits"""
        max_single = self.safety_limits.get('max_single_dose_ml', 50)
        
        if pump_type == 'ph_pump':
            max_single = min(max_single, 20)  # pH pump has lower limit
        
        return 0 < dosage_ml <= max_single
    
    async def apply_stable_unless_better_logic(self, proposed_actions: Dict[str, Any],
                                             current_performance: Dict[str, Any]) -> Dict[str, Any]:
        """Apply stable-unless-better filter to proposed actions"""
        try:
            # If current performance is good, reduce action aggressiveness
            health_score = current_performance.get('health_score', 0.8)
            
            if health_score > 0.9:  # Excellent performance
                # Reduce dosing amounts by 50%
                filtered_actions = {}
                for action_type, action_data in proposed_actions.items():
                    if action_type == 'dose':
                        filtered_actions[action_type] = {}
                        for pump, dose_data in action_data.items():
                            if isinstance(dose_data, dict) and 'ml' in dose_data:
                                filtered_ml = dose_data['ml'] * 0.5
                                filtered_actions[action_type][pump] = {
                                    'ml': round(filtered_ml, 1),
                                    'reason': f"Reduced dose (stable system): {dose_data.get('reason', '')}"
                                }
                    else:
                        filtered_actions[action_type] = action_data
                
                return {
                    "filtered_actions": filtered_actions,
                    "stability_factor": 0.5,
                    "reason": f"High performance ({health_score:.2f}) - reduced intervention"
                }
            
            elif health_score > 0.8:  # Good performance
                # Slight reduction
                filtered_actions = {}
                for action_type, action_data in proposed_actions.items():
                    if action_type == 'dose':
                        filtered_actions[action_type] = {}
                        for pump, dose_data in action_data.items():
                            if isinstance(dose_data, dict) and 'ml' in dose_data:
                                filtered_ml = dose_data['ml'] * 0.8
                                filtered_actions[action_type][pump] = {
                                    'ml': round(filtered_ml, 1),
                                    'reason': f"Slightly reduced (good system): {dose_data.get('reason', '')}"
                                }
                    else:
                        filtered_actions[action_type] = action_data
                
                return {
                    "filtered_actions": filtered_actions,
                    "stability_factor": 0.8,
                    "reason": f"Good performance ({health_score:.2f}) - slight reduction"
                }
            
            else:  # Poor performance - allow full actions
                return {
                    "filtered_actions": proposed_actions,
                    "stability_factor": 1.0,
                    "reason": f"Poor performance ({health_score:.2f}) - full intervention needed"
                }
                
        except Exception as e:
            self.logger.error(f"Stable-unless-better logic failed: {e}")
            return {
                "filtered_actions": proposed_actions,
                "stability_factor": 1.0,
                "error": str(e)
            }