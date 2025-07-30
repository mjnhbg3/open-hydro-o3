"""
Vector memory system using ChromaDB for contextual memory storage
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logging.warning("ChromaDB not available, using mock vector memory")

class VectorMemory:
    """Vector-based memory system for contextual storage and retrieval"""
    
    def __init__(self, persist_directory: str = None):
        if persist_directory is None:
            persist_directory = str(Path("~/hydro/chroma").expanduser())
        
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
        self.client = None
        self.collection = None
        self.mock_mode = not CHROMADB_AVAILABLE
        
        if not self.mock_mode:
            self._init_chromadb()
        else:
            self.logger.info("Running vector memory in mock mode")
            self._mock_memories = []
    
    def _init_chromadb(self):
        """Initialize ChromaDB client and collection"""
        try:
            # Initialize client with persistence
            self.client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(anonymized_telemetry=False)
            )
            
            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name="hydro_memories",
                metadata={"description": "Hydroponic system contextual memories"}
            )
            
            self.logger.info(f"ChromaDB initialized with {self.collection.count()} memories")
            
        except Exception as e:
            self.logger.error(f"ChromaDB initialization failed: {e}")
            self.logger.info("Falling back to mock mode")
            self.mock_mode = True
            self._mock_memories = []
    
    async def store(self, memory_data: Dict[str, Any]) -> str:
        """Store a memory with automatic embedding generation"""
        try:
            memory_id = f"memory_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
            
            if self.mock_mode:
                return await self._mock_store(memory_id, memory_data)
            
            # Create text representation for embedding
            text_content = self._create_text_representation(memory_data)
            
            # Store in ChromaDB
            self.collection.add(
                documents=[text_content],
                metadatas=[{
                    "timestamp": memory_data.get("timestamp", datetime.utcnow().isoformat()),
                    "type": memory_data.get("type", "decision"),
                    "data": json.dumps(memory_data)
                }],
                ids=[memory_id]
            )
            
            self.logger.debug(f"Stored memory: {memory_id}")
            return memory_id
            
        except Exception as e:
            self.logger.error(f"Failed to store memory: {e}")
            return await self._mock_store(memory_id, memory_data)
    
    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for similar memories based on query"""
        try:
            if self.mock_mode:
                return await self._mock_search(query, limit)
            
            # Query ChromaDB
            results = self.collection.query(
                query_texts=[query],
                n_results=min(limit, self.collection.count()),
                include=["documents", "metadatas", "distances"]
            )
            
            memories = []
            if results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i]
                    distance = results['distances'][0][i]
                    
                    try:
                        # Parse stored data
                        stored_data = json.loads(metadata.get('data', '{}'))
                        stored_data['similarity_score'] = 1 - distance  # Convert distance to similarity
                        memories.append(stored_data)
                    except json.JSONDecodeError:
                        self.logger.warning(f"Failed to parse stored memory data")
                        continue
            
            return memories
            
        except Exception as e:
            self.logger.error(f"Memory search failed: {e}")
            return await self._mock_search(query, limit)
    
    async def get_recent_memories(self, hours: int = 24, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent memories within specified time window"""
        try:
            if self.mock_mode:
                return self._mock_memories[-limit:] if self._mock_memories else []
            
            # Get all memories and filter by timestamp
            all_memories = self.collection.get(
                include=["metadatas"]
            )
            
            if not all_memories['metadatas']:
                return []
            
            # Filter by timestamp
            cutoff_time = datetime.utcnow().timestamp() - (hours * 3600)
            recent_memories = []
            
            for metadata in all_memories['metadatas']:
                try:
                    timestamp_str = metadata.get('timestamp', '')
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    
                    if timestamp.timestamp() > cutoff_time:
                        data = json.loads(metadata.get('data', '{}'))
                        recent_memories.append(data)
                        
                except (ValueError, json.JSONDecodeError):
                    continue
            
            # Sort by timestamp and limit
            recent_memories.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            return recent_memories[:limit]
            
        except Exception as e:
            self.logger.error(f"Failed to get recent memories: {e}")
            return []
    
    async def delete_old_memories(self, days_to_keep: int = 30):
        """Delete memories older than specified days"""
        try:
            if self.mock_mode:
                # Keep only recent mock memories
                cutoff_time = datetime.utcnow().timestamp() - (days_to_keep * 24 * 3600)
                self._mock_memories = [
                    m for m in self._mock_memories 
                    if datetime.fromisoformat(m.get('timestamp', '')).timestamp() > cutoff_time
                ]
                return
            
            # Get all memories
            all_memories = self.collection.get(
                include=["metadatas"]
            )
            
            if not all_memories['metadatas']:
                return
            
            # Find old memories to delete
            cutoff_time = datetime.utcnow().timestamp() - (days_to_keep * 24 * 3600)
            ids_to_delete = []
            
            for i, metadata in enumerate(all_memories['metadatas']):
                try:
                    timestamp_str = metadata.get('timestamp', '')
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    
                    if timestamp.timestamp() < cutoff_time:
                        ids_to_delete.append(all_memories['ids'][i])
                        
                except ValueError:
                    continue
            
            # Delete old memories
            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
                self.logger.info(f"Deleted {len(ids_to_delete)} old memories")
            
        except Exception as e:
            self.logger.error(f"Failed to delete old memories: {e}")
    
    def _create_text_representation(self, memory_data: Dict[str, Any]) -> str:
        """Create text representation of memory for embedding"""
        text_parts = []
        
        # Add timestamp context
        if 'timestamp' in memory_data:
            try:
                dt = datetime.fromisoformat(memory_data['timestamp'].replace('Z', '+00:00'))
                text_parts.append(f"Time: {dt.strftime('%Y-%m-%d %H:%M')}")
            except ValueError:
                pass
        
        # Add sensor context
        if 'sensor_data' in memory_data:
            sensor_data = memory_data['sensor_data']
            water = sensor_data.get('water', {})
            air = sensor_data.get('air', {})
            
            text_parts.append(f"pH {water.get('ph', 'unknown')}")
            text_parts.append(f"EC {water.get('ec', 'unknown')} mS/cm")
            text_parts.append(f"water temp {water.get('temperature', 'unknown')}°C")
            text_parts.append(f"air temp {air.get('temperature', 'unknown')}°C")
            text_parts.append(f"humidity {air.get('humidity', 'unknown')}%")
            text_parts.append(f"CO2 {air.get('co2', 'unknown')} ppm")
        
        # Add decision context
        if 'decision' in memory_data:
            decision = memory_data['decision']
            decisions = decision.get('decisions', {})
            
            if 'dose' in decisions:
                dose_data = decisions['dose']
                doses = []
                for pump, data in dose_data.items():
                    if isinstance(data, dict) and data.get('ml', 0) > 0:
                        doses.append(f"{pump} {data['ml']}ml")
                if doses:
                    text_parts.append(f"Dosed: {', '.join(doses)}")
            
            if 'fan' in decisions:
                fan_data = decisions['fan']
                speed = fan_data.get('fan_speed', 0)
                if speed > 0:
                    text_parts.append(f"Fan: {speed}%")
            
            if 'led' in decisions:
                led_data = decisions['led']
                power = led_data.get('led_power', 0)
                text_parts.append(f"LED: {power}%")
            
            # Add reasoning
            if 'reasoning' in decision:
                text_parts.append(f"Reasoning: {decision['reasoning']}")
        
        # Add summary if available
        if 'summary' in memory_data:
            text_parts.append(f"Summary: {memory_data['summary']}")
        
        return " | ".join(text_parts)
    
    async def _mock_store(self, memory_id: str, memory_data: Dict[str, Any]) -> str:
        """Mock storage for testing"""
        memory_data['id'] = memory_id
        self._mock_memories.append(memory_data)
        
        # Keep only recent memories in mock mode
        if len(self._mock_memories) > 100:
            self._mock_memories = self._mock_memories[-50:]
        
        return memory_id
    
    async def _mock_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Mock search for testing"""
        # Simple keyword matching for mock
        results = []
        query_lower = query.lower()
        
        for memory in self._mock_memories:
            text_repr = self._create_text_representation(memory).lower()
            
            # Simple relevance scoring based on keyword matches
            score = 0
            for word in query_lower.split():
                if word in text_repr:
                    score += 1
            
            if score > 0:
                memory_copy = memory.copy()
                memory_copy['similarity_score'] = score / len(query_lower.split())
                results.append(memory_copy)
        
        # Sort by score and return top results
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        return results[:limit]
    
    async def get_status(self) -> Dict[str, Any]:
        """Get vector memory status"""
        try:
            if self.mock_mode:
                return {
                    "mode": "mock",
                    "memory_count": len(self._mock_memories),
                    "available": True
                }
            
            return {
                "mode": "chromadb",
                "memory_count": self.collection.count(),
                "persist_directory": str(self.persist_directory),
                "available": True
            }
            
        except Exception as e:
            return {
                "mode": "error",
                "error": str(e),
                "available": False
            }
    
    async def clear_all_memories(self):
        """Clear all stored memories (for testing/reset)"""
        try:
            if self.mock_mode:
                self._mock_memories.clear()
                return
            
            # Delete all memories in ChromaDB
            all_ids = self.collection.get()['ids']
            if all_ids:
                self.collection.delete(ids=all_ids)
            
            self.logger.info("All memories cleared")
            
        except Exception as e:
            self.logger.error(f"Failed to clear memories: {e}")
    
    def __del__(self):
        """Cleanup on destruction"""
        # ChromaDB handles cleanup automatically
        pass