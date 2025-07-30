"""
Main application entry point
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .utils import load_config
from .memory.db import Database
from .sensor_io import SensorInterface
from .actuators import ActuatorController
from .llm_agent import LLMAgent
from .rules import RulesEngine
from .utils import setup_logging

app = FastAPI(title="Open Hydro O3", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class HydroController:
    def __init__(self):
        self.config = load_config()
        self.db = Database()
        self.sensors = SensorInterface(mock=os.getenv("MOCK_HARDWARE", "true").lower() == "true")
        self.actuators = ActuatorController(mock=os.getenv("MOCK_HARDWARE", "true").lower() == "true")
        self.llm = LLMAgent()
        self.rules = RulesEngine(self.config)
        self.running = False
        
    async def start(self):
        """Start the hydroponic controller"""
        setup_logging()
        logging.info("Starting Open Hydro O3 controller")
        
        await self.db.init()
        self.running = True
        
        # Register shutdown handlers
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        
        logging.info("Controller started successfully")
        
    async def shutdown(self):
        """Graceful shutdown"""
        logging.info("Shutting down controller...")
        self.running = False
        await self.actuators.shutdown()
        await self.db.close()
        logging.info("Controller shutdown complete")
        
    def _shutdown_handler(self, signum, frame):
        """Handle shutdown signals"""
        logging.info(f"Received signal {signum}, initiating shutdown")
        asyncio.create_task(self.shutdown())

controller = HydroController()

@app.on_event("startup")
async def startup_event():
    await controller.start()

@app.on_event("shutdown") 
async def shutdown_event():
    await controller.shutdown()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.get("/status")
async def get_status():
    """Get current system status"""
    try:
        sensor_data = await controller.sensors.read_all()
        actuator_status = await controller.actuators.get_status()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "sensors": sensor_data,
            "actuators": actuator_status,
            "running": controller.running
        }
    except Exception as e:
        logging.error(f"Error getting status: {e}")
        return {"error": str(e)}, 500

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)