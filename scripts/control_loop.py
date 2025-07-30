#!/usr/bin/env python3
"""
Main control loop script - runs every 10 minutes to make control decisions
"""

import asyncio
import json
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sensor_io import SensorInterface
from app.actuators import ActuatorController
from app.llm_agent import LLMAgent
from app.rules import RulesEngine
from app.memory.db import Database
from app.memory.kpis import KPICalculator
from app.utils import setup_logging, create_alert
from app.utils import load_config


class ControlLoop:
    """Main control loop orchestrator"""
    
    def __init__(self):
        self.config = load_config()
        self.db = None
        self.sensors = None
        self.actuators = None
        self.llm_agent = None
        self.rules_engine = None
        self.kpi_calc = None
        self.logger = logging.getLogger(__name__)
        
        # Mock mode for development
        self.mock_mode = os.getenv('MOCK_HARDWARE', 'true').lower() == 'true'
        self.use_llm = os.getenv('USE_LLM', 'true').lower() == 'true'
    
    async def initialize(self):
        """Initialize all components"""
        try:
            self.db = Database()
            await self.db.init()
            
            self.sensors = SensorInterface(mock=self.mock_mode)
            self.actuators = ActuatorController(mock=self.mock_mode)
            self.kpi_calc = KPICalculator(self.db)
            self.rules_engine = RulesEngine(self.config, self.db)
            
            if self.use_llm:
                try:
                    self.llm_agent = LLMAgent()
                    self.logger.info("LLM agent initialized")
                except Exception as e:
                    self.logger.warning(f"LLM agent initialization failed: {e}")
                    self.use_llm = False
            
            self.logger.info("Control loop initialized")
            
        except Exception as e:
            self.logger.error(f"Control loop initialization failed: {e}")
            raise
    
    async def run_control_cycle(self) -> dict:
        """Execute one complete control cycle"""
        cycle_start = datetime.utcnow()
        
        try:
            self.logger.info("Starting control cycle")
            
            # Step 1: Get current sensor data
            sensor_data = await self.sensors.read_all()
            
            # Step 2: Calculate current KPIs
            current_kpis = await self.kpi_calc.calculate_current_kpis(
                sensor_data, self.config.get('targets', {})
            )
            
            # Step 3: Run rules engine evaluation
            rules_result = await self.rules_engine.evaluate_rules(sensor_data, current_kpis)
            
            # Step 4: Get LLM decision (if enabled and available)
            llm_result = None
            if self.use_llm and self.llm_agent:
                try:
                    recent_actions = await self.db.get_recent_actions(hours=6)
                    llm_result = await self.llm_agent.make_decision(
                        sensor_data, self.config, recent_actions
                    )
                except Exception as e:
                    self.logger.error(f"LLM decision failed: {e}")
                    llm_result = {"error": str(e)}
            
            # Step 5: Combine decisions from rules and LLM
            combined_decisions = self._combine_decisions(rules_result, llm_result)
            
            # Step 6: Apply stable-unless-better logic
            filtered_decisions = await self.rules_engine.apply_stable_unless_better_logic(
                combined_decisions, current_kpis
            )
            
            # Step 7: Execute approved actions
            execution_results = await self._execute_actions(filtered_decisions['filtered_actions'])
            
            # Step 8: Store cycle results
            cycle_result = {
                "timestamp": cycle_start.isoformat(),
                "cycle_duration_ms": int((datetime.utcnow() - cycle_start).total_seconds() * 1000),
                "sensor_data": sensor_data,
                "kpis": current_kpis,
                "rules_evaluation": rules_result,
                "llm_decision": llm_result,
                "combined_decisions": combined_decisions,
                "filtered_decisions": filtered_decisions,
                "execution_results": execution_results,
                "success": True
            }
            
            # Store control cycle in database
            if execution_results.get('executed'):
                await self.db.store_actuator_action({
                    "timestamp": cycle_start.isoformat(),
                    "action_type": "control_cycle",
                    **execution_results,
                    "cycle_data": json.dumps(cycle_result)
                })
            
            self.logger.info(f"Control cycle completed in {cycle_result['cycle_duration_ms']}ms")
            
            return cycle_result
            
        except Exception as e:
            self.logger.error(f"Control cycle failed: {e}")
            
            # Store error event
            error_alert = create_alert(
                "error",
                "system",
                f"Control cycle failed: {str(e)}",
                {"error": str(e), "cycle_start": cycle_start.isoformat()}
            )
            
            if self.db:
                try:
                    await self.db.store_system_event(error_alert)
                except Exception as db_error:
                    self.logger.error(f"Failed to store control cycle error: {db_error}")
            
            return {
                "timestamp": cycle_start.isoformat(),
                "success": False,
                "error": str(e)
            }
    
    def _combine_decisions(self, rules_result: dict, llm_result: dict = None) -> dict:
        """Combine decisions from rules engine and LLM"""
        combined = {
            "timestamp": datetime.utcnow().isoformat(),
            "sources": {"rules": True, "llm": llm_result is not None and "error" not in llm_result}
        }
        
        # Start with rules engine decisions
        rules_actions = rules_result.get('actions', {})
        
        # If LLM is available and successful, merge its decisions
        if llm_result and "error" not in llm_result:
            llm_decisions = llm_result.get('decisions', {})
            
            # Rules engine takes precedence for safety-critical decisions
            # LLM can supplement with additional insights
            
            # Merge dosing decisions (rules engine overrides for safety)
            if 'dose' in llm_decisions and not any(
                key in rules_actions for key in ['ph_adjustment', 'ec_adjustment']
            ):
                combined['dose'] = llm_decisions['dose']
                combined['dose_reason'] = llm_result.get('reasoning', 'LLM decision')
            
            # Merge environmental controls (LLM can provide more nuanced control)
            for control_type in ['fan', 'led', 'heater']:
                if control_type in llm_decisions:
                    # Check if rules engine has conflicting decision
                    if not any(key.startswith(control_type) for key in rules_actions):
                        combined[control_type] = llm_decisions[control_type]
            
            combined['llm_confidence'] = llm_result.get('confidence', 0.5)
        
        # Apply rules engine decisions (these override LLM where there's conflict)
        for action_type, action_data in rules_actions.items():
            if action_type == 'ph_adjustment' and 'action' in action_data:
                combined['dose'] = action_data['action']
                combined['dose_reason'] = f"Rules: {action_data['result']}"
            elif action_type == 'ec_adjustment' and 'action' in action_data:
                if 'dose' in combined:
                    # Merge EC adjustment with existing dose
                    ec_action = action_data['action']
                    for pump, dose_data in ec_action.items():
                        combined['dose'][pump] = dose_data
                else:
                    combined['dose'] = action_data['action']
                combined['dose_reason'] = f"Rules: {action_data['result']}"
            elif action_type in ['fan', 'led'] and 'action' in action_data:
                combined[action_type] = action_data['action']
        
        # Handle emergency situations
        if rules_result.get('rollback_required', {}).get('required'):
            combined = {
                "emergency_rollback": True,
                "rollback_reason": rules_result['rollback_required']['reason'],
                "timestamp": combined['timestamp']
            }
        
        return combined
    
    async def _execute_actions(self, actions: dict) -> dict:
        """Execute approved control actions"""
        execution_results = {
            "timestamp": datetime.utcnow().isoformat(),
            "executed": {},
            "skipped": {},
            "errors": []
        }
        
        try:
            # Handle emergency rollback
            if actions.get('emergency_rollback'):
                self.logger.critical(f"Emergency rollback triggered: {actions['rollback_reason']}")
                
                # Emergency stop all actuators
                stop_result = await self.actuators.emergency_stop()
                execution_results['executed']['emergency_stop'] = stop_result
                
                return execution_results
            
            # Execute dosing commands
            if 'dose' in actions:
                dose_result = await self.actuators.dose_nutrients(actions['dose'])
                execution_results['executed']['dosing'] = dose_result
                
                if dose_result.get('errors'):
                    execution_results['errors'].extend(dose_result['errors'])
            
            # Execute fan control
            if 'fan' in actions:
                fan_data = actions['fan']
                fan_result = await self.actuators.control_fan(
                    fan_data.get('fan_speed', 0),
                    fan_data.get('duration_minutes')
                )
                execution_results['executed']['fan'] = fan_result
            
            # Execute LED control
            if 'led' in actions:
                led_data = actions['led']
                led_result = await self.actuators.control_led(
                    led_data.get('led_power', 0),
                    led_data.get('schedule')
                )
                execution_results['executed']['led'] = led_result
            
            # Log execution summary
            if execution_results['executed']:
                action_summary = []
                if 'dosing' in execution_results['executed']:
                    executed_doses = execution_results['executed']['dosing'].get('executed', {})
                    if executed_doses:
                        dose_desc = [f"{pump} {data['ml']}ml" for pump, data in executed_doses.items()]
                        action_summary.append(f"Dosed: {', '.join(dose_desc)}")
                
                if 'fan' in execution_results['executed']:
                    fan_speed = execution_results['executed']['fan']['fan_speed']
                    action_summary.append(f"Fan: {fan_speed}%")
                
                if 'led' in execution_results['executed']:
                    led_power = execution_results['executed']['led']['led_power']
                    action_summary.append(f"LED: {led_power}%")
                
                self.logger.info(f"Actions executed: {', '.join(action_summary)}")
            else:
                self.logger.info("No actions executed this cycle")
            
            return execution_results
            
        except Exception as e:
            self.logger.error(f"Action execution failed: {e}")
            execution_results['errors'].append(str(e))
            return execution_results
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.actuators:
            await self.actuators.shutdown()
        
        if self.db:
            await self.db.close()
        
        self.logger.info("Control loop cleanup complete")


async def main():
    """Main execution function"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    control_loop = ControlLoop()
    
    try:
        logger.info("Starting control loop cycle")
        
        await control_loop.initialize()
        result = await control_loop.run_control_cycle()
        
        if result['success']:
            logger.info("Control cycle completed successfully")
            print(json.dumps(result, indent=2, default=str))
            exit_code = 0
        else:
            logger.error(f"Control cycle failed: {result.get('error')}")
            print(json.dumps(result, indent=2, default=str))
            exit_code = 1
        
    except Exception as e:
        logger.error(f"Control loop script failed: {e}")
        print(json.dumps({
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }, indent=2))
        exit_code = 2
    
    finally:
        await control_loop.cleanup()
    
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())