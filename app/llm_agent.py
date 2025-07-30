"""
LLM Agent interface for OpenAI o3 model integration
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

import openai
from openai import OpenAI

from .memory.vector import VectorMemory
from .memory.kpis import KPICalculator
from .utils import load_json_schema, validate_json_schema

class LLMAgent:
    """Manages LLM interactions with OpenAI o3 model"""
    
    SYSTEM_PROMPT = """You are an intelligent hydroponic system controller with expertise in plant biology, nutrient management, and environmental control.

Your role is to analyze sensor data and make precise decisions about:
- Nutrient dosing (pumps A, B, pH adjustment)
- Environmental controls (fan speed, LED intensity, temperature)
- System maintenance and optimization

Key principles:
1. SAFETY FIRST: Never exceed safety limits defined in the configuration
2. STABLE-UNLESS-BETTER: Only make changes if current conditions are suboptimal
3. GRADUAL ADJUSTMENTS: Make small, incremental changes rather than large corrections
4. DATA-DRIVEN: Base decisions on sensor trends, not single readings
5. PLANT-CENTRIC: Prioritize plant health over perfect target values

You must respond in valid JSON format using the provided tool schemas. Each action must include a clear reason for the decision.

Current grow phase: {grow_phase}
Target ranges: pH {ph_range}, EC {ec_range}, Temperature {temp_range}°C
Days since reservoir change: {days_since_change}

Recent context:
{memory_context}

Use your expertise to maintain optimal growing conditions while following the stable-unless-better philosophy."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.client = None
        self.vector_memory = VectorMemory()
        self.kpi_calc = KPICalculator()
        
        # Load tool schemas
        self.schemas = self._load_schemas()
        
        # Initialize OpenAI client
        self._init_client()
    
    def _init_client(self):
        """Initialize OpenAI client"""
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            self.logger.error("OPENAI_API_KEY not found in environment")
            raise ValueError("OpenAI API key required")
        
        self.client = OpenAI(api_key=api_key)
        self.logger.info("OpenAI client initialized")
    
    def _load_schemas(self) -> Dict[str, Any]:
        """Load JSON schemas for validation"""
        schema_files = [
            'actuator_dose.json',
            'actuator_fan.json', 
            'actuator_led.json',
            'actuator_heater.json'
        ]
        
        schemas = {}
        for schema_file in schema_files:
            try:
                schema_path = f"schemas/{schema_file}"
                schemas[schema_file.replace('.json', '')] = load_json_schema(schema_path)
            except Exception as e:
                self.logger.error(f"Failed to load schema {schema_file}: {e}")
        
        return schemas
    
    async def make_decision(self, sensor_data: Dict[str, Any], 
                          config: Dict[str, Any],
                          recent_actions: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make control decisions based on sensor data and context"""
        try:
            # Get memory context
            memory_context = await self._get_memory_context(sensor_data)
            
            # Calculate current KPIs
            kpis = await self.kpi_calc.calculate_current_kpis(sensor_data)
            
            # Prepare prompt with context
            system_prompt = self._prepare_system_prompt(config, memory_context, kpis)
            
            # Prepare user message with current data
            user_message = self._prepare_user_message(sensor_data, kpis, recent_actions)
            
            # Make API call to o3
            response = await self._call_llm(system_prompt, user_message)
            
            # Validate and parse response
            parsed_response = await self._validate_response(response)
            
            # Store decision in memory
            await self._store_decision(sensor_data, parsed_response)
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "decisions": parsed_response,
                "reasoning": response.get("reasoning", "No reasoning provided"),
                "confidence": response.get("confidence", 0.8),
                "kpis": kpis
            }
            
        except Exception as e:
            self.logger.error(f"LLM decision making failed: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
                "fallback": True
            }
    
    def _prepare_system_prompt(self, config: Dict[str, Any], 
                             memory_context: str, kpis: Dict[str, Any]) -> str:
        """Prepare system prompt with current context"""
        grow_phase = config.get('grow_phase', 'vegetative')
        
        # Extract target ranges from config
        targets = config.get('targets', {})
        ph_range = f"{targets.get('ph_min', 5.5)}-{targets.get('ph_max', 6.5)}"
        ec_range = f"{targets.get('ec_min', 1.2)}-{targets.get('ec_max', 2.0)}"
        temp_range = f"{targets.get('temp_min', 18)}-{targets.get('temp_max', 26)}"
        
        days_since_change = kpis.get('days_since_reservoir_change', 0)
        
        return self.SYSTEM_PROMPT.format(
            grow_phase=grow_phase,
            ph_range=ph_range,
            ec_range=ec_range,
            temp_range=temp_range,
            days_since_change=days_since_change,
            memory_context=memory_context
        )
    
    def _prepare_user_message(self, sensor_data: Dict[str, Any], 
                            kpis: Dict[str, Any],
                            recent_actions: List[Dict[str, Any]] = None) -> str:
        """Prepare user message with current sensor data"""
        message_parts = [
            "CURRENT SENSOR READINGS:",
            json.dumps(sensor_data, indent=2),
            "",
            "CURRENT KPIs:",
            json.dumps(kpis, indent=2)
        ]
        
        if recent_actions:
            message_parts.extend([
                "",
                "RECENT ACTIONS (last 6 hours):",
                json.dumps(recent_actions, indent=2)
            ])
        
        message_parts.extend([
            "",
            "Please analyze the current conditions and provide any necessary control actions.",
            "Respond in JSON format with your decisions and reasoning.",
            "Only take action if current conditions are suboptimal or trending toward problems.",
            "Remember: stable-unless-better principle applies."
        ])
        
        return "\n".join(message_parts)
    
    async def _call_llm(self, system_prompt: str, user_message: str) -> Dict[str, Any]:
        """Make API call to OpenAI o3 model""" 
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
            
            response = self.client.chat.completions.create(
                model="o3-mini",  # Using o3-mini as o3 may not be available yet
                messages=messages,
                temperature=0.0,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            
            try:
                parsed_content = json.loads(content)
                return parsed_content
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse LLM response as JSON: {e}")
                self.logger.error(f"Raw response: {content}")
                return {"error": "Invalid JSON response from LLM"}
                
        except Exception as e:
            self.logger.error(f"OpenAI API call failed: {e}")
            return {"error": str(e)}
    
    async def _validate_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Validate LLM response against schemas"""
        if "error" in response:
            return response
        
        validated_decisions = {}
        
        # Validate each decision type
        for decision_type, decision_data in response.get("decisions", {}).items():
            schema_name = f"actuator_{decision_type}"
            
            if schema_name in self.schemas:
                try:
                    validate_json_schema(decision_data, self.schemas[schema_name])
                    validated_decisions[decision_type] = decision_data
                    self.logger.info(f"Validated {decision_type} decision")
                except Exception as e:
                    self.logger.error(f"Schema validation failed for {decision_type}: {e}")
                    # Skip invalid decisions
            else:
                self.logger.warning(f"No schema found for decision type: {decision_type}")
        
        return {
            "decisions": validated_decisions,
            "reasoning": response.get("reasoning", ""),
            "confidence": response.get("confidence", 0.5)
        }
    
    async def _get_memory_context(self, sensor_data: Dict[str, Any]) -> str:
        """Retrieve relevant context from vector memory"""
        try:
            # Create query from current sensor conditions
            query = f"pH {sensor_data['water']['ph']} EC {sensor_data['water']['ec']} temp {sensor_data['air']['temperature']}"
            
            # Retrieve similar historical situations
            memories = await self.vector_memory.search(query, limit=3)
            
            if not memories:
                return "No relevant historical context found."
            
            context_parts = []
            for memory in memories:
                context_parts.append(f"Similar situation: {memory.get('summary', 'No summary')}")
                if 'outcome' in memory:
                    context_parts.append(f"Outcome: {memory['outcome']}")
                context_parts.append("")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve memory context: {e}")
            return "Memory context unavailable."
    
    async def _store_decision(self, sensor_data: Dict[str, Any], 
                            decision: Dict[str, Any]):
        """Store decision in vector memory for future reference"""
        try:
            # Create summary of situation and decision
            summary = self._create_decision_summary(sensor_data, decision)
            
            # Store in vector memory
            await self.vector_memory.store({
                "timestamp": datetime.utcnow().isoformat(),
                "sensor_data": sensor_data,
                "decision": decision,
                "summary": summary
            })
            
        except Exception as e:
            self.logger.error(f"Failed to store decision in memory: {e}")
    
    def _create_decision_summary(self, sensor_data: Dict[str, Any], 
                               decision: Dict[str, Any]) -> str:
        """Create a text summary of the decision for vector storage"""
        water = sensor_data.get('water', {})
        air = sensor_data.get('air', {})
        
        summary_parts = [
            f"pH {water.get('ph', 'unknown')}",
            f"EC {water.get('ec', 'unknown')}",
            f"temp {air.get('temperature', 'unknown')}°C",
            f"humidity {air.get('humidity', 'unknown')}%"
        ]
        
        decisions = decision.get('decisions', {})
        if decisions:
            actions = []
            for action_type, action_data in decisions.items():
                if action_type == 'dose':
                    doses = []
                    for pump, data in action_data.items():
                        if isinstance(data, dict) and data.get('ml', 0) > 0:
                            doses.append(f"{pump} {data['ml']}ml")
                    if doses:
                        actions.append(f"dosed {', '.join(doses)}")
                elif action_type == 'fan':
                    speed = action_data.get('fan_speed', 0)
                    if speed > 0:
                        actions.append(f"fan {speed}%")
                elif action_type == 'led':
                    power = action_data.get('led_power', 0)
                    actions.append(f"LED {power}%")
            
            if actions:
                summary_parts.append(f"Actions: {', '.join(actions)}")
        
        return " | ".join(summary_parts)
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get LLM agent status"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "model": "o3-mini",
            "schemas_loaded": len(self.schemas),
            "client_initialized": self.client is not None,
            "memory_status": await self.vector_memory.get_status()
        }